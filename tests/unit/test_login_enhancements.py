"""
测试login功能增强：本地保存用户信息和token复用
"""
import os
import json
import pytest
import tempfile
from unittest.mock import patch, AsyncMock, MagicMock
from service import MCPService


class TestLoginEnhancements:
    """测试login功能增强"""
    
    def setup_method(self):
        """每个测试前重置环境"""
        # 清除环境变量，使用测试配置
        if 'SUPERVISOR_API_URL' in os.environ:
            del os.environ['SUPERVISOR_API_URL']
        os.environ['SUPERVISOR_API_URL'] = 'http://test.api.com/api/v1'

    @pytest.mark.asyncio
    async def test_login_success_saves_user_info_to_user_json(self):
        """测试：login成功后应该保存用户信息到user.json"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            # 模拟API响应
            mock_response = {
                'success': True,
                'data': {
                    'user_id': '123',
                    'username': 'testuser',
                    'access_token': 'test_token_12345'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('testuser', 'password')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '123'
                    assert result['username'] == 'testuser'
                    
                    # 验证user.json中保存了用户信息
                    user_info_path = os.path.join(supervisor_dir, 'user.json')
                    assert os.path.exists(user_info_path)
                    
                    with open(user_info_path, 'r') as f:
                        user_info = json.load(f)
                    
                    assert 'user_id' in user_info
                    assert 'username' in user_info
                    assert 'access_token' in user_info
                    assert user_info['user_id'] == '123'
                    assert user_info['username'] == 'testuser'
                    assert user_info['access_token'] == 'test_token_12345'

    @pytest.mark.asyncio
    async def test_login_overwrites_existing_user_info(self):
        """测试：login应该覆盖已存在的用户信息"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和已存在的user.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            user_info_path = os.path.join(supervisor_dir, 'user.json')
            existing_user_info = {
                'user_id': 'old_user',
                'username': 'olduser',
                'access_token': 'old_token'
            }
            with open(user_info_path, 'w') as f:
                json.dump(existing_user_info, f)
                
            # 创建project.json保持项目信息分离
            project_info_path = os.path.join(supervisor_dir, 'project.json')
            project_info = {
                'project_id': 'old_project',
                'project_name': 'Old Project'
            }
            with open(project_info_path, 'w') as f:
                json.dump(project_info, f)
            
            # 模拟API响应
            mock_response = {
                'success': True,
                'data': {
                    'user_id': '456',
                    'username': 'newuser',
                    'access_token': 'new_token_67890'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('newuser', 'newpassword')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '456'
                    assert result['username'] == 'newuser'
                    
                    # 验证user.json中用户信息被覆盖
                    with open(user_info_path, 'r') as f:
                        user_info = json.load(f)
                    
                    assert user_info['user_id'] == '456'
                    assert user_info['username'] == 'newuser'
                    assert user_info['access_token'] == 'new_token_67890'
                    
                    # 验证project.json保持不变
                    with open(project_info_path, 'r') as f:
                        project_info = json.load(f)
                    assert project_info['project_id'] == 'old_project'

    @pytest.mark.asyncio
    async def test_session_manager_auto_restores_from_user_json(self):
        """测试：SessionManager自动从user.json恢复有效session"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和包含有效token的user.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            user_info_path = os.path.join(supervisor_dir, 'user.json')
            existing_info = {
                'user_id': '789',
                'username': 'existinguser',
                'access_token': 'valid_token_123'
            }
            with open(user_info_path, 'w') as f:
                json.dump(existing_info, f)
            
            with patch('os.getcwd', return_value=temp_dir):
                service = MCPService()
                
                # 验证SessionManager已自动恢复session
                assert service.session_manager.is_authenticated()
                assert service.session_manager.current_user_id == '789'
                assert service.session_manager.current_user_token == 'valid_token_123'
                assert service.session_manager.current_username == 'existinguser'

    @pytest.mark.asyncio
    async def test_login_updates_user_info_file(self):
        """测试：login方法更新用户信息文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和包含旧token的user.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            user_info_path = os.path.join(supervisor_dir, 'user.json')
            existing_info = {
                'user_id': '999',
                'username': 'testuser',
                'access_token': 'old_token'
            }
            with open(user_info_path, 'w') as f:
                json.dump(existing_info, f)
            
            # 模拟登录成功的API响应
            mock_login_response = {
                'success': True,
                'data': {
                    'user_id': '999',
                    'username': 'testuser',
                    'access_token': 'new_valid_token'
                }
            }
            
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                with patch('service.get_api_client') as mock_get_client:
                    mock_client = AsyncMock()
                    # 第一次调用是token验证(失败)，第二次是实际登录(成功)
                    mock_client.request.side_effect = [
                        {'success': False, 'error_code': 'TOKEN_INVALID'},  # token验证失败
                        mock_login_response  # 登录成功
                    ]
                    mock_get_client.return_value.__aenter__.return_value = mock_client
                    
                    service = MCPService()
                    
                    # 验证初始时有旧的session
                    assert service.session_manager.current_user_token == 'old_token'
                    
                    # 执行登录
                    result = await service.login('testuser', 'password')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '999' 
                    assert result['username'] == 'testuser'
                    
                    # 验证新token被保存到user.json（这是关键功能）
                    with open(user_info_path, 'r') as f:
                        user_info = json.load(f)
                    assert user_info['access_token'] == 'new_valid_token'
                    assert user_info['user_id'] == '999'
                    assert user_info['username'] == 'testuser'
                    
            finally:
                os.chdir(original_cwd)

    @pytest.mark.asyncio 
    async def test_login_no_existing_project_info(self):
        """测试：没有现有project_info时的正常登录流程"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录但不创建project_info.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            # 模拟登录成功的API响应
            mock_login_response = {
                'success': True,
                'data': {
                    'user_id': '111',
                    'username': 'newuser',
                    'access_token': 'fresh_token'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_login_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('newuser', 'password')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '111'
                    assert result['username'] == 'newuser'
                    
                    # 验证只调用了登录API
                    mock_client.request.assert_called_once()
                    call_args = mock_client.request.call_args
                    assert 'auth/login' in call_args[0][1]  # 验证调用了login接口

    @pytest.mark.asyncio
    async def test_validate_local_token_handles_missing_user_json_gracefully(self):
        """测试：_validate_local_token应该优雅处理user.json不存在的情况"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录但不创建user.json文件
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            with patch('os.getcwd', return_value=temp_dir):
                service = MCPService()
                
                # 直接调用_validate_local_token方法
                result = await service._validate_local_token('testuser')
                
                # 应该返回None而不是抛出异常
                assert result is None

    @pytest.mark.asyncio
    async def test_login_with_missing_user_json_calls_api_directly(self):
        """测试：当user.json不存在时，login应该直接调用API而不是报网络错误"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录但不创建user.json文件
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            # 模拟登录成功的API响应
            mock_login_response = {
                'success': True,
                'data': {
                    'user_id': '222',
                    'username': 'newuser',
                    'access_token': 'api_token'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_login_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('newuser', 'password')
                    
                    # 验证登录成功，不应该有NETWORK_ERROR
                    assert result['success'] == True
                    assert result['user_id'] == '222'
                    assert result['username'] == 'newuser'
                    assert 'error_code' not in result
                    
                    # 验证只调用了登录API，没有调用token验证API
                    mock_client.request.assert_called_once()
                    call_args = mock_client.request.call_args
                    assert 'auth/login' in call_args[0][1]

    @pytest.mark.asyncio
    async def test_login_with_no_supervisor_directory_creates_directory_and_succeeds(self):
        """测试：当.supervisor目录不存在时，login应该创建目录并成功登录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 不创建.supervisor目录，模拟全新环境
            
            # 模拟登录成功的API响应
            mock_login_response = {
                'success': True,
                'data': {
                    'user_id': '333',
                    'username': 'freshuser',
                    'access_token': 'fresh_api_token'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_login_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('freshuser', 'password')
                    
                    # 验证登录成功，不应该有NETWORK_ERROR或FileNotFoundError
                    assert result['success'] == True
                    assert result['user_id'] == '333'
                    assert result['username'] == 'freshuser'
                    assert 'error_code' not in result
                    
                    # 验证.supervisor目录和user.json被创建
                    supervisor_dir = os.path.join(temp_dir, '.supervisor')
                    assert os.path.exists(supervisor_dir)
                    
                    user_file = os.path.join(supervisor_dir, 'user.json')
                    assert os.path.exists(user_file)
                    
                    with open(user_file, 'r') as f:
                        user_info = json.load(f)
                    assert user_info['user_id'] == '333'
                    assert user_info['username'] == 'freshuser'
                    assert user_info['access_token'] == 'fresh_api_token'