import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from service.mcp_service import MCPService


@pytest.mark.asyncio
async def test_login_success(tmp_path: Path):
    svc = MCPService()
    # mock API client login success
    with patch("service.get_api_client") as mock_get_client:
        mock_api = AsyncMock()
        mock_api.request = AsyncMock(
            return_value={
                "success": True,
                "data": {"user_id": "u1", "access_token": "tok", "username": "user"},
            }
        )
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        res = await svc.login("user", "pass", str(tmp_path))
        assert res["success"] is True
        # 会话应被设置
        assert svc.session_manager.is_authenticated()


@pytest.mark.asyncio
async def test_logout_success(tmp_path: Path):
    svc = MCPService()
    # 先设置登录状态
    svc.session_manager.login("u1", "tok", "user")
    with patch("service.get_api_client") as mock_get_client:
        mock_api = AsyncMock()
        mock_api.request = AsyncMock(return_value={"success": True})
        mock_api.headers = {}
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        res = await svc.logout()
        assert res["success"] is True
        assert not svc.session_manager.is_authenticated()


@pytest.mark.asyncio
async def test_login_with_project_success(tmp_path: Path):
    svc = MCPService()

    # 打桩实例方法 login 与 init
    with patch.object(svc, "login", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = {"success": True, "user_id": "u1", "username": "user"}
        with patch.object(svc, "init", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = {
                "status": "success",
                "data": {"project_id": "p1", "project_name": "proj", "templates_downloaded": 0},
            }

            # projects/{id}/info/ 调用
            with patch("service.get_api_client") as mock_get_client:
                mock_api = AsyncMock()
                mock_api.headers = {}
                mock_api.request = AsyncMock(
                    return_value={
                        "project_id": "p1",
                        "project_name": "proj",
                        "in_progress_task": None,
                        "suspended_tasks": [],
                    }
                )
                mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

                res = await svc.login_with_project("user", "pass", "p1", str(tmp_path))
                assert res["success"] is True
                assert res["project"]["project_id"] == "p1"


@pytest.mark.asyncio
async def test_validate_local_token_with_file_manager(tmp_path: Path):
    svc = MCPService()
    # 构造 .supervisor/user.json
    sup_dir = tmp_path / ".supervisor"
    sup_dir.mkdir(parents=True, exist_ok=True)
    user_file = sup_dir / "user.json"
    user_info = {"user_id": "u1", "username": "user", "access_token": "tok"}
    user_file.write_text(json.dumps(user_info), encoding="utf-8")

    # 使用指定 base_path 的 FileManager 读取
    with patch("service.get_api_client") as mock_get_client:
        mock_api = AsyncMock()
        mock_api.request = AsyncMock(return_value={"success": True})
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # 直接调用私有方法以复用 service 层的封装
        from file_manager import FileManager

        fm = FileManager(base_path=str(tmp_path))
        result = await svc._validate_local_token_with_file_manager("user", fm)
        assert result is not None
        assert result["username"] == "user"
