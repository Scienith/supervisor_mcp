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


def handle_exceptions(func):
    """为MCP工具添加异常处理装饰器"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            # 处理异步任务取消
            return {"status": "error", "message": "Operation was cancelled"}
        except Exception as e:
            # 处理所有其他异常
            return {
                "status": "error",
                "message": f"Tool execution failed: {str(e)}",
                "error_type": type(e).__name__,
            }

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
        dict: 服务器状态信息
            - status: "ok" 表示MCP服务器正常
            - message: 状态描述
            - timestamp: 响应时间戳
    """
    import time

    return {
        "status": "ok",
        "message": "MCP server is running",
        "timestamp": time.time(),
        "server_name": "Scienith Supervisor MCP",
    }


@mcp_server.tool(name="login")
@handle_exceptions
async def login(username: str, password: str, working_directory: str) -> dict:
    """
    用户登录工具

    在使用其他MCP工具之前，需要先使用此工具进行登录认证。
    登录成功后会获得访问令牌，在本地保存，下次session启动会从本地自动恢复。
    在本地令牌存在的情况下，可以免登录；但是如果过期，就应该重新发起login。
    
    重要：调用此工具前，请先使用 Bash 工具执行 pwd 命令获取当前工作目录，
    然后将获取的路径作为 working_directory 参数传入。

    Args:
        username: 用户名
        password: 密码
        working_directory: 当前工作目录路径（必需，使用 pwd 命令获取）

    Returns:
        dict: 登录结果
            - success: bool, 登录是否成功
            - user_id: str, 用户ID（成功时）
            - username: str, 用户名（成功时）
            - error_code: str, 错误代码（失败时）
            - message: str, 错误消息（失败时）
    """
    service = get_mcp_service()
    return await service.login(username, password, working_directory)


@mcp_server.tool(name="logout")
@handle_exceptions
async def logout() -> dict:
    """
    用户登出工具

    清除当前登录会话，删除服务器端的访问令牌。

    Returns:
        dict: 登出结果
            - success: bool, 登出是否成功
            - message: str, 结果消息
    """
    service = get_mcp_service()
    return await service.logout()


@mcp_server.tool(name="health")
@handle_exceptions
async def health_check() -> dict:
    """检查 MCP 服务器的健康状态

    用于验证 MCP 服务器是否正常运行和响应。
    这是一个轻量级检查，仅测试MCP服务器本身的连接状态。

    Returns:
        dict: 包含状态信息的字典
            - status: "ok" 表示MCP服务器正常
            - message: 状态描述信息
            - server_name: 服务器名称
    """
    return {
        "status": "ok",
        "message": "MCP server is running and responding",
        "server_name": "Scienith Supervisor MCP",
    }


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
        dict: 包含项目信息的字典
            - status: "success" 或 "error"
            - data.project_id: 新创建项目的唯一标识符
            - data.project_name: 项目名称
            - message: 操作结果描述

    Examples:
        # 创建新项目
        结果 = create_project(project_name="智能聊天机器人", description="基于 AI 的客服系统")
        project_id = 结果["data"]["project_id"]  # 保存此 ID
    """
    # 使用MCP服务处理新项目创建（包含认证检查）
    service = get_mcp_service()
    return await service.init(
        project_name=project_name,
        description=description,
        working_directory=working_directory,
    )


@mcp_server.tool(name="setup_workspace")
@handle_exceptions
async def setup_workspace(
    project_id: str,
    working_directory: Optional[str] = None,
) -> Dict[str, Any]:
    """
    设置已有项目的本地工作区

    当你已经有一个项目ID时，使用此工具设置本地工作区。
    系统会下载项目信息、SOP模板，并为PENDING/IN_PROGRESS任务组创建本地文件夹。

    Args:
        project_id: 已存在项目的ID（必需）
        working_directory: 工作目录路径（可选，默认当前目录）

    Returns:
        dict: 包含项目信息的字典
            - status: "success" 或 "error"
            - data.project_id: 项目的唯一标识符
            - data.project_name: 项目名称
            - message: 操作结果描述

    Examples:
        # 设置已有项目本地工作区
        结果 = setup_workspace(project_id="existing-project-id-123")
    """
    # 使用MCP服务处理已知项目本地初始化（包含认证检查）
    service = get_mcp_service()
    return await service.init(
        project_id=project_id, working_directory=working_directory
    )


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
        dict: 包含任务信息的字典
            - status: "success"、"no_available_tasks" 或 "error"
            - task: 当前任务的详细信息（如果有可用任务）
                - id: 任务 ID
                - title: 任务标题
                - type: 任务类型（UNDERSTANDING/PLANNING/IMPLEMENTING/FIXING/VALIDATION）
                - status: 任务状态
            - context: 任务上下文，包含完成任务所需的所有信息

    Note:
        如果返回 "no_available_tasks"，表示当前没有可执行的任务，
        可能需要先完成其他任务或检查项目状态。
    """
    # 使用MCP服务处理获取下一个任务（包含认证检查）
    service = get_mcp_service()
    return await service.next()


