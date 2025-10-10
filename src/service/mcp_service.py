"""
MCP服务层 - 处理认证和API调用（已迁移至 service 包）
"""
from typing import Dict, Any, Optional, List, Union
from session import SessionManager
import service
from file_manager import FileManager

class MCPService:
    """MCP服务类，整合认证、API调用和文件管理"""
    
    def __init__(self):
        self.file_manager = FileManager()
        self.session_manager = SessionManager(self.file_manager)
        self.api_client = None
        self._session_restore_attempted = False
        # Note: current_task_id is now retrieved from project_info['in_progress_task']['id']
        # Note: project context is now managed by SessionManager
    async def _auto_restore_session(self):
        """自动从本地文件恢复session和项目上下文"""
        try:
            # 检查是否存在项目信息
            if not self.file_manager.has_project_info():
                return
            
            # 读取本地项目信息
            project_info = self.file_manager.read_project_info()
            
            # 项目上下文信息已经由SessionManager自动恢复
            
            # 用户信息由SessionManager自动恢复
            if self.session_manager.is_authenticated():
                user_info = self.session_manager.get_current_user_info()
                if user_info:
                    print(f"Auto-restored session for user: {user_info.get('username', 'unknown')}", 
                          file=__import__('sys').stderr)
                
        except Exception:
            # 任何错误都静默处理，不影响服务启动
            pass

    async def _ensure_session_restored(self):
        """确保session已经尝试过恢复"""
        if not self._session_restore_attempted:
            self._session_restore_attempted = True
            await self._auto_restore_session()

    def get_current_project_id(self) -> Optional[str]:
        """获取当前项目ID（如果已恢复）"""
        return self.session_manager.get_current_project_id()
    
    def get_current_project_name(self) -> Optional[str]:
        """获取当前项目名称（如果已恢复）"""
        return self.session_manager.get_current_project_name()
    
    def get_current_task_id(self) -> Optional[str]:
        """获取当前任务组ID（如果已恢复）"""
        if not self.file_manager.has_project_info():
            return None
        project_info = self.file_manager.read_project_info()
        in_progress_group = project_info.get('in_progress_task')
        return in_progress_group['id'] if in_progress_group else None
    
    def has_project_context(self) -> bool:
        """检查是否有项目上下文"""
        return self.session_manager.has_project_context()

    async def _save_phase_strict(self, task_phase_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """严格保存任务阶段到本地（委托 service.persistence）。"""
        from . import persistence as _p
        return await _p.save_phase_strict(self, task_phase_data, context)

    def _get_project_api_client(self):
        """获取API客户端，使用全局配置"""
        # 始终使用全局配置的API地址
        return service.get_api_client()
    
    async def _validate_local_token_with_file_manager(self, username: str, file_manager: FileManager) -> Optional[Dict[str, Any]]:
        """使用指定 FileManager 验证本地保存的token是否有效（委托 service.auth）。"""
        from . import auth as _auth
        return await _auth.validate_local_token_with_file_manager(self, username, file_manager)
    
    async def _validate_local_token(self, username: str) -> Optional[Dict[str, Any]]:
        """验证本地保存的token是否有效（委托 service.auth）。"""
        from . import auth as _auth
        return await _auth.validate_local_token(self, username)
    
    async def login(self, username: str, password: str, working_directory: str) -> Dict[str, Any]:
        """用户登录（委托 service.auth）。"""
        from . import auth as _auth
        return await _auth.login(self, username, password, working_directory)
    
    async def logout(self) -> Dict[str, Any]:
        """用户登出（委托 service.auth）。"""
        from . import auth as _auth
        return await _auth.logout(self)

    async def login_with_project(self, username: str, password: str, project_id: str,
                                 working_directory: Optional[str] = None) -> Dict[str, Any]:
        """一站式登录并初始化项目工作区（委托 service.auth）。"""
        from . import auth as _auth
        return await _auth.login_with_project(self, username, password, project_id, working_directory)

    async def init(self, project_name: Optional[str] = None, description: Optional[str] = None, 
                   working_directory: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """初始化项目（委托 service.project）。"""
        from . import project as _project
        return await _project.init(self, project_name, description, working_directory, project_id)
    
    async def _init_new_project(self, project_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        from . import project as _project
        return await _project._init_new_project(self, project_name, description)
    
    async def _init_existing_project(self, project_id: str) -> Dict[str, Any]:
        from . import project as _project
        return await _project._init_existing_project(self, project_id)
    
    async def _get_project_templates_by_steps(self, api, project_id: str) -> tuple:
        from . import project as _project
        return await _project._get_project_templates_by_steps(self, api, project_id)
    
    async def _setup_workspace_unified(self, project_info: Dict[str, Any], templates_data: list, scenario: str, sop_structure: dict = None) -> Dict[str, Any]:
        from . import project as _project
        return await _project._setup_workspace_unified(self, project_info, templates_data, scenario, sop_structure)
    
    
    async def _setup_templates(self, templates_data: list, scenario: str):
        from . import project as _project
        return await _project._setup_templates(self, templates_data, scenario)

    async def _download_templates_unified(self, templates_data: list):
        from . import project as _project
        return await _project._download_templates_unified(self, templates_data)
    
    async def _setup_sop_structure(self, sop_structure: dict):
        from . import project as _project
        return await _project._setup_sop_structure(self, sop_structure)
    
    async def _create_task_folders(self, tasks: list):
        from . import project as _project
        return await _project._create_task_folders(self, tasks)
    
    async def next(self) -> Dict[str, Any]:
        from . import tasks as _tasks
        return await _tasks.next(self)
    
    
    async def report(self, task_phase_id: Optional[str], result_data: Dict[str, Any], finish_task: bool = False) -> Dict[str, Any]:
        from . import tasks as _tasks
        return await _tasks.report(self, task_phase_id, result_data, finish_task)
    
    
    
    async def pre_analyze(self, user_requirement: str) -> Dict[str, Any]:
        from . import tasks as _tasks
        return await _tasks.pre_analyze(self, user_requirement)
    
    async def add_task(self, title: str, goal: str, sop_step_identifier: str) -> Dict[str, Any]:
        from . import tasks as _tasks
        return await _tasks.add_task(self, title, goal, sop_step_identifier)
    
    async def cancel_task(self, task_id: Optional[str], cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
        """
        取消指定的任务组
        
        Args:
            task_id: 要取消的任务组ID
            cancellation_reason: 取消原因（可选）
            
        Returns:
            dict: 取消操作的结果
        """
        from . import tasks as _tasks
        return await _tasks.cancel_task(self, task_id, cancellation_reason)

    async def finish_task(self, task_id: Optional[str]) -> Dict[str, Any]:
        """
        直接将任务标记为完成状态

        Args:
            task_id: 要完成的任务ID

        Returns:
            dict: 完成操作的结果
        """
        from . import tasks as _tasks
        return await _tasks.finish_task(self, task_id)

    async def start_task(self, task_id: Optional[str]) -> Dict[str, Any]:
        """
        启动指定的任务组
        
        Args:
            task_id: 要启动的任务组ID
            
        Returns:
            dict: 启动操作结果
        """
        from . import tasks as _tasks
        return await _tasks.start_task(self, task_id)
    
    async def suspend_task(self) -> Dict[str, Any]:
        """
        暂存当前任务组（调用后端API并同步本地状态）
            
        Returns:
            dict: 暂存操作结果
        """
        from . import tasks as _tasks
        return await _tasks.suspend_task(self)
    
    async def continue_suspended_task(self, task_id: Optional[str]) -> Dict[str, Any]:
        """
        恢复指定的暂存任务组（调用后端API并同步本地状态）
        
        Args:
            task_id: 要恢复的暂存任务组ID
            
        Returns:
            dict: 恢复操作结果
        """
        from . import tasks as _tasks
        return await _tasks.continue_suspended_task(self, task_id)
    
    
    async def get_project_status(self, detailed: bool = False) -> Dict[str, Any]:
        from . import tasks as _tasks
        return await _tasks.get_project_status(self, detailed)

    async def update_step_rules(self, stage: str, step_identifier: str) -> Dict[str, Any]:
        """更新Step的规则（委托至 service.sop）"""
        from . import sop as _sop
        return await _sop.update_step_rules(self, stage, step_identifier)

    async def update_output_template(self, stage: str, step_identifier: str, output_name: str) -> Dict[str, Any]:
        """更新Output的模板内容（委托至 service.sop）"""
        from . import sop as _sop
        return await _sop.update_output_template(self, stage, step_identifier, output_name)

    # 读取SOP配置/模板的私有帮助函数已移至 service.sop
    def _read_step_config(self, stage: str, step_identifier: str):
        from . import sop as _sop
        return _sop._read_step_config(self, stage, step_identifier)

    def _read_output_config_and_template(self, stage: str, step_identifier: str, output_name: str):
        from . import sop as _sop
        return _sop._read_output_config_and_template(self, stage, step_identifier, output_name)

    # 读取SOP配置/模板的私有帮助函数已移至 service.sop

    def _get_current_task_phase_type(self) -> str:
        from . import phases as _ph
        return _ph._get_current_task_phase_type(self)

    @staticmethod
    def _format_phase_label(phase_type: Optional[str]) -> str:
        from . import phases as _ph
        return _ph._format_phase_label(phase_type)

    @staticmethod
    def _extract_phase_type_from_filename(filename: Optional[str]) -> str:
        """从任务阶段文件名推断阶段类型"""
        if not filename:
            raise ValueError("无法从文件名推断任务阶段：文件名不存在")
        name = filename.split("/")[-1]
        parts = name.split("_")
        if len(parts) >= 2:
            candidate = parts[1].upper()
            if candidate.isalpha():
                return candidate
        raise ValueError(f"无法从文件名推断任务阶段：{filename}")

    def _predict_next_phase_type(
        self,
        current_phase_type: Optional[str],
        validation_passed: Optional[bool] = None,
    ) -> str:
        from . import phases as _ph
        return _ph._predict_next_phase_type(self, current_phase_type, validation_passed)

    async def _get_pending_tasks_instructions(
        self,
        return_as_string: bool = False
    ) -> Union[List[Dict[str, Any]], str]:
        from . import phases as _ph
        return await _ph._get_pending_tasks_instructions(self, return_as_string)

    def _create_instruction(
        self,
        to_ai: str,
        user_message: List[str] = None,
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        from . import phases as _ph
        return _ph._create_instruction(self, to_ai, user_message, result)
