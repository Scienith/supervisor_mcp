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
        # 项目上下文信息
        self.current_project_id: Optional[str] = None
        self.current_project_name: Optional[str] = None
        self.current_task_group_id: Optional[str] = None
    async def _auto_restore_session(self):
        """自动从本地文件恢复session和项目上下文"""
        try:
            # 检查是否存在项目信息
            if not self.file_manager.has_project_info():
                return
            
            # 读取本地项目信息
            project_info = self.file_manager.read_project_info()
            
            # 恢复项目上下文信息
            self.current_project_id = project_info.get('project_id')
            self.current_project_name = project_info.get('project_name')
            self.current_task_group_id = project_info.get('current_task_group_id')
            
            if self.current_project_id:
                print(f"Auto-restored project context: {self.current_project_name} (ID: {self.current_project_id})", 
                      file=__import__('sys').stderr)
            
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
        return self.current_project_id
    
    def get_current_project_name(self) -> Optional[str]:
        """获取当前项目名称（如果已恢复）"""
        return self.current_project_name
    
    def get_current_task_group_id(self) -> Optional[str]:
        """获取当前任务组ID（如果已恢复）"""
        return self.current_task_group_id
    
    def has_project_context(self) -> bool:
        """检查是否有项目上下文"""
        return self.current_project_id is not None

    def _get_project_api_client(self):
        """获取API客户端，使用全局配置"""
        # 始终使用全局配置的API地址
        return get_api_client()
    
    
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
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """用户登录"""
        try:
            # 首先尝试验证本地保存的token
            local_user_data = await self._validate_local_token(username)
            if local_user_data:
                # 本地token有效，直接使用
                self.session_manager.login(
                    local_user_data['user_id'],
                    local_user_data['access_token'],
                    local_user_data['username']
                )
                return {
                    'success': True,
                    'user_id': local_user_data['user_id'],
                    'username': local_user_data['username']
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
                self.session_manager.login(
                    user_data['user_id'],
                    user_data['access_token'],
                    user_data['username']
                )
                
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
            self.file_manager.suspended_task_groups_dir = self.file_manager.supervisor_dir / "suspended_task_groups"
            self.file_manager.workspace_dir = self.file_manager.base_path / "supervisor_workspace"
            self.file_manager.templates_dir = self.file_manager.workspace_dir / "templates"
            self.file_manager.current_task_group_dir = self.file_manager.workspace_dir / "current_task_group"
        
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
                    "task_groups": []  # 新项目通常没有现有任务组
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
                
                if 'project_id' in project_info_response:
                    # 使用新的按步骤下载逻辑
                    templates_data = await self._get_project_templates_by_steps(api, project_id)
                    
                    # 使用通用工作区设置函数（与create_project使用相同逻辑）
                    return await self._setup_workspace_unified(
                        project_info_response, 
                        templates_data, 
                        scenario="existing_project"
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
    
    async def _get_project_templates_by_steps(self, api, project_id: str) -> list:
        """按步骤获取项目SOP模板"""
        try:
            # 1. 获取SOP图，获得所有步骤列表
            sop_response = await api.request('GET', 'sop/graph/', params={'project_id': project_id})
            steps = sop_response.get('steps', {})
            
            templates = []
            
            # 2. 循环每个步骤，获取模板详情
            for step_identifier, step_info in steps.items():
                try:
                    # 3. 调用单个步骤API获取模板详情
                    step_detail = await api.request(
                        'GET', 
                        f'sop/steps/{step_identifier}/', 
                        params={'project_id': project_id}
                    )
                    
                    stage = step_detail.get('stage', 'unknown')
                    
                    # 4. 处理每个步骤的输出模板
                    for output in step_detail.get('outputs', []):
                        if output.get('template_content'):  # 只处理有模板内容的输出
                            template_name = output.get('template')
                            
                            # 如果template字段为None或空，这是数据错误，应该报错
                            if not template_name:
                                print(f"ERROR: Step {step_identifier} output missing template name.")
                                print(f"Full output data: {output}")
                                print(f"Expected: template field should contain filename like 'contract-units.md'")
                                print(f"Actual: template field is {repr(template_name)}")
                                raise ValueError(f"Step {step_identifier} has template_content but missing template name. This indicates a backend data issue.")
                            
                            # 生成新的路径结构: {stage}/{step_identifier}/{template_name}
                            template_path = f".supervisor/templates/{stage}/{step_identifier}/{template_name}"
                            
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
            
            return templates
            
        except Exception as e:
            print(f"Failed to get templates by steps: {e}")
            return []
    
    async def _setup_workspace_unified(self, project_info: Dict[str, Any], templates_data: list, scenario: str) -> Dict[str, Any]:
        """通用的工作区设置函数，适用于新项目和已有项目
        
        Args:
            project_info: 项目信息
            templates_data: 模板数据列表
            scenario: 场景标识 ("new_project" 或 "existing_project")
        """
        try:
            # 1. 创建.supervisor目录结构
            self.file_manager.create_supervisor_directory()
            
            # 2. 保存项目信息
            self.file_manager.save_project_info({
                "project_id": project_info["project_id"],
                "project_name": project_info["project_name"],
                "description": project_info.get("description", ""),
                "created_at": project_info.get("created_at", ""),
                "project_path": str(self.file_manager.base_path),
            })
            
            # 3. 下载模板 - 统一的下载机制
            await self._setup_templates(templates_data, scenario)
            
            # 4. 为PENDING/IN_PROGRESS任务组创建文件夹
            await self._create_task_group_folders(project_info.get("task_groups", []))
            
            # 5. 构建统一的返回格式
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
    
    
    async def _create_task_group_folders(self, task_groups: list):
        """为PENDING/IN_PROGRESS任务组创建本地文件夹"""
        for task_group in task_groups:
            if task_group.get('status') in ['PENDING', 'IN_PROGRESS']:
                self.file_manager.switch_task_group_directory(task_group['id'])
    
    async def next(self, project_id: str) -> Dict[str, Any]:
        """获取下一个任务（需要登录）"""
        # 尝试自动恢复session
        await self._ensure_session_restored()
        
        if not self.session_manager.is_authenticated():
            return {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            # 检查项目信息是否存在
            if not self.file_manager.has_project_info():
                return {
                    "status": "error",
                    "message": "project_info.json not found. Please run 'init' first.",
                }
            
            # 使用项目配置的API客户端
            async with self._get_project_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'GET', 
                    'tasks/next/', 
                    params={'project_id': project_id}
                )
            
            # 如果成功获取到任务，保存到本地
            if response.get("status") == "success" and "task" in response:
                task_data = response["task"]
                
                # 创建包含任务和上下文的完整数据
                full_task_data = {"task": task_data, "context": response.get("context", {})}
                
                try:
                    # 保存当前任务信息（包含上下文）
                    task_order = task_data.get("order")
                    task_group_id = task_data.get("task_group_id")
                    
                    if not task_group_id:
                        response["warning"] = "Task missing task_group_id, cannot save locally"
                    else:
                        if task_order is not None:
                            self.file_manager.save_current_task(full_task_data, task_group_id=task_group_id, task_order=task_order)
                        else:
                            self.file_manager.save_current_task(full_task_data, task_group_id=task_group_id)
                        
                except Exception as e:
                    # 文件操作失败不影响任务获取，但添加警告
                    response["warning"] = f"Failed to save task locally: {str(e)}"
            
            return response
            
        except Exception as e:
            return {
                'success': False,
                'error_code': 'AUTH_002',
                'message': f'获取任务失败: {str(e)}'
            }
    
    async def report(self, task_id: str, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """提交任务结果（需要登录）"""
        if not self.session_manager.is_authenticated():
            return {
                'success': False,
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            # 先读取当前任务信息以获取task_group_id
            try:
                current_task = self.file_manager.read_current_task_data()
                task_group_id = current_task.get('task_group_id', 'test-task-group-id')  # 获取实际的task_group_id
            except Exception as e:
                return {"status": "error", "message": f"Failed to read current task: {str(e)}"}
            
            # 检查当前任务是否存在
            if not self.file_manager.has_current_task(task_group_id):
                return {
                    "status": "error",
                    "message": "No numbered prefix instruction files found. Please run 'next' first.",
                }
            
            # 在API调用之前验证VALIDATION任务的数据格式
            if current_task.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if not isinstance(validation_result, dict):
                    return {
                        "status": "error", 
                        "message": f"VALIDATION task requires validation_result to be a dictionary with 'passed' field, got {type(validation_result).__name__}: {validation_result}"
                    }
            
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'tasks/{task_id}/report-result/',
                    json={'result_data': result_data}
                )
            
            # 判断API调用是否成功
            if isinstance(response, dict) and response.get("status") == "success":
                # 检查是否是validation任务并且结果为passed
                should_clear = False
                
                if current_task.get("type") == "VALIDATION":
                    validation_result = result_data.get("validation_result", {})
                    if validation_result.get("passed") is True:
                        should_clear = True
                
                if should_clear:
                    # 只有validation passed时才清理任务组文件（删除整个目录）
                    try:
                        self.file_manager.cleanup_task_group_files(task_group_id)
                    except Exception as e:
                        # 清理失败不影响结果上报，但添加警告
                        response["warning"] = f"Failed to cleanup task_group files: {str(e)}"
            
            return response
            
        except Exception as e:
            return {
                'success': False,
                'error_code': 'AUTH_004',
                'message': f'提交任务失败: {str(e)}'
            }
    
    async def switch_task_group(self, project_id: str, task_group_id: str) -> Dict[str, Any]:
        """切换任务组（需要登录）"""
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/task-groups/switch/',
                    json={'task_group_id': task_group_id}
                )
            
            # 如果切换成功，更新本地文件
            if response.get('status') == 'success':
                try:
                    # 更新 project_info.json
                    project_info = self.file_manager.read_project_info()
                    if project_info:
                        project_info['current_task_group_id'] = task_group_id
                        
                        # 更新任务组状态信息（如果有的话）
                        current_task_group = response.get('current_task_group', {})
                        previous_task_group = response.get('previous_task_group', {})
                        
                        if 'task_groups' not in project_info:
                            project_info['task_groups'] = {}
                        
                        if current_task_group:
                            project_info['task_groups'][task_group_id] = {
                                'status': current_task_group.get('status'),
                                'current_task': current_task_group.get('current_task')
                            }
                        
                        if previous_task_group:
                            prev_id = previous_task_group.get('id')
                            if prev_id:
                                project_info['task_groups'][prev_id] = {
                                    'status': previous_task_group.get('status'),
                                    'order': previous_task_group.get('order')
                                }
                        
                        self.file_manager.save_project_info(project_info)
                    
                    # 切换工作目录
                    self.file_manager.switch_task_group_directory(task_group_id)
                    
                except Exception as e:
                    # 文件操作失败不影响API调用结果，但添加警告
                    response['warning'] = f'本地文件更新失败: {str(e)}'
            
            return response
            
        except Exception as e:
            return {
                'status': 'error',
                'error_code': 'API_005',
                'message': f'任务组切换失败: {str(e)}'
            }
    
    async def list_task_groups(self, project_id: str) -> Dict[str, Any]:
        """获取任务组列表（需要登录）"""
        if not self.session_manager.is_authenticated():
            return {
                'status': 'error',
                'error_code': 'AUTH_001',
                'message': '请先登录'
            }
        
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'GET',
                    f'projects/{project_id}/task-groups/switchable/'
                )
            
            # 补充本地任务状态信息
            if response.get('status') == 'success' and 'data' in response:
                try:
                    project_info = self.file_manager.read_project_info()
                    local_task_groups = project_info.get('task_groups', {}) if project_info else {}
                    
                    # 为任务组添加本地状态信息
                    data = response['data']
                    
                    # 为当前任务组添加本地信息
                    if data.get('current_group'):
                        group_id = data['current_group']['id']
                        if group_id in local_task_groups:
                            data['current_group']['local_task_status'] = local_task_groups[group_id].get('current_task')
                    
                    # 为可切换任务组添加本地信息
                    for group in data.get('switchable_groups', []):
                        group_id = group['id']
                        if group_id in local_task_groups:
                            group['local_task_status'] = local_task_groups[group_id].get('current_task')
                    
                except Exception as e:
                    # 本地信息补充失败不影响主要功能
                    response['warning'] = f'本地状态信息获取失败: {str(e)}'
            
            return response
            
        except Exception as e:
            return {
                'status': 'error',
                'error_code': 'API_006',
                'message': f'获取任务组列表失败: {str(e)}'
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
            import os
            import json
            
            project_info_path = ".supervisor/project_info.json"
            if not os.path.exists(project_info_path):
                return {
                    "status": "error",
                    "message": "项目未初始化，请先执行 init 工具初始化项目",
                }

            with open(project_info_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

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
3. **任务组创建**: 使用add_task_group工具创建执行任务组

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
                "next_action": "基于分析结果，请调用add_task_group工具创建任务组",
            }

        except Exception as e:
            return {
                "status": "error", 
                "message": f"需求分析失败: {str(e)}"
            }
    
    async def add_task_group(self, title: str, goal: str, sop_step_identifier: str) -> Dict[str, Any]:
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
        
        try:
            # 1. 读取本地项目信息
            import os
            import json
            
            project_info_path = ".supervisor/project_info.json"
            if not os.path.exists(project_info_path):
                return {
                    "status": "error",
                    "message": "项目未初始化，请先执行 init 工具初始化项目",
                }

            with open(project_info_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

            project_id = project_data.get("project_id")
            if not project_id:
                return {
                    "status": "error",
                    "message": "项目信息中缺少 project_id，请重新初始化项目",
                }

            # 2. 调用Django API创建任务组
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    method="POST",
                    endpoint="task-groups/",
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
    
    async def cancel_task_group(self, project_id: str, task_group_id: str, cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
        """
        取消指定的任务组
        
        Args:
            project_id: 项目ID
            task_group_id: 要取消的任务组ID
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
            
        try:
            async with get_api_client() as api:
                # 设置认证头
                api._client.headers.update(self.session_manager.get_headers())
                
                # 调用Django API取消任务组
                response = await api.request(
                    method="POST",
                    endpoint=f"task-groups/{task_group_id}/cancel/",
                    json={
                        "project_id": project_id,
                        "cancellation_reason": cancellation_reason
                    }
                )
                
                return response
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"取消任务组失败: {str(e)}"
            }