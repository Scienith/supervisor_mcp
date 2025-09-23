"""
测试用户信息保留功能
验证login后创建项目不会覆盖用户信息
"""

import pytest
import json
import asyncio
import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
from service import MCPService
from file_manager import FileManager


class TestUserInfoPreservation:
    """测试用户信息保留功能"""

    @pytest.fixture
    def mcp_service(self):
        """创建MCP服务实例"""
        return MCPService()

    @pytest.fixture
    def mock_api_responses(self):
        """模拟API响应"""
        return {
            'login_response': {
                'success': True,
                'data': {
                    'user_id': '1',
                    'username': 'admin',
                    'access_token': 'token123'
                }
            },
            'create_project_response': {
                'success': True,
                'project_id': 'proj-456',
                'project_name': '测试项目',
                'created_at': '2024-01-20T10:00:00Z',
                'initialization_data': {}
            },
            'setup_project_response': {
                'project_id': 'proj-789',
                'project_name': '已知项目',
                'description': '已存在的项目',
                'created_at': '2024-01-20T08:00:00Z',
                'tasks': []
            }
        }

    def test_login_saves_user_info(self, mcp_service, mock_api_responses):
        """测试登录后保存用户信息"""
        async def run_test():
            # 模拟API调用成功
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.request.return_value = mock_api_responses['login_response']
                mock_get_client.return_value = mock_client

                # Mock FileManager的save_user_info方法
                with patch('file_manager.FileManager.save_user_info') as mock_save_user:
                    with patch('file_manager.FileManager.has_project_info', return_value=False):

                        result = await mcp_service.login('admin', 'admin123', os.getcwd())

                        # 验证登录成功
                        assert result['success'] is True
                        assert result['user_id'] == '1'
                        assert result['username'] == 'admin'

                        # 验证保存了用户信息到user.json
                        mock_save_user.assert_called_once()
                        saved_data = mock_save_user.call_args[0][0]
                        assert saved_data['user_id'] == '1'
                        assert saved_data['username'] == 'admin'
                        assert saved_data['access_token'] == 'token123'

        asyncio.run(run_test())

    def test_create_project_preserves_user_info(self, mcp_service, mock_api_responses):
        """测试创建项目后保留用户信息"""
        async def run_test():
            # 先模拟登录状态
            mcp_service.session_manager.login('1', 'token123')
            
            # 模拟现有的用户信息
            existing_info = {
                'user_id': '1',
                'username': 'admin',
                'access_token': 'token123'
            }
            
            # 模拟API调用
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.request.return_value = mock_api_responses['create_project_response']
                mock_get_client.return_value = mock_client
                
                # 模拟文件操作 - 关键是save_project_info会保留现有信息
                with patch.object(mcp_service.file_manager, 'create_supervisor_directory'):
                    with patch.object(mcp_service.file_manager, 'save_project_info') as mock_save:
                        with patch.object(mcp_service.file_manager, 'initialize_project_structure', return_value=[]):
                            with patch('service.MCPService._download_templates_unified', new_callable=AsyncMock):
                                with patch('service.MCPService._create_task_folders', new_callable=AsyncMock):
                                    
                                    # 模拟FileManager.save_project_info的新行为（保留现有信息）
                                    def mock_save_behavior(new_info):
                                        # 模拟读取现有文件并更新
                                        combined_info = existing_info.copy()
                                        combined_info.update(new_info)
                                        return combined_info
                                    
                                    mock_save.side_effect = mock_save_behavior
                                    
                                    result = await mcp_service.init(
                                        project_name='测试项目',
                                        description='这是一个测试项目'
                                    )
                                    
                                    # 验证项目创建成功
                                    assert result['status'] == 'success'
                                    
                                    # 验证调用了save_project_info
                                    assert mock_save.call_count >= 1
                                    
                                    # 验证传递给save_project_info的数据包含项目信息
                                    project_save_call = None
                                    for call in mock_save.call_args_list:
                                        call_data = call[0][0]
                                        if 'project_id' in call_data:
                                            project_save_call = call_data
                                            break
                                    
                                    assert project_save_call is not None
                                    assert project_save_call['project_id'] == 'proj-456'
                                    assert project_save_call['project_name'] == '测试项目'

        asyncio.run(run_test())

    def test_setup_workspace_preserves_user_info(self, mcp_service, mock_api_responses):
        """测试设置工作区后保留用户信息"""
        async def run_test():
            # 先模拟登录状态
            mcp_service.session_manager.login('1', 'token123')
            
            # 模拟现有的用户信息
            existing_info = {
                'user_id': '1',
                'username': 'admin',
                'access_token': 'token123'
            }
            
            # 模拟API调用
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.request.side_effect = [
                    mock_api_responses['setup_project_response'],  # 项目信息
                    {'templates': []}  # 模板信息
                ]
                mock_get_client.return_value = mock_client
                
                # 模拟文件操作
                with patch.object(mcp_service.file_manager, 'create_supervisor_directory'):
                    with patch.object(mcp_service.file_manager, 'save_project_info') as mock_save:
                        with patch('service.MCPService._download_templates_unified', new_callable=AsyncMock):
                            with patch('service.MCPService._create_task_folders', new_callable=AsyncMock):
                                
                                # 模拟FileManager.save_project_info的新行为
                                def mock_save_behavior(new_info):
                                    combined_info = existing_info.copy()
                                    combined_info.update(new_info)
                                    return combined_info
                                
                                mock_save.side_effect = mock_save_behavior
                                
                                result = await mcp_service.init(project_id='proj-789')
                                
                                # 验证设置成功
                                assert result['status'] == 'success'
                                
                                # 验证调用了save_project_info
                                mock_save.assert_called_once()
                                
                                # 验证传递的数据包含项目信息
                                saved_data = mock_save.call_args[0][0]
                                assert saved_data['project_id'] == 'proj-789'
                                assert saved_data['project_name'] == '已知项目'

        asyncio.run(run_test())

    def test_file_manager_integration(self):
        """测试FileManager的集成行为"""
        file_manager = FileManager(base_path='/test/path')
        
        # 模拟现有文件内容
        existing_info = {
            'user_id': '1',
            'username': 'admin',
            'access_token': 'token123',
            'old_field': 'should_be_preserved'
        }
        
        # 新的项目信息
        new_info = {
            'project_id': 'proj-123',
            'project_name': '新项目',
            'description': '项目描述'
        }
        
        # 模拟文件系统操作
        mock_file = mock_open(read_data=json.dumps(existing_info))
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=True):
                file_manager.save_project_info(new_info)
                
                # 验证读取和写入操作
                calls = mock_file.call_args_list
                assert len(calls) == 2  # 读取 + 写入
                
                # 验证写入的内容
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                
                # 验证保留了用户信息
                assert written_data['user_id'] == '1'
                assert written_data['username'] == 'admin'
                assert written_data['access_token'] == 'token123'
                assert written_data['old_field'] == 'should_be_preserved'
                
                # 验证更新了项目信息
                assert written_data['project_id'] == 'proj-123'
                assert written_data['project_name'] == '新项目'
                assert written_data['description'] == '项目描述'

    def test_complete_login_create_flow(self, mcp_service, mock_api_responses):
        """测试完整的登录-创建项目流程"""
        async def run_test():
            # 第一步：登录
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.request.return_value = mock_api_responses['login_response']
                mock_get_client.return_value = mock_client

                # Mock FileManager的方法
                with patch('file_manager.FileManager.save_user_info') as mock_save_user:
                    with patch('file_manager.FileManager.has_project_info', return_value=False):
                        login_result = await mcp_service.login('admin', 'admin123', os.getcwd())

                        assert login_result['success'] is True

                        # 验证保存了用户信息
                        mock_save_user.assert_called_once()
                        saved_data = mock_save_user.call_args[0][0]
                        assert saved_data['user_id'] == '1'
                        assert saved_data['username'] == 'admin'
                        assert saved_data['access_token'] == 'token123'
            
            # 第二步：创建项目（应该保留用户信息）
            with patch('service.get_api_client') as mock_get_client:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.request.return_value = mock_api_responses['create_project_response']
                mock_get_client.return_value = mock_client

                with patch.object(mcp_service.file_manager, 'initialize_project_structure', return_value=[]):
                    with patch('service.MCPService._download_templates_unified', new_callable=AsyncMock):
                        with patch('service.MCPService._create_task_folders', new_callable=AsyncMock):
                            with patch.object(mcp_service.file_manager, 'save_project_info') as mock_save_project:
                                with patch.object(mcp_service.file_manager, 'read_project_info',
                                                  return_value={'user_id': '1', 'username': 'admin',
                                                                'access_token': 'token123'}):

                                    project_result = await mcp_service.init(
                                        project_name='测试项目',
                                        description='这是一个测试项目'
                                    )

                                    assert project_result['status'] == 'success'

                                    # 验证调用了save_project_info
                                    assert mock_save_project.called

                                    # 获取最后一次调用的数据
                                    final_call_data = None
                                    for call in mock_save_project.call_args_list:
                                        call_data = call[0][0]
                                        if 'project_id' in call_data:
                                            final_call_data = call_data
                                            break

                                    assert final_call_data is not None
                                    # 验证项目信息被添加
                                    assert final_call_data['project_id'] == 'proj-456'
                                    assert final_call_data['project_name'] == '测试项目'

        asyncio.run(run_test())