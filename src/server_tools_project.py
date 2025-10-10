from __future__ import annotations

from typing import Optional, Dict, Any

from server_utils import _wrap_tool_payload, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="create_project")
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
        return _wrap_tool_payload(
            result, success_default="项目初始化成功", failure_default="项目初始化失败"
        )

    @mcp_server.tool()
    @handle_exceptions
    async def get_project_status(detailed: bool = False) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.get_project_status(detailed)
        return _wrap_tool_payload(
            result, success_default="已获取项目状态", failure_default="获取项目状态失败"
        )
