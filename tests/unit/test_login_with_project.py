"""
测试 login_with_project 功能
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import aiohttp

from service import MCPService
from file_manager import FileManager
from session import SessionManager


class TestLoginWithProject:
    """测试 login_with_project 方法"""

    @pytest.fixture
    def mock_file_manager(self, tmp_path):
        """创建 mock FileManager"""
        fm = Mock(spec=FileManager)
        fm.base_path = tmp_path
        fm.supervisor_dir = tmp_path / ".supervisor"
        fm.read_user_info.return_value = None
        fm.save_user_info = Mock()
        fm.save_project_info = Mock()
        fm.has_project_info.return_value = False
        fm.read_project_info.return_value = {}
        fm.create_supervisor_directory = Mock()
        fm.initialize_project_structure = Mock(return_value=[])
        return fm

    @pytest.fixture
    def mock_session_manager(self):
        """创建 mock SessionManager"""
        sm = Mock(spec=SessionManager)
        sm.is_authenticated.return_value = False
        sm.login = Mock()
        sm.get_headers.return_value = {"Authorization": "Bearer test_token"}
        sm.set_project_context = Mock()
        return sm

    @pytest.fixture
    def service(self, mock_file_manager, mock_session_manager):
        """创建带有 mock 依赖的 MCPService"""
        service = MCPService()
        service.file_manager = mock_file_manager
        service.session_manager = mock_session_manager
        return service

    @pytest.mark.asyncio
    async def test_login_with_project_success(self, service, mock_file_manager, mock_session_manager):
        """测试成功的登录和项目初始化"""
        # Mock login 成功
        with patch.object(service, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                'success': True,
                'user_id': 'user123',
                'username': 'testuser'
            }

            # Mock init 成功
            with patch.object(service, 'init', new_callable=AsyncMock) as mock_init:
                mock_init.return_value = {
                    'status': 'success',
                    'data': {
                        'project_id': 'proj123',
                        'project_name': 'Test Project',
                        'templates_downloaded': 5,
                        'scenario': 'existing_project'
                    }
                }

                # 调用 login_with_project（service层仍然接受参数）
                result = await service.login_with_project(
                    username='testuser',
                    password='testpass',
                    project_id='proj123',
                    working_directory='/test/path'
                )

                # 验证结果
                assert result['success'] is True
                assert result['user_id'] == 'user123'
                assert result['username'] == 'testuser'
                assert result['project']['project_id'] == 'proj123'
                assert result['project']['project_name'] == 'Test Project'
                assert result['project']['templates_downloaded'] == 5
                assert 'message' in result

                # 验证调用
                mock_login.assert_called_once_with('testuser', 'testpass', '/test/path')
                mock_init.assert_called_once_with(project_id='proj123', working_directory='/test/path')

    @pytest.mark.asyncio
    async def test_login_with_project_login_failed(self, service):
        """测试登录失败的情况"""
        # Mock login 失败
        with patch.object(service, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '用户名或密码错误'
            }

            # 调用 login_with_project
            result = await service.login_with_project(
                username='testuser',
                password='wrongpass',
                project_id='proj123'
            )

            # 验证结果 - 应该返回登录失败的结果
            assert result['success'] is False
            assert result['error_code'] == 'AUTH_001'
            assert result['message'] == '用户名或密码错误'

            # 验证没有调用 init
            with patch.object(service, 'init', new_callable=AsyncMock) as mock_init:
                mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_with_project_init_failed(self, service):
        """测试登录成功但项目初始化失败的情况"""
        # Mock login 成功
        with patch.object(service, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                'success': True,
                'user_id': 'user123',
                'username': 'testuser'
            }

            # Mock init 失败
            with patch.object(service, 'init', new_callable=AsyncMock) as mock_init:
                mock_init.return_value = {
                    'status': 'error',
                    'message': '项目不存在'
                }

                # 调用 login_with_project
                result = await service.login_with_project(
                    username='testuser',
                    password='testpass',
                    project_id='invalid_proj'
                )

                # 验证结果 - 登录成功但初始化失败
                assert result['success'] is False
                assert result['error_code'] == 'INIT_001'
                assert '登录成功但项目初始化失败' in result['message']
                assert result['user_id'] == 'user123'
                assert result['username'] == 'testuser'

    @pytest.mark.asyncio
    async def test_login_with_project_no_working_directory(self, service):
        """测试不提供 working_directory 参数的情况"""
        with patch('pathlib.Path.cwd') as mock_cwd:
            mock_cwd.return_value = Path('/current/dir')

            with patch.object(service, 'login', new_callable=AsyncMock) as mock_login:
                mock_login.return_value = {
                    'success': True,
                    'user_id': 'user123',
                    'username': 'testuser'
                }

                with patch.object(service, 'init', new_callable=AsyncMock) as mock_init:
                    mock_init.return_value = {
                        'status': 'success',
                        'data': {
                            'project_id': 'proj123',
                            'project_name': 'Test Project',
                            'templates_downloaded': 0
                        }
                    }

                    # 调用 login_with_project，不提供 working_directory
                    result = await service.login_with_project(
                        username='testuser',
                        password='testpass',
                        project_id='proj123'
                    )

                    # 验证使用了当前目录
                    mock_login.assert_called_once_with('testuser', 'testpass', '/current/dir')
                    mock_init.assert_called_once_with(project_id='proj123', working_directory='/current/dir')

    @pytest.mark.asyncio
    async def test_login_with_project_exception_handling(self, service):
        """测试异常处理"""
        # Mock login 成功
        with patch.object(service, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                'success': True,
                'user_id': 'user123',
                'username': 'testuser'
            }

            # Mock init 抛出异常
            with patch.object(service, 'init', new_callable=AsyncMock) as mock_init:
                mock_init.side_effect = Exception("Unexpected error")

                # 调用 login_with_project
                result = await service.login_with_project(
                    username='testuser',
                    password='testpass',
                    project_id='proj123'
                )

                # 验证结果 - 应该捕获异常并返回错误
                assert result['success'] is False
                assert result['error_code'] == 'INIT_002'
                assert 'Unexpected error' in result['message']
                assert result['user_id'] == 'user123'
                assert result['username'] == 'testuser'