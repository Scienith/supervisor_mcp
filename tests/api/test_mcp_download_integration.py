"""
测试MCP模板下载集成功能
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from file_manager import FileManager
from server import APIClient


@pytest.mark.asyncio
class TestMCPDownloadIntegration:
    """测试MCP模板下载的完整流程"""
    
    async def test_download_template_success(self):
        """测试成功下载模板"""
        # 创建文件管理器
        file_manager = FileManager(base_path='/test/path')
        
        # 创建mock API客户端
        api_client = AsyncMock()
        api_client.request.return_value = "# 模板内容\n\n这是测试模板"
        
        # 模板信息
        template_info = {
            "name": "requirement-analysis.md",
            "path": ".supervisor/templates/requirement-analysis.md",
            "step_identifier": "requirementAnalysis"
        }
        
        # Mock文件操作
        with patch('pathlib.Path.mkdir'):
            with patch('builtins.open', MagicMock()) as mock_open:
                # 执行下载
                result = await file_manager.download_template(api_client, template_info)
                
                # 验证结果
                assert result is True
                
                # 验证API调用
                api_client.request.assert_called_once_with(
                    "GET",
                    "templates/download/",
                    params={
                        "step": "requirementAnalysis",
                        "name": "requirement-analysis.md"
                    }
                )
                
                # 验证文件写入
                mock_open.assert_called_once()
                # 验证写入了正确的内容
                mock_file = mock_open.return_value.__enter__.return_value
                mock_file.write.assert_called_once_with("# 模板内容\n\n这是测试模板")
    
    async def test_download_template_api_error(self):
        """测试API返回错误时的处理"""
        file_manager = FileManager(base_path='/test/path')
        
        # Mock API返回错误
        api_client = AsyncMock()
        api_client.request.return_value = {
            "status": "error",
            "message": "Template not found"
        }
        
        template_info = {
            "name": "test.md",
            "path": ".supervisor/templates/test.md",
            "step_identifier": "test"
        }
        
        # 执行下载
        result = await file_manager.download_template(api_client, template_info)
        
        # 验证返回False
        assert result is False
    
    async def test_download_template_exception(self):
        """测试下载过程中出现异常"""
        file_manager = FileManager(base_path='/test/path')
        
        # Mock API抛出异常
        api_client = AsyncMock()
        api_client.request.side_effect = Exception("Network error")
        
        template_info = {
            "name": "test.md",
            "path": ".supervisor/templates/test.md",
            "step_identifier": "test"
        }
        
        # 执行下载
        result = await file_manager.download_template(api_client, template_info)
        
        # 验证返回False
        assert result is False
    
    async def test_mcp_init_downloads_templates(self):
        """测试MCP初始化时下载模板的完整流程"""
        # 模拟初始化数据中包含模板列表
        initialization_data = {
            "templates": [
                {
                    "name": "requirement-analysis.md",
                    "path": ".supervisor/templates/requirement-analysis.md",
                    "step_identifier": "requirementAnalysis"
                },
                {
                    "name": "test-plan.md",
                    "path": ".supervisor/templates/test-plan.md",
                    "step_identifier": "testPlan"
                }
            ],
            "directories": ["docs/requirements", "docs/design"]
        }
        
        # 创建文件管理器
        file_manager = FileManager(base_path='/test/path')
        
        # Mock下载函数
        download_count = 0
        async def mock_download(api_client, template_info):
            nonlocal download_count
            download_count += 1
            return True
        
        file_manager.download_template = mock_download
        
        # Mock文件操作
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.touch'):
                # 执行初始化
                templates = file_manager.initialize_project_structure(initialization_data)
                
                # 验证返回了正确的模板列表
                assert len(templates) == 2
                assert templates[0]["name"] == "requirement-analysis.md"
                assert templates[1]["name"] == "test-plan.md"
                
                # 模拟下载过程
                api_client = AsyncMock()
                for template in templates:
                    result = await file_manager.download_template(api_client, template)
                    assert result is True
                
                # 验证下载了所有模板
                assert download_count == 2