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
            # 创建.supervisor目录和project.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            yield temp_dir, supervisor_dir

    @pytest.fixture
    def mock_project_info_with_token(self, temp_workspace):
        """模拟包含用户token的user.json和project.json"""
        temp_dir, supervisor_dir = temp_workspace
        
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
        
        # 分别保存到user.json和project.json
        user_file = supervisor_dir / "user.json"
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_info, f)
            
        project_file = supervisor_dir / "project.json"
        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(project_info, f)
        
        # 返回合并的信息以保持向后兼容测试代码
        combined_info = {**user_info, **project_info}
        return temp_dir, combined_info

    @pytest.fixture
    def mock_project_info_without_token(self, temp_workspace):
        """模拟只有项目信息没有用户token的情况"""
        temp_dir, supervisor_dir = temp_workspace
        
        # 只有项目信息，没有用户信息
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project"
        }
        
        project_file = supervisor_dir / "project.json"
        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(project_info, f)
        
        return temp_dir, project_info

    @pytest.mark.asyncio
    async def test_auto_restore_session_with_valid_token(self, mock_project_info_with_token):
        """测试：当本地有有效token时，自动恢复session和项目上下文"""
        temp_dir, project_info = mock_project_info_with_token
        
        # 切换到临时工作目录
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # 创建MCPService实例，SessionManager会自动从user.json恢复会话
            service = MCPService()
            
            # 验证session是否已经恢复（SessionManager自动恢复）
            assert service.session_manager.is_authenticated()
            assert service.session_manager.current_user_id == "user123"
            assert service.session_manager.current_user_token == "valid-token-123"
            
            # 调用自动恢复方法恢复项目上下文
            await service._auto_restore_session()
            
            # 验证项目上下文是否已经恢复
            assert service.session_manager.current_project_id == "test-project-123"
            assert service.session_manager.current_project_name == "Test Project"
                
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_with_invalid_token(self, mock_project_info_with_token):
        """测试：即使token可能无效，会话仍会从本地恢复（验证在后续API调用中处理）"""
        temp_dir, project_info = mock_project_info_with_token
        
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # SessionManager会从本地文件自动恢复会话，不进行API验证
            service = MCPService()
            await service._auto_restore_session()
            
            # 验证session已从本地恢复（即使token可能无效）
            assert service.session_manager.is_authenticated()
            assert service.session_manager.current_user_id == "user123"
            assert service.session_manager.current_user_token == "valid-token-123"
            # token有效性会在后续API调用时验证
            
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
        """测试：当没有project.json时，不恢复session"""
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
        """测试：本地会话恢复不依赖API，即使API不可用也能正常恢复"""
        temp_dir, project_info = mock_project_info_with_token
        
        # Mock API调用抛出异常（不应影响本地恢复）
        with patch('src.service.get_api_client') as mock_api_client:
            mock_api_client.side_effect = Exception("API connection failed")
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                await service._auto_restore_session()
                
                # 验证session仍然从本地恢复（不依赖API）
                assert service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id == "user123"
                assert service.session_manager.current_user_token == "valid-token-123"
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_session_on_first_auth_required_call(self, mock_project_info_with_token):
        """测试：验证session恢复的幂等性和_ensure_session_restored方法的行为"""
        temp_dir, project_info = mock_project_info_with_token
        
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # 创建MCPService，SessionManager已经自动恢复会话
            service = MCPService()
            
            # 验证session已经在初始化时恢复
            assert service.session_manager.is_authenticated()
            assert service.session_manager.current_user_token == "valid-token-123"
            
            # 验证首次标记状态
            assert not service._session_restore_attempted
            
            # 调用_ensure_session_restored()，应该标记已尝试恢复
            await service._ensure_session_restored()
            
            # 验证标记已设置，但session状态不变（幂等性）
            assert service._session_restore_attempted
            assert service.session_manager.is_authenticated()
            assert service.session_manager.current_user_token == "valid-token-123"
                
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_restore_project_context_without_token(self):
        """测试：即使没有token，也恢复项目上下文信息"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建只包含项目信息（无token）的project.json
            supervisor_dir = Path(temp_dir) / ".supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            
            project_info = {
                "project_id": "test-project-456",
                "project_name": "Test Project Name",
                "in_progress_task_group": {
                "id": "task-group-789",
                "title": "测试任务组",
                "status": "IN_PROGRESS"
            },
                "description": "A test project"
            }
            
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
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
                "project_name": "Complete Project",
                "in_progress_task_group": {
                "id": "tg-456",
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
                await service._auto_restore_session()
                
                # 验证session已恢复（SessionManager自动恢复）
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
                "in_progress_task_group": {
                "id": "helper-tg-456",
                "title": "测试任务组",
                "status": "IN_PROGRESS"
            }
            }
            
            project_file = supervisor_dir / "project.json"
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_info, f)
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                service = MCPService()
                
                # SessionManager现在在初始化时就自动恢复了项目上下文
                # 所以直接验证恢复后的状态
                assert service.has_project_context()
                assert service.get_current_project_id() == "helper-test-123"
                assert service.get_current_project_name() == "Helper Test Project"
                assert service.get_current_task_group_id() == "helper-tg-456"
                
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auth_header_format_mismatch(self, mock_project_info_with_token):
        """测试：验证认证头格式正确（Token而不是Bearer）"""
        temp_dir, project_info = mock_project_info_with_token
        
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            service = MCPService()
            await service._auto_restore_session()
            
            # 验证session已从本地恢复
            assert service.session_manager.is_authenticated()
            assert service.session_manager.current_user_token == "valid-token-123"
            
            # 验证认证头格式正确：使用Token而不是Bearer
            headers = service.session_manager.get_headers()
            assert 'Authorization' in headers
            assert headers['Authorization'] == 'Token valid-token-123'  # 正确的格式
            assert not headers['Authorization'].startswith('Bearer ')  # 不应该是Bearer格式
            
        finally:
            os.chdir(original_cwd)