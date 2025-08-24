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


class TestSOPStructureCompleteness:
    """测试SOP结构下载是否包含完整字段"""

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
    async def test_sop_structure_should_include_rules_field(self):
        """测试SOP结构下载应包含rules字段"""
        # 准备测试数据 - 模拟后端返回完整的SOP数据
        step_identifier = 'contractConfirmation'
        database_step_id = 'step_db_12345'
        
        mock_sop_structure = {
            'steps': {
                step_identifier: {  # key是identifier，用于创建目录
                    'identifier': step_identifier,
                    'name': '契约确认（Checkpoint）',
                    'stage': 'analysis', 
                    'description': '确认上游冻结的对外API',
                    'step_id': database_step_id,  # 后端返回的数据库真实ID
                    'outputs': [
                        {
                            'output_id': 'output_001',
                            'name': 'API接口跟踪清单',
                            'template_filename': 'api-trace.md'
                        }
                    ],
                    'rules': [  # 这是关键的rules字段
                        {
                            'name': '契约冻结验证',
                            'when_condition': '开始Library开发前',
                            'must': ['上游API规格已冻结'],
                            'must_not': ['不得随意改变API名称']
                        }
                    ]
                }
            }
        }
        
        # 执行SOP结构设置
        await self.service._setup_sop_structure(mock_sop_structure)
        
        # 验证文件是否创建 - 文件路径使用identifier
        config_path = self.temp_dir / 'supervisor_workspace' / 'sop' / 'analysis' / step_identifier / 'config.json'
        assert config_path.exists(), f"配置文件应该存在: {config_path}"
        
        # 读取并验证配置文件内容
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 验证必须包含rules字段
        assert 'rules' in config_data, "配置文件必须包含rules字段"
        assert isinstance(config_data['rules'], list), "rules应该是数组类型"
        assert len(config_data['rules']) > 0, "rules数组不应该为空"
        
        # 验证rules内容正确
        first_rule = config_data['rules'][0]
        assert first_rule['name'] == '契约冻结验证'
        assert 'must' in first_rule
        assert 'must_not' in first_rule

    @pytest.mark.asyncio
    async def test_sop_structure_should_include_step_id_field(self):
        """测试SOP结构下载应包含step_id字段（数据库真实ID）"""
        # 准备测试数据 - 模拟后端返回的格式
        database_step_id = 'step_db_12345'  # 数据库真实ID
        step_identifier = 'contractConfirmation'  # identifier用作目录名
        
        mock_sop_structure = {
            'steps': {
                step_identifier: {  # key是identifier，用于创建目录
                    'identifier': step_identifier,
                    'name': '契约确认（Checkpoint）',
                    'stage': 'analysis',
                    'description': '确认上游冻结的对外API',
                    'step_id': database_step_id,  # 后端应该返回的数据库真实ID
                    'outputs': [],
                    'rules': []
                }
            }
        }
        
        # 执行SOP结构设置
        await self.service._setup_sop_structure(mock_sop_structure)
        
        # 验证配置文件内容 - 文件路径使用identifier
        config_path = self.temp_dir / 'supervisor_workspace' / 'sop' / 'analysis' / step_identifier / 'config.json'
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 验证必须包含step_id字段，且值是数据库真实ID
        assert 'step_id' in config_data, "配置文件必须包含step_id字段"
        assert config_data['step_id'] == database_step_id, f"step_id应该等于数据库ID: {database_step_id}"

    @pytest.mark.asyncio
    async def test_sop_structure_should_include_output_ids(self):
        """测试SOP结构下载的outputs应包含output_id字段"""
        # 准备测试数据
        step_identifier = 'contractConfirmation'
        database_step_id = 'step_db_67890'
        
        mock_sop_structure = {
            'steps': {
                step_identifier: {  # key是identifier，用于创建目录
                    'identifier': step_identifier,
                    'name': '契约确认',
                    'stage': 'analysis',
                    'description': '测试',
                    'step_id': database_step_id,  # 后端返回的数据库真实ID
                    'outputs': [
                        {
                            'output_id': 'output_001_test',  # 应该包含这个字段
                            'name': 'API接口跟踪清单',
                            'template_filename': 'api-trace.md'
                        }
                    ],
                    'rules': []
                }
            }
        }
        
        # 执行SOP结构设置
        await self.service._setup_sop_structure(mock_sop_structure)
        
        # 验证配置文件内容 - 文件路径使用identifier
        config_path = self.temp_dir / 'supervisor_workspace' / 'sop' / 'analysis' / step_identifier / 'config.json'
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 验证outputs包含output_id
        assert 'outputs' in config_data
        assert len(config_data['outputs']) > 0
        
        first_output = config_data['outputs'][0]
        assert 'output_id' in first_output, "每个output必须包含output_id字段"
        assert first_output['output_id'] == 'output_001_test'

    @pytest.mark.asyncio  
    async def test_sop_update_tools_require_complete_fields(self):
        """测试SOP更新工具需要完整字段才能工作"""
        # 先创建一个缺少字段的配置文件（模拟当前问题）
        incomplete_config = {
            'identifier': 'contractConfirmation',
            'name': '契约确认',
            'stage': 'analysis',
            'description': '测试',
            'outputs': [
                {
                    'name': 'API接口跟踪清单',
                    'template_filename': 'api-trace.md'
                    # 缺少 output_id
                }
            ]
            # 缺少 rules 和 step_id
        }
        
        # 手动创建不完整的配置文件
        config_dir = self.temp_dir / 'supervisor_workspace' / 'sop' / 'analysis' / 'contractConfirmation'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / 'config.json'
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(incomplete_config, f, ensure_ascii=False, indent=2)
        
        # 尝试使用update_step_rules工具
        result = await self.service.update_step_rules('analysis', 'contractConfirmation')
        
        # 应该返回错误，因为缺少rules字段（rules检查在step_id之前）
        assert result['status'] == 'error'
        assert 'rules' in result['message']

    @pytest.mark.asyncio
    async def test_complete_sop_structure_enables_update_tools(self):
        """测试完整的SOP结构应该能支持更新工具正常工作"""
        # 创建完整的SOP结构
        step_identifier = 'contractConfirmation'
        database_step_id = 'step_db_complete_test'
        
        complete_sop_structure = {
            'steps': {
                step_identifier: {  # key是identifier，用于创建目录
                    'identifier': step_identifier, 
                    'name': '契约确认',
                    'stage': 'analysis',
                    'description': '测试',
                    'step_id': database_step_id,  # 后端返回的数据库真实ID
                    'outputs': [
                        {
                            'output_id': 'output_001_test',
                            'name': 'API接口跟踪清单',
                            'template_filename': 'api-trace.md'
                        }
                    ],
                    'rules': [
                        {
                            'name': '测试规则',
                            'must': ['必须做的事'],
                            'must_not': ['不能做的事']
                        }
                    ]
                }
            }
        }
        
        # 先设置完整的SOP结构
        await self.service._setup_sop_structure(complete_sop_structure)
        
        # 创建模板文件
        template_dir = self.temp_dir / 'supervisor_workspace' / 'sop' / 'analysis' / step_identifier / 'templates'
        template_dir.mkdir(parents=True, exist_ok=True)
        template_file = template_dir / 'api-trace.md'
        template_file.write_text('# 测试模板内容', encoding='utf-8')
        
        # Mock API调用成功
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client._client.headers = Mock()
            mock_client._client.headers.update = Mock()
            mock_client._client.headers.__setitem__ = Mock()
            mock_client.request = AsyncMock(return_value={
                'status': 'success', 
                'message': 'Updated successfully'
            })
            mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # 现在更新工具应该能正常工作
            result = await self.service.update_step_rules('analysis', 'contractConfirmation')
            
            # 应该成功，不再报缺少字段的错误
            assert result['status'] == 'success'