"""
持久化与本地文件写入的辅助函数。

- save_phase_strict: 严格保存任务阶段文件和描述
"""
from __future__ import annotations

from typing import Any, Dict


async def save_phase_strict(service_obj, task_phase_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """严格保存任务阶段到本地（供 next 和 login_with_project 复用）。

    要求：
    - task_phase_data 必须包含 instruction_markdown
    - 如果是 UNDERSTANDING 且 order==1，必须包含 task_markdown

    行为：
    - 统一写入 supervisor_workspace/current_task/XX_{type}_instructions.md
    - 对于 Understanding 首阶段，写入 task_description.md
    - 更新 .supervisor/project.json 的 in_progress_task.current_task_phase

    返回：
    - { prefix, phase_type, file_path, task_description_path, wrote_task_description }
    """
    if "instruction_markdown" not in task_phase_data:
        raise ValueError("API响应缺少必需字段: task_phase.instruction_markdown")

    instruction_md = task_phase_data["instruction_markdown"]
    task_id = task_phase_data.get("task_id")
    if not task_id:
        raise ValueError("Task phase missing task_id, cannot save locally")

    # 准备保存结构
    task_phase_data_for_save = dict(task_phase_data)
    task_phase_data_for_save["description"] = instruction_md
    full_task_phase_data = {"task_phase": task_phase_data_for_save, "context": context or {}}

    # 保存并决定前缀
    task_phase_type = task_phase_data.get("type", "unknown").lower()
    task_phase_order = task_phase_data.get("order")
    if task_phase_order is not None:
        prefix = f"{task_phase_order:02d}"
        service_obj.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id, task_phase_order=task_phase_order)
    else:
        existing_files = list(service_obj.file_manager.current_task_dir.glob("[0-9][0-9]_*_instructions.md"))
        prefix = f"{len(existing_files) + 1:02d}"
        service_obj.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id)

    filename = f"{prefix}_{task_phase_type}_instructions.md"
    file_path = f"supervisor_workspace/current_task/{filename}"
    task_description_path = str(service_obj.file_manager.current_task_dir / "task_description.md")

    # 若是 Understanding 且首阶段，写入任务说明
    wrote_task_description = False
    if task_phase_data.get("type") == "UNDERSTANDING" and task_phase_order == 1:
        if "task_markdown" not in task_phase_data:
            raise ValueError("API响应缺少必需字段: task_phase.task_markdown")
        if task_phase_data["task_markdown"] is None:
            raise ValueError("API响应字段非法：task_phase.task_markdown 不能为 None")
        # 写任务说明
        description_path = service_obj.file_manager.current_task_dir / "task_description.md"
        with open(description_path, "w", encoding="utf-8") as df:
            df.write(task_phase_data["task_markdown"])
        wrote_task_description = True

    return {
        "prefix": prefix,
        "phase_type": task_phase_type,
        "file_path": file_path,
        "task_description_path": task_description_path,
        "wrote_task_description": wrote_task_description,
    }

