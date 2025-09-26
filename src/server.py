"""
FastMCP服务器实现
通过HTTP API调用Django服务
"""

import os
import json
import aiohttp
import asyncio
import functools
from fastmcp import FastMCP
from typing import Optional, Dict, Any
from file_manager import FileManager
from config import config

# 创建MCP服务器实例
mcp_server = FastMCP("Scienith Supervisor MCP")

# 全局服务实例
_mcp_service = None


def get_mcp_service():
    """获取MCP服务实例（单例模式）"""
    global _mcp_service
    if _mcp_service is None:
        from service import MCPService

        _mcp_service = MCPService()
    return _mcp_service


def reset_mcp_service():
    """重置MCP服务实例（用于测试）"""
    global _mcp_service
    _mcp_service = None


_SUCCESS_STATUSES = {"success", "ok", "info"}


def _is_success_payload(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    if "success" in payload:
        return bool(payload["success"])

    status = payload.get("status")
    if status is None:
        return False
    return str(status).lower() in _SUCCESS_STATUSES


def _format_details_text(details: Dict[str, Any]) -> str:
    if not details:
        return ""
    return json.dumps(details, ensure_ascii=False, indent=2)


def _build_instruction_text(
    payload: Dict[str, Any],
    success: bool,
    success_default: str,
    failure_default: str,
) -> str:
    parts = []

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())

    instructions = payload.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            for item in instructions:
                if isinstance(item, dict) and "to_ai" in item:
                    parts.append(str(item["to_ai"]).strip())
                elif item is not None:
                    text = str(item).strip()
                    if text:
                        parts.append(text)
        else:
            text = str(instructions).strip()
            if text:
                parts.append(text)

    excluded_keys = {"success", "status", "message", "instructions"}
    details = {
        key: value
        for key, value in payload.items()
        if key not in excluded_keys and value not in (None, "")
    }
    details_text = _format_details_text(details)
    if details_text:
        parts.append(f"详情:\n{details_text}")

    if parts:
        return "\n\n".join(part for part in parts if part)

    return success_default if success else failure_default


def _wrap_tool_payload(
    payload: Dict[str, Any],
    success_default: str = "操作成功",
    failure_default: str = "操作失败",
) -> Dict[str, Any]:
    if payload is None:
        return {"success": False, "instructions_to_ai": failure_default}

    if not isinstance(payload, dict):
        text = str(payload)
        return {"success": True, "instructions_to_ai": text or success_default}

    success = _is_success_payload(payload)
    instructions_text = _build_instruction_text(
        payload,
        success,
        success_default,
        failure_default,
    )
    return {
        "success": success,
        "instructions_to_ai": instructions_text,
    }


