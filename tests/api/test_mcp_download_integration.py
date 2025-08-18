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
        """测试成功下载模板 - 使用正确的API设计"""
        # 创建文件管理器
        file_manager = FileManager(base_path='/test/path')
        
        # 模拟模板内容
        template_content = "# 模板内容\n\n这是测试模板"
        
        # API客户端不应该被调用，因为content已经包含在template_info中
        api_client = AsyncMock()
        
        # 模板信息 - 新的按步骤下载设计：使用 stage/step_identifier/template_name 结构
        template_info = {
            "name": "requirement-analysis.md",
            "path": ".supervisor/templates/需求分析/requirementAnalysis/requirement-analysis.md",
            "step_identifier": "requirementAnalysis",
            "content": template_content  # 从步骤API获取的模板内容
        }
        
        # Mock文件操作
        with patch('pathlib.Path.mkdir'):
            with patch('builtins.open', MagicMock()) as mock_open:
                # 执行下载
                result = await file_manager.download_template(api_client, template_info)
                
                # 验证结果
                assert result is True
                
                # 验证API不应该被调用（因为content已经包含完整内容）
                api_client.request.assert_not_called()
                
                # 验证文件写入
                mock_open.assert_called_once()
                # 验证写入了正确的内容
                mock_file = mock_open.return_value.__enter__.return_value
                mock_file.write.assert_called_once_with(template_content)
    
    async def test_download_template_missing_content(self):
        """测试模板信息缺少content字段时抛出异常"""
        file_manager = FileManager(base_path='/test/path')
        
        # API客户端不会被调用
        api_client = AsyncMock()
        
        # 模板信息缺少content字段
        template_info = {
            "name": "test.md",
            "path": ".supervisor/templates/测试阶段/test/test.md",
            "step_identifier": "test"
            # 缺少 "content" 字段
        }
        
        # 执行下载应该返回False（异常被捕获）
        result = await file_manager.download_template(api_client, template_info)
        
        # 验证返回False（因为异常被捕获）
        assert result is False
    
    async def test_download_template_empty_content(self):
        """测试模板content字段为空时抛出异常"""
        file_manager = FileManager(base_path='/test/path')
        
        api_client = AsyncMock()
        
        # 模板信息content字段为空
        template_info = {
            "name": "test.md",
            "path": ".supervisor/templates/测试阶段/test/test.md", 
            "step_identifier": "test",
            "content": ""  # 空的content字段
        }
        
        # 执行下载应该返回False（异常被捕获）
        result = await file_manager.download_template(api_client, template_info)
        
        # 验证返回False（因为异常被捕获）
        assert result is False
    
    async def test_mcp_init_downloads_templates(self):
        """测试MCP初始化时下载模板的完整流程"""
        # 模拟新的按步骤下载设计的模板数据
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