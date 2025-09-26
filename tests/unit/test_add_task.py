"""
测试 add_task 工具
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil

from service import MCPService
from file_manager import FileManager


class TestAddTask:
    """测试 add_task 方法"""

    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path)

    @pytest.fixture
    def file_manager(self, temp_dir):
        return FileManager(base_path=str(temp_dir))

    @pytest.fixture
    def mcp_service(self, file_manager):
        service = MCPService()
        service.file_manager = file_manager
        # Mock session manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service.session_manager.get_headers.return_value = {"Authorization": "Token test-token"}
        service._session_restore_attempted = True
        # 设置项目上下文
        service.session_manager.current_project_id = "test-project-123"
        service.session_manager.current_project_name = "Test Project"
        service.session_manager.get_current_project_id.return_value = "test-project-123"
        service.session_manager.get_current_project_name.return_value = "Test Project"
        service.session_manager.has_project_context.return_value = True
        # 初始化本地项目结构
        file_manager.create_supervisor_directory()
        file_manager.save_project_info({
            "project_id": "test-project-123",
            "project_name": "Test Project"
        })
        return service

    @pytest.mark.asyncio
    async def test_add_task_success(self, mcp_service):
        """成功创建任务组，返回task_id并附带instructions"""
        mock_api_response = {
            "status": "success",
            "data": {
                "id": "tg-001",
                "title": "visualIdentity"
            },
            "message": "任务组已创建"
        }

        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client

            result = await mcp_service.add_task(
                title="visualIdentity",
                goal="完成品牌视觉识别系统设计，定义核心视觉元素和应用规范",
                sop_step_identifier="visualIdentity",
            )

        assert result["status"] == "success"
        assert result["task_id"] == "tg-001"
        assert "instructions" in result
        assert len(result["instructions"]) > 0

    @pytest.mark.asyncio
    async def test_add_task_error_transparent(self, mcp_service):
        """后端错误时应透传错误码与消息"""
        mock_api_response = {
            "status": "error",
            "error_code": "SOP_STEP_INVALID",
            "message": "无效的步骤"
        }

        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client

            result = await mcp_service.add_task(
                title="visualIdentity",
                goal="完成品牌视觉识别系统设计，定义核心视觉元素和应用规范",
                sop_step_identifier="invalidStep",
            )

        assert result["status"] == "error"
        assert result["error_code"] == "SOP_STEP_INVALID"
        assert result["message"] == "无效的步骤"