def handle_exceptions(func):
    """为MCP工具添加异常处理装饰器"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            # 处理异步任务取消
            return _wrap_tool_payload(
                {"status": "error", "message": "操作已取消"},
                failure_default="操作已取消",
            )
        except Exception as e:
            # 处理所有其他异常
            return _wrap_tool_payload(
                {
                    "status": "error",
                    "message": f"工具执行失败: {str(e)}",
                    "error_type": type(e).__name__,
                },
                failure_default="工具执行失败",
            )

    return wrapper


# API配置
API_BASE_URL = config.api_url
API_TOKEN = os.getenv("SUPERVISOR_API_TOKEN", "")


class APIClient:
    """API客户端"""

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._session = None

    async def _get_session(self):
        """获取或创建session"""
        if self._session is None or self._session.closed:
            # 创建连接器配置，设置超时
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers=self.headers
            )
        return self._session

    async def request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送API请求"""
        url = f"{self.base_url}/{endpoint}"
        session = await self._get_session()

        try:
            async with session.request(method, url, **kwargs) as response:
                # 检查响应类型
                content_type = response.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    data = await response.json()

                    if response.status >= 400:
                        return {
                            "status": "error",
                            "message": data.get("error", f"HTTP {response.status}"),
                        }

                    return data
                else:
                    # 对于非JSON响应（如文件下载），返回文本内容
                    text = await response.text()

                    if response.status >= 400:
                        return {
                            "status": "error",
                            "message": f"HTTP {response.status}: {text}",
                        }

                    return text

        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timeout"}
        except aiohttp.ClientError as e:
            return {"status": "error", "message": f"API request failed: {str(e)}"}
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                return {"status": "error", "message": f"Event loop is closed"}
            return {"status": "error", "message": f"Runtime error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    async def close(self):
        """关闭session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()


def get_api_client():
    """获取新的API客户端实例（每次调用都创建新实例，确保测试隔离）"""
    client = APIClient(API_BASE_URL, API_TOKEN)
    # 为了向后兼容，在客户端上添加一个自动关闭的装饰
    return AutoCloseAPIClient(client)


class AutoCloseAPIClient:
    """API客户端的自动关闭包装器，向后兼容非async-with用法"""

    def __init__(self, client):
        self._client = client
        self._used_without_context = False

    def __getattr__(self, name):
        """代理所有属性访问到实际的客户端"""
        attr = getattr(self._client, name)
        if name == "request":
            # 包装request方法，在第一次使用后标记需要清理
            async def wrapped_request(*args, **kwargs):
                self._used_without_context = True
                try:
                    result = await attr(*args, **kwargs)
                    # 请求完成后自动关闭（非async with模式）
                    if self._used_without_context:
                        await self._client.close()
                    return result
                except Exception as e:
                    # 异常时也要关闭
                    if self._used_without_context:
                        await self._client.close()
                    raise e

            return wrapped_request
        return attr

    async def __aenter__(self):
        """async with支持"""
        self._used_without_context = False  # 使用async with，不需要自动关闭
        return self  # 返回包装器本身，以便可以访问._client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """async with支持"""
        await self._client.close()


@mcp_server.tool(name="ping")
@handle_exceptions
async def ping() -> dict:
    """快速检查 MCP 服务器状态

    这是一个轻量级的健康检查，仅验证MCP服务器本身是否正常运行。
    不会进行任何外部API调用，响应时间最快。

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}
    """
    import time

    payload = {
        "status": "ok",
        "message": "MCP server is running",
        "timestamp": time.time(),
        "server_name": "Scienith Supervisor MCP",
    }
    return _wrap_tool_payload(payload, success_default="MCP服务器运行正常")


@mcp_server.tool(name="login_with_project")
@handle_exceptions
async def login_with_project(working_directory: str) -> Dict[str, Any]:
    """
    一站式登录并初始化项目工作区（从项目 .env 文件读取认证信息）

    该工具从项目目录的 .env 文件读取认证信息，然后执行登录和项目初始化。

    Args:
        working_directory: 项目工作目录（必填）

    要求：
    必须在项目目录创建 .env 文件，包含以下必需字段：
    - SUPERVISOR_USERNAME: 用户名
    - SUPERVISOR_PASSWORD: 密码
    - SUPERVISOR_PROJECT_ID: 项目ID

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}
            instructions_to_ai 会包含登录结果与下一步行动指引。

    Examples:
        # 指定项目根目录（必须使用绝对路径）并确保该目录有 .env 文件
        result = login_with_project("/abs/path/to/project")

    注意：
        - working_directory 必须是项目根目录的绝对路径，且该目录下需要存在 .env 文件。
        - 使用相对路径（例如 "./"、"../project"）可能会解析到错误目录，导致无法找到 .env。
        - 如果缺少 .env，可复制 .env.example 并补全 SUPERVISOR_* 认证信息。

    Note:
        这是唯一支持的登录方式。所有认证信息必须通过 .env 文件提供。
        .env 文件不应提交到版本控制系统中，请将其添加到 .gitignore。
    """
    import os
    import json
    from pathlib import Path
    from dotenv import dotenv_values

    # 使用用户指定的项目目录
    env_path = Path(working_directory) / '.env'

    # 检查 .env 文件是否存在
    if not env_path.exists():
        return {
            'success': False,
            'error_code': 'ENV_001',
            'message': f'未找到 .env 文件：{env_path}',
            'hint': '请传入项目根目录的绝对路径，并确认其中包含 .env（可从 .env.example 复制后填写认证信息）'
        }

    # 直接读取 .env 文件为字典（避免环境变量冲突）
    env_values = dotenv_values(env_path)

    # 从字典中获取认证信息
    username = env_values.get('SUPERVISOR_USERNAME')
    password = env_values.get('SUPERVISOR_PASSWORD')
    project_id = env_values.get('SUPERVISOR_PROJECT_ID')

    # 如果 .env 中没有 project_id，尝试从现有的 project.json 读取
    if not project_id:
        supervisor_dir = Path(working_directory) / '.supervisor'
        project_json_path = supervisor_dir / 'project.json'
        if project_json_path.exists():
            try:
                with open(project_json_path, 'r', encoding='utf-8') as f:
                    project_info = json.load(f)
                    project_id = project_info.get('project_id')
                    if project_id:
                        print(f"📋 从 project.json 读取到项目ID: {project_id}")
            except (json.JSONDecodeError, IOError):
                pass  # 忽略读取错误，继续使用 None

    # 验证必需字段
    missing_fields = []
    if not username:
        missing_fields.append('SUPERVISOR_USERNAME')
    if not password:
        missing_fields.append('SUPERVISOR_PASSWORD')
    if not project_id:
        missing_fields.append('SUPERVISOR_PROJECT_ID')

    if missing_fields:
        return {
            'success': False,
            'error_code': 'ENV_002',
            'message': f'.env 文件缺少必需字段: {", ".join(missing_fields)}',
            'hint': '请在 .env 文件中添加所有必需的认证字段',
            'required_fields': ['SUPERVISOR_USERNAME', 'SUPERVISOR_PASSWORD', 'SUPERVISOR_PROJECT_ID']
        }

    print("\n🔐 Scienith Supervisor 登录")
    print("─" * 40)
    print(f"📧 用户名: {username}")
    print(f"🆔 项目ID: {project_id}")
    print(f"📂 工作目录: {working_directory}")
    print("─" * 40)
    print("⏳ 正在登录并初始化项目...")

    service = get_mcp_service()
    result = await service.login_with_project(username, password, project_id, working_directory)

    # 美化输出结果
    if result.get('success'):
        print("\n✅ 登录成功！")
        print(f"👤 用户: {result.get('username')}")
        if 'project' in result:
            print(f"📦 项目: {result['project'].get('project_name')}")
            print(f"📑 已下载模板: {result['project'].get('templates_downloaded', 0)} 个")
        payload = {
            "success": True,
            "message": result.get('message'),
            "instructions": result.get('instructions'),
        }
        return _wrap_tool_payload(payload, success_default="登录成功")

    print(f"\n❌ 登录失败: {result.get('message', '未知错误')}")
    payload = {
        "success": False,
        "message": result.get('message'),
        "error_code": result.get('error_code'),
        "hint": result.get('hint'),
        "required_fields": result.get('required_fields'),
    }
    return _wrap_tool_payload(payload, failure_default="登录失败")


@mcp_server.tool(name="logout")
@handle_exceptions
async def logout() -> dict:
    """
    用户登出工具

    清除当前登录会话，删除服务器端的访问令牌。

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}
    """
    service = get_mcp_service()
    result = await service.logout()
    return _wrap_tool_payload(result, success_default="登出成功", failure_default="登出失败")


@mcp_server.tool(name="health")
@handle_exceptions
async def health_check() -> dict:
    """检查 MCP 服务器的健康状态

    用于验证 MCP 服务器是否正常运行和响应。
    这是一个轻量级检查，仅测试MCP服务器本身的连接状态。

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}
    """
    payload = {
        "status": "ok",
        "message": "MCP server is running and responding",
        "server_name": "Scienith Supervisor MCP",
    }
    return _wrap_tool_payload(payload, success_default="MCP服务器运行正常")


@mcp_server.tool(name="create_project")
@handle_exceptions
async def create_project(
    project_name: str,
    description: Optional[str] = None,
    working_directory: Optional[str] = None,
) -> Dict[str, Any]:
    """
    创建新项目并初始化本地工作区

    使用此工具开始一个新项目。系统会根据内置的 SOP（标准操作程序）
    自动创建项目结构和初始任务组。创建成功后会返回 project_id，
    后续所有操作都需要使用这个 ID。

    Args:
        project_name: 项目名称（必需）
        description: 项目的详细描述（可选）
        working_directory: 工作目录路径（可选，默认当前目录）

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 创建新项目
        结果 = create_project(project_name="智能聊天机器人", description="基于 AI 的客服系统")
        project_id = 结果["data"]["project_id"]  # 保存此 ID
    """
    # 使用MCP服务处理新项目创建（包含认证检查）
    service = get_mcp_service()
    result = await service.init(
        project_name=project_name,
        description=description,
        working_directory=working_directory,
    )
    return _wrap_tool_payload(result, success_default="项目初始化成功", failure_default="项目初始化失败")

@mcp_server.tool(name="next")
@handle_exceptions
async def get_next_task() -> Dict[str, Any]:
    """
    获取项目中下一个需要执行的任务

    系统会自动根据任务依赖关系和优先级返回当前应该执行的任务。
    每个任务都包含详细的上下文信息，包括任务描述、相关文档、
    依赖关系等，帮助你理解和完成任务。

    项目ID从当前会话自动获取。如果没有项目上下文，请先运行 setup_workspace 或 create_project。

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Note:
        如果返回 "no_available_tasks"，表示当前没有可执行的任务，
        可能需要先完成其他任务或检查项目状态。
    """
    # 使用MCP服务处理获取下一个任务（包含认证检查）
    service = get_mcp_service()
    result = await service.next()
    return _wrap_tool_payload(result, success_default="已获取下一个任务阶段", failure_default="获取下一个任务阶段失败")


@mcp_server.tool(name="report")
@handle_exceptions
async def report_task_phase_result(
    task_phase_id: Optional[str] = None, result_data: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """
    提交已完成任务阶段的执行结果

    当你完成一个任务阶段后，使用此工具上报结果。系统会根据结果
    更新任务阶段状态，并可能触发后续任务阶段的创建或解锁。

    Args:
        task_phase_id: 要上报的任务阶段 ID（从 next 获得）。可选：省略时将从本地项目文件读取当前阶段ID。
        result_data: 任务阶段执行结果。
            - 对 VALIDATION 阶段：必须为 {"passed": true/false}，且不允许其他字段。
            - 对其它阶段：不需要传任何内容（请传 {} 或省略）。多余字段将被拒绝并返回错误。

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Example:
        # VALIDATION 任务阶段示例
        report({"result_data": {"passed": true}})

        # 其它阶段示例
        report({"result_data": {}})
    """
    # 使用MCP服务处理任务阶段结果上报（包含认证检查）
    service = get_mcp_service()
    result = await service.report(task_phase_id, result_data)
    return _wrap_tool_payload(result, success_default="任务结果已提交", failure_default="提交任务结果失败")


@mcp_server.tool()
@handle_exceptions
async def get_project_status(detailed: bool = False) -> Dict[str, Any]:
    """
    查询项目的当前状态和进度

    获取项目的整体进度、任务完成情况、当前阶段等信息。
    可以选择获取简要信息或详细信息。

    Args:
        project_id: 项目的唯一标识符
        detailed: 是否返回详细信息（默认 False）
            - False: 只返回摘要信息
            - True: 返回所有任务组和任务的详细状态

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    使用场景:
        - 定期检查项目进度
        - 在开始工作前了解项目当前状态
        - 生成项目报告
    """
    # 使用MCP服务处理项目状态查询（包含认证检查）
    service = get_mcp_service()
    result = await service.get_project_status(detailed)
    return _wrap_tool_payload(result, success_default="已获取项目状态", failure_default="获取项目状态失败")


async def handle_tool_call(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """处理工具调用"""
    tools = {
        "create_project": create_project,
        "setup_workspace": setup_workspace,
        "get_next_task": get_next_task,
        "report_task_result": report_task_result,
        "get_project_status": get_project_status,
        "health_check": health_check,
        "pre_analyze": pre_analyze,
        "add_task": add_task,
        "update_step_rules": update_step_rules,
        "update_output_template": update_output_template,
    }

    if tool_name not in tools:
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    tool = tools[tool_name]
    try:
        return await tool(**params)
    except Exception as e:
        return {"status": "error", "message": f"Tool execution failed: {str(e)}"}


def create_server():
    """创建并返回MCP服务器实例"""
    return mcp_server


@mcp_server.tool(name="pre_analyze")
@handle_exceptions
async def pre_analyze(user_requirement: str) -> Dict[str, Any]:
    """
    分析用户需求并提供SOP步骤选择指导

    当用户提出新的工作目标时，使用此工具获取SOP步骤信息和分析指导，
    帮助确定应该从哪个SOP步骤开始执行。

    Args:
        user_requirement: 用户需求描述，如"实现用户头像上传功能"

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        pre_analyze("实现用户头像上传功能")
        pre_analyze("修复用户登录时的超时问题")
    """
    # 使用MCP服务处理需求分析（包含认证检查）
    service = get_mcp_service()
    result = await service.pre_analyze(user_requirement)
    return _wrap_tool_payload(result, success_default="已完成需求分析", failure_default="需求分析失败")


@mcp_server.tool(name="add_task")
@handle_exceptions
async def add_task(
    title: str, goal: str, sop_step_identifier: str
) -> Dict[str, Any]:
    """
    直接创建IMPLEMENTING任务组

    基于pre_analyze的分析结果，创建一个执行任务组并绑定到指定的SOP步骤。

    Args:
        title: 任务组标题，如"用户头像上传功能"
        goal: 任务组目标，详细描述要实现的功能和预期结果
        sop_step_identifier: SOP步骤标识符，如"ui_design"、"implement"等

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        add_task(
            "用户头像上传功能",
            "实现用户头像上传、裁剪和存储功能，支持多种图片格式",
            "ui_design"
        )
    """
    # 使用MCP服务处理任务组创建（包含认证检查）
    service = get_mcp_service()
    result = await service.add_task(title, goal, sop_step_identifier)
    return _wrap_tool_payload(result, success_default="任务组创建成功", failure_default="任务组创建失败")


@mcp_server.tool(name="cancel_task")
@handle_exceptions
async def cancel_task(
    task_id: Optional[str] = None, cancellation_reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    取消指定的任务组

    将任务组标记为已取消状态，该任务组中的所有任务也会被标记为已取消。
    get_next_task 将不再从已取消的任务组中选择任务。
    如果取消的是当前正在进行的任务组，系统会自动切换到下一个可用的任务组。

    Args:
        project_id: 项目ID
        task_id: 要取消的任务组ID（可选；未提供时默认取消当前进行中的任务组）
        cancellation_reason: 取消原因（可选）

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 取消任务组
        cancel_task("tg_456", "项目需求变更")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功取消: 移动端适配",
            "cancelled_task": {
                "id": "tg_456",
                "title": "移动端适配",
                "status": "CANCELLED",
                "cancelled_at": "2024-12-20T10:30:00Z",
                "cancellation_reason": "项目需求变更"
            },
            "auto_switched_to": {
                "id": "tg_789",
                "title": "数据库设计",
                "status": "IN_PROGRESS"
            }
        }
    """
    # 使用MCP服务处理任务组取消（包含认证检查）
    service = get_mcp_service()
    result = await service.cancel_task(task_id, cancellation_reason)
    return _wrap_tool_payload(result, success_default="任务组已取消", failure_default="取消任务组失败")


