from __future__ import annotations

from typing import Dict, Any

from server_utils import _wrap_tool_payload, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="pre_analyze")
    @handle_exceptions
    async def pre_analyze(user_requirement: str) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.pre_analyze(user_requirement)
        return _wrap_tool_payload(
            result, success_default="已完成需求分析", failure_default="需求分析失败"
        )

    @mcp_server.tool(name="update_step_rules")
    @handle_exceptions
    async def update_step_rules(stage: str, step_identifier: str) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.update_step_rules(stage, step_identifier)
        return _wrap_tool_payload(
            result, success_default="步骤规则已更新", failure_default="步骤规则更新失败"
        )

    @mcp_server.tool(name="update_output_template")
    @handle_exceptions
    async def update_output_template(
        stage: str, step_identifier: str, output_name: str
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.update_output_template(stage, step_identifier, output_name)
        return _wrap_tool_payload(
            result, success_default="模板已更新", failure_default="模板更新失败"
        )
