from __future__ import annotations

from typing import Optional, Dict, Any

from server_utils import _wrap_tool_result, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="create_project", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def create_project(
        project_name: str,
        description: Optional[str] = None,
        working_directory: Optional[str] = None,
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.init(
            project_name=project_name,
            description=description,
            working_directory=working_directory,
        )
        payload = dict(result)
        payload.pop("instructions", None)
        if payload.get("status") == "success" and "instructions_v2" not in payload:
            payload["instructions_v2"] = [
                {
                    "to_ai": "AI注意：项目初始化成功",
                    "user_message": ["✅ 项目初始化成功"],
                    "result": "success",
                    "kind": "display",
                }
            ]
        return _wrap_tool_result(payload, success_default="项目初始化成功", failure_default="项目初始化失败")

    @mcp_server.tool(description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def get_project_status(detailed: bool = False) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.get_project_status(detailed)
        payload = dict(result)
        payload.pop("instructions", None)
        if payload.get("status") == "success":
            payload["instructions_v2"] = [
                {
                    "to_ai": "AI注意：已获取项目状态",
                    "user_message": ["ℹ️ 已获取项目状态（详细信息见日志/控制台或后端返回数据）"],
                    "result": "success",
                    "kind": "display",
                }
            ]
        else:
            payload["instructions_v2"] = [
                {
                    "to_ai": "AI注意：获取项目状态失败",
                    "user_message": [f"❌ 获取项目状态失败：{payload.get('message','未知错误')}"],
                    "result": "failure",
                    "kind": "display",
                }
            ]
        return _wrap_tool_result(payload, success_default="已获取项目状态", failure_default="获取项目状态失败")