@mcp_server.tool(name="finish_task")
@handle_exceptions
async def finish_task() -> Dict[str, Any]:
    """
    直接将任务标记为完成状态

    该工具用于跳过剩余的任务阶段，直接将整个任务标记为完成。
    通常在以下场景使用：
    1. IMPLEMENTING阶段完成后，用户认为可以跳过验证和修复阶段
    2. VALIDATION阶段验证通过后，用户认为可以跳过复盘阶段
    3. FIXING阶段修复完成后，用户认为可以跳过重新验证

    注意：
    - 只有任务所有者可以执行此操作
    - 所有任务阶段必须处于已完成(COMPLETED)或已取消(CANCELLED)状态
    - 对已完成的任务调用是幂等的，会返回提示信息

    Args:
        无参数：默认完成当前进行中的任务组

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 完成任务
        finish_task("task-123")

        # 返回成功示例
        {
            "status": "success",
            "message": "任务已成功标记为完成",
            "data": {
                "task_id": "task-123",
                "title": "实现用户登录功能",
                "previous_status": "IN_PROGRESS",
                "new_status": "COMPLETED",
                "completed_at": "2024-01-20T10:30:00Z"
            }
        }

        # 返回幂等示例（任务已完成）
        {
            "status": "info",
            "message": "任务已经处于完成状态",
            "data": {
                "task_id": "task-123",
                "title": "实现用户登录功能",
                "status": "COMPLETED"
            }
        }
    """
    # 使用MCP服务处理任务完成（包含认证检查）
    service = get_mcp_service()
    result = await service.finish_task(None)
    return _wrap_tool_payload(result, success_default="任务已标记为完成", failure_default="任务完成操作失败")


