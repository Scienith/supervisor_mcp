"""
测试模板下载到正确路径：supervisor_workspace/templates
采用TDD方式：先写失败的测试（红灯），然后修复实现（绿灯）
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from file_manager import FileManager


class TestTemplateDownloadPath:
    """测试模板下载到supervisor_workspace/templates路径"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def file_manager(self, temp_dir):
        """创建FileManager实例"""
        return FileManager(base_path=str(temp_dir))
    
    @pytest.mark.asyncio
    async def test_template_should_download_to_workspace_templates_dir(self, file_manager, temp_dir):
        """测试模板应该下载到supervisor_workspace/templates目录下"""
        # 模板信息
        template_info = {
            "name": "requirement-analysis.md",
            "path": "templates/understanding/requirement-analysis.md",  # 后端返回的相对路径
            "step_identifier": "understanding",
            "content": "# 需求分析模板\n\n这是需求分析模板的内容"
        }
        
        api_client = AsyncMock()
        
        # 执行下载
        result = await file_manager.download_template(api_client, template_info)
        
        # 验证下载成功
        assert result is True
        
        # 关键验证：文件应该在supervisor_workspace/templates目录下
        expected_path = temp_dir / "supervisor_workspace" / "templates" / "understanding" / "requirement-analysis.md"
        assert expected_path.exists(), f"模板文件应该在 {expected_path}"
        
        # 验证目录结构
        workspace_dir = temp_dir / "supervisor_workspace"
        assert workspace_dir.exists(), "supervisor_workspace目录应该存在"
        
        templates_dir = workspace_dir / "templates"
        assert templates_dir.exists(), "supervisor_workspace/templates目录应该存在"
        
        step_dir = templates_dir / "understanding"
        assert step_dir.exists(), "步骤子目录应该在templates下"
        
        # 验证文件内容
        with open(expected_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert content == template_info["content"]
    
    @pytest.mark.asyncio
    async def test_multiple_templates_same_step(self, file_manager, temp_dir):
        """测试同一个步骤的多个模板都下载到正确位置"""
        templates = [
            {
                "name": "template1.md",
                "path": "templates/planning/template1.md",
                "step_identifier": "planning", 
                "content": "模板1内容"
            },
            {
                "name": "template2.md", 
                "path": "templates/planning/template2.md",
                "step_identifier": "planning",
                "content": "模板2内容"
            }
        ]
        
        api_client = AsyncMock()
        
        # 下载所有模板
        for template_info in templates:
            result = await file_manager.download_template(api_client, template_info)
            assert result is True
        
        # 验证都在supervisor_workspace/templates/planning目录下
        planning_dir = temp_dir / "supervisor_workspace" / "templates" / "planning"
        assert planning_dir.exists()
        
        template1_path = planning_dir / "template1.md"
        template2_path = planning_dir / "template2.md"
        
        assert template1_path.exists()
        assert template2_path.exists()
        
        # 验证内容
        assert template1_path.read_text(encoding='utf-8') == "模板1内容"
        assert template2_path.read_text(encoding='utf-8') == "模板2内容"
        
    def test_templates_dir_property_points_to_workspace(self, file_manager, temp_dir):
        """测试FileManager.templates_dir属性指向正确的工作区路径"""
        expected_templates_dir = temp_dir / "supervisor_workspace" / "templates"
        assert file_manager.templates_dir == expected_templates_dir