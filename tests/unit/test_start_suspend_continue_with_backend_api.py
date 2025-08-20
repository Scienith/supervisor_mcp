"""
测试基于后端API的start、suspend、continue功能的单元测试
采用TDD方式，先写测试（红灯），再实现功能（绿灯）
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil
from pathlib import Path
import json
from datetime import datetime

from src.service import MCPService
from src.file_manager import FileManager


class TestStartSuspendContinueWithBackendAPI:
    """基于后端API的任务组状态管理功能测试"""

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

    def setup_test_project(self, file_manager):
        """设置测试项目环境"""
        file_manager.create_supervisor_directory()
        
        # 创建项目信息
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "in_progress_task_group": None,
            "suspended_task_groups": []
        }
        file_manager.save_project_info(project_info)

    # ===== START 功能测试 =====

    @pytest.mark.asyncio
    async def test_start_task_group_success(self, mcp_service, file_manager):
        """测试成功启动PENDING任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-001",
                "title": "用户界面设计",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T15:30:00Z"
            },
            "message": "任务组已成功启动"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute - 这个方法还不存在，需要实现
            result = await mcp_service.start_task_group("test-project-123", "tg-001")
            
            # Verify
            assert result["status"] == "success"
            assert "任务组已成功启动" in result["message"]
            assert result["data"]["task_group_id"] == "tg-001"
            assert result["data"]["new_status"] == "IN_PROGRESS"
            
            # 验证API调用
            mock_client.request.assert_called_once_with(
                'POST',
                'projects/test-project-123/task-groups/tg-001/start/'
            )

    @pytest.mark.asyncio
    async def test_start_task_group_already_has_in_progress(self, mcp_service, file_manager):
        """测试启动任务组时已有其他IN_PROGRESS任务组的错误情况"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API错误响应
        mock_api_response = {
            "status": "error",
            "error_code": "TASK_GROUP_CONFLICT",
            "message": "项目中已有IN_PROGRESS状态的任务组"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.start_task_group("test-project-123", "tg-001")
            
            # Verify
            assert result["status"] == "error"
            assert "已有IN_PROGRESS状态的任务组" in result["message"]

    # ===== SUSPEND 功能测试（修改为调用后端API）=====

    @pytest.mark.asyncio
    async def test_suspend_task_group_with_backend_api(self, mcp_service, file_manager):
        """测试通过后端API暂存任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # 设置项目有当前任务组
        project_info = file_manager.read_project_info()
        project_info["in_progress_task_group"] = {
            "id": "tg-001",
            "title": "测试任务组",
            "status": "IN_PROGRESS"
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_group_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_understanding_instructions.md").write_text("Test instructions")
        (current_dir / "task_data.json").write_text('{"test": "data"}')
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-001",
                "title": "用户界面设计",
                "previous_status": "IN_PROGRESS",
                "new_status": "SUSPENDED",
                "suspended_at": "2024-12-20T15:30:00Z"
            },
            "message": "任务组已成功暂存"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.suspend_task_group("test-project-123")
            
            # Verify
            assert result["status"] == "success"
            assert "任务组已成功暂存" in result["message"]
            
            # 验证后端API调用
            mock_client.request.assert_called_once_with(
                'POST',
                'projects/test-project-123/task-groups/tg-001/suspend/'
            )
            
            # 验证本地文件被暂存
            suspended_dir = file_manager.suspended_task_groups_dir / "task_group_tg-001"
            assert suspended_dir.exists()
            assert (suspended_dir / "01_understanding_instructions.md").exists()
            
            # 验证项目信息更新
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info["in_progress_task_group"] is None

    # ===== RESUME/CONTINUE 功能测试（修改为调用后端API）=====

    @pytest.mark.asyncio
    async def test_continue_suspended_with_backend_api(self, mcp_service, file_manager):
        """测试通过后端API恢复暂存任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # 添加暂停的任务组信息到项目信息中
        project_info = file_manager.read_project_info()
        project_info["suspended_task_groups"] = [{
            "id": "tg-002",
            "title": "数据库设计",
            "status": "SUSPENDED",
            "suspended_at": "2024-12-20T15:00:00Z",
            "files_count": 1
        }]
        file_manager.save_project_info(project_info)
        
        # 创建暂存的任务组文件
        suspended_dir = file_manager.suspended_task_groups_dir / "task_group_tg-002"
        suspended_dir.mkdir(parents=True, exist_ok=True)
        (suspended_dir / "02_planning_instructions.md").write_text("Suspended task")
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_group_id": "tg-002",
                "title": "数据库设计",
                "previous_status": "SUSPENDED",
                "new_status": "IN_PROGRESS",
                "resumed_at": "2024-12-20T16:00:00Z"
            },
            "message": "任务组已成功恢复"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.continue_suspended_task_group("test-project-123", "tg-002")
            
            # Verify
            assert result["status"] == "success"
            assert "任务组已成功恢复" in result["message"]
            
            # 验证后端API调用
            mock_client.request.assert_called_once_with(
                'POST',
                'projects/test-project-123/task-groups/tg-002/resume/'
            )
            
            # 验证文件被恢复到当前工作目录
            assert (file_manager.current_task_group_dir / "02_planning_instructions.md").exists()
            
            # 验证项目信息更新
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info["in_progress_task_group"]["id"] == "tg-002"

    # ===== GET_PROJECT_STATUS 修改测试 =====

    @pytest.mark.asyncio
    async def test_get_project_status_with_new_format(self, mcp_service, file_manager):
        """测试get_project_status返回新格式（包含不同状态的任务组）"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API新格式响应
        mock_api_response = {
            "status": "success",
            "data": {
                "project_id": "test-project-123",
                "project_name": "Test Project",
                "created_at": "2024-12-01T10:00:00Z",
                "overall_progress": 65,
                "task_groups_summary": {
                    "total": 4,
                    "pending": 2,
                    "in_progress": 1,
                    "suspended": 1,
                    "completed": 0,
                    "cancelled": 0
                },
                "current_in_progress_group": {
                    "id": "tg_001",
                    "title": "用户界面设计",
                    "status": "IN_PROGRESS",
                    "progress": {
                        "total_tasks": 5,
                        "completed_tasks": 2
                    }
                },
                "pending_groups": [
                    {
                        "id": "tg_002", 
                        "title": "数据库设计",
                        "status": "PENDING",
                        "order": 1
                    },
                    {
                        "id": "tg_003", 
                        "title": "API设计",
                        "status": "PENDING",
                        "order": 2
                    }
                ],
                "suspended_groups": [
                    {
                        "id": "tg_004",
                        "title": "测试设计", 
                        "status": "SUSPENDED",
                        "suspended_at": "2024-12-20T15:30:00Z"
                    }
                ]
            }
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute - 这个方法可能需要修改以支持新格式
            result = await mcp_service.get_project_status("test-project-123", detailed=True)
            
            # Verify
            assert result["status"] == "success"
            data = result["data"]
            
            # 验证新格式字段
            assert "current_in_progress_group" in data
            assert "pending_groups" in data
            assert "suspended_groups" in data
            
            assert data["current_in_progress_group"]["id"] == "tg_001"
            assert len(data["pending_groups"]) == 2
            assert len(data["suspended_groups"]) == 1
            assert data["suspended_groups"][0]["id"] == "tg_004"


    # ===== NEXT API 修改测试 =====

    @pytest.mark.asyncio
    async def test_next_only_from_in_progress_groups(self, mcp_service, file_manager):
        """测试next API只从IN_PROGRESS任务组返回任务"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应 - 正常情况
        mock_api_response = {
            "status": "success",
            "task": {
                "id": "task_123",
                "title": "理解现状: UI设计需求",
                "type": "UNDERSTANDING",
                "task_group_id": "tg_001"
            },
            "context": {
                "description": "分析当前UI设计需求"
            }
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # Verify
            assert result["status"] == "success"
            assert "task" in result
            assert result["task"]["id"] == "task_123"

    @pytest.mark.asyncio
    async def test_next_no_in_progress_groups(self, mcp_service, file_manager):
        """测试next API在没有IN_PROGRESS任务组时返回no_available_tasks"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应 - 没有可用任务
        mock_api_response = {
            "status": "no_available_tasks",
            "message": "当前没有可执行的任务"
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # Verify
            assert result["status"] == "no_available_tasks"
            assert "没有可执行的任务" in result["message"]

    @pytest.mark.asyncio
    async def test_next_task_group_state_inconsistent_error(self, mcp_service, file_manager):
        """测试next API遇到任务组状态不一致时的错误处理"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应 - 状态不一致错误
        mock_api_response = {
            "status": "error",
            "error_code": "TASK_GROUP_STATE_INCONSISTENT",
            "message": "任务组状态异常：任务组为IN_PROGRESS状态但没有可执行任务",
            "data": {
                "task_group_id": "tg_123",
                "task_group_title": "用户界面设计",
                "task_group_status": "IN_PROGRESS",
                "last_completed_task": {
                    "id": "task_789",
                    "title": "验收: UI设计完成确认",
                    "type": "VALIDATION",
                    "completed_at": "2024-12-20T15:30:00Z"
                }
            }
        }
        
        with patch('src.service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next("test-project-123")
            
            # Verify
            assert result["status"] == "error"
            assert result["error_code"] == "TASK_GROUP_STATE_INCONSISTENT"
            assert "任务组状态异常" in result["message"]
            assert "data" in result
            assert result["data"]["task_group_id"] == "tg_123"