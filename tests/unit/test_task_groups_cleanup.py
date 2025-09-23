"""
测试任务组清理逻辑
"""
import pytest
import tempfile
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from service import MCPService
from session import SessionManager
from file_manager import FileManager


class TestTasksCleanup:
    """测试任务组清理功能"""

    @pytest.fixture
    def file_manager(self):
        """创建临时文件管理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 切换到临时目录
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            # 清除PWD环境变量
            if "PWD" in os.environ:
                del os.environ["PWD"]
            try:
                yield FileManager(base_path=Path(temp_dir))
            finally:
                os.chdir(original_cwd)

    @pytest.fixture
    def mcp_service(self, file_manager):
        """创建MCP服务实例（已认证）"""
        service = MCPService()
        service.file_manager = file_manager
        
        # Mock session manager认证状态
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service.session_manager.get_headers.return_value = {'Authorization': 'Token test-token'}
        service.session_manager.current_user_id = "test-user"
        
        # 标记已恢复session
        service._session_restore_attempted = True
        # 设置项目上下文
        service.session_manager.current_project_id = "test-project-123"
        service.session_manager.current_project_name = "Test Project"
        # 设置方法返回值
        service.session_manager.get_current_project_id.return_value = "test-project-123"
        service.session_manager.get_current_project_name.return_value = "Test Project"
        service.session_manager.has_project_context.return_value = True
        return service

    def setup_project_with_active_task(self, file_manager):
        """设置有活跃任务组的项目"""
        file_manager.create_supervisor_directory()
        
        # 创建项目信息，包含当前进行中的任务组
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "in_progress_task": {
                "id": "tg-active",
                "title": "测试任务组",
                "status": "IN_PROGRESS",
                "current_task_phase": {
                    "id": "task-001",
                    "title": "当前任务",
                    "type": "IMPLEMENTING",
                    "task_id": "tg-active"
                }
            },
            "suspended_tasks": []
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_implementing_instructions.md").write_text("Test task content")

    @pytest.mark.asyncio
    async def test_cancel_task_cleans_active_task(self, mcp_service, file_manager):
        """测试cancel_task成功时清理当前活跃任务组"""
        # Setup
        self.setup_project_with_active_task(file_manager)
        
        # 验证初始状态：有活跃任务组
        initial_project_info = file_manager.read_project_info()
        assert initial_project_info.get("in_progress_task") is not None
        assert initial_project_info["in_progress_task"]["id"] == "tg-active"
        
        # Mock成功的cancel响应
        mock_api_response = {
            "status": "success",
            "message": "Task group cancelled successfully"
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.cancel_task("tg-active")
            
            # Verify API调用成功
            assert result["status"] == "success"
            
            # 验证活跃任务组被清理
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info.get("in_progress_task") is None

    @pytest.mark.asyncio
    async def test_cancel_task_api_failure_no_cleanup(self, mcp_service, file_manager):
        """测试cancel_task API失败时不清理任务组"""
        # Setup
        self.setup_project_with_active_task(file_manager)
        
        # Mock失败的API响应
        mock_api_response = {
            "status": "error",
            "message": "API failure"
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.cancel_task("tg-active")
            
            # Verify API调用失败
            assert result["status"] == "error"
            
            # 验证任务组没有被清理（因为API失败）
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info.get("in_progress_task") is not None
            assert updated_project_info["in_progress_task"]["id"] == "tg-active"
