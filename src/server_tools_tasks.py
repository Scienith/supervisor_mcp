from __future__ import annotations

from typing import Optional, Dict, Any

from server_utils import _wrap_tool_result, handle_exceptions


def register(mcp_server):
    @mcp_server.tool(name="next", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def get_next_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.next()
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="已获取下一个任务阶段", failure_default="获取下一个任务阶段失败"
        )

    @mcp_server.tool(name="report", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def report_task_phase_result(
        task_phase_id: Optional[str] = None, result_data: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.report(task_phase_id, result_data)
        # 清理逻辑已在 service 层完成，这里不再重复或吞错
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务结果已提交", failure_default="提交任务结果失败"
        )

    @mcp_server.tool(name="add_task", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def add_task(
        title: str, goal: str, sop_step_identifier: str
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.add_task(title, goal, sop_step_identifier)
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务组创建成功", failure_default="任务组创建失败"
        )

    @mcp_server.tool(name="cancel_task", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def cancel_task(
        task_id: Optional[str] = None, cancellation_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.cancel_task(task_id, cancellation_reason)
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务组已取消", failure_default="取消任务组失败"
        )

    @mcp_server.tool(name="finish_task", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def finish_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.finish_task(None)
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务已成功完成", failure_default="完成任务失败"
        )

    @mcp_server.tool(name="start", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def start_task(task_id: Optional[str] = None) -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.start_task(task_id)
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务组已启动", failure_default="启动任务组失败"
        )

    @mcp_server.tool(name="suspend", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def suspend_task() -> Dict[str, Any]:
        from server import get_mcp_service as _get
        service = _get()
        result = await service.suspend_task()
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="任务组已暂存", failure_default="暂存任务组失败"
        )

    @mcp_server.tool(name="continue_suspended", description="工具执行后会返回要执行的命令列表，需要依次执行")
    @handle_exceptions
    async def continue_suspended_task(task_id: str) -> Dict[str, Any]:
        service = get_mcp_service()
        result = await service.continue_suspended_task(task_id)
        payload = dict(result)
        payload.pop("instructions", None)
        return _wrap_tool_result(
            payload, success_default="已恢复暂存任务组", failure_default="恢复暂存任务组失败"
        )