@mcp_server.tool(name="start")
@handle_exceptions
async def start_task(task_id: str) -> Dict[str, Any]:
    """
    启动指定的任务组

    将PENDING状态的任务组启动为IN_PROGRESS状态，使其成为当前活跃的任务组。
    一个项目同时只能有一个IN_PROGRESS状态的任务组。

    Args:
        project_id: 项目ID
        task_id: 要启动的任务组ID

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 启动待处理的任务组
        start_task("proj_123", "tg_456")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功启动",
            "data": {
                "task_id": "tg_456",
                "title": "数据库设计",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T15:30:00Z"
            }
        }
    """
    # 使用MCP服务处理任务组启动（包含认证检查）
    service = get_mcp_service()
    result = await service.start_task(task_id)
    return _wrap_tool_payload(result, success_default="任务组已启动", failure_default="启动任务组失败")


@mcp_server.tool(name="suspend")
@handle_exceptions
async def suspend_task() -> Dict[str, Any]:
    """
    暂存当前任务组到本地存储

    将当前正在进行的任务组及其所有工作文件保存到本地暂存区域，
    并从当前工作区移出。这样可以暂时搁置当前工作，转而处理其他任务组。

    Args:
        project_id: 项目ID

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 暂存当前任务组
        suspend_task("proj_123")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功暂存: 用户界面设计",
            "suspended_task": {
                "id": "tg_001",
                "title": "用户界面设计",
                "files_count": 5,
                "suspended_at": "2024-12-20T15:30:00Z"
            }
        }
    """
    # 使用MCP服务处理任务组暂存（包含认证检查）
    service = get_mcp_service()
    result = await service.suspend_task()
    return _wrap_tool_payload(result, success_default="任务组已暂存", failure_default="暂存任务组失败")


