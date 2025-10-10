"""
认证与会话相关逻辑的独立模块。

包含：
- validate_local_token_with_file_manager
- validate_local_token
- login
- logout
- login_with_project

说明：为了兼容测试用例对 `service.get_api_client` 的打桩，这里所有外部 API 调用
均通过 `service.get_api_client()` 获取客户端。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import service  # 使用包级 get_api_client，便于测试 patch('service.get_api_client')
from .mcp_service import SessionManager, FileManager  # 类型/构造使用


async def validate_local_token_with_file_manager(
    service_obj, username: str, file_manager: FileManager
) -> Optional[Dict[str, Any]]:
    """使用指定 FileManager 验证本地保存的 token 是否有效。"""
    try:
        user_info = file_manager.read_user_info()
        if not all(k in user_info for k in ["user_id", "username", "access_token"]):
            return None
        if user_info["username"] != username:
            return None

        async with service.get_api_client() as api:
            headers = {"Authorization": f"Token {user_info['access_token']}"}
            response = await api.request("GET", "auth/validate/", headers=headers)

        if response.get("success"):
            return user_info
        return None

    except FileNotFoundError:
        return None
    except Exception:
        return None


async def validate_local_token(service_obj, username: str) -> Optional[Dict[str, Any]]:
    """验证当前 service 的 FileManager 中本地 token 是否有效。"""
    try:
        user_info = service_obj.file_manager.read_user_info()
        if not all(k in user_info for k in ["user_id", "username", "access_token"]):
            return None
        if user_info["username"] != username:
            return None

        async with service.get_api_client() as api:
            headers = {"Authorization": f"Token {user_info['access_token']}"}
            response = await api.request("GET", "auth/validate/", headers=headers)

        if response.get("success"):
            return user_info
        return None

    except FileNotFoundError:
        return None
    except Exception:
        return None


async def login(
    service_obj, username: str, password: str, working_directory: str
) -> Dict[str, Any]:
    """用户登录：强制走远端登录，拿到 token 后刷新 service 的 FileManager/SessionManager。"""
    local_file_manager = FileManager(base_path=working_directory)
    try:
        async with service.get_api_client() as api:
            response = await api.request(
                "POST", "auth/login/", json={"username": username, "password": password}
            )

        if response.get("success"):
            user_data = response["data"]
            service_obj.file_manager = local_file_manager
            service_obj.session_manager = SessionManager(service_obj.file_manager)
            service_obj.session_manager.login(
                user_data["user_id"], user_data["access_token"], user_data["username"]
            )

            if service_obj.file_manager.has_project_info():
                project_info = service_obj.file_manager.read_project_info()
                project_info["project_path"] = working_directory
                service_obj.file_manager.save_project_info(project_info)

            return {"success": True, "user_id": user_data["user_id"], "username": user_data["username"]}

        return {
            "success": False,
            "error_code": response.get("error_code", "AUTH_001"),
            "message": response.get("message", "登录失败"),
        }

    except Exception as e:  # noqa: BLE001 保持一致
        return {"success": False, "error_code": "NETWORK_ERROR", "message": f"网络请求失败: {str(e)}"}


async def logout(service_obj) -> Dict[str, Any]:
    """用户登出：后端登出即使失败，也清除本地会话。"""
    if not service_obj.session_manager.is_authenticated():
        return {"success": True, "message": "用户未登录"}

    try:
        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            await api.request("POST", "auth/logout/")
        service_obj.session_manager.logout()
        return {"success": True, "message": "登出成功"}

    except Exception:
        service_obj.session_manager.logout()
        return {"success": True, "message": "登出成功（本地会话已清除）"}


async def login_with_project(
    service_obj,
    username: str,
    password: str,
    project_id: str,
    working_directory: Optional[str] = None,
) -> Dict[str, Any]:
    """一站式登录并初始化项目工作区（委托 MCPService.init 完成初始化）。"""
    if not working_directory:
        from pathlib import Path

        working_directory = str(Path.cwd())

    # 必须调用实例方法，保持测试对 service.login 的打桩生效
    login_result = await service_obj.login(username, password, working_directory)
    if not login_result.get("success"):
        return login_result

    try:
        init_result = await service_obj.init(project_id=project_id, working_directory=working_directory)
        if init_result.get("status") == "error":
            return {
                "success": False,
                "error_code": "INIT_001",
                "message": f"登录成功但项目初始化失败: {init_result.get('message', '未知错误')}",
                "user_id": login_result.get("user_id"),
                "username": login_result.get("username"),
            }

        result: Dict[str, Any] = {
            "success": True,
            "user_id": login_result.get("user_id"),
            "username": login_result.get("username"),
            "project": {
                "project_id": init_result["data"]["project_id"],
                "project_name": init_result["data"]["project_name"],
                "templates_downloaded": init_result["data"].get("templates_downloaded", 0),
                "scenario": init_result["data"].get("scenario", "existing_project"),
            },
            "message": f"登录成功并初始化项目 {init_result['data']['project_name']}",
        }

        # 强同步项目信息/当前阶段
        try:
            async with service.get_api_client() as api:
                api.headers.update(service_obj.session_manager.get_headers())
                info_resp = await api.request("GET", f"projects/{project_id}/info/")

            if isinstance(info_resp, dict) and info_resp.get("project_id"):
                project_info_local = service_obj.file_manager.read_project_info()
                project_info_local.update(
                    {
                        "project_id": info_resp.get("project_id"),
                        "project_name": info_resp.get("project_name") or info_resp.get("name", ""),
                        "description": info_resp.get("description", ""),
                        "created_at": info_resp.get("created_at", ""),
                    }
                )

                if "in_progress_task" in info_resp:
                    project_info_local["in_progress_task"] = info_resp.get("in_progress_task")
                if "suspended_tasks" in info_resp:
                    project_info_local["suspended_tasks"] = info_resp.get("suspended_tasks") or []

                service_obj.file_manager.save_project_info(project_info_local)

                in_prog = project_info_local.get("in_progress_task") or {}
                current_phase = (in_prog or {}).get("current_task_phase") or {}
                phase_id = current_phase.get("id")
                if phase_id:
                    try:
                        async with service.get_api_client() as api2:
                            api2.headers.update(service_obj.session_manager.get_headers())
                            phase_detail = await api2.request("GET", f"task-phases/{phase_id}/")

                        async with service.get_api_client() as api3:
                            api3.headers.update(service_obj.session_manager.get_headers())
                            ctx = await api3.request(
                                "GET", f"task-phases/{phase_id}/context/", params={"format": "markdown"}
                            )

                        task_phase_for_strict = {
                            "id": phase_id,
                            "title": (phase_detail or {}).get("title") or current_phase.get("title"),
                            "type": (phase_detail or {}).get("type") or current_phase.get("type"),
                            "status": (phase_detail or {}).get("status") or current_phase.get("status"),
                            "task_id": (phase_detail or {}).get("task", {}).get("id")
                            or current_phase.get("task_id")
                            or in_prog.get("id"),
                            "order": (phase_detail or {}).get("order"),
                            "instruction_markdown": (ctx or {}).get("phase_markdown")
                            or (ctx or {}).get("context_markdown")
                            or "",
                            "task_markdown": (ctx or {}).get("task_markdown"),
                        }

                        await service_obj._save_phase_strict(
                            task_phase_for_strict, ctx if isinstance(ctx, dict) else {}
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            instructions = await service_obj._get_pending_tasks_instructions()
            if instructions:
                result["instructions"] = instructions
        except Exception:
            pass

        return result

    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error_code": "INIT_002",
            "message": f"登录成功但项目初始化出错: {str(e)}",
            "user_id": login_result.get("user_id"),
            "username": login_result.get("username"),
        }
