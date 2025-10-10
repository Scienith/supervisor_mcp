"""
阶段与指令相关的辅助函数。
保留与 MCPService 中相同的行为，供实例方法委托调用。
"""
from typing import Any, Dict, List, Optional, Union


def _get_current_task_phase_type(service_obj) -> str:
    try:
        project_info = service_obj.file_manager.read_project_info()
        if not project_info:
            raise RuntimeError("无法获取项目信息，请确保项目上下文存在")

        in_progress = project_info.get("in_progress_task")
        if not isinstance(in_progress, dict):
            raise RuntimeError("当前没有进行中的任务阶段")

        current_task_phase = in_progress.get("current_task_phase")
        if not isinstance(current_task_phase, dict):
            raise RuntimeError("当前没有进行中的任务阶段")

        phase_type = current_task_phase.get("type")
        if not phase_type:
            raise RuntimeError("当前没有进行中的任务阶段")
        return phase_type
    except Exception as e:
        raise RuntimeError(f"获取任务阶段类型失败: {str(e)}")


def _format_phase_label(phase_type: Optional[str]) -> str:
    if not phase_type:
        raise ValueError("无法确定任务阶段类型")
    mapping = {
        "UNDERSTANDING": "UNDERSTANDING（任务理解阶段）",
        "PLANNING": "PLANNING（方案规划阶段）",
        "IMPLEMENTING": "IMPLEMENTING（实现阶段）",
        "VALIDATION": "VALIDATION（验证阶段）",
        "FIXING": "FIXING（修复阶段）",
        "RETROSPECTIVE": "RETROSPECTIVE（复盘阶段）",
    }
    upper = phase_type.upper()
    if upper not in mapping:
        raise ValueError(f"未知的任务阶段类型：{phase_type}")
    return mapping[upper]


def _extract_phase_type_from_filename(filename: Optional[str]) -> str:
    if not filename:
        raise ValueError("无法从文件名推断任务阶段：文件名不存在")
    name = filename.split("/")[-1]
    parts = name.split("_")
    if len(parts) >= 2:
        candidate = parts[1].upper()
        if candidate.isalpha():
            return candidate
    raise ValueError(f"无法从文件名推断任务阶段：{filename}")


def _predict_next_phase_type(
    service_obj,
    current_phase_type: Optional[str],
    validation_passed: Optional[bool] = None,
) -> str:
    if not current_phase_type:
        raise ValueError("无法推断下一个任务阶段：当前阶段未知")
    phase = current_phase_type.upper()
    if phase == "UNDERSTANDING":
        return "PLANNING"
    if phase == "PLANNING":
        return "IMPLEMENTING"
    if phase == "IMPLEMENTING":
        return "VALIDATION"
    if phase == "FIXING":
        return "VALIDATION"
    if phase == "VALIDATION":
        if validation_passed is False:
            return "FIXING"
        return "RETROSPECTIVE"
    raise ValueError(f"无法推断下一个任务阶段：未知阶段 {current_phase_type}")