@mcp_server.tool(name="continue_suspended")
@handle_exceptions
async def continue_suspended_task(task_id: str) -> Dict[str, Any]:
    """
    恢复指定的暂存任务组到当前工作区

    将之前暂存的任务组恢复到当前工作区，使其成为活跃的工作任务组。
    如果当前有其他任务组正在进行，会先将其暂存再恢复指定任务组。

    Args:
        project_id: 项目ID
        task_id: 要恢复的暂存任务组ID

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Examples:
        # 恢复暂存的任务组
        continue_suspended_task("tg_456")

        # 返回示例
        {
            "status": "success",
            "message": "已成功恢复暂存任务组: 数据库设计",
            "restored_task": {
                "id": "tg_456",
                "title": "数据库设计",
                "files_count": 3,
                "restored_at": "2024-12-20T15:45:00Z"
            },
            "previous_task": {
                "id": "tg_001",
                "title": "用户界面设计",
                "suspended": true
            }
        }
    """
    # 使用MCP服务处理暂存任务组恢复（包含认证检查）
    service = get_mcp_service()
    result = await service.continue_suspended_task(task_id)
    return _wrap_tool_payload(result, success_default="已恢复暂存任务组", failure_default="恢复暂存任务组失败")


@mcp_server.tool(name="update_step_rules")
@handle_exceptions
async def update_step_rules(stage: str, step_identifier: str) -> Dict[str, Any]:
    """
    更新SOP步骤的规则

    读取本地SOP配置文件中的rules，并将其更新到远程服务器。
    直接根据stage和step_identifier定位到对应的config.json文件，
    读取其中的rules数组和step_id，然后发送给服务器进行更新。

    Args:
        stage: SOP阶段名称（如"analysis", "planning", "implementing"）
        step_identifier: 步骤标识符（如"contractConfirmation", "requirementAnalysis"）

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Example:
        # 更新契约确认步骤的规则
        update_step_rules("analysis", "contractConfirmation")
    """
    service = get_mcp_service()
    result = await service.update_step_rules(stage, step_identifier)
    return _wrap_tool_payload(result, success_default="步骤规则已更新", failure_default="步骤规则更新失败")


