"""
测试 setup_workspace 场景的模板下载一致性
验证 setup_workspace 和 create_project 应该有相同的模板下载行为
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from service import MCPService


@pytest.mark.asyncio
class TestSetupWorkspace:
    """测试 setup_workspace 场景的SOP步骤和模板下载"""
    
    async def test_setup_workspace_should_download_templates_like_create_project(self):
        """
        验证 setup_workspace 应该像 create_project 一样下载模板
        
        当前问题：
        - create_project 通过 file_manager.initialize_project_structure 和 download_template 下载模板
        - setup_workspace 只是简单地写入从API获取的模板内容，没有调用标准的下载机制
        
        期望行为：
        - 两种场景都应该使用相同的模板下载机制
        - 都应该调用 file_manager.download_template 方法
        """
        service = MCPService()
        
        # Mock 认证和文件操作
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                with patch.object(service.file_manager, 'create_supervisor_directory'):
                    with patch.object(service.file_manager, 'save_project_info'):
                        
                        # Mock API 响应
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
                                "requirementAnalysis": {
                                    "identifier": "requirementAnalysis",
                                    "name": "需求分析",
                                    "stage": "需求分析",
                                    "description": "分析业务需求"
                                },
                                "uiDesign": {
                                    "identifier": "uiDesign",
                                    "name": "UI设计",
                                    "stage": "设计语言系统",
                                    "description": "设计用户界面"
                                }
                            },
                            "dependencies": []
                        }
                        
                        # Mock 步骤详情响应 - 包含模板内容
                        step_details = {
                            "requirementAnalysis": {
                                "identifier": "requirementAnalysis",
                                "name": "需求分析",
                                "stage": "需求分析",
                                "description": "分析业务需求",
                                "outputs": [
                                    {
                                        "name": "需求分析文档",
                                        "template_filename": "requirement-analysis.md",
                                        "template_content": "# 需求分析模板\n\n这是需求分析模板内容"
                                    }
                                ]
                            },
                            "uiDesign": {
                                "identifier": "uiDesign",
                                "name": "UI设计",
                                "stage": "设计语言系统",
                                "description": "设计用户界面",
                                "outputs": [
                                    {
                                        "name": "UI设计文档",
                                        "template_filename": "ui-design.md",
                                        "template_content": "# UI设计模板\n\n这是UI设计模板内容"
                                    }
                                ]
                            }
                        }
                        
                        # Mock API 调用
                        async def mock_request(method, endpoint, **kwargs):
                            if endpoint == 'projects/test-proj-123/info/':
                                return project_info_response
                            elif endpoint == 'sop/graph/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return sop_graph_response
                            elif endpoint == 'sop/steps/requirementAnalysis/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_details["requirementAnalysis"]
                            elif endpoint == 'sop/steps/uiDesign/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_details["uiDesign"]
                            else:
                                return {}
                        
                        mock_api = AsyncMock()
                        mock_api.request = mock_request
                        
                        # 检查 download_template 是否被调用
                        download_template_calls = []
                        
                        async def mock_download_template(api_client, template_info):
                            download_template_calls.append(template_info)
                            return True
                        
                        # 修复Mock配置
                        with patch('service.get_api_client') as mock_get_client:
                            mock_get_client.return_value.__aenter__.return_value = mock_api
                            mock_get_client.return_value.__aexit__.return_value = None
                            
                            with patch.object(service.file_manager, 'download_template', side_effect=mock_download_template):
                                
                                # 执行 setup_workspace
                                result = await service.init(project_id="test-proj-123")
                                
                                # 验证结果成功
                                assert result["status"] == "success"
                                
                                # 关键验证：应该调用了 download_template 方法
                                assert len(download_template_calls) == 2, "setup_workspace 应该像 create_project 一样下载模板"
                                
                                # 验证下载的模板信息正确转换
                                expected_templates = [
                                    {
                                        "name": "requirement-analysis.md",
                                        "step_identifier": "requirementAnalysis",
                                        "stage": "需求分析",
                                        "path": "sop/需求分析/requirementAnalysis/templates/requirement-analysis.md"
                                    },
                                    {
                                        "name": "ui-design.md", 
                                        "step_identifier": "uiDesign",
                                        "stage": "设计语言系统",
                                        "path": "sop/设计语言系统/uiDesign/templates/ui-design.md"
                                    }
                                ]
                                
                                for i, expected in enumerate(expected_templates):
                                    actual = download_template_calls[i]
                                    assert actual["name"] == expected["name"]
                                    assert actual["step_identifier"] == expected["step_identifier"]
                                    assert actual["path"] == expected["path"], f"模板路径应该按照 stage/step_identifier/template_name 结构"
                                    
                                    # 关键验证：检查content字段是否包含真实的模板内容
                                    assert "content" in actual, f"模板 {actual['name']} 应该包含content字段"
                                    expected_content = "# 需求分析模板\n\n这是需求分析模板内容" if i == 0 else "# UI设计模板\n\n这是UI设计模板内容"
                                    assert actual["content"] == expected_content, f"模板 {actual['name']} 的content应该是真实内容，不是路径"

    async def test_template_content_written_to_file_correctly(self):
        """
        测试模板content字段正确写入文件 - 关键测试用例
        验证当模板包含content字段时，文件写入的是content的内容，而不是路径
        """
        from src.file_manager import FileManager
        from unittest.mock import patch, mock_open, AsyncMock
        
        # 创建文件管理器
        file_manager = FileManager(base_path='/test/path')
        
        # 模拟API客户端（实际不会被调用，因为有content字段）
        api_client = AsyncMock()
        
        # 模板信息 - 使用新的路径结构
        template_info = {
            "name": "test-template.md",
            "path": "测试阶段/test/test-template.md",
            "step_identifier": "test",
            "content": "# 真实的模板内容\n\n这是完整的模板内容，不是路径"
        }
        
        # Mock文件操作
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.exists', return_value=False):
                with patch('builtins.open', mock_open()) as mock_file:
                    # 执行下载
                    result = await file_manager.download_template(api_client, template_info)
                    
                    # 验证结果成功
                    assert result is True
                    
                    # 关键验证：API不应该被调用（因为有content字段）
                    api_client.request.assert_not_called()
                    
                    # 关键验证：文件写入的是content字段的内容
                    mock_file.assert_called_once()
                    mock_handle = mock_file.return_value.__enter__.return_value
                    mock_handle.write.assert_called_once_with("# 真实的模板内容\n\n这是完整的模板内容，不是路径")

    async def test_api_content_to_local_file_consistency(self):
        """
        测试API返回的content正确写入本地文件
        验证：API返回正确的content → 本地文件写入相同内容
        
        假设：projects/{id}/templates/ API 直接返回完整的模板内容
        """
        from src.file_manager import FileManager
        from unittest.mock import patch, mock_open, AsyncMock
        
        # 模拟API返回的正确模板内容
        template_content = """# 架构设计文档模板

