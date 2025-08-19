"""
测试report逻辑的新行为：
1. 只有validation任务passed时才清空current_task
2. 任务编号基于已完成任务数量+1
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

from file_manager import FileManager


def create_mock_api_client(return_value=None):
    """创建支持async context manager的mock API客户端"""
    mock_api = AsyncMock()
    mock_api.__aenter__.return_value = mock_api
    mock_api.__aexit__.return_value = None
    if return_value:
        mock_api.request = AsyncMock(return_value=return_value)
    return mock_api


class TestReportValidationLogic:
    """测试report的validation逻辑"""

    @pytest.mark.asyncio
    async def test_report_validation_passed_clears_directory(self):
        """测试validation任务passed时清空目录"""
        from server import mcp_server
        
        with patch('server.FileManager') as MockFileManager:
            mock_file_manager = MagicMock()
            MockFileManager.return_value = mock_file_manager
            
            # Mock has_current_task返回True
            mock_file_manager.has_current_task.return_value = True
            
            # Mock read_current_task_data返回validation任务
            mock_file_manager.read_current_task_data.return_value = {
                "id": "task-123",
                "type": "VALIDATION",
                "task_group_id": "tg-123"
            }
            
            # Mock MCP服务认证绕过
            with patch('server.get_mcp_service') as mock_get_service:
                from service import MCPService
                from unittest.mock import Mock
                
                # 创建认证通过的MCP服务
                mock_service = MCPService()
                mock_service.session_manager.is_authenticated = Mock(return_value=True)
                mock_service.session_manager.get_headers = Mock(return_value={'Authorization': 'Token test-token'})
                mock_service.file_manager = mock_file_manager
                mock_get_service.return_value = mock_service
                
                # Mock API客户端 - 返回任务组完成状态
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value = create_mock_api_client({
                        "status": "success",
                        "data": {
                            "id": "task-123",
                            "status": "COMPLETED",
                            "task_group_status": "COMPLETED"  # 任务组也完成了
                        }
                    })
                    
                    tools = await mcp_server.get_tools()
                    
                    # 上报validation任务结果，且passed=True
                    result = await tools["report"].run({
                        "task_id": "task-123",
                        "result_data": {
                            "success": True,
                            "validation_result": {
                                "passed": True,
                                "details": "所有验证通过"
                            }
                        }
                    })
                    
                    # 验证清空了任务组目录（因为任务组完成了）
                    mock_file_manager.cleanup_task_group_files.assert_called_once_with('tg-123')

    @pytest.mark.asyncio
    async def test_report_validation_failed_does_not_clear_directory(self):
        """测试validation任务failed时不清空目录"""
        from server import mcp_server
        
        with patch('server.FileManager') as MockFileManager:
            mock_file_manager = MagicMock()
            MockFileManager.return_value = mock_file_manager
            
            # Mock has_current_task返回True
            mock_file_manager.has_current_task.return_value = True
            
            # Mock read_current_task_data返回validation任务
            mock_file_manager.read_current_task_data.return_value = {
                "id": "task-123",
                "type": "VALIDATION",
                "task_group_id": "tg-123"
            }
            
            # Mock MCP服务认证绕过
            with patch('server.get_mcp_service') as mock_get_service:
                from service import MCPService
                from unittest.mock import Mock
                
                # 创建认证通过的MCP服务
                mock_service = MCPService()
                mock_service.session_manager.is_authenticated = Mock(return_value=True)
                mock_service.session_manager.get_headers = Mock(return_value={'Authorization': 'Token test-token'})
                mock_service.file_manager = mock_file_manager
                mock_get_service.return_value = mock_service
                
                # Mock API客户端
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value = create_mock_api_client({
                        "status": "success",
                        "data": {
                            "id": "task-123",
                            "status": "COMPLETED"
                        }
                    })
                    
                    tools = await mcp_server.get_tools()
                    
                    # 上报validation任务结果，但passed=False
                    result = await tools["report"].run({
                        "task_id": "task-123",
                        "result_data": {
                            "success": True,
                            "validation_result": {
                                "passed": False,
                                "details": "验证失败"
                            }
                        }
                    })
                    
                    # 验证没有清空目录
                    mock_file_manager.cleanup_task_group_files.assert_not_called()

    @pytest.mark.asyncio
    async def test_report_non_validation_task_does_not_clear_directory(self):
        """测试非validation任务不清空目录"""
        from server import mcp_server
        
        with patch('server.FileManager') as MockFileManager:
            mock_file_manager = MagicMock()
            MockFileManager.return_value = mock_file_manager
            
            # Mock has_current_task返回True
            mock_file_manager.has_current_task.return_value = True
            
            # Mock read_current_task_data返回非validation任务
            mock_file_manager.read_current_task_data.return_value = {
                "id": "task-123",
                "type": "UNDERSTANDING",
                "task_group_id": "tg-123"
            }
            
            # Mock MCP服务认证绕过
            with patch('server.get_mcp_service') as mock_get_service:
                from service import MCPService
                from unittest.mock import Mock
                
                # 创建认证通过的MCP服务
                mock_service = MCPService()
                mock_service.session_manager.is_authenticated = Mock(return_value=True)
                mock_service.session_manager.get_headers = Mock(return_value={'Authorization': 'Token test-token'})
                mock_service.file_manager = mock_file_manager
                mock_get_service.return_value = mock_service
                
                # Mock API客户端
                with patch('service.get_api_client') as mock_get_client:
                    mock_get_client.return_value = create_mock_api_client({
                        "status": "success",
                        "data": {
                            "id": "task-123",
                            "status": "COMPLETED"
                        }
                    })
                    
                    tools = await mcp_server.get_tools()
                    
                    # 上报非validation任务结果
                    result = await tools["report"].run({
                        "task_id": "task-123",
                        "result_data": {
                            "success": True,
                            "output": "/docs/understanding.md"
                        }
                    })
                    
                    # 验证没有清空目录
                    mock_file_manager.cleanup_task_group_files.assert_not_called()


# 移除了TestTaskNumberingLogic类中的过时测试
# 原因：任务编号逻辑已简化，不再依赖复杂的异步API调用
# 现在直接使用API返回的order参数或本地文件计数，无需单独测试异步资源管理