"""
测试MCP文件管理器
"""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from file_manager import FileManager


class TestFileManager:
    """测试文件管理器"""

    def test_init_with_default_base_path(self):
        """测试使用默认基础路径初始化"""
        with patch('os.getcwd', return_value='/project/root'):
            manager = FileManager()
            assert manager.base_path == Path('/project/root')
            assert manager.supervisor_dir == Path('/project/root/.supervisor')

    def test_init_with_custom_base_path(self):
        """测试使用自定义基础路径初始化"""
        manager = FileManager(base_path='/custom/path')
        assert manager.base_path == Path('/custom/path')
        assert manager.supervisor_dir == Path('/custom/path/.supervisor')

    def test_create_supervisor_directory(self):
        """测试创建supervisor目录结构"""
        manager = FileManager(base_path='/test/path')
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            manager.create_supervisor_directory()
            
            # 验证创建了正确的目录 (现在创建5个目录)
            calls = mock_mkdir.call_args_list
            assert len(calls) == 5
            # 验证所有调用都使用正确的参数
            for call in calls:
                assert call[1]['parents'] == True
                assert call[1]['exist_ok'] == True

    def test_save_project_info(self):
        """测试保存项目信息（新文件）"""
        manager = FileManager(base_path='/test/path')
        project_info = {
            "project_id": "test-123",
            "project_name": "测试项目",
            "description": "这是一个测试项目",
            "created_at": "2024-01-20T10:00:00Z"
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=False):  # 文件不存在
                manager.save_project_info(project_info)
                
                # 验证写入了正确的文件路径
                mock_file.assert_called_once_with(
                    Path('/test/path/.supervisor/project.json'), 
                    'w', 
                    encoding='utf-8'
                )
                
                # 验证写入了正确的JSON内容
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                # 应该包含传入的信息和自动添加的project_path
                expected_data = project_info.copy()
                expected_data["project_path"] = str(Path('/test/path'))
                assert written_data == expected_data

    def test_save_project_info_update_existing(self):
        """测试保存项目信息（更新现有文件）"""
        manager = FileManager(base_path='/test/path')
        
        # 现有文件内容（只包含项目信息）
        existing_info = {
            "project_id": "old-project",
            "project_name": "旧项目名称",
            "description": "旧描述"
        }
        
        # 新要保存的项目信息
        new_project_info = {
            "project_id": "test-123",
            "project_name": "测试项目",
            "description": "这是一个测试项目",
            "created_at": "2024-01-20T10:00:00Z"
        }
        
        # 模拟文件存在，读取时返回现有信息
        mock_file = mock_open(read_data=json.dumps(existing_info))
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=True):  # 文件存在
                manager.save_project_info(new_project_info)
                
                # 验证调用了读取和写入
                calls = mock_file.call_args_list
                assert len(calls) == 2  # 一次读取，一次写入
                
                # 验证第一次调用是读取
                assert calls[0][0] == (Path('/test/path/.supervisor/project.json'), 'r')
                assert calls[0][1]['encoding'] == 'utf-8'
                
                # 验证第二次调用是写入
                assert calls[1][0] == (Path('/test/path/.supervisor/project.json'), 'w')
                assert calls[1][1]['encoding'] == 'utf-8'
                
                # 验证写入的内容更新了项目信息
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                
                # 应该更新项目信息
                assert written_data["project_id"] == "test-123"
                assert written_data["project_name"] == "测试项目"
                assert written_data["description"] == "这是一个测试项目"
                assert written_data["created_at"] == "2024-01-20T10:00:00Z"

    def test_save_project_info_corrupted_file(self):
        """测试保存项目信息（现有文件损坏）"""
        manager = FileManager(base_path='/test/path')
        project_info = {
            "project_id": "test-123",
            "project_name": "测试项目"
        }
        
        # 模拟文件存在但内容损坏
        mock_file = mock_open(read_data="invalid json content")
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=True):  # 文件存在
                manager.save_project_info(project_info)
                
                # 验证仍然能够保存（使用空字典作为基础）
                calls = mock_file.call_args_list
                assert len(calls) == 2  # 一次读取（失败），一次写入
                
                # 验证写入的内容
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                assert written_data["project_id"] == "test-123"
                assert written_data["project_name"] == "测试项目"

    def test_read_project_info(self):
        """测试读取项目信息"""
        manager = FileManager(base_path='/test/path')
        expected_info = {
            "project_id": "test-123",
            "project_name": "测试项目"
        }
        
        mock_file = mock_open(read_data=json.dumps(expected_info))
        with patch('builtins.open', mock_file):
            result = manager.read_project_info()
            
            assert result == expected_info
            mock_file.assert_called_once_with(
                Path('/test/path/.supervisor/project.json'), 
                'r', 
                encoding='utf-8'
            )

    def test_read_project_info_file_not_found(self):
        """测试读取不存在的项目信息文件"""
        manager = FileManager(base_path='/test/path')
        
        with patch('builtins.open', side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError) as exc_info:
                manager.read_project_info()
            assert "project.json not found" in str(exc_info.value)

    def test_save_current_task_with_order_parameter(self):
        """测试保存当前任务信息（使用task_order参数）"""  
        manager = FileManager(base_path='/test/path')
        full_data = {
            "task": {
                "id": "task-123",
                "title": "实施开发任务",
                "type": "IMPLEMENTING",
                "status": "IN_PROGRESS",
                "task_group_id": "tg-456",
                "description": "# 实施开发任务\n\n这是任务描述内容"
            },
            "context": {"key": "value"}
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                # Mock read_project_info
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj"}):
                    with patch.object(manager, 'save_project_info') as mock_save_project:
                        # 直接提供task_order参数和task_group_id（正确的做法）
                        manager.save_current_task(full_data, task_group_id="tg-456", task_order=4)
                    
                    # 验证调用了open写入MD文件（使用传入的task_order：04_implementing_instructions.md）
                    md_call_found = False
                    for call in mock_file.call_args_list:
                        if call[0][0] == Path('/test/path/supervisor_workspace/current_task_group/04_implementing_instructions.md'):
                            md_call_found = True
                            assert call[0][1] == 'w'
                            assert call[1]['encoding'] == 'utf-8'
                    assert md_call_found, f"Expected file '04_implementing_instructions.md' not found in calls: {[str(call[0][0]) for call in mock_file.call_args_list]}"
                    
                    # 验证更新了项目信息
                    mock_save_project.assert_called_once()
                    saved_info = mock_save_project.call_args[0][0]
                    assert 'current_task_group_id' in saved_info
                    assert saved_info['current_task_group_id'] == 'tg-456'
                    assert 'task_groups' in saved_info
                    assert 'tg-456' in saved_info['task_groups']

    def test_save_current_task_with_local_file_counting(self):
        """测试保存当前任务信息时使用本地文件计数"""
        manager = FileManager(base_path='/test/path')
        full_data = {
            "task": {
                "id": "task-123",
                "title": "实施开发任务",
                "type": "IMPLEMENTING",
                "status": "IN_PROGRESS",
                "description": "# 实施开发任务\n\n这是任务描述内容"
            },
            "context": {"key": "value"}
        }
        
        # 模拟已有2个instruction文件
        task_group_id = "tg-456"
        mock_files = [
            Path(f'/test/path/supervisor_workspace/current_task_group/01_understanding_instructions.md'),
            Path(f'/test/path/supervisor_workspace/current_task_group/02_planning_instructions.md')
        ]
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch('pathlib.Path.glob', return_value=mock_files):
                    with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj"}):
                        with patch.object(manager, 'save_project_info'):
                            # 不提供task_order，应该使用本地文件计数（2个现有文件 + 1 = 03前缀）
                            manager.save_current_task(full_data, task_group_id=task_group_id)
                        
                        # 验证创建了03_implementing_instructions.md
                        md_call_found = False
                        for call in mock_file.call_args_list:
                            if call[0][0] == Path(f'/test/path/supervisor_workspace/current_task_group/03_implementing_instructions.md'):
                                md_call_found = True
                        assert md_call_found, f"Expected file '03_implementing_instructions.md' not found in calls"

    def test_read_current_task_with_numbered_prefix(self):
        """测试读取当前任务信息（支持数字前缀）"""
        manager = FileManager(base_path='/test/path')
        
        # 模拟找到数字前缀的instruction文件
        task_group_id = "tg-456"
        mock_files = [
            Path(f'/test/path/supervisor_workspace/current_task_group/01_understanding_instructions.md'),
            Path(f'/test/path/supervisor_workspace/current_task_group/02_planning_instructions.md')
        ]
        with patch('pathlib.Path.glob', return_value=mock_files):
            result = manager.read_current_task(task_group_id=task_group_id)
            
            # 新的实现只返回状态标记
            assert result["status"] == "task_loaded"
            assert "file" in result
            # 应该返回第一个文件
            assert "01_understanding_instructions.md" in str(result["file"])

    def test_read_current_task_no_files(self):
        """测试读取当前任务信息时没有文件"""
        manager = FileManager(base_path='/test/path')
        
        # 模拟没有找到数字前缀的instruction文件
        task_group_id = "tg-456"
        with patch('pathlib.Path.glob', return_value=[]):
            with pytest.raises(FileNotFoundError) as exc_info:
                manager.read_current_task(task_group_id=task_group_id)
            assert "No numbered prefix instruction files found" in str(exc_info.value)
    
    def test_read_current_task_data(self):
        """测试读取当前任务数据"""
        manager = FileManager(base_path='/test/path')
        expected_task = {
            "id": "task-123",
            "title": "测试任务",
            "type": "PLANNING",
            "task_group": {"id": "tg-456"}
        }
        
        project_info = {
            "project_id": "test-proj",
            "current_task_group_id": "tg-456",
            "task_groups": {
                "tg-456": {
                    "current_task": expected_task
                }
            }
        }
        
        with patch.object(manager, 'read_project_info', return_value=project_info):
            result = manager.read_current_task_data()
            assert result == expected_task
    
    def test_read_current_task_data_no_current_task(self):
        """测试读取当前任务数据时没有当前任务"""
        manager = FileManager(base_path='/test/path')
        
        project_info = {
            "project_id": "test-proj"
            # 没有 current_task_group_id
        }
        
        with patch.object(manager, 'read_project_info', return_value=project_info):
            with pytest.raises(ValueError) as exc_info:
                manager.read_current_task_data()
            assert "No current task group found" in str(exc_info.value)





    def test_has_project_info(self):
        """测试检查项目信息是否存在"""
        manager = FileManager(base_path='/test/path')
        
        with patch('pathlib.Path.exists', return_value=True):
            assert manager.has_project_info() is True
            
        with patch('pathlib.Path.exists', return_value=False):
            assert manager.has_project_info() is False

    def test_has_current_task_with_numbered_prefix(self):
        """测试检查指定任务组的当前任务是否存在（支持数字前缀命名策略）"""
        manager = FileManager(base_path='/test/path')
        task_group_id = "tg-456"
        
        # 模拟找到数字前缀的instruction文件
        mock_files = [
            Path(f'/test/path/.supervisor/task_groups/task_group_{task_group_id}/01_understanding_instructions.md'),
            Path(f'/test/path/.supervisor/task_groups/task_group_{task_group_id}/02_planning_instructions.md')
        ]
        with patch('pathlib.Path.glob', return_value=mock_files):
            assert manager.has_current_task(task_group_id=task_group_id) is True
            
        # 模拟没有找到instruction文件
        with patch('pathlib.Path.glob', return_value=[]):
            assert manager.has_current_task(task_group_id=task_group_id) is False

    def test_has_current_task_no_files(self):
        """测试检查指定任务组的当前任务是否存在（没有数字前缀文件）"""
        manager = FileManager(base_path='/test/path')
        task_group_id = "tg-456"
        
        # 模拟没有找到数字前缀instruction文件
        with patch('pathlib.Path.glob', return_value=[]):
            assert manager.has_current_task(task_group_id=task_group_id) is False

    def test_file_operation_error_handling(self):
        """测试文件操作错误处理"""
        manager = FileManager(base_path='/test/path')
        
        # 测试权限错误
        with patch('builtins.open', side_effect=PermissionError("No permission")):
            with pytest.raises(PermissionError) as exc_info:
                manager.save_project_info({"test": "data"})
            assert "No permission" in str(exc_info.value)
        
        # 测试磁盘空间错误 - 使用正确的数据格式
        valid_task_data = {
            "task": {
                "id": "test-123",
                "type": "UNDERSTANDING",
                "description": "Test task"
            }
        }
        with patch('builtins.open', side_effect=OSError("No space left")):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with pytest.raises(OSError) as exc_info:
                    # 直接提供task_order和task_group_id，避免复杂的API调用逻辑
                    manager.save_current_task(valid_task_data, task_group_id="tg-456", task_order=1)
                assert "No space left" in str(exc_info.value)
    
    def test_save_task_result_with_task_order(self):
        """测试保存任务结果（使用task_order参数）"""
        manager = FileManager(base_path='/test/path')
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            # 直接提供task_order和task_group_id参数（正确的做法）
            task_group_id = "tg-456"
            manager.save_task_result('UNDERSTANDING', '# Understanding Results\n\nThis is the analysis.', task_group_id=task_group_id, task_order=3)
            
            # 验证调用了open写入结果文件（使用传入的task_order：03_understanding_results.md）
            result_call_found = False
            for call in mock_file.call_args_list:
                if call[0][0] == Path(f'/test/path/supervisor_workspace/current_task_group/03_understanding_results.md'):
                    result_call_found = True
                    assert call[0][1] == 'w'
                    assert call[1]['encoding'] == 'utf-8'
            assert result_call_found, f"Expected file '03_understanding_results.md' not found in calls: {[str(call[0][0]) for call in mock_file.call_args_list]}"
            
            # 测试implementing类型不保存结果文件
            mock_file.reset_mock()
            manager.save_task_result('IMPLEMENTING', 'Some implementation content', task_group_id=task_group_id, task_order=3)
            
            # 验证没有调用open（implementing不保存结果文件）
            assert len(mock_file.call_args_list) == 0

    def test_save_task_result_auto_detect_order(self):
        """测试保存任务结果时自动检测序号"""
        manager = FileManager(base_path='/test/path')
        
        # 模拟存在对应的instruction文件
        task_group_id = "tg-456"
        mock_instruction_files = [Path(f'/test/path/supervisor_workspace/current_task_group/02_understanding_instructions.md')]
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.glob', return_value=mock_instruction_files):
                manager.save_task_result('UNDERSTANDING', '# Understanding Results\n\nThis is the analysis.', task_group_id=task_group_id)
                
                # 验证使用了instruction文件的前缀（02）
                result_call_found = False
                for call in mock_file.call_args_list:
                    if call[0][0] == Path(f'/test/path/supervisor_workspace/current_task_group/02_understanding_results.md'):
                        result_call_found = True
                assert result_call_found, "Should create result file with same prefix as instruction file"
    
    # 移除了test_get_task_group_completed_count和test_get_task_group_completed_count_error测试
    # 原因：get_task_group_completed_count方法已删除，不再需要复杂的异步API调用逻辑

    def test_cleanup_task_group_files(self):
        """测试清理任务组文件"""
        manager = FileManager(base_path='/test/path')
        
        with patch('shutil.rmtree') as mock_rmtree:
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.mkdir') as mock_mkdir:  # Mock mkdir调用
                    with patch.object(manager, 'read_project_info', return_value={'current_task_group_id': 'tg-456', 'task_groups': {'tg-456': {'current_task': {'id': 'task-123'}}}}):
                        with patch.object(manager, 'save_project_info') as mock_save_project:
                            task_group_id = "tg-456"
                            manager.cleanup_task_group_files(task_group_id)
                            
                            # 验证调用了rmtree来清理current_task_group和暂存目录
                            assert mock_rmtree.call_count >= 1
                            
                            # 验证重新创建了current_task_group目录
                            mock_mkdir.assert_called()
                            
                            # 验证清理了项目信息中的任务组信息
                            mock_save_project.assert_called_once()
                            saved_info = mock_save_project.call_args[0][0]
                            assert task_group_id not in saved_info.get('task_groups', {})

    def test_save_user_info(self):
        """测试保存用户信息（新文件）"""
        manager = FileManager(base_path='/test/path')
        user_info = {
            "user_id": "123",
            "username": "testuser",
            "access_token": "token456"
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=False):  # 文件不存在
                with patch.object(manager, 'create_supervisor_directory'):  # mock目录创建
                    manager.save_user_info(user_info)
                
                # 验证写入了正确的文件路径
                mock_file.assert_called_once_with(
                    Path('/test/path/.supervisor/user.json'), 
                    'w', 
                    encoding='utf-8'
                )
                
                # 验证写入了正确的JSON内容
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                assert written_data == user_info

    def test_save_user_info_update_existing(self):
        """测试保存用户信息（更新现有文件）"""
        manager = FileManager(base_path='/test/path')
        
        # 现有文件内容
        existing_info = {
            "user_id": "123",
            "username": "olduser"
        }
        
        # 新要保存的用户信息
        new_user_info = {
            "user_id": "456",
            "username": "newuser",
            "access_token": "newtoken"
        }
        
        # 模拟文件存在，读取时返回现有信息
        mock_file = mock_open(read_data=json.dumps(existing_info))
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.exists', return_value=True):  # 文件存在
                with patch.object(manager, 'create_supervisor_directory'):  # mock目录创建
                    manager.save_user_info(new_user_info)
                
                # 验证调用了读取和写入
                calls = mock_file.call_args_list
                assert len(calls) == 2  # 一次读取，一次写入
                
                # 验证写入的内容更新了用户信息
                written_content = ''.join(
                    call.args[0] for call in mock_file().write.call_args_list
                )
                written_data = json.loads(written_content)
                
                # 应该更新所有字段
                assert written_data["user_id"] == "456"
                assert written_data["username"] == "newuser"
                assert written_data["access_token"] == "newtoken"

    def test_read_user_info(self):
        """测试读取用户信息"""
        manager = FileManager(base_path='/test/path')
        expected_info = {
            "user_id": "123",
            "username": "testuser",
            "access_token": "token456"
        }
        
        mock_file = mock_open(read_data=json.dumps(expected_info))
        with patch('builtins.open', mock_file):
            result = manager.read_user_info()
            
            assert result == expected_info
            mock_file.assert_called_once_with(
                Path('/test/path/.supervisor/user.json'), 
                'r', 
                encoding='utf-8'
            )

    def test_read_user_info_file_not_found(self):
        """测试读取不存在的用户信息文件"""
        manager = FileManager(base_path='/test/path')
        
        with patch('builtins.open', side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError) as exc_info:
                manager.read_user_info()
            assert "user.json not found" in str(exc_info.value)

    def test_has_user_info(self):
        """测试检查用户信息文件是否存在"""
        manager = FileManager(base_path='/test/path')
        
        with patch('pathlib.Path.exists', return_value=True):
            assert manager.has_user_info() == True
            
        with patch('pathlib.Path.exists', return_value=False):
            assert manager.has_user_info() == False