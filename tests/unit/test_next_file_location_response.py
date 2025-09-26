"""
测试next工具返回文件位置信息功能
验证任务详情保存到本地文件，响应中返回文件位置而非详细内容
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil
from pathlib import Path

from service import MCPService
from file_manager import FileManager


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
        # 设置项目上下文
        service.session_manager.current_project_id = "test-project-123"
        service.session_manager.current_project_name = "Test Project"
        # 设置方法返回值
        service.session_manager.get_current_project_id.return_value = "test-project-123"
        service.session_manager.get_current_project_name.return_value = "Test Project"
        service.session_manager.has_project_context.return_value = True
        return service

    def setup_project(self, file_manager):
        """设置测试项目"""
        file_manager.create_supervisor_directory()
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "api_url": "http://localhost:8000/api/v1"
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
            "task_phase": {
                "id": "task-001",
                "title": "实现用户头像上传功能",
                "type": "IMPLEMENTING",
                "task_id": "tg-001",
                "order": 1,
                "description": full_task_description,
                "instruction_markdown": full_task_description
            }
        }
        
        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None
            
            # Execute
            result = await mcp_service.next()

            # 验证响应格式
            assert result["status"] == "success"
            # 现在task_phase被移除，以message和instructions为主
            assert "message" in result
            assert "instructions" in result

            # 验证instructions字段
            assert len(result["instructions"]) > 0
            instruction = result["instructions"][0]
            assert isinstance(instruction, str)
            assert instruction.startswith("AI注意：")
            
            # 验证文件确实被创建
            expected_file = file_manager.current_task_dir / "01_implementing_instructions.md"
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
            "task_phase": {
                "id": "task-002",
                "title": "数据库设计",
                "type": "PLANNING",
                "task_id": "tg-001",
                # 注意：没有order字段
                "description": "设计用户头像存储的数据库结构...",
                "instruction_markdown": "设计用户头像存储的数据库结构..."
            }
        }
        
        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None
            
            # Execute
            result = await mcp_service.next()
            
            # 验证文件确实被创建
            expected_file = file_manager.current_task_dir / "01_planning_instructions.md"
            assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_next_file_save_failure_shows_error(self, mcp_service, file_manager):
        """测试next文件保存失败时返回错误"""
        # Setup
        self.setup_project(file_manager)

        api_response = {
            "status": "success",
            "task_phase": {
                "id": "task-003",
                "title": "测试任务",
                "type": "UNDERSTANDING",
                "task_id": "tg-001",
                "order": 1,
                "description": "测试任务内容",
                "instruction_markdown": "测试任务内容",
                "task_markdown": "测试任务内容"
            }
        }

        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None

            # Mock file_manager.save_current_task to raise exception
            with patch.object(file_manager, 'save_current_task_phase', side_effect=Exception("File save error")):
                # Execute
                result = await mcp_service.next()

                # 验证返回错误
                assert result["status"] == "error"
                assert result["error_code"] == "FILE_SAVE_ERROR"
                assert "Failed to save task phase locally: File save error" in result["message"]
                # task_phase不应该存在
                assert "task_phase" not in result

    @pytest.mark.asyncio
    async def test_next_missing_task_id_shows_error(self, mcp_service, file_manager):
        """测试next缺少task_id时返回错误"""
        # Setup
        self.setup_project(file_manager)

        api_response = {
            "status": "success",
            "task_phase": {
                "id": "task-004",
                "title": "测试任务",
                "type": "FIXING",
                # 注意：缺少task_id
                "order": 1,
                "description": "修复任务内容",
                "instruction_markdown": "修复任务内容"
            }
        }

        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None

            # Execute
            result = await mcp_service.next()

            # 验证返回错误
            assert result["status"] == "error"
            assert result["error_code"] == "FILE_SAVE_ERROR"
            assert "Task phase missing task_id, cannot save locally" in result["message"]

    @pytest.mark.asyncio
    async def test_next_should_error_on_wrong_response_format(self, mcp_service, file_manager):
        """测试：当API返回错误格式时应该报错，而不是静默忽略"""
        # Setup
        self.setup_project(file_manager)

        # 模拟后端返回 "task" 而不是 "task_phase"
        api_response = {
            "status": "success",
            "task": {  # 错误格式：应该是 task_phase
                "id": "task-001",
                "title": "测试任务",
                "type": "IMPLEMENTING",
                "task_id": "tg-001",
                "order": 1,
                "description": "测试任务描述"
            }
        }

        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None

            # Execute
            result = await mcp_service.next()

            # 验证：应该返回错误，而不是静默忽略
            assert result["status"] == "error"
            assert "格式不匹配" in result["message"] or "task_phase" in result["message"]

    @pytest.mark.asyncio
    async def test_next_validates_required_response_format(self, mcp_service, file_manager):
        """测试：验证必需的响应格式字段"""
        # Setup
        self.setup_project(file_manager)

        # 测试缺少必需字段的情况
        api_response = {
            "status": "success"
            # 缺少 task_phase 字段
        }

        # 使用service.get_api_client而不是_get_project_api_client
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_get_client.return_value.__aexit__.return_value = None

            # Execute
            result = await mcp_service.next()

            # 验证：应该返回错误
            assert result["status"] == "error"
            assert "task_phase" in result["message"]
