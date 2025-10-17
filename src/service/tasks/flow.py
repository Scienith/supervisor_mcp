"""
任务流相关（拉取下一阶段、上报结果、查询项目状态）。

- next
- report
- get_project_status

说明：
- 外部 API 统一通过 `service.get_api_client()` 获取，兼容测试的打桩方式。
- 通过 `service_obj` 访问 MCPService 的 file_manager、session_manager、辅助方法等。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import service


async def next(service_obj) -> Dict[str, Any]:
    await service_obj._ensure_session_restored()
    if not service_obj.session_manager.is_authenticated():
        return {"success": False, "error_code": "AUTH_001", "message": "请先登录"}

    project_id = service_obj.get_current_project_id()
    try:
        if not service_obj.file_manager.has_project_info():
            return {"status": "error", "message": "project.json not found. Please run 'init' first."}

        # 记录当前已保存的阶段ID（用于判断是否重复拉取同一阶段）
        prev_phase_id = None
        if service_obj.file_manager.has_current_task_phase():
            _prev = service_obj.file_manager.read_current_task_phase_data()
            if isinstance(_prev, dict):
                prev_phase_id = _prev.get("id")

        async with service_obj._get_project_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request("GET", "task-phases/next/", params={"project_id": project_id})

        if response["status"] == "success":
            if "task_phase" not in response:
                return {
                    "status": "error",
                    "error_code": "RESPONSE_FORMAT_ERROR",
                    "message": f"API响应格式不匹配：期待包含 'task_phase' 字段，但收到: {list(response.keys())}",
                }
            task_phase_data = response["task_phase"]
            context = response.get("context", {})
            try:
                save_info = await service_obj._save_phase_strict(task_phase_data, context)
            except Exception as e:
                return {
                    "status": "error",
                    "error_code": "FILE_SAVE_ERROR",
                    "message": f"Failed to save task phase locally: {str(e)}",
                }

            phase_type = task_phase_data["type"]
            phase_file_path = save_info.get("file_path")
            task_description_path = save_info.get("task_description_path")
            wrote_task_desc = save_info.get("wrote_task_description", False)

            user_lines: List[str] = []
            to_ai_text = (
                "执行成功\n\n"
                "你需要按照下面的顺序行动\n"
                f"1。使用 `read_file` 工具读取 {task_description_path}（如无则跳过）\n"
                f"2。使用 `read_file` 工具读取 {phase_file_path} 获取阶段说明\n"
                "3。立即按照任务说明和阶段说明执行当前阶段的全部工作，不要等待用户反馈"
            )

            if wrote_task_desc:
                task_file_path = f"supervisor_workspace/current_task/task_description.md"
                user_lines = [
                    f"**已获取任务说明和{phase_type}阶段说明，准备执行**",
                    f"- 任务说明: `{task_file_path}`",
                    f"- {phase_type}阶段说明: `{phase_file_path}`",
                ]
            else:
                user_lines = [
                    f"**已获取{phase_type}阶段说明，准备执行**",
                    f"- {phase_type}阶段说明: `{phase_file_path}`",
                ]

            # 两类指令：展示 + 执行
            instr_display = service_obj._create_instruction(
                to_ai_text,
                user_lines,
                result="success",
                kind="display",
            )
            instr_execute = service_obj._create_instruction(
                "请在阅读完成后继续执行阶段",
                [],
                result="success",
                kind="execute",
                phase=f"执行 {phase_type} 阶段",
            )

            instructions_v2: List[Dict[str, Any]] = []
            # 若未上报导致重复拉取同一阶段，先提示用户
            if prev_phase_id and task_phase_data.get("id") == prev_phase_id:
                phase_label = service_obj._format_phase_label(phase_type)
                notice = service_obj._create_instruction(
                    "提示：当前阶段尚未提交 report，本次重新拉取同一阶段说明",
                    [f"ℹ️ 现有 {phase_label} 的任务还没有 report，已重新拉取 {phase_label} 阶段的任务说明"],
                    result="warning",
                    kind="display",
                )
                instructions_v2.append(notice)

            instructions_v2.extend([instr_display, instr_execute])
            instructions = [instr_display.get("to_ai", ""), instr_execute.get("to_ai", "")]

            return {
                "status": "success",
                "message": f"任务阶段详情已保存到本地文件: {phase_file_path}",
                "instructions": instructions,
                "instructions_v2": instructions_v2,
            }

        if response["status"] == "error":
            error_message = response["message"]
            if len(error_message) > 2000:
                error_message = error_message[:2000] + "\n\n[响应被截断，完整错误信息过长]"
            return {"status": "error", "error_code": response["error_code"], "message": error_message}

        if str(response.get("status")).lower() == "no_available_tasks":
            instructions = []
            try:
                instructions = await service_obj._get_pending_tasks_instructions()
            except Exception:
                instructions = [
                    service_obj._create_instruction(
                        "请先提示用户选择待处理任务或创建新任务，并等待用户指示后再调用 `start_task` 或 `add_task`",
                        ["**当前没有进行中的任务阶段。**", "", "❓请选择一个待处理任务执行 `start_task`，或使用 `add_task` 创建新任务"],
                        result="success",
                    )
                ]

            message = response.get("message") or "当前没有进行中的任务阶段"
            # 兼容：如果 instructions 为结构化对象，附带字符串版本
            if instructions and isinstance(instructions[0], dict):
                instructions_v2 = instructions
                instructions = [i.get("to_ai", "") for i in instructions_v2]
                return {"status": "success", "message": message, "instructions": instructions, "instructions_v2": instructions_v2}
            return {"status": "success", "message": message, "instructions": instructions}

        return {"status": response["status"], "message": response.get("message")}

    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 2000:
            error_msg = error_msg[:2000] + "\n\n[错误信息被截断，完整错误过长]"
        return {"success": False, "error_code": "AUTH_002", "message": f"获取任务失败: {error_msg}"}


async def report(service_obj, task_phase_id: Optional[str], result_data: Dict[str, Any], finish_task: bool = False) -> Dict[str, Any]:
    if not service_obj.session_manager.is_authenticated():
        return {"success": False, "error_code": "AUTH_001", "message": "请先登录"}

    project_id = service_obj.get_current_project_id()
    if not project_id:
        return {
            "status": "error",
            "message": "No project context found. Please run setup_workspace or create_project first.",
        }

    try:
        try:
            current_task_phase = service_obj.file_manager.read_current_task_phase_data()
            if not task_phase_id:
                inferred_id = current_task_phase.get("id")
                if not inferred_id:
                    return {
                        "status": "error",
                        "error_code": "MISSING_TASK_PHASE_ID",
                        "message": "当前阶段ID不存在，请先执行 start 和 next 获取任务阶段",
                    }
                task_phase_id = inferred_id

            project_info = service_obj.file_manager.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            task_id = in_progress_group.get("id") if in_progress_group else None
            if not task_id:
                return {"status": "error", "message": "No active task group found"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to read current task phase: {str(e)}"}

        if not service_obj.file_manager.has_current_task_phase(task_id):
            return {"status": "error", "message": "No current task phase found. Please run 'next' first."}

        phase_type_upper = current_task_phase.get("type")
        if phase_type_upper == "VALIDATION":
            if not isinstance(result_data, dict) or set(result_data.keys()) != {"passed"} or not isinstance(result_data.get("passed"), bool):
                return {
                    "status": "error",
                    "error_code": "INVALID_RESULT_DATA",
                    "message": "VALIDATION 阶段的 result_data 必须为 {\"passed\": true/false}，且不允许包含其他字段",
                }
        else:
            if isinstance(result_data, dict) and len(result_data) > 0:
                return {
                    "status": "error",
                    "error_code": "INVALID_RESULT_DATA",
                    "message": "非 VALIDATION 阶段不需要 result_data，请不要传入任何字段",
                }

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            if phase_type_upper == "VALIDATION":
                request_data = {"result_data": {"validation_result": {"passed": result_data["passed"]}}}
            else:
                request_data = {"result_data": {}}
            if finish_task:
                request_data["finish_task"] = True

            response = await api.request(
                "POST",
                f"task-phases/{task_phase_id}/report-result/",
                json=request_data,
            )

        if response["status"] == "success":
            response_data = response.get("data")
            if not isinstance(response_data, dict):
                return {
                    "status": "error",
                    "error_code": "REPORT_RESPONSE_INVALID",
                    "message": "提交任务失败: API响应缺少data字段或格式不正确",
                }

            task_status = response_data.get("task_status")
            if task_status is None:
                return {
                    "status": "error",
                    "error_code": "REPORT_RESPONSE_MISSING_TASK_STATUS",
                    "message": "提交任务失败: API响应缺少task_status字段，请联系后端维护者",
                }

            if task_status == "COMPLETED":
                cleanup_id = task_id or (current_task_phase.get("task_id") if isinstance(current_task_phase, dict) else None)
                service_obj.file_manager.cleanup_task_files(cleanup_id)

            task_phase_type = current_task_phase.get("type") if isinstance(current_task_phase, dict) else None
            response.pop("data", None)

            instructions: List[Dict[str, Any]] = []
            if task_phase_type:
                if task_status == "COMPLETED":
                    instructions.append(
                        service_obj._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            ["✅ **任务已完成**"],
                            result="success",
                        )
                    )
                    task_instructions = await service_obj._get_pending_tasks_instructions()
                    instructions.extend(task_instructions)
                elif task_phase_type in ["IMPLEMENTING", "FIXING"]:
                    next_phase_type = service_obj._predict_next_phase_type(task_phase_type)
                    next_phase_label = service_obj._format_phase_label(next_phase_type)
                    next_phase_bullet = f"👉 1. 使用 `next` 进入 {next_phase_label} 的任务阶段"
                    instructions.append(
                        service_obj._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            [
                                "✅ **任务阶段已完成**",
                                "",
                                "请选择下一步操作：",
                                next_phase_bullet,
                                f"👉 2. 使用 `finish_task {task_id}` 直接完成整个任务",
                            ],
                            result="success",
                        )
                    )
                elif task_phase_type == "VALIDATION":
                    validation_passed = False
                    api_validation_result = response_data.get("result", {}).get("validation_result")
                    if isinstance(api_validation_result, dict) and "passed" in api_validation_result:
                        validation_passed = bool(api_validation_result["passed"])
                    elif isinstance(result_data, dict):
                        if "passed" in result_data and isinstance(result_data["passed"], bool):
                            validation_passed = result_data["passed"]
                        else:
                            validation_passed = result_data.get("validation_result", {}).get("passed", False)
                    if validation_passed:
                        next_phase_type_after_validation = service_obj._predict_next_phase_type(task_phase_type, True)
                        next_phase_label_after_validation = service_obj._format_phase_label(next_phase_type_after_validation)
                        next_phase_bullet = f"👉 1. 使用 `next` 进入 {next_phase_label_after_validation} 的任务阶段"
                        instructions.append(
                            service_obj._create_instruction(
                                "1。等待用户反馈\n2。基于用户反馈行动",
                                [
                                    "✅ **验证通过！**",
                                    "",
                                    "请选择下一步操作：",
                                    next_phase_bullet,
                                    f"👉 2. 使用 `finish_task {task_id}` 直接完成整个任务",
                                    "👉 3. 征求用户是否需要人工审核结果，确保结论正确",
                                ],
                                result="success",
                            )
                        )
                    else:
                        instructions.append(
                            service_obj._create_instruction(
                                "1。等待用户反馈\n2。基于用户反馈行动",
                                ["❌ **验证未通过**", "", "❓是否要使用 `next` 进入修复阶段（FIXING）"],
                                result="failure",
                            )
                        )
                elif task_phase_type == "RETROSPECTIVE":
                    instructions.append(
                        service_obj._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            ["✅ **复盘阶段已完成，任务已结束**"],
                            result="success",
                        )
                    )

            # 统一提供 instructions_v2 与字符串版 instructions
            instructions_v2 = instructions
            instructions = [i.get("to_ai", i) if isinstance(i, dict) else i for i in instructions_v2]
            return {
                "status": "success",
                "message": response.get("message", "提交成功"),
                "instructions": instructions,
                "instructions_v2": instructions_v2,
            }

        return {"status": response.get("status", "error"), "error_code": response.get("error_code"), "message": response.get("message")}

    except Exception as e:
        return {"status": "error", "error_code": "REPORT_UNEXPECTED_ERROR", "message": f"提交任务失败: {str(e)}"}


async def get_project_status(service_obj, detailed: bool = False) -> Dict[str, Any]:
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
        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            return await api.request(
                "GET",
                f"projects/{project_id}/status/",
                params={"detail": "true" if detailed else "false"},
            )
    except Exception as e:
        return {"status": "error", "message": f"获取项目状态失败: {str(e)}"}
