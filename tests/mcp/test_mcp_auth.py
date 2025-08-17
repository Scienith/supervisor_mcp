"""
MCP服务权限测试用例
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from service import MCPService


class TestMCPAuthentication:
    """MCP认证测试"""
    
    @pytest.fixture
    def mcp_service(self):
        """创建MCP服务实例用于测试"""
        # Mock FileManager 的文件读取，避免自动恢复会话
        with patch('file_manager.FileManager.read_user_info', side_effect=FileNotFoundError):
            with patch('file_manager.FileManager.read_project_info', side_effect=FileNotFoundError):
                service = MCPService()
                yield service
    
    @pytest.mark.asyncio
    async def test_login_success(self, mcp_service):
        """测试MCP登录成功"""
        # Mock get_api_client函数
        mock_api_client = AsyncMock()
        mock_api_client.request = AsyncMock(return_value={
            'success': True,
            'data': {
                'user_id': '123',
                'access_token': 'test_token_123',
                'username': 'testuser'
            }
        })
        
        with patch('service.get_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            
            result = await mcp_service.login('testuser', 'testpass')
        
        assert result['success'] == True
        assert result['user_id'] == '123'
        assert mcp_service.session_manager.current_user_token == 'test_token_123'
    
    @pytest.mark.asyncio
    async def test_login_failure(self, mcp_service):
        """测试MCP登录失败"""
        mock_api_client = AsyncMock()
        mock_api_client.request = AsyncMock(return_value={
            'success': False,
            'error_code': 'AUTH_001',
            'message': '用户名或密码错误'
        })
        
        with patch('service.get_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            
            result = await mcp_service.login('testuser', 'wrongpass')
        
        assert result['success'] == False
        assert result.get('error_code') == 'AUTH_001'
        # 登录失败后 session 不应该有新的 token（保持原状态）
        assert mcp_service.session_manager.current_user_token is None
    
    @pytest.mark.asyncio
    async def test_init_requires_login(self, mcp_service):
        """测试init工具需要登录"""
        # 确保未登录状态
        mcp_service.session_manager.logout()
        assert not mcp_service.session_manager.is_authenticated()
        
        result = await mcp_service.init('test_project')
        
        assert result['status'] == 'error'
        assert result['message'] == '请先登录'
    
    @pytest.mark.asyncio
    async def test_next_requires_login(self, mcp_service):
        """测试next工具需要登录"""
        mcp_service.session_manager.logout()
        assert not mcp_service.session_manager.is_authenticated()
        
        result = await mcp_service.next('project_123')
        
        assert result['success'] == False
        assert result['error_code'] == 'AUTH_001'


class TestMCPProjectPermissions:
    """MCP项目权限测试"""
    
    @pytest.fixture
    def authenticated_mcp_service(self):
        """创建已认证的MCP服务实例用于测试"""
        # Mock FileManager 避免自动恢复会话
        with patch('file_manager.FileManager.read_user_info', side_effect=FileNotFoundError):
            with patch('file_manager.FileManager.read_project_info', side_effect=FileNotFoundError):
                service = MCPService()
                service.session_manager.login('123', 'valid_token', 'test_user')
                yield service
    
    @pytest.mark.asyncio
    async def test_init_with_valid_auth(self, authenticated_mcp_service):
        """测试已认证用户可以初始化项目"""
        mock_api_client = AsyncMock()
        mock_api_client.request = AsyncMock(return_value={
            'success': True,
            'project_id': 'project_456',
            'project_name': 'test_project',
            'created_at': '2024-01-01T00:00:00Z',
            'sop_steps_count': 10,
            'initial_task_groups': 2,
            'initialization_data': {
                'templates': [],
                'directories': []
            },
            'message': '项目初始化成功'
        })
        
        with patch('service.get_api_client') as mock_get_client:
            # Mock API client with _client attribute for header access
            mock_api_client._client = AsyncMock()
            mock_api_client._client.headers = {}
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            with patch.object(authenticated_mcp_service, 'file_manager') as mock_fm:
                # Mock file manager methods
                mock_fm.create_supervisor_directory.return_value = None
                mock_fm.save_project_info.return_value = None
                mock_fm.initialize_project_structure.return_value = []
                result = await authenticated_mcp_service.init('test_project')
        
        assert result['status'] == 'success'
        assert result['data']['project_id'] == 'project_456'
        mock_fm.create_supervisor_directory.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_next_with_permission(self, authenticated_mcp_service):
        """测试有权限的用户可以获取下一个任务"""
        mock_api_client = AsyncMock()
        mock_api_client._client = AsyncMock()
        mock_api_client._client.headers = {}
        mock_api_client.request = AsyncMock(return_value={
            'status': 'success',  # 修正：使用status而不是success
            'task': {
                'id': 'task_789',
                'title': 'Test Task',
                'status': 'pending',
                'task_group_id': 'test-task-group',  # 添加必需的task_group_id字段
                'description': 'Test task description'  # 添加description字段
            }
        })
        
        with patch.object(authenticated_mcp_service, '_get_project_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            with patch.object(authenticated_mcp_service, 'file_manager') as mock_fm:
                # Mock文件管理器方法
                mock_fm.has_project_info.return_value = True
                mock_fm.read_project_info.return_value = {'api_url': 'http://localhost:8000/api/v1'}
                result = await authenticated_mcp_service.next('project_123')
        
        assert result['status'] == 'success'  # 修正：检查status字段
        assert result['task']['id'] == 'task_789'
        mock_fm.save_current_task.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_next_without_permission(self, authenticated_mcp_service):
        """测试无权限用户无法获取任务"""
        mock_api_client = AsyncMock()
        mock_api_client._client = AsyncMock()
        mock_api_client._client.headers = {}
        mock_api_client.request = AsyncMock(return_value={
            'status': 'error',  # 修正：API返回status字段
            'error_code': 'AUTH_002',
            'message': '无权限访问此项目'
        })
        
        with patch.object(authenticated_mcp_service, '_get_project_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            with patch.object(authenticated_mcp_service, 'file_manager') as mock_fm:
                # Mock文件管理器方法
                mock_fm.has_project_info.return_value = True
                mock_fm.read_project_info.return_value = {'api_url': 'http://localhost:8000/api/v1'}
                result = await authenticated_mcp_service.next('other_project')
        
        # 当API返回错误状态时，next方法直接返回API响应
        assert result['status'] == 'error'
        assert result['error_code'] == 'AUTH_002'
    
    @pytest.mark.asyncio
    async def test_report_with_permission(self, authenticated_mcp_service):
        """测试有权限的用户可以提交任务结果"""
        mock_api_client = AsyncMock()
        mock_api_client.request = AsyncMock(return_value={
            'status': 'success',  # 修正：使用status而不是success
            'message': '任务结果提交成功'
        })
        
        with patch('service.get_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            with patch.object(authenticated_mcp_service, 'file_manager') as mock_fm:
                # Mock文件管理器方法
                mock_fm.has_current_task.return_value = True
                mock_fm.read_current_task_data.return_value = {
                    'type': 'VALIDATION',  # 设置为VALIDATION任务才会触发清理
                    'task_group_id': 'test_task_group_id'  # 添加task_group_id
                }
                result = await authenticated_mcp_service.report('task_123', {
                    'output': 'Task completed',
                    'validation_result': {'passed': True}  # 添加validation结果
                })
        
        assert result['status'] == 'success'  # 修正：检查status字段
        mock_fm.cleanup_task_group_files.assert_called_once_with('test_task_group_id')  # 修正：使用新方法名和参数
    
    @pytest.mark.asyncio
    async def test_report_without_permission(self, authenticated_mcp_service):
        """测试无权限用户无法提交任务结果"""
        mock_api_client = AsyncMock()
        mock_api_client.request = AsyncMock(return_value={
            'status': 'error',  # 修正：API返回error状态
            'error_code': 'AUTH_004',
            'message': '无权限访问此任务'
        })
        
        with patch('service.get_api_client') as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_api_client
            with patch.object(authenticated_mcp_service, 'file_manager') as mock_fm:
                # Mock文件管理器方法
                mock_fm.has_current_task.return_value = True
                mock_fm.read_current_task_data.return_value = {
                    'type': 'IMPLEMENTING'
                }
                result = await authenticated_mcp_service.report('other_task', {
                    'output': 'Should fail'
                })
        
        assert result['status'] == 'error'  # 修正：检查status字段
        assert result['error_code'] == 'AUTH_004'


class TestMCPErrorHandling:
    """MCP错误处理测试"""
    
    @pytest.fixture
    def mcp_service(self):
        """创建MCP服务实例用于测试"""
        service = MCPService()
        yield service
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self, mcp_service):
        """测试网络错误处理"""
        # 修正：Mock get_api_client而不是直接mock api_client
        with patch('service.get_api_client') as mock_get_client:
            # Mock异常来模拟网络错误
            mock_get_client.side_effect = Exception('Connection timeout')
            
            result = await mcp_service.login('testuser', 'testpass')
        
        assert result['success'] == False
        assert result['error_code'] == 'NETWORK_ERROR'
        assert '网络请求失败' in result['message']
    
    @pytest.mark.asyncio
    async def test_api_server_error_handling(self, mcp_service):
        """测试API服务器错误处理"""
        # 确保已登录状态
        mcp_service.session_manager.login('123', 'test_token', 'test_user')
        assert mcp_service.session_manager.is_authenticated()
        
        # 修正：Mock get_api_client
        with patch('service.get_api_client') as mock_get_client:
            # Mock API异常来模拟服务器错误
            mock_get_client.side_effect = Exception('Internal server error')
            
            result = await mcp_service.init('test_project')
        
        assert result['status'] == 'error'
        assert '失败' in result['message']
    
    @pytest.mark.asyncio
    async def test_session_token_expiry_handling(self, mcp_service):
        """测试会话令牌过期处理"""
        # 确保已登录状态
        mcp_service.session_manager.login('123', 'test_token', 'test_user')
        assert mcp_service.session_manager.is_authenticated()
        
        # 修正：Mock get_api_client
        with patch('service.get_api_client') as mock_get_client:
            with patch.object(mcp_service, 'file_manager') as mock_fm:
                mock_fm.has_project_info.return_value = True
                # Mock API异常来模拟令牌过期
                mock_get_client.side_effect = Exception('令牌已过期')
                
                result = await mcp_service.next('project_123')
        
        assert result['success'] == False
        assert result['error_code'] == 'AUTH_002'  # 修正：next方法返回AUTH_002


class TestMCPSessionManagement:
    """MCP会话管理测试"""
    
    def test_session_manager_login_state(self):
        """测试会话管理器登录状态"""
        from session import SessionManager
        from file_manager import FileManager
        
        # Mock FileManager 避免自动恢复会话
        with patch('file_manager.FileManager.read_user_info', side_effect=FileNotFoundError):
            session_manager = SessionManager(FileManager())
            
            # 初始状态未登录
            assert not session_manager.is_authenticated()
        
        # 模拟登录
        session_manager.current_user_token = 'test_token'
        session_manager.current_user_id = '123'
        
        assert session_manager.is_authenticated()
        
        # 登出
        session_manager.logout()
        assert not session_manager.is_authenticated()
        assert session_manager.current_user_token is None
    
    def test_session_manager_auth_headers(self):
        """测试会话管理器认证头生成"""
        from session import SessionManager
        from file_manager import FileManager
        
        # Mock FileManager 避免自动恢复会话
        with patch('file_manager.FileManager.read_user_info', side_effect=FileNotFoundError):
            session_manager = SessionManager(FileManager())
        
        # 未登录时无认证头
        headers = session_manager.get_headers()
        assert 'Authorization' not in headers
        
        # 登录后有认证头
        session_manager.current_user_token = 'test_token_123'
        headers = session_manager.get_headers()
        
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Token test_token_123'