## 系统概述
描述系统的整体架构和设计理念

## 核心组件
- 组件A：负责用户认证和授权
- 组件B：负责数据处理和存储

## 技术选型
### 前端技术栈
- React 18
- TypeScript 4.8
- Tailwind CSS

### 后端技术栈
- Python 3.11
- FastAPI 0.95
- PostgreSQL 15

## 部署架构
```
[客户端] -> [CDN] -> [负载均衡器] -> [应用服务器集群] -> [数据库集群]
```

## 开发规范
1. 确保数据一致性
2. 考虑性能优化
3. 遵循安全最佳实践

## 文件路径示例
- 配置文件：`config/app.yaml`
- 模板目录：`templates/`
- 静态资源：`static/css/main.css`
"""
        
        # 创建文件管理器
        file_manager = FileManager(base_path='/test/path')
        
        # 不需要API客户端，因为content已经包含完整内容
        api_client = AsyncMock()
        
        # 模拟API返回的正确数据格式
        template_info = {
            "name": "ARCHITECTURE.md",
            "path": "部署发布/reviewAndRefactor/ARCHITECTURE.md",
            "step_identifier": "reviewAndRefactor",
            "content": template_content  # 正确的API设计：直接包含完整内容
        }
        
        # Mock文件操作
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.exists', return_value=False):
                with patch('builtins.open', mock_open()) as mock_file:
                    # 执行下载
                    result = await file_manager.download_template(api_client, template_info)
                    
                    # 验证结果成功
                    assert result is True
                    
                    # 验证API不应该被调用（因为content已经包含完整内容）
                    api_client.request.assert_not_called()
                    
                    # 获取实际写入的内容
                    mock_handle = mock_file.return_value.__enter__.return_value
                    written_calls = mock_handle.write.call_args_list
                    
                    assert len(written_calls) == 1, "应该写入一次文件"
                    written_content = written_calls[0][0][0]
                    
                    # 关键验证：写入的内容应该与API返回的content完全一致
                    assert written_content == template_content, (
                        f"写入内容与API返回内容不一致\n"
                        f"期望: {template_content[:100]}...\n"
                        f"实际: {written_content[:100]}..."
                    )

    async def test_create_project_downloads_templates_correctly(self):
        """
        验证 create_project 正确下载模板（作为对比基准）
        """
        service = MCPService()
        
        # Mock 认证和文件操作
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                with patch.object(service.file_manager, 'create_supervisor_directory'):
                    with patch.object(service.file_manager, 'save_project_info'):
                        
                        # Mock API 响应 - create_project 的响应格式
                        create_response = {
                            "success": True,
                            "project_id": "new-proj-456",
                            "project_name": "New Project",
                            "created_at": "2024-01-20T10:00:00Z",
                            "sop_steps_count": 5,
                            "initial_task_groups": 2,
                            "initialization_data": {
                                "templates": [
                                    {
                                        "name": "requirement-analysis.md",
                                        "path": "需求分析/requirementAnalysis/requirement-analysis.md",
                                        "step_identifier": "requirementAnalysis"
                                    },
                                    {
                                        "name": "ui-design.md",
                                        "path": "设计语言系统/uiDesign/ui-design.md", 
                                        "step_identifier": "uiDesign"
                                    }
                                ]
                            }
                        }
                        
                        # Mock API 调用
                        mock_api = AsyncMock()
                        mock_api.request.return_value = create_response
                        
                        # 检查 download_template 是否被调用
                        download_template_calls = []
                        
                        async def mock_download_template(api_client, template_info):
                            download_template_calls.append(template_info)
                            return True
                        
                        # Mock initialize_project_structure 返回模板列表
                        def mock_initialize_structure(init_data):
                            return init_data.get("templates", [])
                        
                        # 修复Mock配置 - create_project测试
                        with patch('service.get_api_client') as mock_get_client:
                            mock_get_client.return_value.__aenter__.return_value = mock_api
                            mock_get_client.return_value.__aexit__.return_value = None
                            with patch.object(service.file_manager, 'download_template', side_effect=mock_download_template):
                                with patch.object(service.file_manager, 'initialize_project_structure', side_effect=mock_initialize_structure):
                                    
                                    # 执行 create_project
                                    result = await service.init(project_name="New Project", description="Test Project")
                                    
                                    # 验证结果成功
                                    assert result["status"] == "success"
                                    
                                    # 验证 create_project 正确调用了 download_template
                                    assert len(download_template_calls) == 2
                                    
                                    # 验证模板信息
                                    expected_templates = [
                                        {
                                            "name": "requirement-analysis.md",
                                            "step_identifier": "requirementAnalysis"
                                        },
                                        {
                                            "name": "ui-design.md",
                                            "step_identifier": "uiDesign"
                                        }
                                    ]
                                    
                                    for i, expected in enumerate(expected_templates):
                                        actual = download_template_calls[i]
                                        assert actual["name"] == expected["name"]
                                        assert actual["step_identifier"] == expected["step_identifier"]
    
    async def test_setup_workspace_missing_templates_directory_bug(self):
        """
        测试setup_workspace缺少templates目录创建的缺陷
        
        这个测试捕捉了一个关键缺陷：
        - create_project会调用initialize_project_structure创建templates目录
        - setup_workspace直接跳过目录创建，直接下载模板到不存在的目录
        """
        service = MCPService()
        
        # Mock 认证和基础文件操作
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                with patch.object(service.file_manager, 'create_supervisor_directory'):
                    with patch.object(service.file_manager, 'save_project_info'):
                        
                        # Mock API 响应
                        project_info_response = {
                            "project_id": "test-proj-123",
                            "project_name": "Test Project",
                            "description": "Test Description",
                            "created_at": "2024-01-20T10:00:00Z",
                            "task_groups": []
                        }
                        
                        # Mock SOP图响应
                        sop_graph_response = {
                            "steps": {
                                "requirementAnalysis": {
                                    "identifier": "requirementAnalysis",
                                    "name": "需求分析",
                                    "stage": "需求分析",
                                    "description": "分析业务需求"
                                }
                            },
                            "dependencies": []
                        }
                        
                        # Mock 步骤详情响应
                        step_detail_response = {
                            "identifier": "requirementAnalysis",
                            "name": "需求分析",
                            "stage": "需求分析",
                            "description": "分析业务需求",
                            "outputs": [
                                {
                                    "name": "需求分析文档",
                                    "template_filename": "requirement-analysis.md",
                                    "template_content": "# 需求分析模板内容"
                                }
                            ]
                        }
                        
                        # Mock API 调用
                        async def mock_request(method, endpoint, **kwargs):
                            if endpoint == 'projects/test-proj-123/info/':
                                return project_info_response
                            elif endpoint == 'sop/graph/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return sop_graph_response
                            elif endpoint == 'sop/steps/requirementAnalysis/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                                return step_detail_response
                            return {}
                        
                        mock_api = AsyncMock()
                        mock_api.request = mock_request
                        
                        # 重要：检查是否调用了initialize_project_structure
                        initialize_calls = []
                        
                        def mock_initialize_structure(init_data):
                            initialize_calls.append(init_data)
                            return init_data.get("templates", [])
                        
                        with patch('service.get_api_client') as mock_get_client:
                            mock_get_client.return_value.__aenter__.return_value = mock_api
                            mock_get_client.return_value.__aexit__.return_value = None
                            
                            with patch.object(service.file_manager, 'initialize_project_structure', side_effect=mock_initialize_structure):
                                with patch.object(service.file_manager, 'download_template', return_value=True):
                                    
                                    # 执行 setup_workspace
                                    result = await service.init(project_id="test-proj-123")
                                    
                                    # 验证执行成功
                                    assert result["status"] == "success"
                                    
                                    # 要求：setup_workspace应该像create_project一样调用initialize_project_structure
                                    # 这样才能确保templates目录被创建
                                    assert len(initialize_calls) == 1, (
                                        "BUG：setup_workspace应该调用initialize_project_structure来创建templates目录，"
                                        "但目前没有调用！这就是为什么templates目录不存在的原因。"
                                    )
    
    async def test_create_project_creates_templates_directory(self):
        """
        验证create_project正确创建templates目录（作为对比）
        """
        service = MCPService()
        
        # Mock 认证和文件操作
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                with patch.object(service.file_manager, 'create_supervisor_directory'):
                    with patch.object(service.file_manager, 'save_project_info'):
                        
                        # Mock create_project API 响应
                        create_response = {
                            "success": True,
                            "project_id": "new-proj-456",
                            "project_name": "New Project",
                            "created_at": "2024-01-20T10:00:00Z",
                            "initialization_data": {
                                "templates": [
                                    {
                                        "name": "requirement-analysis.md",
                                        "path": "需求分析/requirementAnalysis/requirement-analysis.md",
                                        "step_identifier": "requirementAnalysis"
                                    }
                                ]
                            }
                        }
                        
                        mock_api = AsyncMock()
                        mock_api.request.return_value = create_response
                        
                        # 检查是否调用了initialize_project_structure
                        initialize_calls = []
                        
                        def mock_initialize_structure(init_data):
                            initialize_calls.append(init_data)
                            return init_data.get("templates", [])
                        
                        with patch('service.get_api_client') as mock_get_client:
                            mock_get_client.return_value.__aenter__.return_value = mock_api
                            mock_get_client.return_value.__aexit__.return_value = None
                            
                            with patch.object(service.file_manager, 'initialize_project_structure', side_effect=mock_initialize_structure):
                                with patch.object(service.file_manager, 'download_template', return_value=True):
                                    
                                    # 执行 create_project
                                    result = await service.init(project_name="New Project", description="Test Project")
                                    
                                    # 验证执行成功
                                    assert result["status"] == "success"
                                    
                                    # create_project应该调用initialize_project_structure创建目录
                                    assert len(initialize_calls) == 1, (
                                        "create_project应该调用initialize_project_structure创建templates目录"
                                    )
                                    
                                    # 验证传递的数据正确
                                    assert "templates" in initialize_calls[0]
    
    
    async def test_setup_workspace_function_calls_verification(self):
        """
        验证setup_workspace确实调用了必要的函数
        这个测试重点关注函数调用，而不是文件系统操作
        """
        service = MCPService()
        
        # Mock认证
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                
                # 记录函数调用
                initialize_calls = []
                download_calls = []
                
                def track_initialize(init_data):
                    initialize_calls.append(init_data)
                    return init_data.get("templates", [])
                
                async def track_download(api_client, template_info):
                    download_calls.append(template_info)
                    return True
                
                # Mock API响应
                project_info_response = {
                    "project_id": "test-proj-123",
                    "project_name": "Test Project",
                    "task_groups": []
                }
                
                # Mock SOP图响应
                sop_graph_response = {
                    "steps": {
                        "test": {
                            "identifier": "test",
                            "name": "测试步骤",
                            "stage": "测试阶段",
                            "description": "测试描述"
                        }
                    },
                    "dependencies": []
                }
                
                # Mock 步骤详情响应
                step_detail_response = {
                    "identifier": "test",
                    "name": "测试步骤",
                    "stage": "测试阶段",
                    "description": "测试描述",
                    "outputs": [
                        {
                            "name": "测试模板",
                            "template_filename": "test-template.md",
                            "template_content": "Test content"
                        }
                    ]
                }
                
                async def mock_request(method, endpoint, **kwargs):
                    if endpoint == 'projects/test-proj-123/info/':
                        return project_info_response
                    elif endpoint == 'sop/graph/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                        return sop_graph_response
                    elif endpoint == 'sop/steps/test/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                        return step_detail_response
                    return {}
                
                mock_api = AsyncMock()
                mock_api.request = mock_request
                
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value.__aenter__.return_value = mock_api
                    mock_get_client.return_value.__aexit__.return_value = None
                    
                    # 只mock必要的文件操作，让函数调用追踪正常工作
                    with patch.object(service.file_manager, 'create_supervisor_directory'):
                        with patch.object(service.file_manager, 'save_project_info'):
                            with patch.object(service.file_manager, 'initialize_project_structure', side_effect=track_initialize):
                                with patch.object(service.file_manager, 'download_template', side_effect=track_download):
                                    
                                    # 执行setup_workspace
                                    result = await service.init(project_id="test-proj-123")
                                    
                                    # 验证执行成功
                                    assert result["status"] == "success"
                                    
                                    # 验证initialize_project_structure被调用
                                    assert len(initialize_calls) == 1, (
                                        f"initialize_project_structure应该被调用1次，实际调用了{len(initialize_calls)}次"
                                    )
                                    
                                    # 验证download_template被调用
                                    assert len(download_calls) == 1, (
                                        f"download_template应该被调用1次，实际调用了{len(download_calls)}次"
                                    )
                                    
                                    # 验证传递的数据正确
                                    assert "templates" in initialize_calls[0]
                                    assert download_calls[0]["name"] == "test-template.md"
    
    async def test_create_project_function_calls_verification(self):
        """
        验证create_project也确实调用了必要的函数（对比测试）
        """
        service = MCPService()
        
        # Mock认证
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                
                # 记录函数调用
                initialize_calls = []
                download_calls = []
                
                def track_initialize(init_data):
                    initialize_calls.append(init_data)
                    return init_data.get("templates", [])
                
                async def track_download(api_client, template_info):
                    download_calls.append(template_info)
                    return True
                
                # Mock create_project API响应
                create_response = {
                    "success": True,
                    "project_id": "new-proj-456",
                    "project_name": "New Project",
                    "created_at": "2024-01-20T10:00:00Z",
                    "initialization_data": {
                        "templates": [
                            {
                                "name": "create-template.md",
                                "path": "测试阶段/create_test/create-template.md",
                                "step_identifier": "create_test"
                            }
                        ]
                    }
                }
                
                mock_api = AsyncMock()
                mock_api.request.return_value = create_response
                
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value.__aenter__.return_value = mock_api
                    mock_get_client.return_value.__aexit__.return_value = None
                    
                    with patch.object(service.file_manager, 'create_supervisor_directory'):
                        with patch.object(service.file_manager, 'save_project_info'):
                            with patch.object(service.file_manager, 'initialize_project_structure', side_effect=track_initialize):
                                with patch.object(service.file_manager, 'download_template', side_effect=track_download):
                                    
                                    # 执行create_project
                                    result = await service.init(project_name="New Project", description="Test Project")
                                    
                                    # 验证执行成功
                                    assert result["status"] == "success"
                                    
                                    # 验证initialize_project_structure被调用
                                    assert len(initialize_calls) == 1, (
                                        f"create_project的initialize_project_structure应该被调用1次，实际调用了{len(initialize_calls)}次"
                                    )
                                    
                                    # 验证download_template被调用
                                    assert len(download_calls) == 1, (
                                        f"create_project的download_template应该被调用1次，实际调用了{len(download_calls)}次"
                                    )
                                    
                                    # 验证传递的数据正确
                                    assert "templates" in initialize_calls[0]
                                    assert download_calls[0]["name"] == "create-template.md"
    
    async def test_template_name_none_handling(self):
        """测试API返回template字段为None时应该抛出错误"""
        service = MCPService()
        
        # Mock认证
        with patch.object(service.session_manager, 'is_authenticated', return_value=True):
            with patch.object(service.session_manager, 'get_headers', return_value={'Authorization': 'Token test'}):
                
                # Mock API响应 - template字段为None
                project_info_response = {
                    "project_id": "test-proj-123",
                    "project_name": "Test Project",
                    "task_groups": []
                }
                
                sop_graph_response = {
                    "steps": {
                        "testStep": {
                            "identifier": "testStep",
                            "name": "测试步骤",
                            "stage": "测试阶段",
                            "description": "测试描述"
                        }
                    },
                    "dependencies": []
                }
                
                # 关键：template字段为None，但有template_content - 这是数据错误
                step_detail_response = {
                    "identifier": "testStep",
                    "name": "测试步骤",
                    "stage": "测试阶段",
                    "description": "测试描述",
                    "outputs": [
                        {
                            "name": "测试文档",
                            "template_filename": None,  # 数据错误：有content但没有template名称
                            "template_content": "# 测试内容"
                        }
                    ]
                }
                
                async def mock_request(method, endpoint, **kwargs):
                    if endpoint == 'projects/test-proj-123/info/':
                        return project_info_response
                    elif endpoint == 'sop/graph/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                        return sop_graph_response
                    elif endpoint == 'sop/steps/testStep/' and kwargs.get('params', {}).get('project_id') == 'test-proj-123':
                        return step_detail_response
                    return {}
                
                mock_api = AsyncMock()
                mock_api.request = mock_request
                
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value.__aenter__.return_value = mock_api
                    mock_get_client.return_value.__aexit__.return_value = None
                    
                    with patch.object(service.file_manager, 'create_supervisor_directory'):
                        with patch.object(service.file_manager, 'save_project_info'):
                            with patch.object(service.file_manager, 'initialize_project_structure', return_value=[]):
                                
                                # 验证执行成功（单个模板错误不影响整体流程）
                                with patch('builtins.print') as mock_print:
                                    result = await service.init(project_id="test-proj-123")
                                    
                                    # 验证执行成功（容错设计）
                                    assert result["status"] == "success"
                                    
                                    # 验证错误被正确记录和报告
                                    print_calls = [call.args[0] for call in mock_print.call_args_list]
                                    error_messages = [msg for msg in print_calls if "missing template name" in msg]
                                    assert len(error_messages) > 0, "应该打印template字段为None的错误信息"
                                    
                                    # 验证错误信息包含关键信息
                                    error_logged = any("Step testStep output missing template name" in msg for msg in print_calls)
                                    assert error_logged, "应该记录具体的步骤和错误信息"