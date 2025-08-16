"""
测试MCP服务自动session恢复功能
"""
import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import tempfile
import os

from src.service import MCPService
from src.session import SessionManager
from src.file_manager import FileManager


class TestAutoSessionRestore:
    """测试自动session恢复功能"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作空间"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            yield temp_dir, supervisor_dir

    @pytest.fixture
    def mock_project_info_with_token(self, temp_workspace):
        """模拟包含用户token的project_info.json"""
        temp_dir, supervisor_dir = temp_workspace
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
        
        return temp_dir, project_info

    @pytest.fixture
    def mock_project_info_without_token(self, temp_workspace):
        """模拟不包含用户token的project_info.json"""
        temp_dir, supervisor_dir = temp_workspace
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project"
        }
        
        project_info_file = supervisor_dir / "project_info.json"
        with open(project_info_file, 'w', encoding='utf-8') as f:
            json.dump(project_info, f)
        
        return temp_dir, project_info

    @pytest.mark.asyncio
    async def test_auto_restore_session_with_valid_token(self, mock_project_info_with_token):
        """测试：当本地有有效token时，自动恢复session"""
        temp_dir, project_info = mock_project_info_with_token
        
        # Mock API验证请求，返回成功
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api = AsyncMock()
            mock_api.request = AsyncMock(return_value={'success': True})
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
            mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # 切换到临时工作目录
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # 创建MCPService实例，此时应该自动恢复session
                service = MCPService()
                
                # 调用我们即将实现的方法（这里先手动调用进行测试）
                await service._auto_restore_session()
                
                # 验证session是否已经恢复
                assert service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id == "user123"
                assert service.session_manager.current_user_token == "valid-token-123"
                
                # 验证API调用被正确执行
                mock_api.request.assert_called_once_with(
                    'GET',
                    'auth/users/',
                    headers={'Authorization': 'Token valid-token-123'}
                )
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_with_invalid_token(self, mock_project_info_with_token):
        """测试：当本地token无效时，不恢复session"""
        temp_dir, project_info = mock_project_info_with_token
        
        # Mock API验证请求，返回失败
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api = AsyncMock()
            mock_api.request = AsyncMock(return_value={'success': False})
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
            mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证session没有被恢复
                assert not service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id is None
                assert service.session_manager.current_user_token is None
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_without_token(self, mock_project_info_without_token):
        """测试：当本地没有token时，不恢复session"""
        temp_dir, project_info = mock_project_info_without_token
        
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            service = MCPService()
            await service._auto_restore_session()
            
            # 验证session没有被恢复
            assert not service.session_manager.is_authenticated()
            assert service.session_manager.current_user_id is None
            assert service.session_manager.current_user_token is None
            
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_no_project_info(self):
        """测试：当没有project_info.json时，不恢复session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证session没有被恢复
                assert not service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id is None
                assert service.session_manager.current_user_token is None
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_api_error(self, mock_project_info_with_token):
        """测试：当API调用出错时，不恢复session"""
        temp_dir, project_info = mock_project_info_with_token
        
        # Mock API验证请求，抛出异常
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api_client.side_effect = Exception("API connection failed")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证session没有被恢复
                assert not service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id is None
                assert service.session_manager.current_user_token is None
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_on_first_auth_required_call(self, mock_project_info_with_token):
        """测试：验证在第一次需要认证的调用时自动恢复session"""
        temp_dir, project_info = mock_project_info_with_token
        
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api = AsyncMock()
            mock_api.request = AsyncMock(return_value={'success': True})
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
            mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # 创建MCPService
                service = MCPService()
                
                # 验证session还未恢复
                assert not service.session_manager.is_authenticated()
                assert not service._session_restore_attempted
                
                # 调用_ensure_session_restored()，应该触发session恢复
                await service._ensure_session_restored()
                
                # 验证session已经恢复
                assert service.session_manager.is_authenticated()
                assert service._session_restore_attempted
                assert service.session_manager.current_user_token == "valid-token-123"
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_project_context_without_token(self):
        """测试：即使没有token，也恢复项目上下文信息"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建只包含项目信息（无token）的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "test-project-456",
                "project_name": "Test Project Name",
                "current_task_group_id": "task-group-789",
                "description": "A test project"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证项目上下文已恢复
                assert service.get_current_project_id() == "test-project-456"
                assert service.get_current_project_name() == "Test Project Name"
                assert service.get_current_task_group_id() == "task-group-789"
                assert service.has_project_context()
                
                # 验证session没有恢复（因为没有token）
                assert not service.session_manager.is_authenticated()
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_both_session_and_project_context(self):
        """测试：同时恢复session和项目上下文"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含完整信息的project_info.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "test-project-123",
                "project_name": "Complete Project",
                "current_task_group_id": "tg-456",
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
                
                # Mock API验证请求，返回成功
                with patch('src.service.get_api_client') as mock_api_client:
                    mock_api = AsyncMock()
                    mock_api.request = AsyncMock(return_value={'success': True})
                    mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
                    mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    service = MCPService()
                    await service._auto_restore_session()
                    
                    # 验证session已恢复
                    assert service.session_manager.is_authenticated()
                    assert service.session_manager.current_user_id == "user123"
                    assert service.session_manager.current_user_token == "valid-token-123"
                    
                    # 验证项目上下文已恢复
                    assert service.get_current_project_id() == "test-project-123"
                    assert service.get_current_project_name() == "Complete Project"
                    assert service.get_current_task_group_id() == "tg-456"
                    assert service.has_project_context()
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_project_context_helper_methods(self):
        """测试：项目上下文辅助方法"""
        with tempfile.TemporaryDirectory() as temp_dir:
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "helper-test-123",
                "project_name": "Helper Test Project",
                "current_task_group_id": "helper-tg-456"
            }
            
            project_info_file = supervisor_dir / "project_info.json"
            with open(project_info_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                
                # 恢复前
                assert not service.has_project_context()
                assert service.get_current_project_id() is None
                assert service.get_current_project_name() is None
                assert service.get_current_task_group_id() is None
                
                # 恢复后
                await service._auto_restore_session()
                
                assert service.has_project_context()
                assert service.get_current_project_id() == "helper-test-123"
                assert service.get_current_project_name() == "Helper Test Project"
                assert service.get_current_task_group_id() == "helper-tg-456"
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auth_header_format_mismatch(self, mock_project_info_with_token):
        """测试：验证当前代码使用错误的认证头格式（Bearer vs Token）"""
        temp_dir, project_info = mock_project_info_with_token
        
        # Mock API验证请求，验证使用了错误的Bearer格式
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api = AsyncMock()
            mock_api.request = AsyncMock(return_value={'success': True})
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_api)
            mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证API调用应该使用Token格式而不是Bearer格式
                mock_api.request.assert_called_once_with(
                    'GET',
                    'auth/users/',
                    headers={'Authorization': 'Token valid-token-123'}  # 期望的正确格式
                )
                
            finally:
                os.chdir(original_cwd)