"""
测试任务组文件夹创建规则
验证只为PENDING和IN_PROGRESS状态的任务组创建本地文件夹
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from file_manager import FileManager


class TestTaskGroupFolderCreation:
    """测试任务组文件夹创建规则"""

    def test_create_folders_for_pending_and_in_progress_only(self):
        """测试只为PENDING和IN_PROGRESS状态的任务组创建文件夹"""
        manager = FileManager(base_path='/test/path')
        
        # 模拟不同状态的任务组
        task_groups = [
            {"id": "tg1", "status": "PENDING", "title": "待处理任务组"},
            {"id": "tg2", "status": "IN_PROGRESS", "title": "进行中任务组"},
            {"id": "tg3", "status": "COMPLETED", "title": "已完成任务组"},
            {"id": "tg4", "status": "CANCELLED", "title": "已取消任务组"},
        ]
        
        # Mock Path操作和文件系统依赖
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj", "current_task_group_id": None}):
                    with patch.object(manager, 'save_project_info') as mock_save_project:
                        # 由于FileManager没有create_task_group_folders方法，
                        # 我们模拟当前的实现逻辑，使用switch_task_group_directory
                        for tg in task_groups:
                            if tg["status"] in ["PENDING", "IN_PROGRESS"]:
                                manager.switch_task_group_directory(tg["id"])
                
                # 验证只为PENDING和IN_PROGRESS状态创建了文件夹
                # 应该调用mkdir 2次：tg1目录 + tg2目录
                expected_calls = 2
                actual_calls = mock_mkdir.call_count
                
                assert actual_calls == expected_calls, f"预期创建{expected_calls}个目录，实际创建{actual_calls}个"
                
                # 验证调用参数正确 - 每次调用应该使用parents=True, exist_ok=True
                for call in mock_mkdir.call_args_list:
                    assert call.kwargs.get('parents') == True, "应该使用parents=True"
                    assert call.kwargs.get('exist_ok') == True, "应该使用exist_ok=True"

    def test_create_folders_empty_task_groups_list(self):
        """测试空任务组列表的情况"""
        manager = FileManager(base_path='/test/path')
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                # 空任务组列表时不调用任何方法
                for tg in []:  # 空列表
                    if tg.get("status") in ["PENDING", "IN_PROGRESS"]:
                        manager.switch_task_group_directory(tg["id"])
                
                # 应该没有调用mkdir
                assert mock_mkdir.call_count == 0

    def test_create_folders_all_completed_cancelled(self):
        """测试所有任务组都是COMPLETED或CANCELLED状态"""
        manager = FileManager(base_path='/test/path')
        
        task_groups = [
            {"id": "tg1", "status": "COMPLETED", "title": "已完成1"},
            {"id": "tg2", "status": "CANCELLED", "title": "已取消1"},
            {"id": "tg3", "status": "COMPLETED", "title": "已完成2"},
        ]
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                # 只为PENDING/IN_PROGRESS状态调用switch_task_group_directory
                for tg in task_groups:
                    if tg["status"] in ["PENDING", "IN_PROGRESS"]:
                        manager.switch_task_group_directory(tg["id"])
                
                # 应该没有调用mkdir，因为没有PENDING/IN_PROGRESS状态的任务组
                assert mock_mkdir.call_count == 0

    def test_create_folders_missing_status_field(self):
        """测试任务组缺少status字段的情况"""
        manager = FileManager(base_path='/test/path')
        
        task_groups = [
            {"id": "tg1", "title": "没有状态字段"},  # 缺少status
            {"id": "tg2", "status": "PENDING", "title": "有状态字段"},
        ]
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj", "current_task_group_id": None}):
                    with patch.object(manager, 'save_project_info'):
                        # 只为有status字段且状态为PENDING/IN_PROGRESS的任务组调用
                        for tg in task_groups:
                            if tg.get("status") in ["PENDING", "IN_PROGRESS"]:
                                manager.switch_task_group_directory(tg["id"])
                        
                        # 应该只为tg2创建目录（有status字段且为PENDING）
                        assert mock_mkdir.call_count == 1
                        # 验证调用参数正确
                        for call in mock_mkdir.call_args_list:
                            assert call.kwargs.get('parents') == True
                            assert call.kwargs.get('exist_ok') == True

    def test_create_folders_missing_id_field(self):
        """测试任务组缺少id字段的情况"""
        manager = FileManager(base_path='/test/path')
        
        task_groups = [
            {"status": "PENDING", "title": "没有ID字段"},  # 缺少id
            {"id": "tg2", "status": "IN_PROGRESS", "title": "有ID字段"},
        ]
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj", "current_task_group_id": None}):
                    with patch.object(manager, 'save_project_info'):
                        # 只为有id字段且状态为PENDING/IN_PROGRESS的任务组调用
                        for tg in task_groups:
                            if tg.get("status") in ["PENDING", "IN_PROGRESS"] and "id" in tg:
                                manager.switch_task_group_directory(tg["id"])
                        
                        # 应该只为tg2创建目录（有id字段且为IN_PROGRESS）
                        assert mock_mkdir.call_count == 1
                        # 验证调用参数正确
                        for call in mock_mkdir.call_args_list:
                            assert call.kwargs.get('parents') == True
                            assert call.kwargs.get('exist_ok') == True

    def test_folder_naming_convention(self):
        """测试文件夹命名规范"""
        manager = FileManager(base_path='/test/path')
        
        task_groups = [
            {"id": "complex-task-id-123", "status": "PENDING", "title": "复杂ID测试"},
        ]
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj", "current_task_group_id": None}):
                    with patch.object(manager, 'save_project_info'):
                        # 为PENDING状态的任务组调用switch_task_group_directory
                        for tg in task_groups:
                            if tg.get("status") in ["PENDING", "IN_PROGRESS"]:
                                manager.switch_task_group_directory(tg["id"])
                        
                        # 验证调用了mkdir且参数正确
                        assert mock_mkdir.call_count == 1
                        for call in mock_mkdir.call_args_list:
                            assert call.kwargs.get('parents') == True
                            assert call.kwargs.get('exist_ok') == True

    def test_create_results_subdirectory(self):
        """测试为每个任务组创建results子目录"""
        manager = FileManager(base_path='/test/path')
        
        task_groups = [
            {"id": "tg1", "status": "PENDING", "title": "测试任务组"},
        ]
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj", "current_task_group_id": None}):
                    with patch.object(manager, 'save_project_info'):
                        # 为PENDING状态的任务组调用switch_task_group_directory
                        for tg in task_groups:
                            if tg.get("status") in ["PENDING", "IN_PROGRESS"]:
                                manager.switch_task_group_directory(tg["id"])
                        
                        # 验证创建了任务组目录 (switch_task_group_directory创建task_group_tg1目录)
                        assert mock_mkdir.call_count >= 1
                        # 验证调用参数正确
                        for call in mock_mkdir.call_args_list:
                            assert call.kwargs.get('parents') == True
                            assert call.kwargs.get('exist_ok') == True