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

from service import MCPService
from file_manager import FileManager


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
        # 设置项目上下文
        service.session_manager.current_project_id = "test-project-123"
        service.session_manager.current_project_name = "Test Project"
        # 设置方法返回值
        service.session_manager.get_current_project_id.return_value = "test-project-123"
        service.session_manager.get_current_project_name.return_value = "Test Project"
        service.session_manager.has_project_context.return_value = True
        return service

    def setup_test_project(self, file_manager):
        """设置测试项目环境"""
        file_manager.create_supervisor_directory()

        # 创建项目信息
        project_info = {
            "project_id": "test-project-123",
            "project_name": "Test Project",
            "in_progress_task": {
                "id": "tg_001",
                "title": "测试任务",
                "status": "IN_PROGRESS"
            },
            "suspended_tasks": []
        }
        file_manager.save_project_info(project_info)

    # ===== START 功能测试 =====

    @pytest.mark.asyncio
    async def test_start_task_success(self, mcp_service, file_manager):
        """测试成功启动PENDING任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_id": "tg-001",
                "title": "用户界面设计",
                "previous_status": "PENDING",
                "new_status": "IN_PROGRESS",
                "started_at": "2024-12-20T15:30:00Z"
            },
            "message": "任务组已成功启动"
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute - 这个方法还不存在，需要实现
            result = await mcp_service.start_task("tg-001")
            
            # Verify
            assert result["status"] == "success"
            assert "任务组已成功启动" in result["message"]
            # data字段已被移除，检查instructions字段
            assert "instructions" in result
            assert len(result["instructions"]) > 0
            
            # 验证API调用
            mock_client.request.assert_called_once_with(
                'POST',
                'projects/test-project-123/tasks/tg-001/start/'
            )

    @pytest.mark.asyncio
    async def test_start_task_already_has_in_progress(self, mcp_service, file_manager):
        """测试启动任务组时已有其他IN_PROGRESS任务组的错误情况"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API错误响应
        mock_api_response = {
            "status": "error",
            "error_code": "TASK_GROUP_CONFLICT",
            "message": "项目中已有IN_PROGRESS状态的任务组"
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.start_task("tg-001")
            
            # Verify
            assert result["status"] == "error"
            assert "已有IN_PROGRESS状态的任务组" in result["message"]

    # ===== SUSPEND 功能测试（修改为调用后端API）=====

    @pytest.mark.asyncio
    async def test_suspend_task_with_backend_api(self, mcp_service, file_manager):
        """测试通过后端API暂存任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # 设置项目有当前任务组
        project_info = file_manager.read_project_info()
        project_info["in_progress_task"] = {
            "id": "tg-001",
            "title": "测试任务组",
            "status": "IN_PROGRESS"
        }
        file_manager.save_project_info(project_info)
        
        # 创建当前任务组的工作文件
        current_dir = file_manager.current_task_dir
        current_dir.mkdir(parents=True, exist_ok=True)
        (current_dir / "01_understanding_instructions.md").write_text("Test instructions")
        (current_dir / "task_data.json").write_text('{"test": "data"}')
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_id": "tg-001",
                "title": "用户界面设计",
                "previous_status": "IN_PROGRESS",
                "new_status": "SUSPENDED",
                "suspended_at": "2024-12-20T15:30:00Z"
            },
            "message": "任务组已成功暂存"
        }
        
        # Mock status response for _get_pending_tasks_instructions
        mock_status_response = {
            "status": "success",
            "pending_tasks": [],
            "suspended_tasks": [
                {
                    "id": "tg-001",
                    "title": "用户界面设计",
                    "sop_step_identifier": "uiDesign",
                    "goal": "设计用户界面",
                    "suspended_at": "2024-12-20T15:30:00Z"
                }
            ]
        }

        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            # 设置side_effect以返回不同的响应
            mock_client.request.side_effect = [mock_api_response, mock_status_response]
            mock_get_client.return_value.__aenter__.return_value = mock_client

            # Execute
            result = await mcp_service.suspend_task()

            # Verify
            assert result["status"] == "success"
            assert "任务组已成功暂存" in result["message"]

            # 验证后端API调用 - 现在应该有两次调用
            assert mock_client.request.call_count == 2
            # 第一次调用是suspend
            mock_client.request.assert_any_call(
                'POST',
                'projects/test-project-123/tasks/tg-001/suspend/'
            )
            # 第二次调用是get_project_status (由_get_pending_tasks_instructions内部调用)
            mock_client.request.assert_any_call(
                'GET',
                'projects/test-project-123/status/',
                params={'detail': 'true'}
            )
            
            # 验证本地文件被暂存
            suspended_dir = file_manager.suspended_tasks_dir / "task_tg-001"
            assert suspended_dir.exists()
            assert (suspended_dir / "01_understanding_instructions.md").exists()
            
            # 验证项目信息更新
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info["in_progress_task"] is None

    # ===== RESUME/CONTINUE 功能测试（修改为调用后端API）=====

    @pytest.mark.asyncio
    async def test_continue_suspended_with_backend_api(self, mcp_service, file_manager):
        """测试通过后端API恢复暂存任务组"""
        # Setup
        self.setup_test_project(file_manager)
        
        # 添加暂停的任务组信息到项目信息中
        project_info = file_manager.read_project_info()
        project_info["suspended_tasks"] = [{
            "id": "tg-002",
            "title": "数据库设计",
            "status": "SUSPENDED",
            "suspended_at": "2024-12-20T15:00:00Z",
            "files_count": 1
        }]
        file_manager.save_project_info(project_info)
        
        # 创建暂存的任务组文件
        suspended_dir = file_manager.suspended_tasks_dir / "task_tg-002"
        suspended_dir.mkdir(parents=True, exist_ok=True)
        (suspended_dir / "02_planning_instructions.md").write_text("Suspended task")
        
        # Mock后端API响应
        mock_api_response = {
            "status": "success",
            "data": {
                "task_id": "tg-002",
                "title": "数据库设计",
                "previous_status": "SUSPENDED",
                "new_status": "IN_PROGRESS",
                "resumed_at": "2024-12-20T16:00:00Z"
            },
            "message": "任务组已成功恢复"
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.continue_suspended_task("tg-002")
            
            # Verify
            assert result["status"] == "success"
            assert "任务组已成功恢复" in result["message"]
            
            # 验证后端API调用
            mock_client.request.assert_called_once_with(
                'POST',
                'projects/test-project-123/tasks/tg-002/resume/'
            )
            
            # 验证文件被恢复到当前工作目录
            assert (file_manager.current_task_dir / "02_planning_instructions.md").exists()
            
            # 验证项目信息更新
            updated_project_info = file_manager.read_project_info()
            assert updated_project_info["in_progress_task"]["id"] == "tg-002"

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
                "tasks_summary": {
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
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute - 这个方法可能需要修改以支持新格式
            result = await mcp_service.get_project_status(detailed=True)
            
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
            "task_phase": {
                "id": "task_123",
                "title": "理解现状: UI设计需求",
                "type": "UNDERSTANDING",
                "task_id": "tg_001",
                "order": 1,
                "description": "分析当前UI设计需求的详细说明"
            },
            "context": {
                "description": "分析当前UI设计需求"
            }
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next()
            
            # Verify
            assert result["status"] == "success"
            # task_phase已被移除，返回instructions引导信息
            assert "instructions" in result

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
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next()
            
            # Verify
            assert result["status"] == "no_available_tasks"
            assert "没有可执行的任务" in result["message"]

    @pytest.mark.asyncio
    async def test_next_task_state_inconsistent_error(self, mcp_service, file_manager):
        """测试next API遇到任务组状态不一致时的错误处理"""
        # Setup
        self.setup_test_project(file_manager)
        
        # Mock后端API响应 - 状态不一致错误
        mock_api_response = {
            "status": "error",
            "error_code": "TASK_GROUP_STATE_INCONSISTENT",
            "message": "任务组状态异常：任务组为IN_PROGRESS状态但没有可执行任务",
            "data": {
                "task_id": "tg_123",
                "task_title": "用户界面设计",
                "task_status": "IN_PROGRESS",
                "last_completed_task": {
                    "id": "task_789",
                    "title": "验收: UI设计完成确认",
                    "type": "VALIDATION",
                    "completed_at": "2024-12-20T15:30:00Z"
                }
            }
        }
        
        with patch('service.get_api_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.headers = {}  # 添加headers属性
            mock_client.request.return_value = mock_api_response
            mock_get_client.return_value.__aenter__.return_value = mock_client
            
            # Execute
            result = await mcp_service.next()
            
            # Verify
            assert result["status"] == "error"
            assert result["error_code"] == "TASK_GROUP_STATE_INCONSISTENT"
            assert "任务组状态异常" in result["message"]

    @pytest.mark.asyncio
    async def test_start_task_no_project_context(self, file_manager):
        """测试start_task在没有项目上下文时返回错误"""
        # Setup service without project context
        service = MCPService()
        service.file_manager = file_manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service.session_manager.get_headers.return_value = {"Authorization": "Bearer test-token"}
        service._session_restore_attempted = True
        # 不设置current_project_id，模拟没有项目上下文
        service.session_manager.has_project_context.return_value = False
        service.session_manager.get_current_project_id.return_value = None

        # Execute
        result = await service.start_task("tg-001")
        
        # Verify
        assert result["status"] == "error"
        assert "No project context found" in result["message"]
        assert "setup_workspace or create_project" in result["message"]

    @pytest.mark.asyncio
    async def test_suspend_task_no_project_context(self, file_manager):
        """测试suspend_task在没有项目上下文时返回错误"""
        # Setup service without project context
        service = MCPService()
        service.file_manager = file_manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service._session_restore_attempted = True
        # 不设置current_project_id
        service.session_manager.has_project_context.return_value = False
        service.session_manager.get_current_project_id.return_value = None

        # Execute
        result = await service.suspend_task()
        
        # Verify
        assert result["status"] == "error"
        assert "No project context found" in result["message"]

    @pytest.mark.asyncio
    async def test_get_project_status_no_project_context(self, file_manager):
        """测试get_project_status在没有项目上下文时返回错误"""
        # Setup service without project context
        service = MCPService()
        service.file_manager = file_manager
        service.session_manager = MagicMock()
        service.session_manager.is_authenticated.return_value = True
        service._session_restore_attempted = True
        # 不设置current_project_id
        service.session_manager.has_project_context.return_value = False
        service.session_manager.get_current_project_id.return_value = None

        # Execute
        result = await service.get_project_status(detailed=True)
        
        # Verify
        assert result["status"] == "error"
        assert "No project context found" in result["message"]