@mcp_server.tool(name="update_output_template")
@handle_exceptions
async def update_output_template(
    stage: str, step_identifier: str, output_name: str
) -> Dict[str, Any]:
    """
    更新Output的模板内容

    读取本地SOP配置和模板文件，并将模板内容更新到远程服务器。
    直接根据stage、step_identifier和output_name定位到对应的配置和模板文件，
    读取模板内容和output_id后发送给服务器进行更新。

    Args:
        stage: SOP阶段名称（如"analysis", "planning", "implementing"）
        step_identifier: 步骤标识符（如"contractConfirmation", "requirementAnalysis"）
        output_name: 输出名称（如"API接口跟踪清单", "需求文档"）

    Returns:
        dict: {"success": bool, "instructions_to_ai": str}

    Example:
        # 更新契约确认步骤中API接口跟踪清单的模板
        update_output_template("analysis", "contractConfirmation", "API接口跟踪清单")
    """
    service = get_mcp_service()
    result = await service.update_output_template(stage, step_identifier, output_name)
    return _wrap_tool_payload(result, success_default="模板已更新", failure_default="模板更新失败")


# 注意：API连接检查会在服务器启动后进行
# 这样即使API不可用，MCP服务器也能正常启动

if __name__ == "__main__":
    import sys

    # 打印启动信息
    print(f"Starting MCP server...", file=sys.stderr)
    print(f"API URL: {API_BASE_URL}", file=sys.stderr)
    # 显示项目路径配置
    project_path = os.environ.get("SUPERVISOR_PROJECT_PATH", os.getcwd())
    print(f"Project Path: {project_path}", file=sys.stderr)
    print(
        f".supervisor directory will be created at: {project_path}/.supervisor",
        file=sys.stderr,
    )

    if "--http" in sys.argv:
        # HTTP模式 - 用于远程访问
        mcp_server.run(transport="http", host="0.0.0.0", port=8080, path="/mcp")
    else:
        # 默认STDIO模式 - 用于本地Claude Code
        mcp_server.run()
