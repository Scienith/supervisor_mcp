"""
测试next工具返回文件位置信息功能
验证任务详情保存到本地文件，响应中返回文件位置而非详细内容
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil
from pathlib import Path

from src.service import MCPService
from src.file_manager import FileManager


class TestNextFileLocationResponse:
    """测试next工具文件位置响应"""

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

    @pytest.fixture
    def mcp_service(self, file_manager):
        """创建MCPService实例"""
        service = MCPService()
        service.file_manager = file_manager
        # Mock session manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service.session_manager.get_headers.return_value = {"Authorization": "Bearer test-token"}
        service._session_restore_attempted = True
        return service

    def setup_project(self, file_manager):
        """设置测试项目"""
        file_manager.create_supervisor_directory()
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project"
        }
        file_manager.save_project_info(project_info)

    @pytest.mark.asyncio
    async def test_next_saves_full_content_returns_file_location(self, mcp_service, file_manager):
        """测试next保存完整内容到文件，响应中返回文件位置"""
        # Setup
        self.setup_project(file_manager)
        
        # 创建包含详细内容的API响应
        full_task_description = """# 实现用户头像上传功能

## 需求描述
实现用户头像上传、裁剪和存储功能。

## 技术要求
- 支持 PNG、JPG、GIF 格式
- 自动裁剪为正方形
- 压缩到 200KB 以内

## 实现步骤
1. 前端上传组件
2. 后端接收处理
3. 存储到云存储
4. 更新用户信息

## 验收标准
- 用户可以成功上传头像
- 头像显示正确
- 存储大小符合要求
"""
        
        api_response = {
            "status": "success",
            "task": {
                "id": "task-001",
                "title": "实现用户头像上传功能",
                "type": "IMPLEMENTING",
                "task_group_id": "tg-001",
                "order": 1,
                "description": full_task_description
            }
        }
        
        with patch.object(mcp_service, '_get_project_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # 验证响应格式
            assert result["status"] == "success"
            assert result["task"]["id"] == "task-001"
            assert result["task"]["title"] == "实现用户头像上传功能"
            
            # 验证响应中的description被替换为文件位置信息
            expected_file_path = "supervisor_workspace/current_task_group/01_implementing_instructions.md"
            assert expected_file_path in result["task"]["description"]
            assert "任务详情已保存到本地文件" in result["task"]["description"]
            assert "请查看该文件获取完整的任务说明和要求" in result["task"]["description"]
            
            # 验证原始详细内容没有在响应中返回
            assert "## 需求描述" not in result["task"]["description"]
            assert "## 技术要求" not in result["task"]["description"]
            
            # 验证文件确实被创建
            expected_file = file_manager.current_task_group_dir / "01_implementing_instructions.md"
            assert expected_file.exists()
            
            # 验证文件内容包含完整的原始description
            saved_content = expected_file.read_text(encoding="utf-8")
            assert "# 实现用户头像上传功能" in saved_content
            assert "## 需求描述" in saved_content
            assert "## 技术要求" in saved_content
            assert "## 实现步骤" in saved_content
            assert "## 验收标准" in saved_content

    @pytest.mark.asyncio
    async def test_next_without_order_generates_correct_filename(self, mcp_service, file_manager):
        """测试next没有order时生成正确的文件名"""
        # Setup
        self.setup_project(file_manager)
        
        api_response = {
            "status": "success",
            "task": {
                "id": "task-002",
                "title": "数据库设计",
                "type": "PLANNING",
                "task_group_id": "tg-001",
                # 注意：没有order字段
                "description": "设计用户头像存储的数据库结构..."
            }
        }
        
        with patch.object(mcp_service, '_get_project_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # 验证文件名生成逻辑（第一个文件应该是01）
            expected_file_path = "supervisor_workspace/current_task_group/01_planning_instructions.md"
            assert expected_file_path in result["task"]["description"]
            
            # 验证文件确实被创建
            expected_file = file_manager.current_task_group_dir / "01_planning_instructions.md"
            assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_next_file_save_failure_shows_warning(self, mcp_service, file_manager):
        """测试next文件保存失败时显示警告"""
        # Setup
        self.setup_project(file_manager)
        
        api_response = {
            "status": "success", 
            "task": {
                "id": "task-003",
                "title": "测试任务",
                "type": "UNDERSTANDING",
                "task_group_id": "tg-001",
                "order": 1,
                "description": "测试任务内容"
            }
        }
        
        with patch.object(mcp_service, '_get_project_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Mock file_manager.save_current_task to raise exception
            with patch.object(file_manager, 'save_current_task', side_effect=Exception("File save error")):
                # Execute
                result = await mcp_service.next("test-project-123")
                
                # 验证警告信息
                assert "warning" in result
                assert "Failed to save task locally: File save error" in result["warning"]
                
                # 验证基本响应仍然正确
                assert result["status"] == "success"
                assert result["task"]["id"] == "task-003"

    @pytest.mark.asyncio
    async def test_next_missing_task_group_id_shows_warning(self, mcp_service, file_manager):
        """测试next缺少task_group_id时显示警告"""
        # Setup
        self.setup_project(file_manager)
        
        api_response = {
            "status": "success",
            "task": {
                "id": "task-004", 
                "title": "测试任务",
                "type": "FIXING",
                # 注意：缺少task_group_id
                "order": 1,
                "description": "修复任务内容"
            }
        }
        
        with patch.object(mcp_service, '_get_project_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # 验证警告信息
            assert "warning" in result
            assert "Task missing task_group_id, cannot save locally" in result["warning"]