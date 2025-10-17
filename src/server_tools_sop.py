from __future__ import annotations

from typing import Dict, Any

from server_utils import _wrap_tool_result, handle_exceptions


def register(mcp_server):

    @mcp_server.tool(name="update_step_rules", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def update_step_rules(stage: str, step_identifier: str) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.update_step_rules(stage, step_identifier)
        payload = dict(result)
        payload.pop("instructions", None)
        payload["instructions_v2"] = [
            {"to_ai": "AI注意：步骤规则已更新", "user_message": ["✅ 步骤规则已更新"], "result": "success", "kind": "display"}
        ]
        return _wrap_tool_result(payload, success_default="步骤规则已更新", failure_default="步骤规则更新失败")

    @mcp_server.tool(name="update_output_template", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def update_output_template(
        stage: str, step_identifier: str, output_name: str
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.update_output_template(stage, step_identifier, output_name)
        payload = dict(result)
        payload.pop("instructions", None)
        payload["instructions_v2"] = [
            {"to_ai": "AI注意：模板已更新", "user_message": ["✅ 模板已更新"], "result": "success", "kind": "display"}
        ]
        return _wrap_tool_result(payload, success_default="模板已更新", failure_default="模板更新失败")
