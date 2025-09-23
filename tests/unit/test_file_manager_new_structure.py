"""
测试文件管理器的新文件结构 (tasks/task_{id})
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from file_manager import FileManager


class TestFileManagerNewStructure:
    """测试文件管理器的新文件结构"""

    def test_init_with_new_structure(self):
        """测试初始化时使用新的文件结构"""
        manager = FileManager(base_path='/test/path')
        assert manager.base_path == Path('/test/path')
        assert manager.supervisor_dir == Path('/test/path/.supervisor')
        assert manager.suspended_tasks_dir == Path('/test/path/.supervisor/suspended_tasks')
        assert manager.workspace_dir == Path('/test/path/supervisor_workspace')
        assert manager.templates_dir == Path('/test/path/supervisor_workspace/templates')
        assert manager.current_task_dir == Path('/test/path/supervisor_workspace/current_task')

    def test_create_supervisor_directory_with_new_structure(self):
        """测试创建新的supervisor目录结构"""
        manager = FileManager(base_path='/test/path')
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            manager.create_supervisor_directory()
            
            # 验证创建了正确的目录
            calls = mock_mkdir.call_args_list
            assert len(calls) == 5  # .supervisor + suspended_tasks + workspace_dir + sop + current_task
            # 验证所有调用都使用正确的参数
            for call in calls:
                assert call[1]['parents'] == True
                assert call[1]['exist_ok'] == True

    def test_save_current_task_with_task_id(self):
        """测试保存当前任务信息到指定任务组目录"""  
        manager = FileManager(base_path='/test/path')
        task_id = "tg-456"
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "实施开发任务",
                "type": "IMPLEMENTING",
                "status": "IN_PROGRESS",
                "task_id": task_id,
                "description": "# 实施开发任务\n\n这是任务描述内容"
            },
            "context": {"key": "value"}
        }
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('pathlib.Path.mkdir'):  # 模拟目录创建成功
                with patch.object(manager, 'create_supervisor_directory'):
                    with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj"}):
                        with patch.object(manager, 'save_project_info') as mock_save_project:
                            # 新接口：需要传递task_id
                            manager.save_current_task_phase(full_data, task_id=task_id, task_phase_order=4)
                            
                            # 验证文件保存到当前任务组目录
                            expected_path = Path('/test/path/supervisor_workspace/current_task/04_implementing_instructions.md')
                            md_call_found = False
                            for call in mock_file.call_args_list:
                                if call[0][0] == expected_path:
                                    md_call_found = True
                                    assert call[0][1] == 'w'
                                    assert call[1]['encoding'] == 'utf-8'
                            assert md_call_found, f"Expected file not found in calls: {[str(call[0][0]) for call in mock_file.call_args_list]}"
                            
                            # 验证项目信息更新
                            mock_save_project.assert_called_once()
                            saved_info = mock_save_project.call_args[0][0]
                            assert 'in_progress_task' in saved_info
                            assert saved_info['in_progress_task']['id'] == task_id

    def test_read_current_task_from_task(self):
        """测试从指定任务组目录读取当前任务"""
        manager = FileManager(base_path='/test/path')
        task_id = "tg-123"
        
        mock_files = [
            Path('/test/path/.supervisor/tasks/task_tg-123/01_understanding_instructions.md'),
            Path('/test/path/.supervisor/tasks/task_tg-123/02_planning_instructions.md')
        ]
        
        with patch('pathlib.Path.glob', return_value=mock_files):
            result = manager.read_current_task_phase(task_id=task_id)
            
            assert result["status"] == "task_phase_loaded"
            assert "01_understanding_instructions.md" in str(result["file"])

    def test_has_current_task_in_task(self):
        """测试检查指定任务组是否有当前任务"""
        manager = FileManager(base_path='/test/path')
        task_id = "tg-123"
        
        # Mock project info with current_task
        project_info = {
            "in_progress_task": {
                "id": task_id,
                "current_task_phase": {"id": "task-456", "title": "test task"}
            }
        }
        
        with patch.object(manager, 'read_project_info', return_value=project_info):
            assert manager.has_current_task_phase() is True
            
        # 测试没有current_task的情况
        project_info_no_task = {
            "in_progress_task": {
                "id": task_id
                # No current_task field
            }
        }
        
        with patch.object(manager, 'read_project_info', return_value=project_info_no_task):
            assert manager.has_current_task_phase() is False

    def test_switch_task_directory(self):
        """测试切换任务组目录"""
        manager = FileManager(base_path='/test/path')
        task_id = "tg-456"
        
        with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj"}):
            with patch.object(manager, 'save_project_info') as mock_save_project:
                manager.switch_task_directory(task_id)
                
                # 验证更新了项目信息
                mock_save_project.assert_called_once()
                saved_info = mock_save_project.call_args[0][0]
                assert saved_info["in_progress_task"]["id"] == task_id

    def test_get_current_task_phase_status(self):
        """测试获取当前任务组的任务状态"""
        manager = FileManager(base_path='/test/path')
        
        mock_files = [
            Path('/test/path/supervisor_workspace/current_task/01_understanding_instructions.md'),
            Path('/test/path/supervisor_workspace/current_task/02_planning_instructions.md')
        ]
        
        # 模拟文件stat信息，确保第二个文件有更新的时间戳
        mock_stat_1 = MagicMock()
        mock_stat_1.st_mtime = 1640995200  # 较早的时间戳
        mock_stat_2 = MagicMock() 
        mock_stat_2.st_mtime = 1640995300  # 较晚的时间戳
        
        with patch('pathlib.Path.glob', return_value=mock_files):
            with patch('pathlib.Path.stat', side_effect=[mock_stat_1, mock_stat_2]):
                result = manager.get_current_task_phase_status()
                
                assert result["has_current_task_phase"] is True
                assert result["task_phase_count"] == 2
                assert "02_planning_instructions.md" in result["latest_task_phase_file"]

    def test_project_info_structure(self):
        """测试新的project.json结构"""
        manager = FileManager(base_path='/test/path')
        
        # 新的project.json结构应该包含in_progress_task
        project_info = {
            "project_id": "proj-123",
            "in_progress_task": {
                "id": "tg-456",
                "title": "测试任务组",
                "status": "IN_PROGRESS"
            },
            "tasks": {
                "tg-456": {
                    "status": "IN_PROGRESS",
                    "order": 0
                },
                "tg-789": {
                    "status": "PENDING", 
                    "order": 1
                }
            }
        }
        
        with patch('builtins.open', mock_open()) as mock_file:
            manager.save_project_info(project_info)
            
            # 验证保存了正确的结构
            mock_file.assert_called_once()
            written_content = ''.join(call[0][0] for call in mock_file().write.call_args_list)
            parsed_content = json.loads(written_content)
            
            assert parsed_content["in_progress_task"]["id"] == "tg-456"
            assert "tasks" in parsed_content
            assert len(parsed_content["tasks"]) == 2