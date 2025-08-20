import pytest
from unittest.mock import Mock, patch, AsyncMock
import json
from pathlib import Path
import tempfile
import shutil

# 导入要测试的类和函数
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from service import MCPService
from session import SessionManager
from file_manager import FileManager


class TestSOPUpdateTools:
    """测试SOP更新相关的工具"""

    def setup_method(self):
        """每个测试方法的设置"""
        # 创建临时目录
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # 创建MCPService实例
        self.service = MCPService()
        
        # Mock file_manager使用临时目录
        self.service.file_manager = FileManager(base_path=self.temp_dir)
        
        # Mock session_manager为已认证状态
        self.service.session_manager = Mock(spec=SessionManager)
        self.service.session_manager.is_authenticated.return_value = True
        self.service.session_manager.get_headers.return_value = {
            'Authorization': 'Bearer test_token',
            'Content-Type': 'application/json'
        }

    def teardown_method(self):
        """每个测试方法的清理"""
        # 清理临时目录
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @pytest.mark.asyncio
    async def test_update_step_rules_success(self):
        """测试成功更新步骤规则"""
        # 准备测试数据
        stage = "analysis"
        step_identifier = "contractConfirmation"
        step_id = "test_step_123"
        expected_rules = [
            {"type": "validation", "description": "检查输入参数"},
            {"type": "process", "description": "执行业务逻辑"}
        ]
        
        # Mock配置文件数据
        mock_config = {
            "step_id": step_id,
            "rules": expected_rules
        }
        
        # Mock API响应
        expected_response = {
            "status": "success",
            "message": "Rules updated successfully"
        }
        
        # Mock 文件读取方法
        with patch.object(self.service, '_read_step_config', return_value=mock_config):
            with patch('service.get_api_client') as mock_get_client:
                # 设置Mock客户端
                mock_client = AsyncMock()
                mock_client._client.headers = Mock()
                mock_client._client.headers.update = Mock()
                mock_client.request = AsyncMock(return_value=expected_response)
                mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # 执行测试
                result = await self.service.update_step_rules(stage, step_identifier)
                
                # 验证结果
                assert result == expected_response
                
                # 验证API调用
                mock_client.request.assert_called_once_with(
                    "PUT",
                    f"steps/{step_id}/rules",
                    json={"rules": expected_rules}
                )
                
                # 验证设置了正确的认证头
                mock_client._client.headers.update.assert_called_once_with({
                    'Authorization': 'Bearer test_token',
                    'Content-Type': 'application/json'
                })

    @pytest.mark.asyncio
    async def test_update_step_rules_not_authenticated(self):
        """测试未认证时更新步骤规则"""
        # 设置为未认证状态
        self.service.session_manager.is_authenticated.return_value = False
        
        # 执行测试
        result = await self.service.update_step_rules("analysis", "contractConfirmation")
        
        # 验证返回认证错误
        assert result['status'] == 'error'
        assert result['error_code'] == 'AUTH_001'
        assert result['message'] == '请先登录'

    @pytest.mark.asyncio
    async def test_update_step_rules_api_error(self):
        """测试API调用出错时的处理"""
        stage = "analysis" 
        step_identifier = "contractConfirmation"
        step_id = "test_step_123"
        expected_rules = [{"type": "validation"}]
        
        # Mock配置文件数据
        mock_config = {
            "step_id": step_id,
            "rules": expected_rules
        }
        
        # Mock 文件读取方法
        with patch.object(self.service, '_read_step_config', return_value=mock_config):
            with patch('service.get_api_client') as mock_get_client:
                # 设置Mock客户端抛出异常
                mock_client = AsyncMock()
                mock_client._client.headers = Mock()
                mock_client._client.headers.update = Mock()
                mock_client.request = AsyncMock(side_effect=Exception("Network error"))
                mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # 执行测试
                result = await self.service.update_step_rules(stage, step_identifier)
                
                # 验证错误处理
                assert result['status'] == 'error'
                assert 'Network error' in result['message']

    @pytest.mark.asyncio
    async def test_update_output_template_success(self):
        """测试成功更新输出模板"""
        # 准备测试数据
        stage = "analysis"
        step_identifier = "contractConfirmation"
        output_name = "API接口跟踪清单"
        output_id = "test_output_456"
        expected_template_content = "# 测试模板\n\n这是测试内容"
        
        # Mock output数据
        mock_output_data = {
            "output_id": output_id,
            "template_content": expected_template_content
        }
        
        # Mock API响应
        expected_response = {
            "status": "success",
            "message": "Template updated successfully"
        }
        
        # Mock 文件读取方法
        with patch.object(self.service, '_read_output_config_and_template', return_value=mock_output_data):
            with patch('service.get_api_client') as mock_get_client:
                # 设置Mock客户端
                mock_client = AsyncMock()
                mock_client._client.headers = Mock()
                mock_client._client.headers.update = Mock()
                mock_client._client.headers.__setitem__ = Mock()
                mock_client.request = AsyncMock(return_value=expected_response)
                mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # 执行测试
                result = await self.service.update_output_template(stage, step_identifier, output_name)
                
                # 验证结果
                assert result == expected_response
                
                # 验证API调用
                mock_client.request.assert_called_once_with(
                    "PUT",
                    f"outputs/{output_id}/template",
                    data=expected_template_content
                )
                
                # 验证至少调用了headers.update方法（设置认证头）
                assert mock_client._client.headers.update.call_count >= 1
                # 验证设置了Content-Type
                mock_client._client.headers.__setitem__.assert_any_call('Content-Type', 'text/plain')
                mock_client._client.headers.__setitem__.assert_any_call('Content-Type', 'application/json')

    @pytest.mark.asyncio
    async def test_update_output_template_not_authenticated(self):
        """测试未认证时更新输出模板"""
        # 设置为未认证状态
        self.service.session_manager.is_authenticated.return_value = False
        
        # 执行测试
        result = await self.service.update_output_template("analysis", "contractConfirmation", "API接口跟踪清单")
        
        # 验证返回认证错误
        assert result['status'] == 'error'
        assert result['error_code'] == 'AUTH_001'
        assert result['message'] == '请先登录'

    @pytest.mark.asyncio
    async def test_update_output_template_api_error(self):
        """测试API调用出错时的处理"""
        stage = "analysis"
        step_identifier = "contractConfirmation" 
        output_name = "API接口跟踪清单"
        output_id = "test_output_456"
        expected_template_content = "test content"
        
        # Mock output数据
        mock_output_data = {
            "output_id": output_id,
            "template_content": expected_template_content
        }
        
        # Mock 文件读取方法
        with patch.object(self.service, '_read_output_config_and_template', return_value=mock_output_data):
            with patch('service.get_api_client') as mock_get_client:
                # 设置Mock客户端抛出异常
                mock_client = AsyncMock()
                mock_client._client.headers = Mock()
                mock_client._client.headers.update = Mock()
                mock_client._client.headers.__setitem__ = Mock()
                mock_client.request = AsyncMock(side_effect=Exception("Connection timeout"))
                mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # 执行测试
                result = await self.service.update_output_template(stage, step_identifier, output_name)
                
                # 验证错误处理
                assert result['status'] == 'error'
                assert 'Connection timeout' in result['message']

    @pytest.mark.asyncio
    async def test_update_step_rules_file_not_found(self):
        """测试配置文件未找到"""
        stage = "nonexistent"
        step_identifier = "nonexistent_step"
        
        # Mock 文件读取方法返回None
        with patch.object(self.service, '_read_step_config', return_value=None):
            # 执行测试
            result = await self.service.update_step_rules(stage, step_identifier)
            
            # 验证错误处理
            assert result['status'] == 'error'
            assert f"未找到配置文件: sop/{stage}/{step_identifier}/config.json" in result['message']
    
    @pytest.mark.asyncio
    async def test_update_output_template_file_not_found(self):
        """测试输出配置或模板文件未找到"""
        stage = "analysis"
        step_identifier = "contractConfirmation"
        output_name = "nonexistent_output"
        
        # Mock 文件读取方法返回None
        with patch.object(self.service, '_read_output_config_and_template', return_value=None):
            # 执行测试
            result = await self.service.update_output_template(stage, step_identifier, output_name)
            
            # 验证错误处理
            assert result['status'] == 'error'
            assert f"未找到配置或模板: sop/{stage}/{step_identifier}/config.json 中名为 '{output_name}' 的output" in result['message']

    def test_method_signatures(self):
        """测试方法签名是否正确"""
        # 验证方法存在且可调用
        assert hasattr(self.service, 'update_step_rules')
        assert hasattr(self.service, 'update_output_template')
        assert callable(self.service.update_step_rules)
        assert callable(self.service.update_output_template)