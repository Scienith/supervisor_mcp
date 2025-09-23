"""
测试文件保存功能的内容正确性
专门测试save_current_task方法对不同数据格式的内容提取和保存
"""

import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

from file_manager import FileManager


class TestSaveCurrentTaskContent:
    """测试save_current_task方法的内容处理逻辑"""

    def test_save_current_task_with_task_description(self):
        """测试从task.description字段提取并保存内容（当前MCP格式）"""
        manager = FileManager(base_path='/test/path')
        
        # 模拟实际的MCP数据格式
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "理解: 实施: VI 视觉识别设计",
                "type": "UNDERSTANDING",
                "status": "IN_PROGRESS",
                "description": "# 理解: 实施: VI 视觉识别设计\n\n这是任务描述内容\n\n## 任务说明\n- 执行要求1\n- 执行要求2"
            },
            "context": {"project_id": "test-proj"}
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test-proj"}):
                    with patch.object(manager, 'save_project_info'):
                        task_id = "tg-123"
                        manager.save_current_task_phase(full_data, task_id=task_id, task_phase_order=1)
                    
                    # 验证写入的内容是task.description（保存到当前任务组目录）
                    expected_path = Path('/test/path/supervisor_workspace/current_task/01_understanding_instructions.md')
                    mock_file.assert_called_with(
                        expected_path, 
                        'w', 
                        encoding='utf-8'
                    )
                    handle = mock_file()
                    handle.write.assert_called_once_with(full_data["task_phase"]["description"])

    def test_save_current_task_with_top_level_description(self):
        """测试标准API格式的数据处理"""
        manager = FileManager(base_path='/test/path')
        
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "测试任务",
                "type": "PLANNING",
                "description": "# 标准API格式任务描述\n\n这是从task.description提取的内容"
            }
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch.object(manager, 'read_project_info', return_value={}):
                    with patch.object(manager, 'save_project_info'):
                        manager.save_current_task_phase(full_data, task_id="tg-123", task_phase_order=1)
                    
                    handle = mock_file()
                    handle.write.assert_called_once_with("# 标准API格式任务描述\n\n这是从task.description提取的内容")

    def test_save_current_task_with_context_markdown(self):
        """测试标准API格式的IMPLEMENTING任务"""
        manager = FileManager(base_path='/test/path')
        
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "测试任务",
                "type": "IMPLEMENTING",
                "description": "# 实现任务\n\n这是标准API格式的实现任务描述"
            }
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch.object(manager, 'read_project_info', return_value={}):
                    with patch.object(manager, 'save_project_info'):
                        manager.save_current_task_phase(full_data, task_id="tg-123", task_phase_order=1)
                    
                    handle = mock_file()
                    handle.write.assert_called_once_with("# 实现任务\n\n这是标准API格式的实现任务描述")

    def test_save_current_task_empty_content(self):
        """测试没有description字段时的错误处理"""
        manager = FileManager(base_path='/test/path')
        
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "测试任务",
                "type": "VALIDATION"
                # 没有description字段 - 这应该引发错误
            },
            "context": {}
        }
        
        # 即使mock目录创建，也会因为缺少description字段而抛出错误
        with patch('pathlib.Path.mkdir'):  # Mock directory creation
            with pytest.raises(ValueError, match="Invalid task phase data format"):
                manager.save_current_task_phase(full_data, task_id="tg-123", task_phase_order=1)

    def test_save_current_task_priority_order(self):
        """测试标准格式的任务描述使用"""
        manager = FileManager(base_path='/test/path')
        
        # 只使用标准的task.description格式
        full_data = {
            "task_phase": {
                "id": "task-123",
                "title": "测试任务",
                "type": "FIXING",
                "description": "任务描述"  # 标准格式
            }
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch.object(manager, 'read_project_info', return_value={}):
                    with patch.object(manager, 'save_project_info'):
                        manager.save_current_task_phase(full_data, task_id="tg-123", task_phase_order=1)
                    
                    # 应该使用task.description
                    handle = mock_file()
                    handle.write.assert_called_once_with("任务描述")

    def test_save_current_task_real_mcp_data_format(self):
        """测试真实的MCP数据格式"""
        manager = FileManager(base_path='/test/path')
        
        # 这是实际从MCP服务器返回的数据格式
        real_mcp_data = {
            "task_phase": {
                "id": "5b4b24a9-eb44-4938-965a-e0d216c5fbd3",
                "title": "理解: 实施: VI 视觉识别设计",
                "type": "UNDERSTANDING",
                "status": "IN_PROGRESS",
                "task_id": "684b158a-a391-490c-9139-010636ebf0ee",
                "description": "# 理解: 实施: VI 视觉识别设计\n\n理解 '实施: VI 视觉识别设计' 的需求和目标\n\n**任务类型**: UNDERSTANDING\n\n## 现状理解\n\n### 上游工作产出\n- 暂无上游工作产出"
            },
            "context": {}
        }
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file):
            with patch('pathlib.Path.mkdir'):  # Mock directory creation
                with patch.object(manager, 'read_project_info', return_value={"project_id": "test"}):
                    with patch.object(manager, 'save_project_info'):
                        manager.save_current_task_phase(real_mcp_data, task_id="tg-123", task_phase_order=1)
                    
                    # 验证内容正确保存
                    handle = mock_file()
                    expected_content = real_mcp_data["task_phase"]["description"]
                    handle.write.assert_called_once_with(expected_content)
                    
                    # 验证内容不为空
                    assert len(expected_content) > 0
                    assert "理解: 实施: VI 视觉识别设计" in expected_content
                    assert "## 现状理解" in expected_content