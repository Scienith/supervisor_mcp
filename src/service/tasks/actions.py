"""
任务动作聚合器：将具体实现委托到子模块，便于维护与测试。

- add_task/cancel_task/finish_task -> actions_management
- start_task/suspend_task/continue_suspended_task -> actions_lifecycle
"""
from __future__ import annotations

from typing import Any, Dict, Optional


async def add_task(service_obj, title: str, goal: str, sop_step_identifier: str) -> Dict[str, Any]:
    from .actions_management import add_task as _impl
    return await _impl(service_obj, title, goal, sop_step_identifier)


async def cancel_task(service_obj, task_id: Optional[str], cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
    from .actions_management import cancel_task as _impl
    return await _impl(service_obj, task_id, cancellation_reason)


async def finish_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
    from .actions_management import finish_task as _impl
    return await _impl(service_obj, task_id)


async def start_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
    from .actions_lifecycle import start_task as _impl
    return await _impl(service_obj, task_id)


async def suspend_task(service_obj) -> Dict[str, Any]:
    from .actions_lifecycle import suspend_task as _impl
    return await _impl(service_obj)


async def continue_suspended_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
    from .actions_lifecycle import continue_suspended_task as _impl
    return await _impl(service_obj, task_id)
