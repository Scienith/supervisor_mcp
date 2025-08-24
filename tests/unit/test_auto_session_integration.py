"""
测试自动session恢复的集成场景
"""
import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

from src.service import MCPService


class TestAutoSessionIntegration:
    """测试自动session恢复的集成场景"""

    @pytest.mark.asyncio
    async def test_next_task_with_auto_restored_session(self):
        """测试：调用next任务时自动恢复session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建分离的用户信息和项目信息文件
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            # 用户信息
            user_info = {
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            # 项目信息
            project_info = {
                "project_id": "test-project-123",
                "project_name": "Test Project"
            }
            
            user_file = supervisor_dir / "user.json"
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_info, f)
                
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock API调用for next task
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    mock_api.request = AsyncMock(return_value={'status': 'no_available_tasks'})
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    # 创建MCPService（SessionManager会自动恢复会话）
                    service = MCPService()
                    
                    # 验证session已在初始化时自动恢复
                    assert service.session_manager.is_authenticated()
                    assert service.session_manager.current_user_id == "user123"
                    assert service.session_manager.current_user_token == "valid-token-123"
                    
                    # 调用next
                    result = await service.next()
                    
                    # 验证项目上下文已自动恢复
                    assert service.get_current_project_id() == "test-project-123"
                    assert service.get_current_project_name() == "Test Project"
                    assert service.has_project_context()
                    
                    # 验证API调用（只有一次next任务调用，没有token验证调用）
                    assert mock_api.request.call_count == 1
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_init_project_with_auto_restored_session(self):
        """测试：初始化项目时自动恢复session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建分离的用户信息和项目信息文件
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            # 用户信息
            user_info = {
                "user_id": "user456",
                "username": "existinguser",
                "access_token": "existing-token-456"
            }
            
            # 项目信息
            project_info = {
                "project_id": "existing-project-456",
                "project_name": "Existing Project"
            }
            
            user_file = supervisor_dir / "user.json"
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_info, f)
                
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # 创建MCPService（SessionManager会自动恢复会话）
                service = MCPService()
                
                # 验证session已在初始化时自动恢复
                assert service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id == "user456"
                assert service.session_manager.current_user_token == "existing-token-456"
                
                # 验证项目上下文在_auto_restore_session调用后恢复
                await service._auto_restore_session()
                assert service.get_current_project_id() == "existing-project-456"
                assert service.get_current_project_name() == "Existing Project"
                assert service.has_project_context()
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_multiple_calls_only_restore_once(self):
        """测试：多次调用只恢复一次session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建分离的用户信息和项目信息文件
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            # 用户信息
            user_info = {
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            # 项目信息
            project_info = {
                "project_id": "test-project-123"
            }
            
            user_file = supervisor_dir / "user.json"
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_info, f)
                
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                
                # 验证SessionManager已在初始化时自动恢复
                assert service.session_manager.is_authenticated()
                
                # 验证初始状态
                assert not service._session_restore_attempted
                
                # 第一次调用_ensure_session_restored
                await service._ensure_session_restored()
                assert service._session_restore_attempted
                
                # 第二次调用_ensure_session_restored
                await service._ensure_session_restored()
                
                # 验证标记仍然为True（幂等性）
                assert service._session_restore_attempted
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_project_context_available_immediately_after_restore(self):
        """测试：恢复后项目上下文立即可用"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建分离的用户信息和项目信息文件
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            # 用户信息
            user_info = {
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            # 项目信息
            project_info = {
                "project_id": "context-test-123",
                "project_name": "Context Test Project",
                "in_progress_task_group": {
                "id": "tg-789",
                "title": "测试任务组",
                "status": "IN_PROGRESS"
            }
            }
            
            user_file = supervisor_dir / "user.json"
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_info, f)
                
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                
                # 验证SessionManager已在初始化时自动恢复
                assert service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id == "user123"
                assert service.session_manager.current_user_token == "valid-token-123"
                
                # SessionManager现在在初始化时就自动恢复了项目上下文
                # 直接验证项目上下文已恢复
                assert service.has_project_context()
                assert service.get_current_project_id() == "context-test-123"
                assert service.get_current_project_name() == "Context Test Project"
                assert service.get_current_task_group_id() == "tg-789"
                    
            finally:
                os.chdir(original_cwd)