"""
任务动作 - 生命周期相关（启动/暂存/恢复）。

- start_task
- suspend_task
- continue_suspended_task
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import service


async def start_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
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
            status = await service_obj.get_project_status(detailed=True)
            if status.get("status") != "success":
                return {"status": "error", "message": "无法获取项目状态以选择待处理任务"}
            data = status.get("data", {})
            pending = data.get("pending_tasks", []) or data.get("pending_groups", [])
            if not pending:
                return {"status": "error", "message": "当前没有待处理任务可启动"}
            if len(pending) > 1:
                instructions = await service_obj._get_pending_tasks_instructions()
                return {
                    "status": "error",
                    "error_code": "MULTIPLE_PENDING_TASKS",
                    "message": "存在多个待处理任务，请指定 task_id",
                    "instructions": instructions,
                }
            task_id = pending[0]["id"]

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request("POST", f"projects/{project_id}/tasks/{task_id}/start/")

        if response["status"] == "success":
            if service_obj.file_manager.has_project_info():
                project_info = service_obj.file_manager.read_project_info()
                task_title = response["data"]["title"]
                project_info["in_progress_task"] = {"id": task_id, "title": task_title, "status": "IN_PROGRESS"}
                service_obj.file_manager.save_project_info(project_info)
                service_obj.file_manager.switch_task_directory(task_id)

        if response["status"] == "success":
            task_title = response["data"]["title"]
            first_phase_label = service_obj._format_phase_label("UNDERSTANDING")
            first_phase_hint = (
                f"❓当前步骤{task_title}的任务在进行中，是否要使用next获得下一个阶段{first_phase_label}的任务说明进入任务的下一阶段"
            )
            instr_display = service_obj._create_instruction(
                "1。等待用户反馈\n2。基于用户反馈行动",
                ["✅ **任务已成功启动**", f"- 任务: `{task_title}`", "", first_phase_hint],
                result="success",
                kind="display",
            )
            response["instructions_v2"] = [instr_display]
            response["instructions"] = [instr_display.get("to_ai", "")]
        elif response["error_code"] == "CONFLICT_IN_PROGRESS":
            error_message = response["message"]
            current_task_title = "当前任务"
            if "已有进行中的任务" in error_message:
                import re

                match = re.search(r"已有进行中的任务：(.*)", error_message)
                if match:
                    current_task_title = match.group(1)
            current_task_id = response.get("data", {}).get("current_task_id", "")
            instr_display = service_obj._create_instruction(
                "1。等待用户反馈\n2。基于用户反馈行动",
                [
                    "❌ **无法启动新任务**",
                    f"原因：任务 `{current_task_title}` 正在进行中",
                    "",
                    "**解决方案：**",
                    f"👉 1. 使用 `suspend` 暂存当前任务，然后使用 `start {task_id}` 启动新任务",
                    f"👉 2. 使用 `finish_task {current_task_id}` 完成当前任务，然后使用 `start {task_id}` 启动新任务",
                ],
                result="failure",
                kind="display",
            )
            instr_execute = service_obj._create_instruction(
                "请根据用户选择处理冲突后继续",
                [],
                result="warning",
                kind="execute",
                phase="暂存或完成当前任务后再启动新任务",
            )
            response["instructions_v2"] = [instr_display, instr_execute]
            response["instructions"] = [instr_display.get("to_ai", ""), instr_execute.get("to_ai", "")]

        simplified: Dict[str, Any] = {
            "status": response["status"],
            "message": response["message"],
            "instructions": response.get("instructions", []),
        }
        # 传递结构化指令给上层（供 MCP action 渲染使用）
        if "instructions_v2" in response:
            simplified["instructions_v2"] = response["instructions_v2"]
        if response["status"] != "success" and "error_code" in response:
            simplified["error_code"] = response["error_code"]
        return simplified
    except Exception as e:
        return {"status": "error", "message": f"启动任务组失败: {str(e)}"}


async def suspend_task(service_obj) -> Dict[str, Any]:
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
        if not service_obj.file_manager.has_project_info():
            return {"status": "error", "message": "项目信息不存在，请先运行 init 工具初始化项目"}

        project_info = service_obj.file_manager.read_project_info()
        in_progress_group = project_info.get("in_progress_task")
        if not in_progress_group:
            return {"status": "error", "message": "当前没有进行中的任务组"}

        current_task_id = in_progress_group["id"]
        if not current_task_id:
            return {"status": "error", "message": "当前没有活跃的任务组可以暂存"}

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request("POST", f"projects/{project_id}/tasks/{current_task_id}/suspend/")

        # 本地持久化更新（容错）
        try:
            response_data = response.get("data", {}) if isinstance(response, dict) else {}
            response_title = response_data.get("title", "")
            response_suspended_at = response_data.get("suspended_at", None)
            files_count = 0
            if service_obj.file_manager.current_task_dir.exists():
                suspended_dir = service_obj.file_manager.suspended_tasks_dir / f"task_{current_task_id}"
                suspended_dir.mkdir(parents=True, exist_ok=True)
                for item in service_obj.file_manager.current_task_dir.iterdir():
                    target = suspended_dir / item.name
                    if item.is_file():
                        import shutil
                        shutil.copy2(item, target)
                        files_count += 1
            suspended_group = project_info.pop("in_progress_task", {})
            project_info["in_progress_task"] = None
            if "suspended_tasks" not in project_info:
                project_info["suspended_tasks"] = []
            from datetime import datetime
            suspended_info = {
                "id": current_task_id,
                "title": suspended_group.get("title", response_title),
                "status": "SUSPENDED",
                "suspended_at": response_suspended_at or datetime.now().isoformat(),
                "files_count": files_count,
            }
            project_info["suspended_tasks"] = [
                sg for sg in project_info["suspended_tasks"] if sg.get("id") != current_task_id
            ]
            project_info["suspended_tasks"].append(suspended_info)
            service_obj.file_manager.save_project_info(project_info)
        except Exception as e:
            raise

        instructions_v2 = [service_obj._create_instruction("1。等待用户反馈\n2。基于用户反馈行动", ["✅ **任务已成功暂存**"], result="success", kind="display")]
        task_instructions = await service_obj._get_pending_tasks_instructions()
        instructions_v2.extend(task_instructions)
        return {"status": "success", "message": "任务组已成功暂存", "instructions": [i.get("to_ai", i) if isinstance(i, dict) else i for i in instructions_v2], "instructions_v2": instructions_v2}
    except Exception as e:
        # 容错处理：尽力完成本地暂存与指引，仍返回success以保持工具可用性
        try:
            project_info = service_obj.file_manager.read_project_info()
            in_progress_group = project_info.get("in_progress_task") if isinstance(project_info, dict) else None
            current_task_id = in_progress_group.get("id") if in_progress_group else None
            if current_task_id:
                # 本地暂存
                files_count = 0
                if service_obj.file_manager.current_task_dir.exists():
                    files_count = len([f for f in service_obj.file_manager.current_task_dir.iterdir() if f.is_file()])
                service_obj.file_manager.suspend_current_task(current_task_id)
                # 更新项目状态
                suspended_group = project_info.pop("in_progress_task", {})
                project_info["in_progress_task"] = None
                if "suspended_tasks" not in project_info:
                    project_info["suspended_tasks"] = []
                from datetime import datetime
                project_info["suspended_tasks"].append({
                    "id": current_task_id,
                    "title": suspended_group.get("title", ""),
                    "status": "SUSPENDED",
                    "suspended_at": datetime.now().isoformat(),
                    "files_count": files_count,
                })
                service_obj.file_manager.save_project_info(project_info)
        except Exception as e:
            # 无法本地暂存时，直接抛出由上层捕获
            raise

        instructions_v2 = await service_obj._get_pending_tasks_instructions()
        return {"status": "success", "message": "任务已成功暂存", "instructions": [i.get("to_ai", i) if isinstance(i, dict) else i for i in instructions_v2], "instructions_v2": instructions_v2}


async def continue_suspended_task(service_obj, task_id: Optional[str]) -> Dict[str, Any]:
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
            suspended = project_info.get("suspended_tasks", [])
            if not suspended:
                return {"status": "error", "message": "当前没有暂存任务可恢复"}
            if len(suspended) > 1:
                instructions = await service_obj._get_pending_tasks_instructions()
                return {
                    "status": "error",
                    "error_code": "MULTIPLE_SUSPENDED_TASKS",
                    "message": "存在多个暂存任务，请指定 task_id",
                    "instructions": instructions,
                }
            task_id = suspended[0]["id"]

        if not service_obj.file_manager.has_project_info():
            return {"status": "error", "message": "项目信息不存在，请先运行 init 工具初始化项目"}

        project_info = service_obj.file_manager.read_project_info()

        if not service_obj.file_manager.is_task_suspended(task_id):
            return {"status": "error", "message": f"任务组 {task_id} 未找到或未被暂存"}

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request("POST", f"projects/{project_id}/tasks/{task_id}/resume/")

        if response["status"] == "success":
            try:
                in_progress_group = project_info.get("in_progress_task")
                previous_task_info = None
                if in_progress_group:
                    current_task_id = in_progress_group["id"]
                    current_task_phase_status = service_obj.file_manager.get_current_task_phase_status()
                    if current_task_phase_status.get("has_current_task_phase"):
                        files_count = 0
                        if service_obj.file_manager.current_task_dir.exists():
                            files_count = len([f for f in service_obj.file_manager.current_task_dir.iterdir() if f.is_file()])
                        service_obj.file_manager.suspend_current_task(current_task_id)
                        previous_task_info = {"id": current_task_id, "title": in_progress_group.get("title", "之前的任务组"), "suspended": True}

                        from datetime import datetime
                        if "suspended_tasks" not in project_info:
                            project_info["suspended_tasks"] = []

                        suspended_info = {
                            "id": current_task_id,
                            "title": in_progress_group.get("title", "之前的任务组"),
                            "status": "SUSPENDED",
                            "suspended_at": datetime.now().isoformat(),
                            "files_count": files_count,
                        }
                        project_info["suspended_tasks"] = [
                            sg for sg in project_info["suspended_tasks"] if sg.get("id") != current_task_id
                        ]
                        project_info["suspended_tasks"].append(suspended_info)

                # 手动恢复文件（避免环境差异导致的失败）
                suspended_dir = service_obj.file_manager.suspended_tasks_dir / f"task_{task_id}"
                restore_success = False
                if suspended_dir.exists():
                    import shutil
                    # 清空并重建当前目录
                    if service_obj.file_manager.current_task_dir.exists():
                        shutil.rmtree(service_obj.file_manager.current_task_dir)
                    service_obj.file_manager.current_task_dir.mkdir(parents=True, exist_ok=True)
                    for item in suspended_dir.iterdir():
                        target = service_obj.file_manager.current_task_dir / item.name
                        if item.is_file():
                            shutil.copy2(item, target)
                        elif item.is_dir():
                            shutil.copytree(item, target, dirs_exist_ok=True)
                    restore_success = True
                if not restore_success:
                    return {"status": "error", "message": f"恢复任务组失败：暂存文件不存在或已损坏"}

                files_count = 0
                if service_obj.file_manager.current_task_dir.exists():
                    files_count = len([f for f in service_obj.file_manager.current_task_dir.iterdir() if f.is_file()])

                restored_group = None
                for sg in project_info.get("suspended_tasks", []):
                    if sg.get("id") == task_id:
                        restored_group = sg
                        break
                task_title = restored_group.get("title") if restored_group else None
                if not task_title:
                    task_title = response.get("data", {}).get("title", "")

                project_info["in_progress_task"] = {"id": task_id, "title": task_title, "status": "IN_PROGRESS"}
                if "suspended_tasks" in project_info:
                    project_info["suspended_tasks"] = [sg for sg in project_info["suspended_tasks"] if sg.get("id") != task_id]
                service_obj.file_manager.save_project_info(project_info)

                title = response["data"]["title"]
                resumed_at = response["data"]["resumed_at"]
                restored_info = {"id": task_id, "title": title, "files_count": files_count, "restored_at": resumed_at}
                if "data" in response:
                    del response["data"]
                response["restored_task"] = restored_info
                if previous_task_info:
                    response["previous_task"] = previous_task_info

                phase_status = service_obj.file_manager.get_current_task_phase_status()
                if not phase_status.get("has_current_task_phase"):
                    raise ValueError("无法获取恢复后任务的阶段说明文件")
                latest_phase_file = phase_status.get("latest_task_phase_file")
                inferred_phase_type = service_obj._extract_phase_type_from_filename(latest_phase_file)
                resumed_phase_label = service_obj._format_phase_label(inferred_phase_type)
                try:
                    next_type = service_obj._predict_next_phase_type(inferred_phase_type)
                    next_label = service_obj._format_phase_label(next_type)
                except Exception:
                    next_label = resumed_phase_label
                next_hint_text = (
                    f"❓当前步骤{title}的任务在进行中，是否要使用next获得下一个阶段{next_label}的任务说明进入任务的下一阶段"
                )
                instr_display = service_obj._create_instruction(
                    "1。等待用户反馈\n2。基于用户反馈行动",
                    [
                        "✅ **任务已成功恢复**",
                        f"- 任务: `{title}`",
                        f"- 文件数量: {files_count}",
                        "",
                        next_hint_text,
                    ],
                    result="success",
                    kind="display",
                )
                instr_execute = service_obj._create_instruction(
                    "请根据用户选择继续推进任务",
                    [],
                    result="success",
                    kind="execute",
                    phase="获取当前任务的下一个阶段说明",
                )
                response["instructions_v2"] = [instr_display, instr_execute]
                response["instructions"] = [instr_display.get("to_ai", ""), instr_execute.get("to_ai", "")]
            except Exception:
                raise

        return {"status": "success", "message": "任务组已成功恢复", "instructions": response.get("instructions", [])}
    except Exception as e:
        # 容错处理：尝试本地恢复并返回成功
        try:
            project_info = service_obj.file_manager.read_project_info()
            # 自动选择一个可恢复的任务
            if not task_id:
                suspended = project_info.get("suspended_tasks", []) if isinstance(project_info, dict) else []
                if suspended:
                    task_id = suspended[0].get("id")
            if task_id:
                service_obj.file_manager.restore_task(task_id)
                # 设置为进行中
                if isinstance(project_info, dict):
                    project_info["in_progress_task"] = {
                        "id": task_id,
                        "title": next((s.get("title") for s in project_info.get("suspended_tasks", []) if s.get("id") == task_id), ""),
                        "status": "IN_PROGRESS",
                    }
                    project_info["suspended_tasks"] = [s for s in project_info.get("suspended_tasks", []) if s.get("id") != task_id]
                    service_obj.file_manager.save_project_info(project_info)
        except Exception:
            raise

        instructions_v2 = await service_obj._get_pending_tasks_instructions()
        return {"status": "success", "message": "任务组已成功恢复", "instructions": [i.get("to_ai", i) if isinstance(i, dict) else i for i in instructions_v2], "instructions_v2": instructions_v2}
