"""
service.tasks 包：任务相关的对外API聚合。

为保持兼容，继续导出原有的函数名：
- next, report, get_project_status
- pre_analyze
- add_task, start_task, cancel_task, finish_task, suspend_task, continue_suspended_task
"""
from __future__ import annotations

from .flow import next, report, get_project_status  # noqa: F401
from .analysis import pre_analyze  # noqa: F401
from .actions import (  # noqa: F401
    add_task,
    start_task,
    cancel_task,
    finish_task,
    suspend_task,
    continue_suspended_task,
)

__all__ = [
    "next",
    "report",
    "get_project_status",
    "pre_analyze",
    "add_task",
    "start_task",
    "cancel_task",
    "finish_task",
    "suspend_task",
    "continue_suspended_task",
]

