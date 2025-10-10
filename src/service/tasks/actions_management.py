"""
任务动作 - 管理相关（创建/取消/完成）。

- add_task
- cancel_task
- finish_task
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import service


async def add_task(service_obj, title: str, goal: str, sop_step_identifier: str) -> Dict[str, Any]:
    if not service_obj.session_manager.is_authenticated():
        return {"status": "error", "error_code": "AUTH_001", "message": "请先登录"}

    project_id = service_obj.get_current_project_id()
    if not project_id:
        return {
            "status": "error",
            "message": "No project context found. Please run setup_workspace or create_project first.",
        }

    try:
        if not service_obj.file_manager.has_project_info():
            return {"status": "error", "message": "项目未初始化，请先执行 init 工具初始化项目"}

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request(
                method="POST",
                endpoint="tasks/",
                json={
                    "project_id": project_id,
                    "title": title,
                    "goal": goal,
                    "type": "IMPLEMENTING",
                    "sop_step_identifier": sop_step_identifier,
                },
            )

        if isinstance(response, dict) and response.get("status") == "success":
            task_data = response.get("data", {})
            new_task_id = task_data.get("id", "")
            new_task_title = task_data.get("title", title)
            if "data" in response:
                del response["data"]
            response["instructions"] = [
                service_obj._create_instruction(
                    "1。等待用户反馈\n2。基于用户反馈行动",
                    [
                        "✅ **任务创建成功**",
                        f"- 标题: `{new_task_title}`",
                        f"- ID: `{new_task_id}`",
                        "",
                        f"👉 是否立即启动？使用 `start {new_task_id}`",
                    ],
                    result="success",
                )
            ]
            return {
                "status": "success",
                "message": response.get("message", "任务组已创建"),
                "task_id": new_task_id,
                "instructions": response.get("instructions", []),
            }
        else:
            if response.get("error_code") == "TASK_VALIDATION_ERROR":
                conflicting_task_id = response.get("conflicting_task_id") or response.get("data", {}).get(
                    "conflicting_task_id"
                )
                task_state = None
                try:
                    status_resp = await service_obj.get_project_status(detailed=True)
                    if status_resp.get("status") == "success" and conflicting_task_id:
                        data = status_resp.get("data", {})
                        pending = data.get("pending_tasks", []) or data.get("pending_groups", []) or []
                        suspended = data.get("suspended_tasks", []) or data.get("suspended_groups", []) or []
                        if any(t.get("id") == conflicting_task_id for t in pending):
                            task_state = "PENDING"
                        elif any(t.get("id") == conflicting_task_id for t in suspended):
                            task_state = "SUSPENDED"
                except Exception:
                    pass

                action_line = ""
                if task_state == "PENDING":
                    action_line = f"👉 请先使用 `start {conflicting_task_id}` 启动该任务，或取消它后再创建新任务"
                elif task_state == "SUSPENDED":
                    action_line = f"👉 请先使用 `continue_suspended {conflicting_task_id}` 恢复该任务，或取消它后再创建新任务"
                else:
                    action_line = "👉 请检查是否存在同名或冲突任务，必要时先取消或完成后再创建"

                return {
                    "status": response.get("status", "error"),
                    "error_code": response.get("error_code", "TASK_VALIDATION_ERROR"),
                    "message": response.get("message", "任务创建失败：存在冲突"),
                    "instructions": [
                        service_obj._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            [
                                "❌ **任务创建失败：存在冲突**",
                                "",
                                action_line,
                            ],
                            result="failure",
                        )
                    ],
                }

            return {
                "status": response.get("status", "error"),
                "error_code": response.get("error_code", "UNKNOWN_ERROR"),
                "message": response.get("message", "任务创建失败"),
            }
    except Exception as e:
        return {"status": "error", "message": f"创建任务组失败: {str(e)}"}


async def cancel_task(service_obj, task_id: Optional[str], cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
    await service_obj._ensure_session_restored()
    if not service_obj.session_manager.is_authenticated():
        return {"status": "error", "error_code": "AUTH_001", "message": "请先登录"}

    project_id = service_obj.get_current_project_id()
    if not project_id:
        return {
            "status": "error",
            "message": "No project context found. Please run setup_workspace or create_project first.",
        }

    try:
        if not task_id:
            project_info = service_obj.file_manager.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            if not in_progress_group or not in_progress_group.get("id"):
                return {"status": "error", "message": "当前没有进行中的任务组可取消"}
            task_id = in_progress_group["id"]

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request(
                method="POST",
                endpoint=f"tasks/{task_id}/cancel/",
                json={
                    "project_id": project_id,
                    "cancellation_reason": cancellation_reason,
                },
            )

        if response.get("status") == "success":
            try:
                service_obj.file_manager.cleanup_task_files(task_id)
                if service_obj.file_manager.has_project_info():
                    project_info = service_obj.file_manager.read_project_info()
                    in_progress_group = project_info.get("in_progress_task")
                    if in_progress_group and in_progress_group.get("id") == task_id:
                        project_info["in_progress_task"] = None
                        service_obj.file_manager.save_project_info(project_info)
            except Exception:
                pass

            instructions = []
            instructions.append(
                service_obj._create_instruction(
                    "1。等待用户反馈\n2。基于用户反馈行动",
                    ["✅ **任务已成功取消**"],
                    result="success",
                )
            )
            try:
                task_instructions = await service_obj._get_pending_tasks_instructions()
                instructions.extend(task_instructions)
            except Exception:
                pass

            return {"status": "success", "message": response.get("message", "任务已成功取消"), "instructions": instructions}

        return {
            "status": response.get("status", "error"),
            "error_code": response.get("error_code", "UNKNOWN_ERROR"),
            "message": response.get("message", "取消失败"),
        }
    except Exception as e:
        return {"status": "error", "message": f"取消任务组失败: {str(e)}"}


async def finish_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
    await service_obj._ensure_session_restored()
    if not service_obj.session_manager.is_authenticated():
        return {"status": "error", "error_code": "AUTH_001", "message": "请先登录"}

    project_id = service_obj.get_current_project_id()
    if not project_id:
        return {
            "status": "error",
            "message": "No project context found. Please run setup_workspace or create_project first.",
        }

    try:
        if not task_id:
            project_info = service_obj.file_manager.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            if not in_progress_group or not in_progress_group.get("id"):
                return {"status": "error", "message": "当前没有进行中的任务组可完成"}
            task_id = in_progress_group["id"]

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request(method="POST", endpoint=f"tasks/{task_id}/finish/")

        if response.get("status") == "success":
            try:
                if service_obj.file_manager.has_project_info():
                    project_info = service_obj.file_manager.read_project_info()
                    in_progress_group = project_info.get("in_progress_task")
                    if in_progress_group and in_progress_group.get("id") == task_id:
                        project_info["in_progress_task"]["status"] = "COMPLETED"
                        service_obj.file_manager.save_project_info(project_info)
                        try:
                            service_obj.file_manager.cleanup_task_files(task_id)
                        except Exception:
                            pass
            except Exception:
                pass

            instructions = []
            instructions.append(
                service_obj._create_instruction(
                    "请告知任务已成功完成",
                    ["✅ **任务已成功完成**"],
                    result="success",
                )
            )
            try:
                task_instructions = await service_obj._get_pending_tasks_instructions()
                instructions.extend(task_instructions)
            except Exception:
                pass

            return {
                "status": "success",
                "message": response.get("message", "任务已成功完成"),
                "instructions": instructions,
            }

        error_code = response.get("error_code", "FINISH_TASK_FAILED")
        error_message = response.get("message") or response.get("error") or "完成任务失败，后端未返回错误详情"
        detail = response.get("detail")
        if detail and detail not in error_message:
            error_message = f"{error_message}（{detail}）"

        current_phase_type = service_obj._get_current_task_phase_type()
        predicted_next = service_obj._predict_next_phase_type(current_phase_type)
        next_stage_hint = service_obj._format_phase_label(predicted_next)

        instructions = [
            service_obj._create_instruction(
                "请告知任务完成操作失败，并指导用户继续推进",
                [
                    f"❌ **完成任务失败**：{error_message}",
                    "",
                    f"👉 请确认 IMPLEMENTING 阶段已完成；如需继续推进，可使用 `next` 进入 {next_stage_hint} 或 `cancel_task` 取消任务",
                ],
                result="failure",
            )
        ]

        return {
            "status": response.get("status", "error"),
            "error_code": error_code,
            "message": error_message,
            "instructions": instructions,
        }
    except Exception as e:
        return {"status": "error", "message": f"完成任务失败: {str(e)}"}