@mcp_server.tool(name="report")
@handle_exceptions
async def report_task_result(
    task_id: str, result_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    提交已完成任务的执行结果

    当你完成一个任务后，使用此工具上报结果。系统会根据结果
    更新任务状态，并可能触发后续任务的创建或解锁。

    Args:
        task_id: 要上报的任务 ID（从 get_next_task 获得）
        result_data: 任务执行结果的详细数据，应包含：
            - success: bool，任务是否成功完成
            - output: 任务产出（如生成的文档路径、代码文件等）
            - validation_result: 仅VALIDATION任务需要，必须是字典格式，如 {"passed": true} 或 {"passed": false}

    Returns:
        dict: 处理结果
            - status: "success" 或 "error"
            - 更新后的任务信息

    Example:
        # 普通任务示例
        result_data = {
            "success": True,
            "output": "/docs/requirements.md"
        }

        # VALIDATION任务示例
        validation_result_data = {
            "success": True,
            "output": "/docs/validation_results.md",
            "validation_result": {"passed": True}  # 必须是字典格式
        }

        report_task_result(task_id, result_data)
    """
    # 使用MCP服务处理任务结果上报（包含认证检查）
    service = get_mcp_service()
    return await service.report(task_id, result_data)


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
        dict: 项目状态信息
            - status: 项目当前状态
            - created_at: 项目创建时间
            - task_groups_summary: 任务组统计
                - total: 总数
                - pending: 待处理数
                - in_progress: 进行中数
                - completed: 已完成数
            - overall_progress: 整体进度百分比
            - current_tasks: 当前正在进行的任务列表（如果 detailed=True）
            - task_groups: 所有任务组的详细信息（如果 detailed=True）

    使用场景:
        - 定期检查项目进度
        - 在开始工作前了解项目当前状态
        - 生成项目报告
    """
    # 使用MCP服务处理项目状态查询（包含认证检查）
    service = get_mcp_service()
    return await service.get_project_status(detailed)


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
        "add_task_group": add_task_group,
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
        dict: 包含分析指导和SOP步骤信息
            - status: "success" 或 "error"
            - analysis_content: 分析指导内容
            - user_requirement: 原始用户需求
            - available_sop_steps: 按拓扑排序的SOP步骤信息
            - next_action: 后续操作建议

    Examples:
        pre_analyze("实现用户头像上传功能")
        pre_analyze("修复用户登录时的超时问题")
    """
    # 使用MCP服务处理需求分析（包含认证检查）
    service = get_mcp_service()
    return await service.pre_analyze(user_requirement)


@mcp_server.tool(name="add_task_group")
@handle_exceptions
async def add_task_group(
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
        dict: 任务组创建结果
            - status: "success" 或 "error"
            - data: 创建的任务组信息
                - task_group_id: 任务组ID
                - title: 任务组标题
                - type: 任务组类型（IMPLEMENTING）
                - sop_step_identifier: 绑定的SOP步骤

    Examples:
        add_task_group(
            "用户头像上传功能",
            "实现用户头像上传、裁剪和存储功能，支持多种图片格式",
            "ui_design"
        )
    """
    # 使用MCP服务处理任务组创建（包含认证检查）
    service = get_mcp_service()
    return await service.add_task_group(title, goal, sop_step_identifier)


@mcp_server.tool(name="cancel_task_group")
@handle_exceptions
async def cancel_task_group(
    task_group_id: str, cancellation_reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    取消指定的任务组

    将任务组标记为已取消状态，该任务组中的所有任务也会被标记为已取消。
    get_next_task 将不再从已取消的任务组中选择任务。
    如果取消的是当前正在进行的任务组，系统会自动切换到下一个可用的任务组。

    Args:
        project_id: 项目ID
        task_group_id: 要取消的任务组ID
        cancellation_reason: 取消原因（可选）

    Returns:
        dict: 取消操作的结果信息
            - status: "success" 或 "error"
            - message: 操作结果消息
            - cancelled_task_group: 被取消的任务组信息
            - auto_switched_to: 如果自动切换，显示切换到的任务组信息

    Examples:
        # 取消任务组
        cancel_task_group("tg_456", "项目需求变更")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功取消: 移动端适配",
            "cancelled_task_group": {
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
    return await service.cancel_task_group(task_group_id, cancellation_reason)


@mcp_server.tool(name="start")
@handle_exceptions
async def start_task_group(task_group_id: str) -> Dict[str, Any]:
    """
    启动指定的任务组

    将PENDING状态的任务组启动为IN_PROGRESS状态，使其成为当前活跃的任务组。
    一个项目同时只能有一个IN_PROGRESS状态的任务组。

    Args:
        project_id: 项目ID
        task_group_id: 要启动的任务组ID

    Returns:
        dict: 启动操作结果
            - status: "success" 或 "error"
            - message: 操作结果消息
            - data: 启动的任务组信息
                - task_group_id: 任务组ID
                - title: 任务组标题
                - previous_status: 之前的状态（PENDING）
                - new_status: 新状态（IN_PROGRESS）
                - started_at: 启动时间戳

    Examples:
        # 启动待处理的任务组
        start_task_group("proj_123", "tg_456")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功启动",
            "data": {
                "task_group_id": "tg_456",
                "title": "数据库设计",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T15:30:00Z"
            }
        }
    """
    # 使用MCP服务处理任务组启动（包含认证检查）
    service = get_mcp_service()
    return await service.start_task_group(task_group_id)


@mcp_server.tool(name="suspend")
@handle_exceptions
async def suspend_task_group() -> Dict[str, Any]:
    """
    暂存当前任务组到本地存储

    将当前正在进行的任务组及其所有工作文件保存到本地暂存区域，
    并从当前工作区移出。这样可以暂时搁置当前工作，转而处理其他任务组。

    Args:
        project_id: 项目ID

    Returns:
        dict: 暂存操作结果
            - status: "success" 或 "error"
            - message: 操作结果消息
            - suspended_task_group: 被暂存的任务组信息
                - id: 任务组ID
                - files_count: 暂存的文件数量
                - suspended_at: 暂存时间戳

    Examples:
        # 暂存当前任务组
        suspend_task_group("proj_123")

        # 返回示例
        {
            "status": "success",
            "message": "任务组已成功暂存: 用户界面设计",
            "suspended_task_group": {
                "id": "tg_001",
                "title": "用户界面设计",
                "files_count": 5,
                "suspended_at": "2024-12-20T15:30:00Z"
            }
        }
    """
    # 使用MCP服务处理任务组暂存（包含认证检查）
    service = get_mcp_service()
    return await service.suspend_task_group()


@mcp_server.tool(name="continue_suspended")
@handle_exceptions
async def continue_suspended_task_group(task_group_id: str) -> Dict[str, Any]:
    """
    恢复指定的暂存任务组到当前工作区

    将之前暂存的任务组恢复到当前工作区，使其成为活跃的工作任务组。
    如果当前有其他任务组正在进行，会先将其暂存再恢复指定任务组。

    Args:
        project_id: 项目ID
        task_group_id: 要恢复的暂存任务组ID

    Returns:
        dict: 恢复操作结果
            - status: "success" 或 "error"
            - message: 操作结果消息
            - restored_task_group: 恢复的任务组信息
                - id: 任务组ID
                - title: 任务组标题
                - files_count: 恢复的文件数量
                - restored_at: 恢复时间戳
            - previous_task_group: 之前被暂存的任务组信息（如果有）

    Examples:
        # 恢复暂存的任务组
        continue_suspended_task_group("tg_456")

        # 返回示例
        {
            "status": "success",
            "message": "已成功恢复暂存任务组: 数据库设计",
            "restored_task_group": {
                "id": "tg_456",
                "title": "数据库设计",
                "files_count": 3,
                "restored_at": "2024-12-20T15:45:00Z"
            },
            "previous_task_group": {
                "id": "tg_001",
                "title": "用户界面设计",
                "suspended": true
            }
        }
    """
    # 使用MCP服务处理暂存任务组恢复（包含认证检查）
    service = get_mcp_service()
    return await service.continue_suspended_task_group(task_group_id)


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
        dict: 更新结果
            - status: "success" 或 "error"
            - message: 操作结果描述

    Example:
        # 更新契约确认步骤的规则
        update_step_rules("analysis", "contractConfirmation")
    """
    service = get_mcp_service()
    return await service.update_step_rules(stage, step_identifier)


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
        dict: 更新结果
            - status: "success" 或 "error"
            - message: 操作结果描述

    Example:
        # 更新契约确认步骤中API接口跟踪清单的模板
        update_output_template("analysis", "contractConfirmation", "API接口跟踪清单")
    """
    service = get_mcp_service()
    return await service.update_output_template(stage, step_identifier, output_name)


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
