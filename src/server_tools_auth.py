from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import dotenv_values

from server_utils import _wrap_tool_payload, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="ping")
    @handle_exceptions
    async def ping() -> dict:
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
        env_path = Path(working_directory) / ".env"
        if not env_path.exists():
            return {
                "success": False,
                "error_code": "ENV_001",
                "message": f"未找到 .env 文件：{env_path}",
                "hint": "请传入项目根目录的绝对路径，并确认其中包含 .env（可从 .env.example 复制后填写认证信息）",
            }

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
                except (json.JSONDecodeError, IOError):
                    pass

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
                "instructions": result.get("instructions"),
            }
            return _wrap_tool_payload(payload, success_default="登录成功")

        print(f"\n❌ 登录失败: {result.get('message', '未知错误')}")
        payload = {
            "success": False,
            "message": result.get("message"),
            "error_code": result.get("error_code"),
            "hint": result.get("hint"),
            "required_fields": result.get("required_fields"),
        }
        return _wrap_tool_payload(payload, failure_default="登录失败")

    @mcp_server.tool(name="logout")
    @handle_exceptions
    async def logout() -> dict:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.logout()
        return _wrap_tool_payload(
            result, success_default="登出成功", failure_default="登出失败"
        )

    @mcp_server.tool(name="health")
    @handle_exceptions
    async def health_check() -> dict:
        payload = {
            "status": "ok",
            "message": "MCP server is running and responding",
            "server_name": "Scienith Supervisor MCP",
        }
        return _wrap_tool_payload(payload, success_default="MCP服务器运行正常")
