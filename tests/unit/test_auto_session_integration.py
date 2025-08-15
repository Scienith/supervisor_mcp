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
            # 创建包含token的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "test-project-123",
                "project_name": "Test Project",
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock API调用
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    # Mock token验证请求
                    mock_api.request = AsyncMock(side_effect=[
                        {'success': True},  # token验证成功
                        {'status': 'no_available_tasks'}  # next任务调用
                    ])
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    # 创建MCPService
                    service = MCPService()
                    
                    # 验证初始状态：未认证
                    assert not service.session_manager.is_authenticated()
                    
                    # 调用next，应该自动恢复session并执行
                    result = await service.next("test-project-123")
                    
                    # 验证session已自动恢复
                    assert service.session_manager.is_authenticated()
                    assert service.session_manager.current_user_id == "user123"
                    assert service.session_manager.current_user_token == "valid-token-123"
                    
                    # 验证项目上下文已自动恢复
                    assert service.get_current_project_id() == "test-project-123"
                    assert service.get_current_project_name() == "Test Project"
                    assert service.has_project_context()
                    
                    # 验证API调用
                    assert mock_api.request.call_count == 2
                    # 第一次调用：token验证
                    mock_api.request.assert_any_call(
                        'GET',
                        'auth/validate/',
                        headers={'Authorization': 'Bearer valid-token-123'}
                    )
                    # 第二次调用：获取下一个任务
                    mock_api.request.assert_any_call(
                        'GET',
                        'tasks/next/',
                        params={'project_id': 'test-project-123'}
                    )
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_init_project_with_auto_restored_session(self):
        """测试：初始化项目时自动恢复session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含token的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "existing-project-456",
                "project_name": "Existing Project",
                "user_id": "user456",
                "username": "existinguser",
                "access_token": "existing-token-456"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock API调用
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    mock_api.request = AsyncMock(side_effect=[
                        {'success': True},  # token验证成功
                        {  # 项目初始化响应
                            'success': True,
                            'project_id': 'new-project-789',
                            'project_name': 'New Test Project',
                            'created_at': '2024-01-01T00:00:00Z',
                            'sop_steps_count': 10,
                            'initial_task_groups': 2,
                            'initialization_data': {'templates': []}
                        }
                    ])
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    # 创建MCPService
                    service = MCPService()
                    
                    # 验证初始状态：未认证
                    assert not service.session_manager.is_authenticated()
                    
                    # 调用init创建新项目，应该自动恢复session并执行
                    result = await service.init(
                        project_name="New Test Project",
                        description="A test project"
                    )
                    
                    # 验证session已自动恢复
                    assert service.session_manager.is_authenticated()
                    assert service.session_manager.current_user_id == "user456"
                    assert service.session_manager.current_user_token == "existing-token-456"
                    
                    # 验证项目上下文已恢复（恢复的是原来的项目上下文）
                    assert service.get_current_project_id() == "existing-project-456"
                    assert service.get_current_project_name() == "Existing Project"
                    assert service.has_project_context()
                    
                    # 验证项目创建成功
                    assert result['status'] == 'success'
                    assert result['data']['project_id'] == 'new-project-789'
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_multiple_calls_only_restore_once(self):
        """测试：多次调用只恢复一次session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含token的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "test-project-123",
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    mock_api.request = AsyncMock(return_value={'success': True})
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    service = MCPService()
                    
                    # 第一次调用_ensure_session_restored
                    await service._ensure_session_restored()
                    assert service._session_restore_attempted
                    first_call_count = mock_api.request.call_count
                    
                    # 第二次调用_ensure_session_restored
                    await service._ensure_session_restored()
                    second_call_count = mock_api.request.call_count
                    
                    # 验证只进行了一次API调用（即只恢复了一次）
                    assert second_call_count == first_call_count
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_project_context_available_immediately_after_restore(self):
        """测试：恢复后项目上下文立即可用"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含项目信息的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "context-test-123",
                "project_name": "Context Test Project",
                "current_task_group_id": "tg-789",
                "user_id": "user123",
                "username": "testuser",
                "access_token": "valid-token-123"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    mock_api.request = AsyncMock(return_value={'success': True})
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    service = MCPService()
                    
                    # 在任何认证操作之前，项目上下文应该不可用
                    assert not service.has_project_context()
                    
                    # 调用_ensure_session_restored
                    await service._ensure_session_restored()
                    
                    # 验证项目上下文和session都已恢复
                    assert service.has_project_context()
                    assert service.get_current_project_id() == "context-test-123"
                    assert service.get_current_project_name() == "Context Test Project"
                    assert service.get_current_task_group_id() == "tg-789"
                    assert service.session_manager.is_authenticated()
                    
            finally:
                os.chdir(original_cwd)