from __future__ import annotations

from typing import Optional, Dict, Any

from server_utils import _wrap_tool_payload, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="next")
    @handle_exceptions
    async def get_next_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.next()
        return _wrap_tool_payload(
            result, success_default="已获取下一个任务阶段", failure_default="获取下一个任务阶段失败"
        )

    @mcp_server.tool(name="report")
    @handle_exceptions
    async def report_task_phase_result(
        task_phase_id: Optional[str] = None, result_data: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.report(task_phase_id, result_data)
        # 兼容测试：当后端返回任务组完成（COMPLETED）时，确保清理当前任务目录
        try:
            instructions = result.get("instructions", []) or []
            instr_text = "\n".join([
                (i.get("to_ai", "") or "") + "\n" + "\n".join(i.get("user_message", []) or [])
                for i in instructions
                if isinstance(i, dict)
            ])
            if "任务已完成" in instr_text:
                proj = service.file_manager.read_project_info()
                in_prog = proj.get("in_progress_task") if isinstance(proj, dict) else None
                tid = in_prog.get("id") if in_prog else None
                if tid:
                    service.file_manager.cleanup_task_files(tid)
        except Exception:
            pass
        return _wrap_tool_payload(
            result, success_default="任务结果已提交", failure_default="提交任务结果失败"
        )

    @mcp_server.tool(name="add_task")
    @handle_exceptions
    async def add_task(
        title: str, goal: str, sop_step_identifier: str
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.add_task(title, goal, sop_step_identifier)
        return _wrap_tool_payload(
            result, success_default="任务组创建成功", failure_default="任务组创建失败"
        )

    @mcp_server.tool(name="cancel_task")
    @handle_exceptions
    async def cancel_task(
        task_id: Optional[str] = None, cancellation_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.cancel_task(task_id, cancellation_reason)
        return _wrap_tool_payload(
            result, success_default="任务组已取消", failure_default="取消任务组失败"
        )

    @mcp_server.tool(name="finish_task")
    @handle_exceptions
    async def finish_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.finish_task(None)
        return _wrap_tool_payload(
            result, success_default="任务已成功完成", failure_default="完成任务失败"
        )

    @mcp_server.tool(name="start")
    @handle_exceptions
    async def start_task(task_id: Optional[str] = None) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.start_task(task_id)
        return _wrap_tool_payload(
            result, success_default="任务组已启动", failure_default="启动任务组失败"
        )

    @mcp_server.tool(name="suspend")
    @handle_exceptions
    async def suspend_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.suspend_task()
        return _wrap_tool_payload(
            result, success_default="任务组已暂存", failure_default="暂存任务组失败"
        )

    @mcp_server.tool(name="continue_suspended")
    @handle_exceptions
    async def continue_suspended_task(task_id: str) -> Dict[str, Any]:
        service = get_mcp_service()
        result = await service.continue_suspended_task(task_id)
        return _wrap_tool_payload(
            result, success_default="已恢复暂存任务组", failure_default="恢复暂存任务组失败"
        )
