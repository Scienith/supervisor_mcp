"""
测试task_groups字段的清理逻辑
验证在任务组COMPLETED和CANCELLED时，本地缓存被正确清理
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil
from pathlib import Path
import json

from src.service import MCPService
from src.file_manager import FileManager


class TestTaskGroupsCleanup:
    """测试任务组缓存清理逻辑"""

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

    def setup_project_with_task_group_cache(self, file_manager):
        """设置有任务组缓存的项目"""
        file_manager.create_supervisor_directory()
        
        # 创建项目信息，包含任务组缓存
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "current_task_group_id": "tg-active",
            "task_groups": {
                "tg-active": {
                    "current_task": {
                        "id": "task-001",
                        "title": "当前任务",
                        "type": "IMPLEMENTING",
                        "task_group_id": "tg-active"
                    }
                },
                "tg-other": {
                    "current_task": {
                        "id": "task-002", 
                        "title": "其他任务组",
                        "type": "UNDERSTANDING",
                        "task_group_id": "tg-other"
                    }
                }
            }
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_group_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_implementing_instructions.md").write_text("Current task content")

    @pytest.mark.asyncio
    async def test_cancel_task_group_cleans_cache(self, mcp_service, file_manager):
        """测试cancel_task_group成功时清理task_groups缓存"""
        # Setup
        self.setup_project_with_task_group_cache(file_manager)
        
        # 验证初始状态：task_groups中有两个任务组
        initial_project_info = file_manager.read_project_info()
        assert "tg-active" in initial_project_info["task_groups"]
        assert "tg-other" in initial_project_info["task_groups"]
        
        # Mock成功的cancel响应
        cancel_mock_response = {
            "status": "success",
            "message": "任务组已成功取消",
            "data": {
                "task_group_id": "tg-active",
                "cancelled_at": "2024-12-20T15:30:00Z"
            }
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = cancel_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute cancel
            result = await mcp_service.cancel_task_group("test-project-123", "tg-active", "测试取消")
            
            # Verify API调用成功
            assert result["status"] == "success"
            
            # 验证task_groups缓存被清理
            updated_project_info = file_manager.read_project_info()
            assert "tg-active" not in updated_project_info["task_groups"]  # 被取消的任务组被清理
            assert "tg-other" in updated_project_info["task_groups"]       # 其他任务组保持不变
            assert updated_project_info["current_task_group_id"] is None  # 当前任务组ID被清理

    @pytest.mark.asyncio
    async def test_cancel_task_group_api_failure_no_cleanup(self, mcp_service, file_manager):
        """测试cancel_task_group API失败时不清理缓存"""
        # Setup
        self.setup_project_with_task_group_cache(file_manager)
        
        # Mock失败的cancel响应
        cancel_mock_response = {
            "status": "error",
            "message": "任务组取消失败"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = cancel_mock_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute cancel
            result = await mcp_service.cancel_task_group("test-project-123", "tg-active", "测试取消")
            
            # Verify API调用失败
            assert result["status"] == "error"
            
            # 验证task_groups缓存没有被清理
            updated_project_info = file_manager.read_project_info()
            assert "tg-active" in updated_project_info["task_groups"]    # 缓存保持不变
            assert "tg-other" in updated_project_info["task_groups"]

    @pytest.mark.asyncio
    async def test_report_validation_no_special_cleanup(self, mcp_service, file_manager):
        """测试report VALIDATION任务不会因为validation结果而特殊清理缓存"""
        # Setup
        self.setup_project_with_task_group_cache(file_manager)
        
        # Mock VALIDATION任务数据
        validation_task_data = {
            "id": "task-001",
            "title": "验收任务",
            "type": "VALIDATION",
            "task_group_id": "tg-active"
        }
        
        # Mock成功的report响应（没有task_group_status）
        report_mock_response = {
            "status": "success",
            "message": "任务结果提交成功",
            "data": {
                "task_id": "task-001",
                "status": "COMPLETED"
                # 注意：没有task_group_status字段
            }
        }
        
        with patch.object(file_manager, 'read_current_task_data', return_value=validation_task_data):
            with patch.object(file_manager, 'has_current_task', return_value=True):
                with patch('src.service.get_api_client') as mock_get_client:
                    mock_client = AsyncMock()
                    mock_client.request.return_value = report_mock_response
                    mock_get_client.return_value.__aenter__.return_value = mock_client
                    
                    # Execute report with validation passed
                    result = await mcp_service.report("task-001", {
                        "output": "验收完成",
                        "validation_result": {"passed": True}
                    })
                    
                    # Verify API调用成功
                    assert result["status"] == "success"
                    
                    # 验证task_groups缓存没有被清理（因为任务组没有完成）
                    updated_project_info = file_manager.read_project_info()
                    assert "tg-active" in updated_project_info["task_groups"]     # 保持不变
                    assert "tg-other" in updated_project_info["task_groups"]      # 保持不变

    @pytest.mark.asyncio
    async def test_report_task_group_completed_cleans_cache(self, mcp_service, file_manager):
        """测试report返回任务组COMPLETED状态时清理task_groups缓存"""
        # Setup
        self.setup_project_with_task_group_cache(file_manager)
        
        # Mock普通任务数据
        task_data = {
            "id": "task-001",
            "title": "实现任务",
            "type": "IMPLEMENTING", 
            "task_group_id": "tg-active"
        }
        
        # Mock返回任务组已完成的响应
        report_mock_response = {
            "status": "success",
            "message": "任务结果提交成功",
            "data": {
                "task_id": "task-001",
                "status": "COMPLETED",
                "task_group_status": "COMPLETED"  # 任务组已完成
            }
        }
        
        with patch.object(file_manager, 'read_current_task_data', return_value=task_data):
            with patch.object(file_manager, 'has_current_task', return_value=True):
                with patch('src.service.get_api_client') as mock_get_client:
                    mock_client = AsyncMock()
                    mock_client.request.return_value = report_mock_response
                    mock_get_client.return_value.__aenter__.return_value = mock_client
                    
                    # Execute report
                    result = await mcp_service.report("task-001", {
                        "output": "任务完成"
                    })
                    
                    # Verify API调用成功
                    assert result["status"] == "success"
                    
                    # 验证task_groups缓存被清理
                    updated_project_info = file_manager.read_project_info()
                    assert "tg-active" not in updated_project_info["task_groups"]  # 任务组完成，被清理
                    assert "tg-other" in updated_project_info["task_groups"]       # 其他任务组保持不变

