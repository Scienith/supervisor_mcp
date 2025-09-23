"""
MCP服务层 - 处理认证和API调用
"""
import asyncio
from typing import Dict, Any, Optional
from session import SessionManager
from server import APIClient, get_api_client
from file_manager import FileManager
from config import config


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

    def _get_project_api_client(self):
        """获取API客户端，使用全局配置"""
        # 始终使用全局配置的API地址
        return get_api_client()
    
    async def _validate_local_token_with_file_manager(self, username: str, file_manager: FileManager) -> Optional[Dict[str, Any]]:
        """使用指定的 FileManager 验证本地保存的token是否有效"""
        try:
            # 读取本地用户信息
            user_info = file_manager.read_user_info()
            
            # 检查是否有用户信息和token
            if not all(key in user_info for key in ['user_id', 'username', 'access_token']):
                return None
            
            # 检查用户名是否匹配
            if user_info['username'] != username:
                return None
            
            # 验证token是否有效
            async with get_api_client() as api:
                # 设置Authorization header
                headers = {'Authorization': f"Token {user_info['access_token']}"}
                response = await api.request(
                    'GET',
                    'auth/validate/',
                    headers=headers
                )
            
            if response.get('success'):
                return user_info
            else:
                # Token无效或过期
                return None
                
        except FileNotFoundError:
            # 用户信息文件不存在
            return None
        except Exception:
            # 其他错误也返回None，回退到正常登录流程
            return None
    
    async def _validate_local_token(self, username: str) -> Optional[Dict[str, Any]]:
        """验证本地保存的token是否有效"""
        try:
            # 读取本地用户信息
            user_info = self.file_manager.read_user_info()
            
            # 检查是否有用户信息和token
            if not all(key in user_info for key in ['user_id', 'username', 'access_token']):
                return None
            
            # 检查用户名是否匹配
            if user_info['username'] != username:
                return None
            
            # 验证token是否有效
            async with get_api_client() as api:
                # 设置Authorization header
                headers = {'Authorization': f"Token {user_info['access_token']}"}
                response = await api.request(
                    'GET',
                    'auth/validate/',
                    headers=headers
                )
            
            if response.get('success'):
                return user_info
            
            return None
            
        except FileNotFoundError:
            # user.json不存在，返回None让调用者知道需要重新登录
            return None
        except Exception:
            # 其他错误也返回None，回退到正常登录流程
            return None
    
    async def login(self, username: str, password: str, working_directory: str) -> Dict[str, Any]:
        """用户登录
        
        Args:
            username: 用户名
            password: 密码
            working_directory: 当前工作目录（本地使用，不传给后端）
        """
        # 使用指定的工作目录创建新的 FileManager
        local_file_manager = FileManager(base_path=working_directory)
        
        try:
            # 首先尝试验证本地保存的token（使用指定目录的 FileManager）
            local_user_data = await self._validate_local_token_with_file_manager(username, local_file_manager)
            if local_user_data:
                # 本地token有效，直接使用
                # 更新全局 FileManager 和 SessionManager 使用正确的路径
                self.file_manager = local_file_manager
                self.session_manager = SessionManager(self.file_manager)
                self.session_manager.login(
                    local_user_data['user_id'],
                    local_user_data['access_token'],
                    local_user_data['username']
                )
                
                # 保存项目路径到 project.json（如果存在项目信息）
                if self.file_manager.has_project_info():
                    project_info = self.file_manager.read_project_info()
                    project_info['project_path'] = working_directory
                    self.file_manager.save_project_info(project_info)
                
                return {
                    'success': True,
                    'user_id': local_user_data['user_id'],
                    'username': local_user_data['username'],
                    'message': '使用本地缓存登录成功'
                }
            
            # 本地token无效或不存在，进行网络登录
            async with get_api_client() as api:
                response = await api.request(
                    'POST',
                    'auth/login/',
                    json={'username': username, 'password': password}
                )
            
            if response.get('success'):
                user_data = response['data']
                
                # 更新全局 FileManager 和 SessionManager 使用正确的路径
                self.file_manager = local_file_manager
                self.session_manager = SessionManager(self.file_manager)
                self.session_manager.login(
                    user_data['user_id'],
                    user_data['access_token'],
                    user_data['username']
                )
                
                # 如果有项目信息，保存项目路径
                if self.file_manager.has_project_info():
                    project_info = self.file_manager.read_project_info()
                    project_info['project_path'] = working_directory
                    self.file_manager.save_project_info(project_info)
                
                return {
                    'success': True,
                    'user_id': user_data['user_id'],
                    'username': user_data['username']
                }
            else:
                return {
                    'success': False,
                    'error_code': response.get('error_code', 'AUTH_001'),
                    'message': response.get('message', '登录失败')
                }
                
        except Exception as e:
            return {
                'success': False,
                'error_code': 'NETWORK_ERROR',
                'message': f'网络请求失败: {str(e)}'
            }
    
    async def logout(self) -> Dict[str, Any]:
        """用户登出"""
        if not self.session_manager.is_authenticated():
            return {'success': True, 'message': '用户未登录'}
        
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request('POST', 'auth/logout/')
                
            self.session_manager.logout()
            
            return {
                'success': True,
                'message': '登出成功'
            }
            
        except Exception as e:
            # 即使API调用失败，也清除本地会话
            self.session_manager.logout()
            return {
                'success': True,
                'message': '登出成功（本地会话已清除）'
            }

    async def login_with_project(self, username: str, password: str, project_id: str,
                                 working_directory: Optional[str] = None) -> Dict[str, Any]:
        """一站式登录并初始化项目工作区

        该方法整合了登录和项目初始化两个步骤，简化操作流程。

        Args:
            username: 用户名
            password: 密码
            project_id: 项目ID
            working_directory: 工作目录路径（可选，默认当前目录）

        Returns:
            dict: 包含登录和项目初始化结果
                - success: bool, 操作是否成功
                - user_id: str, 用户ID（成功时）
                - username: str, 用户名（成功时）
                - project: dict, 项目信息（成功时）
                    - project_id: str, 项目ID
                    - project_name: str, 项目名称
                    - templates_downloaded: int, 下载的模板数量
                - error_code: str, 错误代码（失败时）
                - message: str, 结果消息
        """
        # 如果未提供 working_directory，使用当前目录
        if not working_directory:
            from pathlib import Path
            working_directory = str(Path.cwd())

        # 步骤1：执行登录
        login_result = await self.login(username, password, working_directory)

        # 如果登录失败，直接返回错误
        if not login_result.get('success'):
            return login_result

        # 步骤2：初始化项目工作区
        try:
            init_result = await self.init(project_id=project_id, working_directory=working_directory)

            # 检查初始化结果
            if init_result.get('status') == 'error':
                # 初始化失败，但保持登录状态
                return {
                    'success': False,
                    'error_code': 'INIT_001',
                    'message': f"登录成功但项目初始化失败: {init_result.get('message', '未知错误')}",
                    'user_id': login_result.get('user_id'),
                    'username': login_result.get('username')
                }

            # 成功：返回整合的结果
            return {
                'success': True,
                'user_id': login_result.get('user_id'),
                'username': login_result.get('username'),
                'project': {
                    'project_id': init_result['data']['project_id'],
                    'project_name': init_result['data']['project_name'],
                    'templates_downloaded': init_result['data'].get('templates_downloaded', 0),
                    'scenario': init_result['data'].get('scenario', 'existing_project')
                },
                'message': f"登录成功并初始化项目 {init_result['data']['project_name']}"
            }

        except Exception as e:
            # 处理异常情况
            return {
                'success': False,
                'error_code': 'INIT_002',
                'message': f"登录成功但项目初始化出错: {str(e)}",
                'user_id': login_result.get('user_id'),
                'username': login_result.get('username')
            }

    async def init(self, project_name: Optional[str] = None, description: Optional[str] = None, 
                   working_directory: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """初始化项目（支持两种场景，需要登录）
        
        Args:
            project_name: 新项目名称
            description: 项目描述
            working_directory: 工作目录（默认当前目录）
            project_id: 已有项目ID
        """
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'message': '请先登录'
            }
        
        # 如果提供了working_directory，更新file_manager的base_path
        if working_directory:
            from pathlib import Path
            self.file_manager.base_path = Path(working_directory)
            # 重新初始化所有路径
            self.file_manager.supervisor_dir = self.file_manager.base_path / ".supervisor"
            self.file_manager.suspended_tasks_dir = self.file_manager.supervisor_dir / "suspended_tasks"
            self.file_manager.workspace_dir = self.file_manager.base_path / "supervisor_workspace"
            self.file_manager.templates_dir = self.file_manager.workspace_dir / "templates"
            self.file_manager.sop_dir = self.file_manager.workspace_dir / "sop"
            self.file_manager.current_task_dir = self.file_manager.workspace_dir / "current_task"
        
        # 参数验证
        if project_id:
            # 场景二：已知项目ID本地初始化
            return await self._init_existing_project(project_id)
        elif project_name:
            # 场景一：新建项目
            return await self._init_new_project(project_name, description)
        else:
            return {
                'status': 'error',
                'message': '必须提供 project_name（新建项目）或 project_id（已知项目ID）参数'
            }
    
    async def _init_new_project(self, project_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """场景一：创建新项目并初始化本地工作区"""
        try:
            # 第1步：调用API创建项目
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    'projects/init/',
                    json={
                        'name': project_name,
                        'description': description or '',
                    }
                )
            
            # 第2步：如果创建成功，设置本地工作区（与setup_workspace使用相同逻辑）
            if response.get('success'):
                # 转换创建响应为标准项目信息格式
                project_info = {
                    "project_id": response["project_id"],
                    "project_name": response.get("project_name", project_name),
                    "description": description or "",
                    "created_at": response.get("created_at", ""),
                    "tasks": []  # 新项目通常没有现有任务组
                }
                
                # 从初始化数据获取模板信息
                initialization_data = response.get("initialization_data", {})
                templates_data = initialization_data.get("templates", [])
                
                # 使用通用工作区设置函数
                return await self._setup_workspace_unified(
                    project_info, 
                    templates_data, 
                    scenario="new_project"
                )
            else:
                return {
                    "status": "error",
                    "message": response.get("error", "创建项目失败")
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f'新项目创建失败: {str(e)}'
            }
    
    async def _init_existing_project(self, project_id: str) -> Dict[str, Any]:
        """场景二：已知项目ID本地初始化"""
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                # 获取项目信息
                project_info_response = await api.request(
                    'GET',
                    f'projects/{project_id}/info/'
                )
                
                # 调试输出：查看 API 返回的数据
                print(f"DEBUG: API 返回的 project_info: {project_info_response}")
                
                if 'project_id' in project_info_response:
                    # 使用新的按步骤下载逻辑
                    templates_data, sop_structure = await self._get_project_templates_by_steps(api, project_id)
                    
                    # 使用通用工作区设置函数（与create_project使用相同逻辑）
                    return await self._setup_workspace_unified(
                        project_info_response, 
                        templates_data, 
                        scenario="existing_project",
                        sop_structure=sop_structure
                    )
                else:
                    return {
                        "status": "error", 
                        "message": f"项目 {project_id} 不存在或无访问权限"
                    }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f'已知项目初始化失败: {str(e)}'
            }
    
    async def _get_project_templates_by_steps(self, api, project_id: str) -> tuple:
        """按步骤获取项目SOP模板和结构数据
        
        Returns:
            tuple: (templates_list, sop_structure_data)
        """
        try:
            # 1. 获取SOP图，获得所有步骤列表
            sop_response = await api.request('GET', 'sop/graph/', params={'project_id': project_id})
            steps = sop_response.get('steps', {})
            
            templates = []
            sop_structure = {
                'steps': {},
                'dependencies': sop_response.get('dependencies', [])
            }
            
            # 2. 循环每个步骤，获取模板详情
            for step_identifier, step_info in steps.items():
                try:
                    # 获取step_id用于API调用
                    step_id = step_info.get('step_id')
                    if not step_id:
                        print(f"Warning: step_id not found for {step_identifier}, skipping")
                        continue
                    
                    # 3. 调用单个步骤API获取模板详情 - 使用step_id而不是step_identifier
                    step_detail = await api.request(
                        'GET', 
                        f'sop/steps/{step_id}/'  # 使用step_id，不需要project_id参数
                    )
                    
                    stage = step_detail.get('stage', 'unknown')
                    
                    # 保存步骤结构信息
                    sop_structure['steps'][step_identifier] = {
                        'identifier': step_identifier,
                        'name': step_detail.get('name', ''),
                        'stage': stage,
                        'description': step_detail.get('description', ''),
                        'outputs': step_detail.get('outputs', []),
                        'rules': step_detail.get('rules', []),
                        'step_id': step_detail.get('step_id')  # 保存后端返回的数据库ID
                    }
                    
                    # 4. 处理每个步骤的输出模板
                    for output in step_detail.get('outputs', []):
                        if output.get('template_content'):  # 只处理有模板内容的输出
                            template_name = output.get('template_filename')
                            
                            # 如果template字段为None或空，这是数据错误，应该报错
                            if not template_name:
                                print(f"ERROR: Step {step_identifier} output missing template name.")
                                print(f"Full output data: {output}")
                                print(f"Expected: template field should contain filename like 'contract-units.md'")
                                print(f"Actual: template field is {repr(template_name)}")
                                raise ValueError(f"Step {step_identifier} has template_content but missing template name. This indicates a backend data issue.")
                            
                            # 模板应该保存在 sop/{stage}/{step_identifier}/templates/ 目录下
                            template_path = f"sop/{stage}/{step_identifier}/templates/{template_name}"
                            
                            template_info = {
                                "name": template_name,
                                "step_identifier": step_identifier,
                                "stage": stage,
                                "path": template_path,
                                "content": output['template_content']
                            }
                            templates.append(template_info)
                            
                except Exception as e:
                    # 单个步骤失败不影响其他步骤
                    print(f"Failed to get templates for step {step_identifier}: {e}")
                    continue
            
            return templates, sop_structure
            
        except Exception as e:
            print(f"Failed to get templates by steps: {e}")
            return [], {}
    
    async def _setup_workspace_unified(self, project_info: Dict[str, Any], templates_data: list, scenario: str, sop_structure: dict = None) -> Dict[str, Any]:
        """通用的工作区设置函数，适用于新项目和已有项目
        
        Args:
            project_info: 项目信息
            templates_data: 模板数据列表
            scenario: 场景标识 ("new_project" 或 "existing_project")
            sop_structure: SOP结构数据
        """
        try:
            # 1. 创建.supervisor目录结构
            self.file_manager.create_supervisor_directory()
            
            # 2. 保存项目信息（包含任务组状态）
            project_data = {
                "project_id": project_info["project_id"],
                "project_name": project_info["project_name"],
                "description": project_info.get("description", ""),
                "created_at": project_info.get("created_at", ""),
                "project_path": str(self.file_manager.base_path),
            }
            
            # 添加任务组状态信息（期望 API 返回完整信息）
            if "in_progress_task" in project_info:
                project_data["in_progress_task"] = project_info["in_progress_task"]
            
            if "suspended_tasks" in project_info:
                project_data["suspended_tasks"] = project_info["suspended_tasks"]
                
            self.file_manager.save_project_info(project_data)
            
            # 3. 下载模板 - 统一的下载机制
            await self._setup_templates(templates_data, scenario)
            
            # 3.5. 下载SOP结构文件
            if sop_structure:
                await self._setup_sop_structure(sop_structure)
            
            # 4. 为PENDING/IN_PROGRESS任务组创建文件夹
            await self._create_task_folders(project_info.get("tasks", []))
            
            # 5. 更新SessionManager的项目上下文
            self.session_manager.set_project_context(project_info["project_id"], project_info["project_name"])
            
            # 6. 构建统一的返回格式
            return {
                "status": "success",
                "data": {
                    "project_id": project_info["project_id"],
                    "project_name": project_info["project_name"],
                    "created_at": project_info.get("created_at", ""),
                    "templates_downloaded": len(templates_data),
                    "scenario": scenario
                },
                "message": f"{'新项目创建并' if scenario == 'new_project' else '已知项目'}本地初始化成功"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"工作区设置失败: {str(e)}"
            }
    
    
    async def _setup_templates(self, templates_data: list, scenario: str):
        """统一的模板设置函数，确保两种场景行为一致
        
        Args:
            templates_data: 模板数据列表
            scenario: 场景标识 ("new_project" 或 "existing_project")
        """
        # 总是调用initialize_project_structure来创建目录结构（包括templates目录）
        actual_templates = self.file_manager.initialize_project_structure({"templates": templates_data})
        
        # 只有在有模板数据时才下载
        if templates_data:
            # 新设计：所有场景都使用相同的下载逻辑
            # templates_data 已经包含正确的 path、content 等字段
            await self._download_templates_unified(templates_data)

    async def _download_templates_unified(self, templates_data: list):
        """统一的模板下载函数
        
        Args:
            templates_data: 模板数据列表，包含 name、path、content 等字段
        """
        async with get_api_client() as api_client:
            api_client._client.headers.update(self.session_manager.get_headers())
            
            for template in templates_data:
                # 新设计：所有模板数据都已经包含正确的格式
                # 直接调用 download_template
                await self.file_manager.download_template(api_client, template)
    
    async def _setup_sop_structure(self, sop_structure: dict):
        """下载SOP结构文件到supervisor_workspace/sop/目录
        
        Args:
            sop_structure: SOP结构数据，包含steps和dependencies
        """
        try:
            # 按阶段组织步骤，创建{stage}/{step_identifier}/目录结构
            stages = {}
            for step_id, step_info in sop_structure.get('steps', {}).items():
                stage = step_info.get('stage', 'unknown')
                if stage not in stages:
                    stages[stage] = {}
                stages[stage][step_id] = step_info
            
            # 为每个阶段下的每个步骤创建config.json
            for stage, steps in stages.items():
                for step_identifier, step_info in steps.items():
                    # 清理outputs，去除template_content字段（内容已保存到独立的模板文件）
                    clean_outputs = []
                    for output in step_info.get('outputs', []):
                        clean_output = {k: v for k, v in output.items() if k != 'template_content'}
                        clean_outputs.append(clean_output)
                    
                    config_data = {
                        'identifier': step_info.get('identifier'),
                        'name': step_info.get('name'),
                        'stage': step_info.get('stage'),
                        'description': step_info.get('description'),
                        'outputs': clean_outputs,
                        'rules': step_info.get('rules', []),
                        'step_id': step_info.get('step_id')  # 从step_info中获取数据库真实ID
                    }
                    
                    # 保存config.json到supervisor_workspace/sop/{stage}/{step_identifier}/config.json
                    # 使用identifier作为目录名
                    await self.file_manager.save_sop_config(stage, step_identifier, config_data)
                    
        except Exception as e:
            print(f"Failed to setup SOP structure: {e}")
    
    async def _create_task_folders(self, tasks: list):
        """为PENDING/IN_PROGRESS任务组创建本地文件夹"""
        for task in tasks:
            if task.get('status') in ['PENDING', 'IN_PROGRESS']:
                self.file_manager.switch_task_directory(task['id'])
    
    async def next(self) -> Dict[str, Any]:
        """获取下一个任务（需要登录）"""
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        if not self.session_manager.is_authenticated():
            return {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            # 检查项目信息是否存在
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "project.json not found. Please run 'init' first.",
                }
            
            # 使用项目配置的API客户端
            async with self._get_project_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'GET', 
                    'task-phases/next/', 
                    params={'project_id': project_id}
                )
            
            # 如果成功获取到任务，保存到本地
            if response.get("status") == "success" and "task_phase" in response:
                task_phase_data = response["task_phase"]

                # 创建包含任务阶段和上下文的完整数据
                full_task_phase_data = {"task_phase": task_phase_data, "context": response.get("context", {})}
                
                try:
                    # 保存当前任务阶段信息（包含上下文）
                    task_phase_order = task_phase_data.get("order")
                    task_id = task_phase_data.get("task_id")
                    task_phase_type = task_phase_data.get("type", "unknown").lower()
                    
                    if not task_id:
                        response["warning"] = "Task phase missing task_id, cannot save locally"
                    else:
                        if task_phase_order is not None:
                            prefix = f"{task_phase_order:02d}"
                            self.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id, task_phase_order=task_phase_order)
                        else:
                            # 先计算文件名，再保存
                            existing_files = list(self.file_manager.current_task_dir.glob("[0-9][0-9]_*_instructions.md"))
                            prefix = f"{len(existing_files) + 1:02d}"
                            self.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id)
                        
                        # 生成文件路径用于提示
                        filename = f"{prefix}_{task_phase_type}_instructions.md"
                        file_path = f"supervisor_workspace/current_task/{filename}"
                        
                        # 简化task_phase.description，提示文件位置
                        response["task_phase"]["description"] = f"任务阶段详情已保存到本地文件: {file_path}\n\n请查看该文件获取完整的任务阶段说明和要求。"
                        
                except Exception as e:
                    # 文件操作失败不影响任务获取，但添加警告
                    response["warning"] = f"Failed to save task phase locally: {str(e)}"
            
            # 截断过长的错误消息以避免MCP响应过大
            if "message" in response and isinstance(response["message"], str):
                if len(response["message"]) > 2000:
                    response["message"] = response["message"][:2000] + "\n\n[响应被截断，完整错误信息过长]"
            
            return response
            
        except Exception as e:
            error_msg = str(e)
            # 截断过长的异常信息
            if len(error_msg) > 2000:
                error_msg = error_msg[:2000] + "\n\n[错误信息被截断，完整错误过长]"
            
            return {
                'success': False,
                'error_code': 'AUTH_002', 
                'message': f'获取任务失败: {error_msg}'
            }
    
    
    async def report(self, task_phase_id: str, result_data: Dict[str, Any], finish_task: bool = False) -> Dict[str, Any]:
        """提交任务结果（需要登录）

        Args:
            task_phase_id: 任务阶段ID
            result_data: 任务结果数据
            finish_task: 是否直接完成整个任务组（跳过后续任务）
        """
        if not self.session_manager.is_authenticated():
            return {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }

        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }

        try:
            # 先读取当前任务阶段信息以获取task_id
            try:
                current_task_phase = self.file_manager.read_current_task_phase_data()
                # 从 in_progress_task 获取 task_id
                project_info = self.file_manager.read_project_info()
                in_progress_group = project_info.get("in_progress_task")
                task_id = in_progress_group.get("id") if in_progress_group else None
                if not task_id:
                    return {"status": "error", "message": "No active task group found"}
            except Exception as e:
                return {"status": "error", "message": f"Failed to read current task phase: {str(e)}"}

            # 检查当前任务阶段是否存在
            if not self.file_manager.has_current_task_phase(task_id):
                return {
                    "status": "error",
                    "message": "No current task phase found. Please run 'next' first.",
                }

            # 在API调用之前验证VALIDATION任务阶段的数据格式
            if current_task_phase.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if not isinstance(validation_result, dict):
                    return {
                        "status": "error",
                        "message": f"VALIDATION task phase requires validation_result to be a dictionary with 'passed' field, got {type(validation_result).__name__}: {validation_result}"
                    }

            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())

                # 构建请求数据，包含finish_task参数
                request_data = {'result_data': result_data}
                if finish_task:
                    request_data['finish_task'] = True

                response = await api.request(
                    'POST',
                    f'task-phases/{task_phase_id}/report-result/',
                    json=request_data
                )

            # 判断API调用是否成功
            if isinstance(response, dict) and response.get("status") == "success":
                # 基于API响应中的任务组状态决定是否清理缓存
                response_data = response.get("data", {})
                task_status = response_data.get("task_status")

                if task_status == "COMPLETED":
                    # 任务组完成时清理本地文件和缓存
                    try:
                        self.file_manager.cleanup_task_files(task_id)
                    except Exception as e:
                        # 清理失败不影响结果上报，但添加警告
                        response["warning"] = f"Failed to cleanup task files: {str(e)}"

            return response

        except Exception as e:
            return {
                'success': False,
                'error_code': 'AUTH_004',
                'message': f'提交任务失败: {str(e)}'
            }
    
    
    
    async def pre_analyze(self, user_requirement: str) -> Dict[str, Any]:
        """
        分析用户需求并提供SOP步骤选择指导
        """
        if not self.session_manager.is_authenticated():
            return {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            # 1. 读取本地项目信息
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "项目未初始化，请先执行 init 工具初始化项目",
                }

            project_data = self.file_manager.read_project_info()
            project_id = project_data.get("project_id")
            if not project_id:
                return {
                    "status": "error",
                    "message": "项目信息中缺少 project_id，请重新初始化项目",
                }

            # 2. 从API获取真实的SOP步骤配置信息
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                sop_response = await api.request("GET", "sop/graph/")
            
            if sop_response.get("status") == "error":
                return {
                    "status": "error",
                    "message": f"无法获取SOP配置信息: {sop_response.get('message', '未知错误')}"
                }
            
            # 处理API返回的SOP步骤信息
            steps_data = sop_response.get("steps", {})
            dependencies = sop_response.get("dependencies", [])
            
            # 创建步骤依赖关系映射
            dependency_map = {}
            for dep in dependencies:
                from_step = dep.get("from")
                to_step = dep.get("to") 
                if to_step not in dependency_map:
                    dependency_map[to_step] = []
                dependency_map[to_step].append(from_step)
            
            # 按阶段分组步骤
            stages = {}
            for identifier, step in steps_data.items():
                stage = step.get("stage", "其他")
                if stage not in stages:
                    stages[stage] = []
                stages[stage].append({
                    "identifier": identifier,
                    "name": step.get("name", identifier),
                    "description": step.get("description", ""),
                    "dependencies": dependency_map.get(identifier, [])
                })
            
            # 生成分析指导内容
            analysis_content = f"""根据您的需求"{user_requirement}"，建议的分析流程：

1. **需求理解**: 仔细分析需求的核心功能和技术要点
2. **SOP步骤选择**: 从下面的步骤列表中选择最合适的起点
3. **任务组创建**: 使用add_task工具创建执行任务组

**选择建议**:
- 如果涉及市场分析：选择 mrd (市场需求文档)
- 如果需要用户研究：选择 stakeholderInterview 或 persona
- 如果需要UI设计：选择 wireframe 或 uiPrototype
- 如果涉及视觉设计：选择 viDesign (VI视觉识别设计)
- 如果是功能实现：选择 implement
- 如果需要业务分析：选择 businessEntities 或 businessRules"""
            
            # 生成结构化的SOP步骤信息
            sop_steps_info = "**可用SOP步骤**（按阶段分组）:\n\n"
            
            # 按推荐顺序展示主要阶段
            stage_order = ["需求分析", "设计语言系统", "系统分析", "技术实现", "测试验证", "部署发布"]
            
            for stage_name in stage_order:
                if stage_name in stages:
                    sop_steps_info += f"## {stage_name}\n"
                    for step in sorted(stages[stage_name], key=lambda x: x["identifier"]):
                        deps_text = ""
                        if step["dependencies"]:
                            deps_text = f" (依赖: {', '.join(step['dependencies'])})"
                        sop_steps_info += f"- **{step['identifier']}** - {step['name']}{deps_text}\n"
                        if step["description"]:
                            sop_steps_info += f"  - 说明: {step['description']}\n"
                    sop_steps_info += "\n"
            
            # 添加其他阶段的步骤
            other_stages = set(stages.keys()) - set(stage_order)
            for stage_name in sorted(other_stages):
                if stages[stage_name]:  # 只显示非空阶段
                    sop_steps_info += f"## {stage_name}\n"
                    for step in sorted(stages[stage_name], key=lambda x: x["identifier"]):
                        deps_text = ""
                        if step["dependencies"]:
                            deps_text = f" (依赖: {', '.join(step['dependencies'])})"
                        sop_steps_info += f"- **{step['identifier']}** - {step['name']}{deps_text}\n"
                        if step["description"]:
                            sop_steps_info += f"  - 说明: {step['description']}\n"
                    sop_steps_info += "\n"

            return {
                "status": "success",
                "analysis_content": analysis_content,
                "user_requirement": user_requirement,
                "available_sop_steps": sop_steps_info,
                "next_action": "基于分析结果，请调用add_task工具创建任务组",
            }

        except Exception as e:
            return {
                "status": "error", 
                "message": f"需求分析失败: {str(e)}"
            }
    
    async def add_task(self, title: str, goal: str, sop_step_identifier: str) -> Dict[str, Any]:
        """
        创建新的任务组（需要登录）
        
        Args:
            title: 任务组标题
            goal: 任务组目标
            sop_step_identifier: SOP步骤标识符
            
        Returns:
            dict: 任务组创建结果
        """
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            # 1. 读取本地项目信息
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "项目未初始化，请先执行 init 工具初始化项目",
                }

            # 2. 调用Django API创建任务组
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    method="POST",
                    endpoint="tasks/",
                    json={
                        "project_id": project_id,
                        "title": title,
                        "goal": goal,
                        "type": "IMPLEMENTING",
                        "sop_step_identifier": sop_step_identifier,
                    },
                )

            return response

        except Exception as e:
            return {
                "status": "error", 
                "message": f"创建任务组失败: {str(e)}"
            }
    
    async def cancel_task(self, task_id: str, cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
        """
        取消指定的任务组
        
        Args:
            task_id: 要取消的任务组ID
            cancellation_reason: 取消原因（可选）
            
        Returns:
            dict: 取消操作的结果
        """
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
            
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                # 调用Django API取消任务组
                response = await api.request(
                    method="POST",
                    endpoint=f"tasks/{task_id}/cancel/",
                    json={
                        "project_id": project_id,
                        "cancellation_reason": cancellation_reason
                    }
                )
                
                # 如果API调用成功，清理本地缓存和项目状态
                if response.get('status') == 'success':
                    try:
                        # 清理文件
                        self.file_manager.cleanup_task_files(task_id)
                        
                        # 如果取消的是当前活跃的任务组，清除活跃状态
                        if self.file_manager.has_project_info():
                            project_info = self.file_manager.read_project_info()
                            in_progress_group = project_info.get("in_progress_task")
                            if in_progress_group and in_progress_group.get("id") == task_id:
                                project_info["in_progress_task"] = None
                                self.file_manager.save_project_info(project_info)
                    except Exception as e:
                        # 清理失败不影响取消操作，但添加警告
                        response['warning'] = f'本地文件清理失败: {str(e)}'
                
                return response
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"取消任务组失败: {str(e)}"
            }
    
    async def start_task(self, task_id: str) -> Dict[str, Any]:
        """
        启动指定的任务组
        
        Args:
            task_id: 要启动的任务组ID
            
        Returns:
            dict: 启动操作结果
        """
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            # 调用后端API启动任务组
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{task_id}/start/'
                )
            
            # 如果启动成功，更新本地项目信息
            if response.get('status') == 'success':
                try:
                    # 更新project.json中的当前任务组
                    if self.file_manager.has_project_info():
                        project_info = self.file_manager.read_project_info()
                        # Set the task group as in_progress_task instead of using current_task_id
                        project_info['in_progress_task'] = {
                            'id': task_id,
                            'title': response.get('data', {}).get('title', ''),
                            'status': 'IN_PROGRESS'
                        }
                        self.file_manager.save_project_info(project_info)
                        
                        # 创建任务组工作目录
                        self.file_manager.switch_task_directory(task_id)
                    
                except Exception as e:
                    # 本地文件操作失败不影响API调用结果，但添加警告
                    response['warning'] = f'本地文件更新失败: {str(e)}'
            
            return response
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"启动任务组失败: {str(e)}"
            }
    
    async def suspend_task(self) -> Dict[str, Any]:
        """
        暂存当前任务组（调用后端API并同步本地状态）
            
        Returns:
            dict: 暂存操作结果
        """
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            # 1. 读取当前项目信息，获取当前任务组ID
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "项目信息不存在，请先运行 init 工具初始化项目"
                }
            
            project_info = self.file_manager.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            
            if not in_progress_group:
                return {
                    "status": "error",
                    "message": "当前没有进行中的任务组"
                }
            
            current_task_id = in_progress_group["id"]
            
            if not current_task_id:
                return {
                    "status": "error",
                    "message": "当前没有活跃的任务组可以暂存"
                }
            
            # 2. 检查当前任务组是否有工作文件
            current_task_phase_status = self.file_manager.get_current_task_phase_status()
            if not current_task_phase_status.get("has_current_task_phase"):
                return {
                    "status": "error",
                    "message": "当前任务组没有工作文件，无需暂存"
                }
            
            # 3. 调用后端API暂存任务组
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{current_task_id}/suspend/'
                )
            
            # 4. 如果后端暂存成功，执行本地文件暂存
            if response.get('status') == 'success':
                try:
                    # 计算工作文件数量
                    files_count = 0
                    if self.file_manager.current_task_dir.exists():
                        files_count = len([f for f in self.file_manager.current_task_dir.iterdir() if f.is_file()])
                    
                    # 执行本地文件暂存
                    self.file_manager.suspend_current_task(current_task_id)
                    
                    # 更新项目信息，清除当前进行中的任务组，并添加到暂停列表
                    suspended_group = project_info.pop("in_progress_task", {})
                    project_info["in_progress_task"] = None
                    if "suspended_tasks" not in project_info:
                        project_info["suspended_tasks"] = []
                    
                    # 记录暂存信息
                    from datetime import datetime
                    suspended_info = {
                        "id": current_task_id,
                        "title": suspended_group.get("title", response["data"].get("title", "未知任务组")),
                        "status": "SUSPENDED",
                        "suspended_at": response["data"].get("suspended_at", datetime.now().isoformat()),
                        "files_count": files_count
                    }
                    
                    # 避免重复记录
                    project_info["suspended_tasks"] = [
                        sg for sg in project_info["suspended_tasks"] 
                        if sg.get("id") != current_task_id
                    ]
                    project_info["suspended_tasks"].append(suspended_info)
                    
                    self.file_manager.save_project_info(project_info)
                    
                    # 更新响应中的本地信息
                    response["suspended_task"] = suspended_info
                    
                except Exception as e:
                    # 本地操作失败不影响后端操作结果，但添加警告
                    response['warning'] = f'本地文件暂存失败: {str(e)}'
            
            return response
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"暂存任务组失败: {str(e)}"
            }
    
    async def continue_suspended_task(self, task_id: str) -> Dict[str, Any]:
        """
        恢复指定的暂存任务组（调用后端API并同步本地状态）
        
        Args:
            task_id: 要恢复的暂存任务组ID
            
        Returns:
            dict: 恢复操作结果
        """
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            # 1. 检查项目信息
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "项目信息不存在，请先运行 init 工具初始化项目"
                }
            
            project_info = self.file_manager.read_project_info()
            
            # 2. 检查指定任务组是否已暂存
            if not self.file_manager.is_task_suspended(task_id):
                return {
                    "status": "error",
                    "message": f"任务组 {task_id} 未找到或未被暂存"
                }
            
            # 3. 调用后端API恢复任务组
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{task_id}/resume/'
                )
            
            # 4. 如果后端恢复成功，执行本地文件恢复
            if response.get('status') == 'success':
                try:
                    # 处理当前活跃的任务组（如果有）
                    in_progress_group = project_info.get("in_progress_task")
                    previous_task_info = None
                    
                    if in_progress_group:
                        current_task_id = in_progress_group["id"]
                        # 暂存当前任务组
                        current_task_phase_status = self.file_manager.get_current_task_phase_status()
                        if current_task_phase_status.get("has_current_task_phase"):
                            # 计算文件数量
                            files_count = 0
                            if self.file_manager.current_task_dir.exists():
                                files_count = len([f for f in self.file_manager.current_task_dir.iterdir() if f.is_file()])
                            
                            # 暂存当前任务组
                            self.file_manager.suspend_current_task(current_task_id)
                            
                            # 记录被暂存的任务组信息
                            previous_task_info = {
                                "id": current_task_id,
                                "title": in_progress_group.get("title", "之前的任务组"),
                                "suspended": True
                            }
                            
                            # 更新暂存列表
                            from datetime import datetime
                            if "suspended_tasks" not in project_info:
                                project_info["suspended_tasks"] = []
                            
                            suspended_info = {
                                "id": current_task_id,
                                "title": in_progress_group.get("title", "之前的任务组"),
                                "status": "SUSPENDED",
                                "suspended_at": datetime.now().isoformat(),
                                "files_count": files_count
                            }
                            
                            # 避免重复记录
                            project_info["suspended_tasks"] = [
                                sg for sg in project_info["suspended_tasks"] 
                                if sg.get("id") != current_task_id
                            ]
                            project_info["suspended_tasks"].append(suspended_info)
                    
                    # 恢复指定的暂存任务组
                    restore_success = self.file_manager.restore_task(task_id)
                    
                    if not restore_success:
                        return {
                            "status": "error",
                            "message": f"恢复任务组失败：暂存文件不存在或已损坏"
                        }
                    
                    # 计算恢复的文件数量
                    files_count = 0
                    if self.file_manager.current_task_dir.exists():
                        files_count = len([f for f in self.file_manager.current_task_dir.iterdir() if f.is_file()])
                    
                    # 更新项目信息，设置新的进行中任务组
                    # 从暂停列表找到要恢复的任务组信息
                    restored_group = None
                    for sg in project_info.get("suspended_tasks", []):
                        if sg.get("id") == task_id:
                            restored_group = sg
                            break
                    
                    project_info["in_progress_task"] = {
                        "id": task_id,
                        "title": restored_group.get("title", response.get("data", {}).get("title", "")),
                        "status": "IN_PROGRESS"
                    }
                    
                    # 从暂存列表中移除已恢复的任务组
                    if "suspended_tasks" in project_info:
                        project_info["suspended_tasks"] = [
                            sg for sg in project_info["suspended_tasks"] 
                            if sg.get("id") != task_id
                        ]
                    
                    self.file_manager.save_project_info(project_info)
                    
                    # 构建返回结果
                    from datetime import datetime
                    restored_info = {
                        "id": task_id,
                        "title": response["data"].get("title", "未知任务组"),
                        "files_count": files_count,
                        "restored_at": response["data"].get("resumed_at", datetime.now().isoformat())
                    }
                    
                    # 更新响应中的本地信息
                    response["restored_task"] = restored_info
                    if previous_task_info:
                        response["previous_task"] = previous_task_info
                    
                except Exception as e:
                    # 本地操作失败不影响后端操作结果，但添加警告
                    response['warning'] = f'本地文件恢复失败: {str(e)}'
            
            return response
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"恢复暂存任务组失败: {str(e)}"
            }
    
    
    async def get_project_status(self, detailed: bool = False) -> Dict[str, Any]:
        """
        获取项目状态（支持新格式，包含不同状态的任务组）
        
        Args:
            detailed: 是否返回详细信息
            
        Returns:
            dict: 项目状态信息
        """
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        # 检查项目上下文
        project_id = self.get_current_project_id()
        if not project_id:
            return {
                "status": "error",
                "message": "No project context found. Please run setup_workspace or create_project first."
            }
        
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                return await api.request(
                    "GET",
                    f"projects/{project_id}/status/",
                    params={"detail": "true" if detailed else "false"},
                )
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"获取项目状态失败: {str(e)}"
            }

    async def update_step_rules(self, stage: str, step_identifier: str) -> Dict[str, Any]:
        """更新Step的规则
        
        根据stage和step_identifier直接定位到对应的config.json文件，
        读取其中的rules数组和step_id，然后发送给服务器更新。
        
        Args:
            stage: SOP阶段名称
            step_identifier: 步骤标识符
            
        Returns:
            dict: 更新结果
        """
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            # 直接定位配置文件并读取rules和step_id
            config_data = self._read_step_config(stage, step_identifier)
            if config_data is None:
                return {
                    "status": "error",
                    "message": f"未找到配置文件: sop/{stage}/{step_identifier}/config.json"
                }
            
            rules = config_data.get('rules')
            step_id = config_data.get('step_id')
            
            if not rules:
                return {
                    "status": "error",
                    "message": f"配置文件中未找到rules字段"
                }
            
            if not step_id:
                return {
                    "status": "error",
                    "message": f"配置文件中未找到step_id字段"
                }
            
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                return await api.request(
                    "PUT",
                    f"steps/{step_id}/rules",
                    json={"rules": rules},
                )
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"更新Step规则失败: {str(e)}"
            }

    async def update_output_template(self, stage: str, step_identifier: str, output_name: str) -> Dict[str, Any]:
        """更新Output的模板内容
        
        根据stage、step_identifier和output_name直接定位到对应的配置文件和模板文件，
        读取模板内容和output_id后发送给服务器进行更新。
        
        Args:
            stage: SOP阶段名称
            step_identifier: 步骤标识符
            output_name: 输出名称
            
        Returns:
            dict: 更新结果
        """
        # 检查用户是否登录
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            # 直接定位配置文件并读取output信息和模板内容
            output_data = self._read_output_config_and_template(stage, step_identifier, output_name)
            if output_data is None:
                return {
                    "status": "error",
                    "message": f"未找到配置或模板: sop/{stage}/{step_identifier}/config.json 中名为 '{output_name}' 的output"
                }
            
            output_id = output_data.get('output_id')
            template_content = output_data.get('template_content')
            
            if not output_id:
                return {
                    "status": "error",
                    "message": f"Output '{output_name}' 中未找到output_id字段"
                }
            
            if template_content is None:
                return {
                    "status": "error",
                    "message": f"未找到Output '{output_name}' 对应的模板文件"
                }
            
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                # 注意：这里使用text/plain作为content-type
                api._client.headers['Content-Type'] = 'text/plain'
                
                result = await api.request(
                    "PUT",
                    f"outputs/{output_id}/template",
                    data=template_content,
                )
                
                # 恢复JSON content-type
                api._client.headers['Content-Type'] = 'application/json'
                
                return result
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"更新Output模板失败: {str(e)}"
            }

    def _read_step_config(self, stage: str, step_identifier: str) -> Optional[dict]:
        """根据stage和step_identifier直接读取配置文件
        
        Args:
            stage: SOP阶段名称
            step_identifier: 步骤标识符
            
        Returns:
            dict: 配置文件内容，如果未找到返回None
        """
        import json
        
        try:
            sop_dir = self.file_manager.sop_dir
            config_file = sop_dir / stage / step_identifier / "config.json"
            
            if not config_file.exists():
                return None
            
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception:
            return None

    def _read_output_config_and_template(self, stage: str, step_identifier: str, output_name: str) -> Optional[dict]:
        """根据stage、step_identifier和output_name读取配置和模板内容
        
        Args:
            stage: SOP阶段名称
            step_identifier: 步骤标识符
            output_name: 输出名称
            
        Returns:
            dict: 包含output_id和template_content的字典，如果未找到返回None
        """
        import json
        
        try:
            # 先读取配置文件
            config_data = self._read_step_config(stage, step_identifier)
            if not config_data:
                return None
            
            # 在outputs中查找匹配的output_name
            outputs = config_data.get('outputs', [])
            target_output = None
            
            for output in outputs:
                if output.get('name') == output_name:
                    target_output = output
                    break
            
            if not target_output:
                return None
            
            # 获取output_id和template_filename
            output_id = target_output.get('output_id')
            template_filename = target_output.get('template_filename')
            
            if not template_filename:
                return None
            
            # 读取模板文件内容
            sop_dir = self.file_manager.sop_dir
            template_file = sop_dir / stage / step_identifier / "templates" / template_filename
            
            if not template_file.exists():
                return None
            
            with open(template_file, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            return {
                'output_id': output_id,
                'template_content': template_content
            }
                
        except Exception:
            return None
    
