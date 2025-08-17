"""
测试 setup_workspace 场景的模板下载一致性
验证 setup_workspace 和 create_project 应该有相同的模板下载行为
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from service import MCPService


@pytest.mark.asyncio
class TestSetupWorkspaceTemplates:
    """测试 setup_workspace 场景的模板下载"""
    
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
                        
                        # Mock 模板响应 - 这是从API获取的模板数据
                        templates_response = {
                            "templates": [
                                {
                                    "filename": "requirement-analysis.md",
                                    "content": "# 需求分析模板\n\n这是需求分析模板内容",
                                    "step_identifier": "requirementAnalysis"
                                },
                                {
                                    "filename": "ui-design.md", 
                                    "content": "# UI设计模板\n\n这是UI设计模板内容",
                                    "step_identifier": "uiDesign"
                                }
                            ]
                        }
                        
                        # Mock API 调用
                        async def mock_request(method, endpoint, **kwargs):
                            if endpoint == 'projects/test-proj-123/info/':
                                return project_info_response
                            elif endpoint == 'projects/test-proj-123/templates/':
                                return templates_response
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
                                        "path": ".supervisor/templates/requirement-analysis.md",
                                        "step_identifier": "requirementAnalysis"
                                    },
                                    {
                                        "name": "ui-design.md",
                                        "path": ".supervisor/templates/ui-design.md", 
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
                        
                        templates_response = {
                            "templates": [
                                {
                                    "filename": "requirement-analysis.md",
                                    "content": "# 需求分析模板内容",
                                    "step_identifier": "requirementAnalysis"
                                }
                            ]
                        }
                        
                        # Mock API 调用
                        async def mock_request(method, endpoint, **kwargs):
                            if endpoint == 'projects/test-proj-123/info/':
                                return project_info_response
                            elif endpoint == 'projects/test-proj-123/templates/':
                                return templates_response
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
                                        "path": ".supervisor/templates/requirement-analysis.md",
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
                
                templates_response = {
                    "templates": [
                        {
                            "filename": "test-template.md",
                            "content": "Test content",
                            "step_identifier": "test"
                        }
                    ]
                }
                
                async def mock_request(method, endpoint, **kwargs):
                    if endpoint == 'projects/test-proj-123/info/':
                        return project_info_response
                    elif endpoint == 'projects/test-proj-123/templates/':
                        return templates_response
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
                                "path": ".supervisor/templates/create-template.md",
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