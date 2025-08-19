"""
测试suspend -> start工作流程
验证用户必须先suspend当前任务组，才能start新任务组的完整流程
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil
from pathlib import Path
import json

from src.service import MCPService
from src.file_manager import FileManager


class TestSuspendStartWorkflow:
    """测试suspend -> start工作流程"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path)

    @pytest.fixture
    def file_manager(self, temp_dir):
        """创建FileManager实例"""
        return FileManager(base_path=str(temp_dir))

    @pytest.fixture
    def mcp_service(self, file_manager):
        """创建MCPService实例"""
        service = MCPService()
        service.file_manager = file_manager
        # Mock session manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service.session_manager.get_headers.return_value = {"Authorization": "Bearer test-token"}
        service._session_restore_attempted = True
        return service

    def setup_project_with_active_task_group(self, file_manager):
        """设置有活跃任务组的项目"""
        file_manager.create_supervisor_directory()
        
        # 创建项目信息，包含当前活跃的任务组
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "current_task_group_id": "tg-active",  # 模拟当前有活跃任务组
            "task_groups": {
                "tg-active": {
                    "current_task": {
                        "id": "task-001",
                        "title": "当前任务",
                        "type": "IMPLEMENTING"
                    }
                }
            }
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_group_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_implementing_instructions.md").write_text("Current task content")
        (current_dir / "task_data.json").write_text('{"test": "data"}')

    @pytest.mark.asyncio
    async def test_complete_suspend_start_workflow(self, mcp_service, file_manager):
        """测试完整的suspend -> start工作流程"""
        # Setup: 创建有活跃任务组的项目
        self.setup_project_with_active_task_group(file_manager)
        
        # 验证初始状态
        initial_project_info = file_manager.read_project_info()
        assert initial_project_info["current_task_group_id"] == "tg-active"
        
        # Step 1: Suspend 当前任务组
        suspend_mock_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-active",
                "title": "当前任务组",
                "previous_status": "IN_PROGRESS",
                "new_status": "SUSPENDED",
                "suspended_at": "2024-12-20T15:30:00Z"
            },
            "message": "任务组已成功暂存"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = suspend_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute suspend
            suspend_result = await mcp_service.suspend_task_group("test-project-123")
            
            # Verify suspend result
            assert suspend_result["status"] == "success"
            assert "任务组已成功暂存" in suspend_result["message"]
            
            # 验证suspend后current_task_group_id为None
            after_suspend_project_info = file_manager.read_project_info()
            assert after_suspend_project_info["current_task_group_id"] is None
            
            # 验证文件被暂存
            suspended_dir = file_manager.suspended_task_groups_dir / "task_group_tg-active"
            assert suspended_dir.exists()
            assert (suspended_dir / "01_implementing_instructions.md").exists()
        
        # Step 2: Start 新任务组
        start_mock_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-new",
                "title": "新任务组",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T16:00:00Z"
            },
            "message": "任务组已成功启动"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = start_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute start
            start_result = await mcp_service.start_task_group("test-project-123", "tg-new")
            
            # Verify start result
            assert start_result["status"] == "success"
            assert "任务组已成功启动" in start_result["message"]
            assert start_result["data"]["task_group_id"] == "tg-new"
            assert start_result["data"]["new_status"] == "IN_PROGRESS"
            
            # 验证start后current_task_group_id指向新任务组
            after_start_project_info = file_manager.read_project_info()
            assert after_start_project_info["current_task_group_id"] == "tg-new"
        
        # Step 3: 验证完整状态
        final_project_info = file_manager.read_project_info()
        
        # 应该有新的current_task_group_id
        assert final_project_info["current_task_group_id"] == "tg-new"
        
        # 旧任务组应该被暂存
        suspended_dir = file_manager.suspended_task_groups_dir / "task_group_tg-active"
        assert suspended_dir.exists()
        
        # 当前工作目录应该是空的或为新任务组准备的
        assert file_manager.current_task_group_dir.exists()

    @pytest.mark.asyncio
    async def test_cannot_start_when_another_task_group_active(self, mcp_service, file_manager):
        """测试当已有活跃任务组时，不能直接启动新任务组"""
        # Setup: 创建有活跃任务组的项目
        self.setup_project_with_active_task_group(file_manager)
        
        # 模拟后端返回冲突错误
        conflict_mock_response = {
            "status": "error",
            "error_code": "TASK_GROUP_CONFLICT",
            "message": "项目中已有IN_PROGRESS状态的任务组，请先暂存当前任务组"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = conflict_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # 尝试启动新任务组（应该失败）
            result = await mcp_service.start_task_group("test-project-123", "tg-new")
            
            # 验证返回错误
            assert result["status"] == "error"
            assert result["error_code"] == "TASK_GROUP_CONFLICT"
            assert "已有IN_PROGRESS状态的任务组" in result["message"]
            
            # 验证本地状态没有改变
            project_info = file_manager.read_project_info()
            assert project_info["current_task_group_id"] == "tg-active"  # 仍然是原来的

    @pytest.mark.asyncio
    async def test_start_when_no_active_task_group(self, mcp_service, file_manager):
        """测试当没有活跃任务组时，可以直接启动新任务组"""
        # Setup: 创建没有活跃任务组的项目
        file_manager.create_supervisor_directory()
        
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "current_task_group_id": None,  # 没有活跃任务组
            "task_groups": {}
        }
        file_manager.save_project_info(project_info)
        
        # Mock成功启动响应
        start_mock_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-first",
                "title": "第一个任务组",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T16:00:00Z"
            },
            "message": "任务组已成功启动"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = start_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute start
            result = await mcp_service.start_task_group("test-project-123", "tg-first")
            
            # Verify
            assert result["status"] == "success"
            assert result["data"]["task_group_id"] == "tg-first"
            
            # 验证current_task_group_id被正确设置
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info["current_task_group_id"] == "tg-first"