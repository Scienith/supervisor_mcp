"""
测试FileManager的项目初始化功能
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call
from file_manager import FileManager


class TestFileManagerInitialization:
    """测试文件管理器的项目初始化功能"""

    def test_initialize_project_structure_creates_directories(self):
        """测试初始化项目结构创建必要的目录"""
        manager = FileManager(base_path='/test/path')
        
        initialization_data = {
            "templates": {
                "requirement-analysis.md": "# Template content",
                "test-plan.md": "# Test plan template"
            },
            "directories": [
                "docs/requirements",
                "docs/design",
                "docs/test"
            ]
        }
        
        # Mock Path操作
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.touch') as mock_touch:
                with patch('builtins.open', mock_open()) as mock_file:
                    manager.initialize_project_structure(initialization_data)
                    
                    # 验证创建了必要的目录
                    assert mock_mkdir.called
                    # 应该创建 .supervisor, task_groups 和 templates 目录
                    assert mock_mkdir.call_count == 3  # .supervisor + task_groups + templates
                    
                    # 不再创建docs目录，所以不创建.gitkeep文件
                    assert not mock_touch.called

    def test_initialize_project_structure_returns_templates(self):
        """测试初始化项目结构返回模板列表"""
        manager = FileManager(base_path='/test/path')
        
        initialization_data = {
            "templates": [
                {
                    "name": "requirement-analysis.md",
                    "path": ".supervisor/templates/需求分析/requirementAnalysis/requirement-analysis.md",
                    "step_identifier": "requirementAnalysis"
                },
                {
                    "name": "test-plan.md",
                    "path": ".supervisor/templates/测试验证/testPlan/test-plan.md",
                    "step_identifier": "testPlan"
                }
            ],
            "directories": []
        }
        
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.touch'):
                with patch('builtins.open', mock_open()):
                    templates = manager.initialize_project_structure(initialization_data)
                    
                    # 验证返回了模板列表
                    assert len(templates) == 2
                    assert templates[0]["name"] == "requirement-analysis.md"
                    assert templates[1]["name"] == "test-plan.md"

    def test_initialize_project_structure_empty_data(self):
        """测试处理空的初始化数据"""
        manager = FileManager(base_path='/test/path')
        
        initialization_data = {
            "templates": {},
            "directories": []
        }
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.touch') as mock_touch:
                with patch('builtins.open', mock_open()):
                    # 不应该抛出异常
                    manager.initialize_project_structure(initialization_data)
                    
                    # 应该至少创建基础目录
                    assert mock_mkdir.called
                    
                    # 不应该创建.gitkeep文件（因为没有子目录）
                    assert mock_touch.call_count == 0

    def test_initialize_project_structure_creates_gitkeep(self):
        """测试在每个目录创建.gitkeep文件"""
        manager = FileManager(base_path='/test/path')
        
        initialization_data = {
            "templates": {},
            "directories": [
                "docs/requirements",
                "docs/design",
                "src/components"
            ]
        }
        
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.touch') as mock_touch:
                with patch('builtins.open', mock_open()):
                    manager.initialize_project_structure(initialization_data)
                    
                    # 不再创建docs目录，所以不创建.gitkeep文件
                    assert mock_touch.call_count == 0