async def _get_pending_tasks_instructions(
    service_obj,
    return_as_string: bool = False,
) -> Union[List[Dict[str, Any]], str]:
    status_response = await service_obj.get_project_status(detailed=True)
    if status_response["status"] != "success":
        raise ValueError(f"Project status error: {status_response}")

    data = status_response["data"]
    pending_tasks = data["pending_tasks"]
    suspended_tasks = data["suspended_tasks"]
    in_progress = data.get("current_in_progress_task")

    instructions: List[Dict[str, Any]] = []

    if in_progress:
        task_id = in_progress["id"]
        title = in_progress.get("title", "")
        try:
            project_info_local = service_obj.file_manager.read_project_info() or {}
            in_prog_local = project_info_local.get("in_progress_task") or {}
            current_phase_local = in_prog_local.get("current_task_phase") or {}
            phase_type = current_phase_local.get("type")
        except Exception:
            phase_type = None

        status = service_obj.file_manager.get_current_task_phase_status()
        phase_description_file = status.get("latest_task_phase_file")
        if not status.get("has_current_task_phase") or not phase_description_file:
            raise ValueError("无法获取当前任务阶段说明文件")
        phase_description_path = str(service_obj.file_manager.current_task_dir / phase_description_file)

        if not phase_type:
            phase_type = _extract_phase_type_from_filename(phase_description_file)

        phase_type_label = _format_phase_label(phase_type)

        user_message: List[str] = [
            f"当前进行中的任务：{title}（ID: `{task_id}`），任务阶段: {phase_type_label}",
        ]
        user_message.append(f"- 阶段说明: `{phase_description_path}`")
        user_message.append("❓是否要立即阅读任务阶段说明，按照里面的要求开始工作？")

        to_ai_text = "请提示当前进行中的任务与阶段"

        instructions.append(
            _create_instruction(
                service_obj,
                to_ai_text,
                user_message,
                result="success",
            )
        )

    if not in_progress and suspended_tasks:
        user_message = [f"**有 {len(suspended_tasks)} 个暂存任务，您可以恢复其中一个继续工作：**", ""]
        for i, task in enumerate(suspended_tasks, 1):
            title = task["title"]
            goal = task["goal"]
            task_id = task["id"]
            suspended_at = (task["suspended_at"] or "")[:10]

            user_message.append(f"👉 {i}. {title}")
            if goal:
                user_message.append(f"   - 目标: {goal}")
            user_message.append(f"   - ID: `{task_id}`")
            if suspended_at:
                user_message.append(f"   - 暂存于: {suspended_at}")
            user_message.append("")

        user_message.append("❓请选择要恢复的任务")

        instructions.append(
            _create_instruction(
                service_obj,
                "请先展示暂存任务列表，并等待用户明确指示后再决定是否调用 `continue_suspended_task`",
                user_message,
                result="success",
            )
        )

    if not in_progress and pending_tasks:
        user_message = [
            f"**{'另有 ' if suspended_tasks else ''}{len(pending_tasks)} 个待处理任务，您可以{'启动新的工作' if suspended_tasks else '选择一个启动'}：**",
            "",
        ]
        for i, task in enumerate(pending_tasks, 1):
            title = task["title"]
            goal = task["goal"]
            task_id = task["id"]
            user_message.append(f"👉 {i}. {title}")
            if goal:
                user_message.append(f"   - 目标: {goal}")
            user_message.append(f"   - ID: `{task_id}`")
            user_message.append("")

        user_message.append("❓请做出选择")

        instructions.append(
            _create_instruction(
                service_obj,
                "请先展示待处理任务列表，等待用户明确选择；在收到指示前不要调用任何工具。若用户指定任务，再根据指示调用 `start_task`",
                user_message,
                result="success",
            )
        )

    if not in_progress and not suspended_tasks and not pending_tasks:
        instructions.append(
            _create_instruction(
                service_obj,
                "请提示用户是否需要创建新任务，并等待用户反馈后再调用 `add_task`",
                [
                    "**目前没有待处理或暂存的任务，您可以创建新任务：**",
                    "",
                    "❓是否要使用 `add_task` 创建新任务",
                ],
                result="success",
            )
        )

    if return_as_string:
        if not instructions:
            return ""
        parts: List[str] = []
        for item in instructions:
            if isinstance(item, dict):
                parts.append(item.get("to_ai", ""))
            else:
                parts.append(str(item))
        return "\n\n".join(part for part in parts if part)

    return instructions


def _create_instruction(
    service_obj,
    to_ai: str,
    user_message: List[str] = None,
    result: Optional[str] = None,
) -> Dict[str, Any]:
    status_map = {
        "success": "执行成功",
        "failure": "执行失败",
        "warning": "执行后存在警告",
    }
    prefix_lines: List[str] = []
    if result:
        descriptor = status_map.get(result.lower(), result)
        prefix_lines.append(f"工具执行结果：{descriptor}")
    if user_message:
        prefix_lines.append("先原封不动地显示给用户user_messages，user_messages内容见后面说明")
    base_instruction = to_ai
    if prefix_lines:
        base_instruction = "\n".join(prefix_lines + [to_ai])
    if user_message:
        try:
            msg_block = "\n".join(user_message)
            base_instruction = (
                f"{base_instruction}\n\nuser_messages 原文内容（请原封不动的显示）：\n{msg_block}"
            )
        except Exception:
            pass
    return f"AI注意：{base_instruction}"

