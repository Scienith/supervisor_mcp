"""
项目初始化与工作区搭建逻辑的独立模块。

包含：
- init（入口，处理 new/existing 两个场景）
- _init_new_project
- _init_existing_project
- _get_project_templates_by_steps
- _setup_workspace_unified
- _setup_templates
- _download_templates_unified
- _setup_sop_structure
- _create_task_folders

说明：保持与原 MCPService 方法相同的行为与签名，通过传入的 service_obj
访问 file_manager、session_manager 等依赖；外部 API 调用通过 service.get_api_client。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import service  # 便于测试对 service.get_api_client 打桩


async def init(
    service_obj,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    working_directory: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    # 自动恢复 session
    await service_obj._ensure_session_restored()

    if not service_obj.session_manager.is_authenticated():
        return {"status": "error", "message": "请先登录"}

    # 更新 file_manager base_path
    if working_directory:
        from pathlib import Path

        service_obj.file_manager.base_path = Path(working_directory)
        service_obj.file_manager.supervisor_dir = service_obj.file_manager.base_path / ".supervisor"
        service_obj.file_manager.suspended_tasks_dir = service_obj.file_manager.supervisor_dir / "suspended_tasks"
        service_obj.file_manager.workspace_dir = service_obj.file_manager.base_path / "supervisor_workspace"
        service_obj.file_manager.templates_dir = service_obj.file_manager.workspace_dir / "templates"
        service_obj.file_manager.sop_dir = service_obj.file_manager.workspace_dir / "sop"
        service_obj.file_manager.current_task_dir = service_obj.file_manager.workspace_dir / "current_task"

    if project_id:
        return await _init_existing_project(service_obj, project_id)
    elif project_name:
        return await _init_new_project(service_obj, project_name, description)
    else:
        return {
            "status": "error",
            "message": "必须提供 project_name（新建项目）或 project_id（已知项目ID）参数",
        }


async def _init_new_project(
    service_obj, project_name: str, description: Optional[str] = None
) -> Dict[str, Any]:
    try:
        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            response = await api.request(
                "POST",
                "projects/init/",
                json={"name": project_name, "description": description or ""},
            )

        if response.get("success"):
            project_info = {
                "project_id": response["project_id"],
                "project_name": response.get("project_name", project_name),
                "description": description or "",
                "created_at": response.get("created_at", ""),
                "tasks": [],
            }

            initialization_data = response.get("initialization_data", {})
            templates_data = initialization_data.get("templates", [])

            return await _setup_workspace_unified(
                service_obj, project_info, templates_data, scenario="new_project"
            )
        else:
            return {"status": "error", "message": response.get("error", "创建项目失败")}

    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"新项目创建失败: {str(e)}"}


async def _init_existing_project(service_obj, project_id: str) -> Dict[str, Any]:
    try:
        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            project_info_response = await api.request("GET", f"projects/{project_id}/info/")

        print(f"DEBUG: API 返回的 project_info: {project_info_response}")

        if "project_id" in project_info_response:
            templates_data, sop_structure = await _get_project_templates_by_steps(
                service_obj, api, project_id
            )
            return await _setup_workspace_unified(
                service_obj,
                project_info_response,
                templates_data,
                scenario="existing_project",
                sop_structure=sop_structure,
            )
        else:
            return {"status": "error", "message": f"项目 {project_id} 不存在或无访问权限"}

    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"已知项目初始化失败: {str(e)}"}


async def _get_project_templates_by_steps(
    service_obj, api, project_id: str
) -> Tuple[list, dict]:
    try:
        sop_response = await api.request("GET", "sop/graph/", params={"project_id": project_id})
        steps = sop_response.get("steps", {})

        templates = []
        sop_structure = {"steps": {}, "dependencies": sop_response.get("dependencies", [])}

        for step_identifier, step_info in steps.items():
            try:
                step_id = step_info.get("step_id")
                if not step_id:
                    print(f"Warning: step_id not found for {step_identifier}, skipping")
                    continue

                step_detail = await api.request("GET", f"sop/steps/{step_id}/")
                stage = step_detail.get("stage", "unknown")

                sop_structure["steps"][step_identifier] = {
                    "identifier": step_identifier,
                    "name": step_detail.get("name", ""),
                    "stage": stage,
                    "description": step_detail.get("description", ""),
                    "outputs": step_detail.get("outputs", []),
                    "rules": step_detail.get("rules", []),
                    "step_id": step_detail.get("step_id"),
                }

                for output in step_detail.get("outputs", []):
                    if output.get("template_content"):
                        template_name = output.get("template_filename")
                        if not template_name:
                            print(
                                f"ERROR: Step {step_identifier} output missing template name."
                            )
                            print(f"Full output data: {output}")
                            print(
                                "Expected: template field should contain filename like 'contract-units.md'"
                            )
                            print(f"Actual: template field is {repr(template_name)}")
                            raise ValueError(
                                f"Step {step_identifier} has template_content but missing template name. This indicates a backend data issue."
                            )

                        template_path = f"sop/{stage}/{step_identifier}/templates/{template_name}"

                        template_info = {
                            "name": template_name,
                            "step_identifier": step_identifier,
                            "stage": stage,
                            "path": template_path,
                            "content": output["template_content"],
                        }
                        templates.append(template_info)

            except Exception as e:  # noqa: BLE001
                print(f"Failed to get templates for step {step_identifier}: {e}")
                continue

        return templates, sop_structure

    except Exception as e:  # noqa: BLE001
        print(f"Failed to get templates by steps: {e}")
        return [], {}


async def _setup_workspace_unified(
    service_obj,
    project_info: Dict[str, Any],
    templates_data: list,
    scenario: str,
    sop_structure: dict | None = None,
) -> Dict[str, Any]:
    try:
        service_obj.file_manager.create_supervisor_directory()

        project_data = {
            "project_id": project_info["project_id"],
            "project_name": project_info["project_name"],
            "description": project_info.get("description", ""),
            "created_at": project_info.get("created_at", ""),
            "project_path": str(service_obj.file_manager.base_path),
        }

        if "in_progress_task" in project_info:
            project_data["in_progress_task"] = project_info["in_progress_task"]
        if "suspended_tasks" in project_info:
            project_data["suspended_tasks"] = project_info["suspended_tasks"]

        service_obj.file_manager.save_project_info(project_data)

        await _setup_templates(service_obj, templates_data, scenario)

        if sop_structure:
            await _setup_sop_structure(service_obj, sop_structure)

        await _create_task_folders(service_obj, project_info.get("tasks", []))

        service_obj.session_manager.set_project_context(
            project_info["project_id"], project_info["project_name"]
        )

        return {
            "status": "success",
            "data": {
                "project_id": project_info["project_id"],
                "project_name": project_info["project_name"],
                "created_at": project_info.get("created_at", ""),
                "templates_downloaded": len(templates_data),
                "scenario": scenario,
            },
            "message": f"{'新项目创建并' if scenario == 'new_project' else '已知项目'}本地初始化成功",
        }

    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"工作区设置失败: {str(e)}"}


async def _setup_templates(service_obj, templates_data: list, scenario: str):
    service_obj.file_manager.initialize_project_structure({"templates": templates_data})
    if templates_data:
        await _download_templates_unified(service_obj, templates_data)


async def _download_templates_unified(service_obj, templates_data: list):
    async with service.get_api_client() as api_client:
        api_client.headers.update(service_obj.session_manager.get_headers())
        for template in templates_data:
            await service_obj.file_manager.download_template(api_client, template)


async def _setup_sop_structure(service_obj, sop_structure: dict):
    try:
        stages = {}
        for step_id, step_info in sop_structure.get("steps", {}).items():
            stage = step_info.get("stage", "unknown")
            if stage not in stages:
                stages[stage] = {}
            stages[stage][step_id] = step_info

        for stage, steps in stages.items():
            for step_identifier, step_info in steps.items():
                clean_outputs = []
                for output in step_info.get("outputs", []):
                    clean_output = {k: v for k, v in output.items() if k != "template_content"}
                    clean_outputs.append(clean_output)

                config_data = {
                    "identifier": step_info.get("identifier"),
                    "name": step_info.get("name"),
                    "stage": step_info.get("stage"),
                    "description": step_info.get("description"),
                    "outputs": clean_outputs,
                    "rules": step_info.get("rules", []),
                    "step_id": step_info.get("step_id"),
                }

                await service_obj.file_manager.save_sop_config(
                    stage, step_identifier, config_data
                )
    except Exception as e:  # noqa: BLE001
        print(f"Failed to setup SOP structure: {e}")


async def _create_task_folders(service_obj, tasks: list):
    for task in tasks:
        if task.get("status") in ["PENDING", "IN_PROGRESS"]:
            service_obj.file_manager.switch_task_directory(task["id"])
