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
    async def test_login_success_saves_user_info_to_project_info(self):
        """测试：login成功后应该保存用户信息到project_info.json"""
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
                    
                    # 验证project_info.json中保存了用户信息
                    project_info_path = os.path.join(supervisor_dir, 'project_info.json')
                    assert os.path.exists(project_info_path)
                    
                    with open(project_info_path, 'r') as f:
                        project_info = json.load(f)
                    
                    assert 'user_id' in project_info
                    assert 'username' in project_info
                    assert 'access_token' in project_info
                    assert project_info['user_id'] == '123'
                    assert project_info['username'] == 'testuser'
                    assert project_info['access_token'] == 'test_token_12345'

    @pytest.mark.asyncio
    async def test_login_overwrites_existing_user_info(self):
        """测试：login应该覆盖已存在的用户信息"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和已存在的project_info.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            project_info_path = os.path.join(supervisor_dir, 'project_info.json')
            existing_info = {
                'project_id': 'old_project',
                'user_id': 'old_user',
                'username': 'olduser',
                'access_token': 'old_token'
            }
            with open(project_info_path, 'w') as f:
                json.dump(existing_info, f)
            
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
                    
                    # 验证project_info.json中用户信息被覆盖
                    with open(project_info_path, 'r') as f:
                        project_info = json.load(f)
                    
                    assert project_info['user_id'] == '456'
                    assert project_info['username'] == 'newuser'
                    assert project_info['access_token'] == 'new_token_67890'
                    # 其他信息应该保留
                    assert project_info['project_id'] == 'old_project'

    @pytest.mark.asyncio
    async def test_auto_reuse_valid_local_token(self):
        """测试：自动复用有效的本地token"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和包含有效token的project_info.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            project_info_path = os.path.join(supervisor_dir, 'project_info.json')
            existing_info = {
                'project_id': 'test_project',
                'user_id': '789',
                'username': 'existinguser',
                'access_token': 'valid_token_123'
            }
            with open(project_info_path, 'w') as f:
                json.dump(existing_info, f)
            
            # 模拟token验证成功的API响应
            mock_validate_response = {
                'success': True,
                'data': {
                    'user_id': '789',
                    'username': 'existinguser'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.request.return_value = mock_validate_response
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('existinguser', 'password')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '789'
                    assert result['username'] == 'existinguser'
                    
                    # 验证只调用了token验证API，没有调用登录API
                    mock_client.request.assert_called_once()
                    call_args = mock_client.request.call_args
                    assert 'auth/validate' in call_args[0][1]  # 验证调用了validate接口

    @pytest.mark.asyncio
    async def test_fallback_to_login_when_token_invalid(self):
        """测试：当本地token无效时，回退到登录流程"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建.supervisor目录和包含无效token的project_info.json
            supervisor_dir = os.path.join(temp_dir, '.supervisor')
            os.makedirs(supervisor_dir)
            
            project_info_path = os.path.join(supervisor_dir, 'project_info.json')
            existing_info = {
                'user_id': '999',
                'username': 'testuser',
                'access_token': 'invalid_token'
            }
            with open(project_info_path, 'w') as f:
                json.dump(existing_info, f)
            
            # 模拟token验证失败和登录成功的API响应
            mock_validate_response = {'success': False, 'error_code': 'TOKEN_INVALID'}
            mock_login_response = {
                'success': True,
                'data': {
                    'user_id': '999',
                    'username': 'testuser',
                    'access_token': 'new_valid_token'
                }
            }
            
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                # 第一次调用返回token验证失败，第二次调用返回登录成功
                mock_client.request.side_effect = [mock_validate_response, mock_login_response]
                mock_get_client.return_value.__aenter__.return_value = mock_client
                
                with patch('os.getcwd', return_value=temp_dir):
                    service = MCPService()
                    result = await service.login('testuser', 'password')
                    
                    # 验证返回结果
                    assert result['success'] == True
                    assert result['user_id'] == '999'
                    assert result['username'] == 'testuser'
                    
                    # 验证调用了两次API：先验证token，后登录
                    assert mock_client.request.call_count == 2
                    
                    # 验证新token被保存
                    with open(project_info_path, 'r') as f:
                        project_info = json.load(f)
                    assert project_info['access_token'] == 'new_valid_token'

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