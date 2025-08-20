#!/usr/bin/env python3
"""
完全修复 test_task_groups_cleanup.py 文件
因为我们已经移除了 task_groups 结构，这些测试需要重新设计
"""

import os

# 由于 task_groups 结构已经完全移除，这些测试实际上已经不再相关
# 我们可以简化这些测试或者删除它们

new_content = '''"""
测试任务组清理逻辑
"""
import pytest
import tempfile
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.service import MCPService
from src.session import SessionManager
from src.file_manager import FileManager


class TestTaskGroupsCleanup:
    """测试任务组清理功能"""

    @pytest.fixture
    def file_manager(self):
        """创建临时文件管理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 切换到临时目录
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
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
        return service

    def setup_project_with_active_task_group(self, file_manager):
        """设置有活跃任务组的项目"""
        file_manager.create_supervisor_directory()
        
        # 创建项目信息，包含当前进行中的任务组
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "in_progress_task_group": {
                "id": "tg-active",
                "title": "测试任务组",
                "status": "IN_PROGRESS",
                "current_task": {
                    "id": "task-001",
                    "title": "当前任务",
                    "type": "IMPLEMENTING",
                    "task_group_id": "tg-active"
                }
            },
            "suspended_task_groups": []
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_group_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_implementing_instructions.md").write_text("Test task content")

    @pytest.mark.asyncio
    async def test_cancel_task_group_cleans_active_task_group(self, mcp_service, file_manager):
        """测试cancel_task_group成功时清理当前活跃任务组"""
        # Setup
        self.setup_project_with_active_task_group(file_manager)
        
        # 验证初始状态：有活跃任务组
        initial_project_info = file_manager.read_project_info()
        assert initial_project_info.get("in_progress_task_group") is not None
        assert initial_project_info["in_progress_task_group"]["id"] == "tg-active"
        
        # Mock成功的cancel响应
        mock_api_response = {
            "status": "success",
            "message": "Task group cancelled successfully"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.cancel_task_group("test-project-123", "tg-active")
            
            # Verify API调用成功
            assert result["status"] == "success"
            
            # 验证活跃任务组被清理
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info.get("in_progress_task_group") is None

    @pytest.mark.asyncio
    async def test_cancel_task_group_api_failure_no_cleanup(self, mcp_service, file_manager):
        """测试cancel_task_group API失败时不清理任务组"""
        # Setup
        self.setup_project_with_active_task_group(file_manager)
        
        # Mock失败的API响应
        mock_api_response = {
            "status": "error",
            "message": "API failure"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.cancel_task_group("test-project-123", "tg-active")
            
            # Verify API调用失败
            assert result["status"] == "error"
            
            # 验证任务组没有被清理（因为API失败）
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info.get("in_progress_task_group") is not None
            assert updated_project_info["in_progress_task_group"]["id"] == "tg-active"
'''

def main():
    """写入新的测试文件"""
    file_path = "tests/unit/test_task_groups_cleanup.py"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Rewrote: {file_path}")

if __name__ == "__main__":
    main()