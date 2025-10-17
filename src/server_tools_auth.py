from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import dotenv_values

from server_utils import _wrap_tool_result, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="ping", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def ping() -> dict:
        import time

        payload = {
            "status": "ok",
            "message": "MCP server is running",
            "timestamp": time.time(),
            "server_name": "Scienith Supervisor MCP",
        }
        # 显式提供 actions
        payload["instructions_v2"] = [
            {
                "to_ai": "AI注意：MCP服务器运行正常",
                "user_message": ["✅ MCP服务器运行正常"],
                "result": "success",
                "kind": "display",
            }
        ]
        return _wrap_tool_result(payload, success_default="MCP服务器运行正常")

    @mcp_server.tool(name="login_with_project", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def login_with_project(working_directory: str) -> Dict[str, Any]:
        env_path = Path(working_directory) / ".env"
        if not env_path.exists():
            # 在项目目录下创建一个 .env 模板文件，提示用户填写必要字段
            try:
                template_lines = [
                    "# Scienith Supervisor MCP Client Configuration",
                    "SUPERVISOR_API_URL=http://localhost:8000/api/v1",
                    "SUPERVISOR_USERNAME=",
                    "SUPERVISOR_PASSWORD=",
                    "SUPERVISOR_PROJECT_ID=",
                    "",
                ]
                env_path.parent.mkdir(parents=True, exist_ok=True)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(template_lines))
                created = True
            except Exception as ce:
                created = False

            # 返回失败并附带明确指引（包含 display 指令）
            message = f"未找到 .env 文件，已在项目中创建模板：{env_path}，请填写账号、密码和 API URL 后重试" if created else \
                      f"未找到 .env 文件，且创建模板失败：{env_path}"
            payload = {
                "success": False,
                "error_code": "ENV_001",
                "message": message,
                "hint": "请在 .env 中填写 SUPERVISOR_API_URL、SUPERVISOR_USERNAME、SUPERVISOR_PASSWORD、SUPERVISOR_PROJECT_ID",
                "created_env": created,
                "env_path": str(env_path),
                "instructions_v2": [
                    {
                        "to_ai": "AI注意：缺少 .env，已引导用户创建并填写配置",
                        "user_message": [
                            "❌ 未找到 .env 配置文件",
                            f"👉 已为您在项目中创建模板：{env_path}" if created else f"⚠️ 无法自动创建：{env_path}",
                            "👉 请在 .env 中填写以下项并重试：",
                            "   - SUPERVISOR_API_URL (后端API地址)",
                            "   - SUPERVISOR_USERNAME (登录用户名)",
                            "   - SUPERVISOR_PASSWORD (登录密码)",
                            "   - SUPERVISOR_PROJECT_ID (项目ID)",
                        ],
                        "result": "failure",
                        "kind": "display",
                    }
                ],
            }
            return _wrap_tool_result(payload, failure_default="缺少 .env 配置文件")

        env_values = dotenv_values(env_path)
        username = env_values.get("SUPERVISOR_USERNAME")
        password = env_values.get("SUPERVISOR_PASSWORD")
        project_id = env_values.get("SUPERVISOR_PROJECT_ID")

        if not project_id:
            supervisor_dir = Path(working_directory) / ".supervisor"
            project_json_path = supervisor_dir / "project.json"
            if project_json_path.exists():
                try:
                    with open(project_json_path, "r", encoding="utf-8") as f:
                        project_info = json.load(f)
                        project_id = project_info.get("project_id")
                        if project_id:
                            print(f"📋 从 project.json 读取到项目ID: {project_id}")
                except (json.JSONDecodeError, IOError) as e:
                    raise ValueError(f"无法读取 {project_json_path}: {e}")

        missing_fields = []
        if not username:
            missing_fields.append("SUPERVISOR_USERNAME")
        if not password:
            missing_fields.append("SUPERVISOR_PASSWORD")
        if not project_id:
            missing_fields.append("SUPERVISOR_PROJECT_ID")

        if missing_fields:
            return {
                "success": False,
                "error_code": "ENV_002",
                "message": f".env 文件缺少必需字段: {', '.join(missing_fields)}",
                "hint": "请在 .env 文件中添加所有必需的认证字段",
                "required_fields": [
                    "SUPERVISOR_USERNAME",
                    "SUPERVISOR_PASSWORD",
                    "SUPERVISOR_PROJECT_ID",
                ],
            }

        print("\n🔐 Scienith Supervisor 登录")
        print("─" * 40)
        print(f"📧 用户名: {username}")
        print(f"🆔 项目ID: {project_id}")
        print(f"📂 工作目录: {working_directory}")
        print("─" * 40)
        print("⏳ 正在登录并初始化项目...")

        from server import get_mcp_service as _get
        service = _get()
        result = await service.login_with_project(
            username, password, project_id, working_directory
        )

        if result.get("success"):
            print("\n✅ 登录成功！")
            print(f"👤 用户: {result.get('username')}")
            if "project" in result:
                print(f"📦 项目: {result['project'].get('project_name')}")
                print(
                    f"📑 已下载模板: {result['project'].get('templates_downloaded', 0)} 个"
                )
            payload = {
                "success": True,
                "message": result.get("message"),
            }
            # 移除字符串版 instructions，统一用 instructions_v2/actions
            payload.pop("instructions", None)
            # 结构化指令：优先根据当前项目状态生成引导；失败则退回最小展示
            try:
                from server import get_mcp_service as _get
                svc = _get()
                instrs = await svc._get_pending_tasks_instructions()
                if instrs:
                    payload["instructions_v2"] = instrs
                else:
                    payload["instructions_v2"] = [
                        {
                            "to_ai": "AI注意：登录成功",
                            "user_message": ["✅ 登录成功"],
                            "result": "success",
                            "kind": "display",
                        }
                    ]
            except Exception as ie:
                msg = str(ie)
                if "无法获取当前任务阶段说明文件" in msg:
                    # 尝试获取当前进行中的阶段类型，便于给出更清晰的提示
                    try:
                        phase_type = svc._get_current_task_phase_type()
                        phase_label = svc._format_phase_label(phase_type)
                    except Exception:
                        phase_label = None
                    # 组装用户提示
                    if phase_label:
                        first_line = f"ℹ️ 当前项目步骤 {phase_label} 存在进行中任务，但本地未找到阶段说明文件"
                    else:
                        first_line = "ℹ️ 当前项目存在进行中任务，但本地未找到阶段说明文件"
                    payload["instructions_v2"] = [
                        {
                            "to_ai": "AI注意：项目存在进行中任务但本地未找到阶段说明文件",
                            "user_message": [
                                first_line,
                                "👉 请立即执行 `next` 拉取阶段说明",
                            ],
                            "result": "warning",
                            "kind": "display",
                        }
                    ]
                else:
                    payload["instructions_v2"] = [
                        {
                            "to_ai": "AI注意：登录成功",
                            "user_message": ["✅ 登录成功"],
                            "result": "success",
                            "kind": "display",
                        }
                    ]
            return _wrap_tool_result(payload, success_default="登录成功")

        print(f"\n❌ 登录失败: {result.get('message', '未知错误')}")
        payload = {
            "success": False,
            "message": result.get("message"),
            "error_code": result.get("error_code"),
            "hint": result.get("hint"),
            "required_fields": result.get("required_fields"),
        }
        payload["instructions_v2"] = [
            {
                "to_ai": "AI注意：登录失败",
                "user_message": [f"❌ 登录失败：{result.get('message', '未知错误')}"] ,
                "result": "failure",
                "kind": "display",
            }
        ]
        return _wrap_tool_result(payload, failure_default="登录失败")

    @mcp_server.tool(name="logout", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def logout() -> dict:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.logout()
        payload = dict(result)
        payload.pop("instructions", None)
        if "instructions_v2" not in payload:
            payload["instructions_v2"] = [
                {"to_ai": "AI注意：登出成功", "user_message": ["✅ 登出成功"], "result": "success", "kind": "display"}
            ]
        return _wrap_tool_result(
            payload, success_default="登出成功", failure_default="登出失败"
        )

    @mcp_server.tool(name="health", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def health_check() -> dict:
        payload = {
            "status": "ok",
            "message": "MCP server is running and responding",
            "server_name": "Scienith Supervisor MCP",
        }
        payload["instructions_v2"] = [
            {"to_ai": "AI注意：健康检查正常", "user_message": ["✅ 健康检查正常"], "result": "success", "kind": "display"}
        ]
        return _wrap_tool_result(payload, success_default="MCP服务器运行正常")
