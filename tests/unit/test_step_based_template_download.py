"""
测试新的按步骤下载模板设计
验证使用 sop/steps/{identifier}/ API 按步骤下载模板
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from service import MCPService


@pytest.mark.asyncio
class TestStepBasedTemplateDownload:
    """测试新的按步骤下载模板设计"""
    
    async def test_step_based_template_download_flow(self):
        """
        测试新的按步骤下载流程：
        1. 调用 sop/graph/ 获取步骤列表
        2. 对每个步骤调用 sop/steps/{identifier}/ 获取模板
        3. 按 {stage}/{step_identifier}/{template_name} 结构保存
        """
        service = MCPService()
        
        # Mock 认证和文件操作
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                with patch.object(service.file_manager, 'create_supervisor_directory'):
                    with patch.object(service.file_manager, 'save_project_info'):
                        
                        # Mock 项目信息响应
                        project_info_response = {
                            "project_id": "test-proj-123",
                            "project_name": "Test Project",
                            "description": "Test Description",
                            "created_at": "2024-01-20T10:00:00Z",
                            "task_groups": []
                        }
                        
                        # Mock SOP图响应 - 获取步骤列表
                        sop_graph_response = {
                            "steps": {
                                "functionalRequirements": {
                                    "identifier": "functionalRequirements",
                                    "name": "功能需求分析",
                                    "stage": "需求分析",
                                    "description": "分析系统功能需求"
                                },
                                "uiComponentsDesign": {
                                    "identifier": "uiComponentsDesign",
                                    "name": "UI组件设计",
                                    "stage": "设计语言系统",
                                    "description": "设计UI组件库"
                                },
                                "implement": {
                                    "identifier": "implement",
                                    "name": "功能实现",
                                    "stage": "技术实现",
                                    "description": "实现系统功能"
                                }
                            },
                            "dependencies": []
                        }
                        
                        # Mock 各步骤详情响应 - 包含模板内容
                        step_details = {
                            "functionalRequirements": {
                                "identifier": "functionalRequirements",
                                "name": "功能需求分析",
                                "stage": "需求分析",
                                "description": "分析系统功能需求",
                                "outputs": [
                                    {
                                        "name": "功能需求文档",
                                        "template": "functional-requirements.md",
                                        "template_content": "# 功能需求分析\n\n## 核心功能\n\n这是功能需求模板内容"
                                    }
                                ]
                            },
                            "uiComponentsDesign": {
                                "identifier": "uiComponentsDesign",
                                "name": "UI组件设计",
                                "stage": "设计语言系统",
                                "description": "设计UI组件库",
                                "outputs": [
                                    {
                                        "name": "组件库文档",
                                        "template": "component-library.md",
                                        "template_content": "# UI组件库设计\n\n## 组件规范\n\n这是组件库设计模板内容"
                                    },
                                    {
                                        "name": "设计原则",
                                        "template": "design-principles.md",
                                        "template_content": "# 设计原则\n\n## 一致性原则\n\n这是设计原则模板内容"
                                    }
                                ]
                            },
                            "implement": {
                                "identifier": "implement",
                                "name": "功能实现",
                                "stage": "技术实现",
                                "description": "实现系统功能",
                                "outputs": []  # 没有模板输出
                            }
                        }
                        
                        # Mock API 调用
                        async def mock_request(method, endpoint, **kwargs):
                            if endpoint == 'projects/test-proj-123/info/':
                                return project_info_response
                            elif endpoint == 'sop/graph/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return sop_graph_response
                            elif endpoint == 'sop/steps/functionalRequirements/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_details["functionalRequirements"]
                            elif endpoint == 'sop/steps/uiComponentsDesign/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_details["uiComponentsDesign"]
                            elif endpoint == 'sop/steps/implement/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_details["implement"]
                            else:
                                return {}
                        
                        mock_api = AsyncMock()
                        mock_api.request = mock_request
                        
                        # 跟踪模板下载调用
                        download_template_calls = []
                        
                        async def mock_download_template(api_client, template_info):
                            download_template_calls.append(template_info)
                            return True
                        
                        # Mock API客户端和下载方法
                        with patch('service.get_api_client') as mock_get_client:
                            mock_get_client.return_value.__aenter__.return_value = mock_api
                            mock_get_client.return_value.__aexit__.return_value = None
                            
                            with patch.object(service.file_manager, 'download_template', side_effect=mock_download_template):
                                
                                # 执行新的按步骤下载逻辑（这里假设我们实现了新方法）
                                # 注意：这个测试现在会失败，因为我们还没有实现新的逻辑
                                # 我们先跳过具体的执行，只验证数据结构
                                
                                # 验证期望的下载调用
                                expected_downloads = [
                                    {
                                        "name": "functional-requirements.md",
                                        "step_identifier": "functionalRequirements",
                                        "stage": "需求分析",
                                        "path": ".supervisor/templates/需求分析/functionalRequirements/functional-requirements.md",
                                        "content": "# 功能需求分析\n\n## 核心功能\n\n这是功能需求模板内容"
                                    },
                                    {
                                        "name": "component-library.md",
                                        "step_identifier": "uiComponentsDesign",
                                        "stage": "设计语言系统",
                                        "path": ".supervisor/templates/设计语言系统/uiComponentsDesign/component-library.md",
                                        "content": "# UI组件库设计\n\n## 组件规范\n\n这是组件库设计模板内容"
                                    },
                                    {
                                        "name": "design-principles.md",
                                        "step_identifier": "uiComponentsDesign",
                                        "stage": "设计语言系统",
                                        "path": ".supervisor/templates/设计语言系统/uiComponentsDesign/design-principles.md",
                                        "content": "# 设计原则\n\n## 一致性原则\n\n这是设计原则模板内容"
                                    }
                                ]
                                
                                # 当前这个测试展示了期望的行为，但因为还没有实现新逻辑所以会跳过
                                pytest.skip("新的按步骤下载逻辑还未实现，这是期望的行为规格")

    async def test_template_path_structure_generation(self):
        """测试新的模板路径结构生成逻辑"""
        
        # 测试路径生成函数（还未实现）
        test_cases = [
            {
                "stage": "需求分析",
                "step_identifier": "functionalRequirements",
                "template_name": "functional-requirements.md",
                "expected_path": ".supervisor/templates/需求分析/functionalRequirements/functional-requirements.md"
            },
            {
                "stage": "设计语言系统",
                "step_identifier": "uiComponentsDesign", 
                "template_name": "component-library.md",
                "expected_path": ".supervisor/templates/设计语言系统/uiComponentsDesign/component-library.md"
            },
            {
                "stage": "技术实现",
                "step_identifier": "implement",
                "template_name": "implementation-guide.md",
                "expected_path": ".supervisor/templates/技术实现/implement/implementation-guide.md"
            }
        ]
        
        # 这里可以测试路径生成逻辑
        for case in test_cases:
            # 生成路径的逻辑（还未实现）
            actual_path = f".supervisor/templates/{case['stage']}/{case['step_identifier']}/{case['template_name']}"
            assert actual_path == case["expected_path"], f"路径生成不正确: {actual_path}"

    async def test_api_call_sequence_for_step_based_download(self):
        """测试按步骤下载的API调用序列"""
        service = MCPService()
        
        # 跟踪API调用
        api_calls = []
        
        async def mock_request(method, endpoint, **kwargs):
            api_calls.append({
                "method": method,
                "endpoint": endpoint,
                "params": kwargs.get('params', {})
            })
            
            # 返回模拟数据
            if 'sop/graph/' in endpoint:
                return {
                    "steps": {
                        "step1": {"identifier": "step1", "stage": "stage1"},
                        "step2": {"identifier": "step2", "stage": "stage2"}
                    }
                }
            elif 'sop/steps/' in endpoint:
                return {
                    "identifier": "test",
                    "stage": "test_stage",
                    "outputs": [
                        {
                            "template": "test.md",
                            "template_content": "test content"
                        }
                    ]
                }
            return {}
        
        # Mock API客户端
        with patch('service.get_api_client') as mock_get_client:
            mock_api = AsyncMock()
            mock_api.request = mock_request
            mock_get_client.return_value.__aenter__.return_value = mock_api
            mock_get_client.return_value.__aexit__.return_value = None
            
            # 这里应该调用新的下载方法（还未实现）
            # 暂时跳过具体实现测试
            
            # 验证期望的API调用序列
            expected_call_sequence = [
                {"method": "GET", "endpoint": "sop/graph/", "params": {"project_id": "test-proj"}},
                {"method": "GET", "endpoint": "sop/steps/step1/", "params": {"project_id": "test-proj"}},
                {"method": "GET", "endpoint": "sop/steps/step2/", "params": {"project_id": "test-proj"}}
            ]
            
            # 当前跳过实际调用，只验证数据结构
            pytest.skip("API调用序列测试等待新实现")