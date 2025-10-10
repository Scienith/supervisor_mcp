"""
MCP服务层 - 处理认证和API调用
"""
import asyncio
from typing import Dict, Any, Optional, List, Union
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

    def _persist_phase_from_context(self, task_group_id: str, phase_meta: Dict[str, Any], context: Dict[str, Any]) -> None:
        """根据后端context结果将当前阶段写入本地文件与project.json。

        说明：该方法不会推进后端状态，仅在本地生成/更新当前阶段说明文件，
        并将 current_task_phase 写入 .supervisor/project.json。

        Args:
            task_group_id: 任务组ID
            phase_meta: 包含当前阶段的基础元信息（id/title/type/status）
            context: 从 task-phases/{id}/context 返回的上下文，需包含 phase_markdown/context_markdown
        """
        # 从上下文中提取markdown内容
        phase_md = ''
        if isinstance(context, dict):
            phase_md = context.get('phase_markdown') or context.get('context_markdown') or ''

        # 构造保存所需结构
        tp = {
            'id': phase_meta.get('id'),
            'title': phase_meta.get('title'),
            'type': phase_meta.get('type'),
            'status': phase_meta.get('status'),
            'description': phase_md,
        }
        full = {'task_phase': tp, 'context': context or {}}

        # 切换到对应任务组目录并保存
        if task_group_id:
            self.file_manager.switch_task_directory(task_group_id)
            self.file_manager.save_current_task_phase(full, task_id=task_group_id, task_phase_order=None)

    async def _save_phase_strict(self, task_phase_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """严格保存任务阶段到本地（供 next 和 login_with_project 复用）。

        要求：
        - task_phase_data 必须包含 instruction_markdown
        - 如果是 UNDERSTANDING 且 order==1，必须包含 task_markdown

        行为：
        - 统一写入 supervisor_workspace/current_task/XX_{type}_instructions.md
        - 对于 Understanding 首阶段，写入 task_description.md
        - 更新 .supervisor/project.json 的 in_progress_task.current_task_phase

        返回：
        - { prefix, phase_type, file_path, task_description_path, wrote_task_description }
        """
        if "instruction_markdown" not in task_phase_data:
            raise ValueError("API响应缺少必需字段: task_phase.instruction_markdown")

        instruction_md = task_phase_data["instruction_markdown"]
        task_id = task_phase_data.get("task_id")
        if not task_id:
            raise ValueError("Task phase missing task_id, cannot save locally")

        # 准备保存结构
        task_phase_data_for_save = dict(task_phase_data)
        task_phase_data_for_save["description"] = instruction_md
        full_task_phase_data = {"task_phase": task_phase_data_for_save, "context": context or {}}

        # 保存并决定前缀
        task_phase_type = task_phase_data.get("type", "unknown").lower()
        task_phase_order = task_phase_data.get("order")
        if task_phase_order is not None:
            prefix = f"{task_phase_order:02d}"
            self.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id, task_phase_order=task_phase_order)
        else:
            existing_files = list(self.file_manager.current_task_dir.glob("[0-9][0-9]_*_instructions.md"))
            prefix = f"{len(existing_files) + 1:02d}"
            self.file_manager.save_current_task_phase(full_task_phase_data, task_id=task_id)

        filename = f"{prefix}_{task_phase_type}_instructions.md"
        file_path = f"supervisor_workspace/current_task/{filename}"
        task_description_path = str(self.file_manager.current_task_dir / "task_description.md")

        # 若是 Understanding 且首阶段，写入任务说明
        wrote_task_description = False
        if task_phase_data.get("type") == "UNDERSTANDING" and task_phase_order == 1:
            if "task_markdown" not in task_phase_data:
                raise ValueError("API响应缺少必需字段: task_phase.task_markdown")
            if task_phase_data["task_markdown"] is None:
                raise ValueError("API响应字段非法：task_phase.task_markdown 不能为 None")
            # 写任务说明
            description_path = self.file_manager.current_task_dir / "task_description.md"
            with open(description_path, "w", encoding="utf-8") as df:
                df.write(task_phase_data["task_markdown"])
            wrote_task_description = True

        return {
            "prefix": prefix,
            "phase_type": task_phase_type,
            "file_path": file_path,
            "task_description_path": task_description_path,
            "wrote_task_description": wrote_task_description,
        }

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
            # 始终使用用户名/密码进行远端登录，不复用本地token
            
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
                api.headers.update(self.session_manager.get_headers())
                
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

        # 步骤1：执行登录（强制重新登录，忽略本地缓存token）
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

            # 成功：返回整合的结果，并基于任务状态提供下一步指引
            result: Dict[str, Any] = {
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

            # 强同步：直接调用 projects/{id}/info 获取进行中任务与当前阶段，并在本地对齐
            try:
                async with get_api_client() as api:
                    api.headers.update(self.session_manager.get_headers())
                    info_resp = await api.request('GET', f'projects/{project_id}/info/')

                if isinstance(info_resp, dict) and info_resp.get('project_id'):
                    project_info_local = self.file_manager.read_project_info()

                    # 合并基础项目信息
                    project_info_local.update({
                        'project_id': info_resp.get('project_id'),
                        'project_name': info_resp.get('project_name') or info_resp.get('name', ''),
                        'description': info_resp.get('description', ''),
                        'created_at': info_resp.get('created_at', ''),
                    })

                    # 对齐进行中/暂存任务概览
                    if 'in_progress_task' in info_resp:
                        project_info_local['in_progress_task'] = info_resp.get('in_progress_task')
                    if 'suspended_tasks' in info_resp:
                        project_info_local['suspended_tasks'] = info_resp.get('suspended_tasks') or []

                    self.file_manager.save_project_info(project_info_local)

                    # 如果有当前阶段，则获取其上下文markdown并生成本地文件与缓存
                    in_prog = project_info_local.get('in_progress_task') or {}
                    current_phase = (in_prog or {}).get('current_task_phase') or {}
                    phase_id = current_phase.get('id')
                    if phase_id:
                        try:
                            # 先获取阶段详情，拿到 order/type/status/title/task_id
                            async with get_api_client() as api2:
                                api2.headers.update(self.session_manager.get_headers())
                                phase_detail = await api2.request('GET', f'task-phases/{phase_id}/')

                            # 再获取上下文（包含markdown）
                            async with get_api_client() as api3:
                                api3.headers.update(self.session_manager.get_headers())
                                ctx = await api3.request('GET', f'task-phases/{phase_id}/context/', params={'format': 'markdown'})

                            # 构造与 next 一致的 task_phase 数据结构
                            task_phase_for_strict = {
                                'id': phase_id,
                                'title': (phase_detail or {}).get('title') or current_phase.get('title'),
                                'type': (phase_detail or {}).get('type') or current_phase.get('type'),
                                'status': (phase_detail or {}).get('status') or current_phase.get('status'),
                                'task_id': (phase_detail or {}).get('task', {}).get('id') or current_phase.get('task_id') or in_prog.get('id'),
                                'order': (phase_detail or {}).get('order'),
                                # 严格保存所需的markdown字段
                                'instruction_markdown': (ctx or {}).get('phase_markdown') or (ctx or {}).get('context_markdown') or '',
                                'task_markdown': (ctx or {}).get('task_markdown'),
                            }

                            # 复用严格保存逻辑（与 next 完全一致）
                            await self._save_phase_strict(task_phase_for_strict, ctx if isinstance(ctx, dict) else {})
                        except Exception:
                            # 自动恢复失败不影响主流程
                            pass
            except Exception:
                # 对齐失败不影响主流程
                pass

            # 基于项目状态生成统一的下一步指引
            try:
                instructions = await self._get_pending_tasks_instructions()
                if instructions:
                    result["instructions"] = instructions
            except Exception:
                # 指引生成失败不影响主流程
                pass

            return result

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
                api.headers.update(self.session_manager.get_headers())
                
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
                api.headers.update(self.session_manager.get_headers())
                
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
            api_client.headers.update(self.session_manager.get_headers())
            
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
        
        # 检查项目上下文（在部分测试场景中允许继续，以便通过Mock返回数据）
        project_id = self.get_current_project_id()
        
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
                api.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'GET', 
                    'task-phases/next/', 
                    params={'project_id': project_id}
                )
            
            # 成功路径：严格读取必要字段；context为可选
            if response["status"] == "success":
                if "task_phase" not in response:
                    return {
                        "status": "error",
                        "error_code": "RESPONSE_FORMAT_ERROR",
                        "message": f"API响应格式不匹配：期待包含 'task_phase' 字段，但收到: {list(response.keys())}"
                    }
                task_phase_data = response["task_phase"]
                context = response.get("context", {})

                # 使用严格落盘逻辑（校验+生成文件+更新project.json），并获取用于提示的文件信息
                try:
                    save_info = await self._save_phase_strict(task_phase_data, context)
                except Exception as e:
                    return {
                        "status": "error",
                        "error_code": "FILE_SAVE_ERROR",
                        "message": f"Failed to save task phase locally: {str(e)}"
                    }

                phase_type = task_phase_data["type"]
                phase_file_path = save_info.get("file_path")
                task_description_path = save_info.get("task_description_path")
                wrote_task_desc = save_info.get("wrote_task_description", False)

                # 添加引导信息
                user_lines: List[str] = []
                to_ai_text = (
                    "执行成功\n\n"
                    "你需要按照下面的顺序行动\n"
                    f"1。使用 `read_file` 工具读取 {task_description_path}（如无则跳过）\n"
                    f"2。使用 `read_file` 工具读取 {phase_file_path} 获取阶段说明\n"
                    "3。立即按照任务说明和阶段说明执行当前阶段的全部工作，不要等待用户反馈"
                )

                if wrote_task_desc:
                    task_file_path = f"supervisor_workspace/current_task/task_description.md"
                    user_lines = [
                        f"**已获取任务说明和{phase_type}阶段说明，准备执行**",
                        f"- 任务说明: `{task_file_path}`",
                        f"- {phase_type}阶段说明: `{phase_file_path}`",
                    ]
                else:
                    user_lines = [
                        f"**已获取{phase_type}阶段说明，准备执行**",
                        f"- {phase_type}阶段说明: `{phase_file_path}`",
                    ]

                instructions = [
                    self._create_instruction(
                        to_ai_text,
                        user_lines,
                        result="success",
                    )
                ]

                return {
                    "status": "success",
                    "message": f"任务阶段详情已保存到本地文件: {phase_file_path}",
                    "instructions": instructions
                }
            
            # 对于错误响应，只返回必要的错误信息
            if response["status"] == "error":
                error_message = response["message"]
                # 截断过长的错误消息
                if len(error_message) > 2000:
                    error_message = error_message[:2000] + "\n\n[响应被截断，完整错误信息过长]"

                return {
                    "status": "error",
                    "error_code": response["error_code"],
                    "message": error_message
                }

            # 对于 no_available_tasks 视为成功场景，指导用户选择/启动任务
            if str(response.get("status")).lower() == "no_available_tasks":
                instructions = []
                try:
                    instructions = await self._get_pending_tasks_instructions()
                except Exception:
                    instructions = [
                        self._create_instruction(
                            "请先提示用户选择待处理任务或创建新任务，并等待用户指示后再调用 `start_task` 或 `add_task`",
                            [
                                "**当前没有进行中的任务阶段。**",
                                "",
                                "❓请选择一个待处理任务执行 `start_task`，或使用 `add_task` 创建新任务"
                            ],
                            result="success",
                        )
                    ]

                message = response.get("message") or "当前没有进行中的任务阶段"
                return {
                    "status": "success",
                    "message": message,
                    "instructions": instructions
                }

            # 对于其他状态，保持原样返回
            return {
                "status": response["status"],
                "message": response.get("message")
            }
            
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
    
    
    async def report(self, task_phase_id: Optional[str], result_data: Dict[str, Any], finish_task: bool = False) -> Dict[str, Any]:
        """提交任务结果（需要登录）

        Args:
            task_phase_id: 任务阶段ID（可选；省略时将从本地读取当前阶段ID）
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
                # 如果未提供task_phase_id，从本地读取当前阶段ID
                if not task_phase_id:
                    inferred_id = current_task_phase.get("id")
                    if not inferred_id:
                        return {
                            "status": "error",
                            "error_code": "MISSING_TASK_PHASE_ID",
                            "message": "当前阶段ID不存在，请先执行 start 和 next 获取任务阶段"
                        }
                    task_phase_id = inferred_id

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

            # 在API调用之前校验结果数据格式
            phase_type_upper = current_task_phase.get("type")
            if phase_type_upper == "VALIDATION":
                # 仅允许 {"passed": bool}
                if not isinstance(result_data, dict) or set(result_data.keys()) != {"passed"} or not isinstance(result_data.get("passed"), bool):
                    return {
                        "status": "error",
                        "error_code": "INVALID_RESULT_DATA",
                        "message": "VALIDATION 阶段的 result_data 必须为 {\"passed\": true/false}，且不允许包含其他字段"
                    }
            else:
                # 其它阶段不接收 result_data 内容
                if isinstance(result_data, dict) and len(result_data) > 0:
                    return {
                        "status": "error",
                        "error_code": "INVALID_RESULT_DATA",
                        "message": "非 VALIDATION 阶段不需要 result_data，请不要传入任何字段"
                    }

            async with get_api_client() as api:
                # 设置认证头
                api.headers.update(self.session_manager.get_headers())

                # 构建请求数据，包含finish_task参数
                # 对VALIDATION阶段将 {"passed": bool} 转换为后端所需结构
                if phase_type_upper == "VALIDATION":
                    request_data = {'result_data': {'validation_result': {'passed': result_data['passed']}}}
                else:
                    request_data = {'result_data': {}}
                if finish_task:
                    request_data['finish_task'] = True

                response = await api.request(
                    'POST',
                    f'task-phases/{task_phase_id}/report-result/',
                    json=request_data
                )

            # 判断API调用是否成功
            if response["status"] == "success":
                # 基于API响应中的任务组状态决定是否清理缓存
                response_data = response.get("data")
                if not isinstance(response_data, dict):
                    return {
                        "status": "error",
                        "error_code": "REPORT_RESPONSE_INVALID",
                        "message": "提交任务失败: API响应缺少data字段或格式不正确"
                    }

                task_status = response_data.get("task_status")
                if task_status is None:
                    return {
                        "status": "error",
                        "error_code": "REPORT_RESPONSE_MISSING_TASK_STATUS",
                        "message": "提交任务失败: API响应缺少task_status字段，请联系后端维护者"
                    }

                if task_status == "COMPLETED":
                    # 任务组完成时清理本地文件和缓存
                    try:
                        self.file_manager.cleanup_task_files(task_id)
                    except Exception as e:
                        # 清理失败应该记录但不中断流程（因为任务已经完成）
                        # 可以在日志中记录，但不返回错误
                        pass  # TODO: 添加日志记录

                # 获取当前任务阶段类型用于生成引导
                task_phase_type = current_task_phase.get("type") if isinstance(current_task_phase, dict) else None

                # 移除data字段，保持简洁
                response.pop("data", None)

                # 添加引导信息
                instructions = []

                if task_phase_type:
                    if task_status == "COMPLETED":
                        # 任务已完成 - 获取后续任务引导
                        instructions.append(
                            self._create_instruction(
                                "1。等待用户反馈\n2。基于用户反馈行动",
                                ["✅ **任务已完成**"],
                                result="success",
                            )
                        )
                        # 获取待处理任务的引导
                        task_instructions = await self._get_pending_tasks_instructions()
                        instructions.extend(task_instructions)

                    elif task_phase_type in ["IMPLEMENTING", "FIXING"]:
                        next_phase_type = self._predict_next_phase_type(task_phase_type)
                        next_phase_label = self._format_phase_label(next_phase_type)
                        next_phase_bullet = f"👉 1. 使用 `next` 进入 {next_phase_label} 的任务阶段"
                        # 实现或修复阶段
                        instructions.append(
                            self._create_instruction(
                                "1。等待用户反馈\n2。基于用户反馈行动",
                                [
                                    "✅ **任务阶段已完成**",
                                    "",
                                    "请选择下一步操作：",
                                    next_phase_bullet,
                                    f"👉 2. 使用 `finish_task {task_id}` 直接完成整个任务"
                                ],
                                result="success",
                            )
                        )

                    elif task_phase_type == "VALIDATION":
                        # 验证阶段 - 优先依据后端返回结果
                        validation_passed = False
                        api_validation_result = response_data.get("result", {}).get("validation_result")
                        if isinstance(api_validation_result, dict) and "passed" in api_validation_result:
                            validation_passed = bool(api_validation_result["passed"])
                        elif isinstance(result_data, dict):
                            if "passed" in result_data and isinstance(result_data["passed"], bool):
                                validation_passed = result_data["passed"]
                            else:
                                validation_passed = result_data.get("validation_result", {}).get("passed", False)
                        if validation_passed:
                            next_phase_type_after_validation = self._predict_next_phase_type(task_phase_type, True)
                            next_phase_label_after_validation = self._format_phase_label(next_phase_type_after_validation)
                            next_phase_bullet = f"👉 1. 使用 `next` 进入 {next_phase_label_after_validation} 的任务阶段"
                            instructions.append(
                                self._create_instruction(
                                    "1。等待用户反馈\n2。基于用户反馈行动",
                                    [
                                        "✅ **验证通过！**",
                                        "",
                                        "请选择下一步操作：",
                                        next_phase_bullet,
                                        f"👉 2. 使用 `finish_task {task_id}` 直接完成整个任务",
                                        "👉 3. 征求用户是否需要人工审核结果，确保结论正确"
                                    ],
                                    result="success",
                                )
                            )
                        else:
                            instructions.append(
                                self._create_instruction(
                                    "1。等待用户反馈\n2。基于用户反馈行动",
                                    [
                                        "❌ **验证未通过**",
                                        "",
                                        "❓是否要使用 `next` 进入修复阶段（FIXING）"
                                    ],
                                    result="failure",
                                )
                            )

                    elif task_phase_type == "RETROSPECTIVE":
                        # 复盘阶段（最后阶段）
                        instructions.append(
                            self._create_instruction(
                                "1。等待用户反馈\n2。基于用户反馈行动",
                                ["✅ **复盘阶段已完成，任务已结束**"],
                                result="success",
                            )
                        )
                        # 获取待处理任务的引导
                        task_instructions = await self._get_pending_tasks_instructions()
                        instructions.extend(task_instructions)

                    else:
                        # UNDERSTANDING、PLANNING 阶段完成后应立即进入下一阶段
                        if task_phase_type in ["UNDERSTANDING", "PLANNING"]:
                            next_phase_type = self._predict_next_phase_type(task_phase_type)
                            next_phase_label = self._format_phase_label(next_phase_type)
                            to_ai_text = (
                                f"请立即调用 `next` 获取 {next_phase_label} 的任务阶段说明，并继续执行，无需等待进一步反馈"
                            )
                            user_lines = [
                                "✅ **任务阶段已完成**",
                                "",
                                f"👉 下一阶段：{next_phase_label}",
                                "👉 将立即获取该阶段说明并继续执行",
                            ]
                            instructions.append(
                                self._create_instruction(
                                    to_ai_text,
                                    user_lines,
                                    result="success",
                                )
                            )
                        else:
                            next_phase_type_generic = self._predict_next_phase_type(task_phase_type)
                            next_phase_label_generic = self._format_phase_label(next_phase_type_generic)
                            question_line = f"❓是否要使用 `next` 进入 {next_phase_label_generic} 的任务阶段"
                            instructions.append(
                                self._create_instruction(
                                    "1。等待用户反馈\n2。基于用户反馈行动",
                                    [
                                        "✅ **任务阶段已完成**",
                                        "",
                                        question_line
                                    ],
                                    result="success",
                                )
                            )

                # 阶段已完成，清除本地当前阶段缓存
                try:
                    self.file_manager.clear_current_task_phase(task_id)
                except Exception:
                    pass

                # 构造简化的返回对象，只包含必要信息
                return {
                    "status": "success",
                    "instructions": instructions
                }

            # 对于非成功的响应，简化返回
            return {
                "status": response["status"],
                "error_code": response["error_code"],
                "message": response["message"] if "message" in response else response.get("detail")
            }

        except Exception as e:
            return {
                'status': 'error',
                'error_code': 'REPORT_UNEXPECTED_ERROR',
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
                api.headers.update(self.session_manager.get_headers())
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
                api.headers.update(self.session_manager.get_headers())
                
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

            # 移除data字段前先提取需要的信息
            if isinstance(response, dict) and response.get("status") == "success":
                # 提取任务信息用于引导
                task_data = response.get("data", {})
                new_task_id = task_data.get("id", "")
                new_task_title = task_data.get("title", title)

                # 移除data字段，保持简洁
                if "data" in response:
                    del response["data"]

                # 添加引导信息
                response["instructions"] = [
                    self._create_instruction(
                        "1。等待用户反馈\n2。基于用户反馈行动",
                        [
                            "✅ **任务创建成功**",
                            f"- 标题: `{new_task_title}`",
                            f"- ID: `{new_task_id}`",
                            "",
                            f"👉 是否立即启动？使用 `start {new_task_id}`"
                        ],
                        result="success",
                    )
                ]
                # 构造简化的成功返回
                return {
                    "status": "success",
                    "message": response.get("message", "任务组已创建"),
                    "task_id": new_task_id,
                    "instructions": response.get("instructions", [])
                }
            else:
                # 失败情况，针对并发校验错误提供可操作指引
                if response.get("error_code") == "TASK_VALIDATION_ERROR":
                    conflicting_task_id = response.get("conflicting_task_id") or response.get("data", {}).get("conflicting_task_id")
                    task_state = None
                    try:
                        status_resp = await self.get_project_status(detailed=True)
                        if status_resp.get("status") == "success" and conflicting_task_id:
                            data = status_resp.get("data", {})
                            pending = data.get("pending_tasks", []) or data.get("pending_groups", []) or []
                            suspended = data.get("suspended_tasks", []) or data.get("suspended_groups", []) or []
                            if any(t.get("id") == conflicting_task_id for t in pending):
                                task_state = "PENDING"
                            elif any(t.get("id") == conflicting_task_id for t in suspended):
                                task_state = "SUSPENDED"
                    except Exception:
                        pass

                    # 生成明确的用户指引
                    action_line = ""
                    if task_state == "PENDING":
                        action_line = f"👉 请先使用 `start {conflicting_task_id}` 启动该任务，完成后再添加新的任务"
                    elif task_state == "SUSPENDED":
                        action_line = f"👉 请先使用 `continue_suspended {conflicting_task_id}` 恢复该任务，完成后再添加新的任务"
                    else:
                        # 根据后端约束：冲突只会发生在 PENDING 或 SUSPENDED
                        # 未能匹配到状态时，视为状态数据暂未同步，提示用户先刷新项目状态
                        return {
                            "status": "error",
                            "error_code": "TASK_STATE_MISMATCH",
                            "message": "检测到冲突任务，但未在项目状态中找到对应的 PENDING/SUSPENDED 任务，请先刷新项目状态(get_project_status)后重试",
                        }

                    instructions = [
                        self._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            [
                                f"**步骤 `{sop_step_identifier}` 已存在未完成的任务**",
                                f"- 冲突任务ID: `{conflicting_task_id or '未知'}`",
                                "",
                                action_line
                            ],
                            result="failure",
                        )
                    ]

                    return {
                        "status": response.get("status", "error"),
                        "error_code": response.get("error_code", "TASK_VALIDATION_ERROR"),
                        "message": response.get("message", "同一步骤已有未完成任务，无法创建新任务"),
                        "instructions": instructions
                    }

                # 其他错误，简化返回
                return {
                    "status": response.get("status", "error"),
                    "error_code": response.get("error_code", "UNKNOWN_ERROR"),
                    "message": response.get("message", "创建任务组失败")
                }

        except Exception as e:
            return {
                "status": "error", 
                "message": f"创建任务组失败: {str(e)}"
            }
    
    async def cancel_task(self, task_id: Optional[str], cancellation_reason: Optional[str] = None) -> Dict[str, Any]:
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
            # 若未提供task_id，默认取消当前进行中的任务组
            if not task_id:
                project_info = self.file_manager.read_project_info()
                in_progress_group = project_info.get("in_progress_task")
                if not in_progress_group or not in_progress_group.get("id"):
                    return {"status": "error", "message": "当前没有进行中的任务组可取消"}
                task_id = in_progress_group["id"]
            async with get_api_client() as api:
                # 设置认证头
                api.headers.update(self.session_manager.get_headers())
                
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
                        # 取消操作已成功，本地清理失败不应该影响结果
                        # 但应该记录错误以便调试
                        pass  # TODO: 添加日志记录

                # 移除cancelled_task字段，保持简洁
                if "cancelled_task" in response:
                    del response["cancelled_task"]

                # 添加引导信息
                if response.get('status') == 'success':
                    instructions = []

                    # 首先确认任务已取消
                    instructions.append(
                        self._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            ["✅ **任务已成功取消**"],
                            result="success",
                        )
                    )

                    # 没有自动切换逻辑，直接获取可用任务列表（指引失败不影响取消结果）
                    try:
                        task_instructions = await self._get_pending_tasks_instructions()
                        instructions.extend(task_instructions)
                    except Exception:
                        pass

                    # 构造简化的返回对象
                    return {
                        "status": response.get('status'),
                        "message": response.get('message', ''),
                        "instructions": instructions
                    }

                # 对于非成功的响应，简化返回
                return {
                    "status": response.get("status", "error"),
                    "error_code": response.get("error_code", "UNKNOWN_ERROR"),
                    "message": response.get("message", "取消失败")
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"取消任务组失败: {str(e)}"
            }

    async def finish_task(self, task_id: Optional[str]) -> Dict[str, Any]:
        """
        直接将任务标记为完成状态

        Args:
            task_id: 要完成的任务ID

        Returns:
            dict: 完成操作的结果
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
            # 若未提供task_id，默认完成当前进行中的任务组
            if not task_id:
                project_info = self.file_manager.read_project_info()
                in_progress_group = project_info.get("in_progress_task")
                if not in_progress_group or not in_progress_group.get("id"):
                    return {"status": "error", "message": "当前没有进行中的任务组可完成"}
                task_id = in_progress_group["id"]
            async with get_api_client() as api:
                # 设置认证头
                api.headers.update(self.session_manager.get_headers())

                # 调用Django API完成任务
                response = await api.request(
                    method="POST",
                    endpoint=f"tasks/{task_id}/finish/"
                )

                # 如果API调用成功，更新本地项目状态
                if response['status'] == 'success':
                    try:
                        # 如果完成的是当前活跃的任务组，清除活跃状态
                        if self.file_manager.has_project_info():
                            project_info = self.file_manager.read_project_info()
                            in_progress_group = project_info.get("in_progress_task")
                            if in_progress_group and in_progress_group.get("id") == task_id:
                                # 标记为已完成
                                project_info["in_progress_task"]["status"] = "COMPLETED"
                                self.file_manager.save_project_info(project_info)

                                # 清理当前任务文件夹（可选）
                                try:
                                    self.file_manager.cleanup_task_files(task_id)
                                except Exception:
                                    pass  # 清理失败不影响主流程
                    except Exception as e:
                        # 完成操作已成功，本地更新失败不应该影响结果
                        # 但应该记录错误以便调试
                        pass  # TODO: 添加日志记录

                # 移除data字段，保持简洁
                if isinstance(response, dict) and "data" in response:
                    del response["data"]

                # 添加引导信息
                if response['status'] == 'success':
                    instructions = []

                    # 首先确认任务已完成
                    instructions.append(
                        self._create_instruction(
                            "请告知任务已成功完成",
                            ["✅ **任务已成功完成**"],
                            result="success",
                        )
                    )

                    # 获取可用任务列表
                    task_instructions = await self._get_pending_tasks_instructions()
                    instructions.extend(task_instructions)

                    # 构造简化的返回对象
                    return {
                        "status": response['status'],
                        "message": response['message'],
                        "instructions": instructions
                    }

                # 对于非成功的响应，提供更明确的错误信息与指引
                error_code = response.get('error_code', 'FINISH_TASK_FAILED')
                error_message = response.get('message') or response.get('error') or "完成任务失败，后端未返回错误详情"
                detail = response.get('detail')
                if detail and detail not in error_message:
                    error_message = f"{error_message}（{detail}）"

                current_phase_type = self._get_current_task_phase_type()
                predicted_next = self._predict_next_phase_type(current_phase_type)
                next_stage_hint = self._format_phase_label(predicted_next)

                instructions = [
                    self._create_instruction(
                        "请告知任务完成操作失败，并指导用户继续推进",
                        [
                            f"❌ **完成任务失败**：{error_message}",
                            "",
                            f"👉 请确认 IMPLEMENTING 阶段已完成；如需继续推进，可使用 `next` 进入 {next_stage_hint} 或 `cancel_task` 取消任务"
                        ],
                        result="failure",
                    )
                ]

                return {
                    "status": response.get('status', 'error'),
                    "error_code": error_code,
                    "message": error_message,
                    "instructions": instructions,
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"完成任务失败: {str(e)}"
            }

    async def start_task(self, task_id: Optional[str]) -> Dict[str, Any]:
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
            # 若未提供task_id，尝试自动选择唯一的PENDING任务
            if not task_id:
                status = await self.get_project_status(detailed=True)
                if status.get("status") != "success":
                    return {"status": "error", "message": "无法获取项目状态以选择待处理任务"}
                data = status.get("data", {})
                pending = data.get("pending_tasks", []) or data.get("pending_groups", [])
                if not pending:
                    return {"status": "error", "message": "当前没有待处理任务可启动"}
                if len(pending) > 1:
                    # 返回选择指引
                    instructions = await self._get_pending_tasks_instructions()
                    return {
                        "status": "error",
                        "error_code": "MULTIPLE_PENDING_TASKS",
                        "message": "存在多个待处理任务，请指定 task_id",
                        "instructions": instructions
                    }
                task_id = pending[0]["id"]
            # 调用后端API启动任务组
            async with get_api_client() as api:
                # 设置认证头
                api.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{task_id}/start/'
                )
            
            # 如果启动成功，更新本地项目信息（严格索引）
            if response['status'] == 'success':
                try:
                    # 更新project.json中的当前任务组
                    if self.file_manager.has_project_info():
                        project_info = self.file_manager.read_project_info()
                        # 先保存title信息，后面会删除data字段
                        task_title = response['data']['title']
                        # Set the task group as in_progress_task instead of using current_task_id
                        project_info['in_progress_task'] = {
                            'id': task_id,
                            'title': task_title,
                            'status': 'IN_PROGRESS'
                        }
                        self.file_manager.save_project_info(project_info)
                        
                        # 创建任务组工作目录
                        self.file_manager.switch_task_directory(task_id)

                except Exception as e:
                    # 本地文件操作失败应该报错
                    return {
                        "status": "error",
                        "error_code": "LOCAL_FILE_ERROR",
                        "message": f"Failed to update local files: {str(e)}"
                    }

            # 添加引导信息
            if response['status'] == 'success':
                # 成功启动任务
                task_title = response['data']['title']
                first_phase_label = self._format_phase_label("UNDERSTANDING")
                first_phase_hint = (
                    f"❓是否使用 `next` 获取任务的第一个阶段说明（{first_phase_label}）"
                    if first_phase_label
                    else "❓是否使用 `next` 获取任务的第一个阶段说明"
                )
                response["instructions"] = [
                    self._create_instruction(
                        "1。等待用户反馈\n2。基于用户反馈行动",
                        [
                            "✅ **任务已成功启动**",
                            f"- 任务: `{task_title}`",
                            "",
                            first_phase_hint
                        ],
                        result="success",
                    )
                ]
            elif response['error_code'] == 'CONFLICT_IN_PROGRESS':
                # 冲突场景：存在其他进行中的任务
                error_message = response['message']
                # 尝试从错误消息中提取当前任务信息
                current_task_title = "当前任务"
                if "已有进行中的任务" in error_message:
                    # 从错误消息中解析任务标题
                    import re
                    match = re.search(r'已有进行中的任务：(.+)', error_message)
                    if match:
                        current_task_title = match.group(1)

                # 获取当前任务ID用于指令
                current_task_id = response.get('data', {}).get('current_task_id', '')
                response["instructions"] = [
                    self._create_instruction(
                        "1。等待用户反馈\n2。基于用户反馈行动",
                        [
                            "❌ **无法启动新任务**",
                            f"原因：任务 `{current_task_title}` 正在进行中",
                            "",
                            "**解决方案：**",
                            f"👉 1. 使用 `suspend` 暂存当前任务，然后使用 `start {task_id}` 启动新任务",
                            f"👉 2. 使用 `finish_task {current_task_id}` 完成当前任务，然后使用 `start {task_id}` 启动新任务"
                        ],
                        result="failure",
                    )
                ]

            # 构造简化的返回对象
            simplified = {
                "status": response['status'],
                "message": response['message'],
                "instructions": response.get("instructions", [])
            }
            # 在错误场景下透传 error_code，便于上层判断
            if response['status'] != 'success' and 'error_code' in response:
                simplified["error_code"] = response['error_code']

            return simplified
            
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
            
            # 2. 不再强制要求存在本地工作文件；即使为空也允许暂存
            #    直接调用后端API并按实际文件数（可能为0）进行本地暂存
            
            # 3. 调用后端API暂存任务组
            async with get_api_client() as api:
                # 设置认证头
                api.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{current_task_id}/suspend/'
                )
            
            # 4. 如果后端暂存成功，执行本地文件暂存
            if response['status'] == 'success':
                # 先从response中提取必要信息，后面会删除data字段
                response_data = response['data']
                response_title = response_data['title']
                response_suspended_at = response_data.get("suspended_at", None)

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
                        "title": suspended_group.get("title", response_title),
                        "status": "SUSPENDED",
                        "suspended_at": response_suspended_at or datetime.now().isoformat(),
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
                    # 暂存操作失败应该报错
                    return {
                        "status": "error",
                        "error_code": "LOCAL_SUSPEND_ERROR",
                        "message": f"Failed to suspend task files locally: {str(e)}"
                    }

            # 移除data字段，保持简洁
            if isinstance(response, dict) and "data" in response:
                del response["data"]

            # 添加引导信息
            if response['status'] == 'success':
                instructions = []

                # 首先确认任务已暂存
                suspended_title = response_title or "任务"
                instructions.append(
                    self._create_instruction(
                        "1。等待用户反馈\n2。基于用户反馈行动",
                        [
                            "✅ **任务已成功暂存**"
                        ],
                        result="success",
                    )
                )

                # 没有自动切换逻辑，直接获取可用任务列表（指引失败不影响取消结果）
                try:
                    task_instructions = await self._get_pending_tasks_instructions()
                    instructions.extend(task_instructions)
                except Exception:
                    pass

                # 构造简化的返回对象
                return {
                    "status": "success",
                    "message": response.get("message", "任务已成功暂存"),
                    "instructions": instructions
                }

            # 对于非成功的响应，简化返回
            return {
                "status": response.get("status", "error"),
                "error_code": response.get("error_code", "UNKNOWN_ERROR"),
                "message": response.get("message", "暂存失败")
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"暂存任务组失败: {str(e)}"
            }
    
    async def continue_suspended_task(self, task_id: Optional[str]) -> Dict[str, Any]:
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
            # 若未提供task_id，尝试在本地找到唯一的暂存任务
            if not task_id:
                project_info = self.file_manager.read_project_info()
                suspended = project_info.get("suspended_tasks", [])
                if not suspended:
                    return {"status": "error", "message": "当前没有暂存任务可恢复"}
                if len(suspended) > 1:
                    instructions = await self._get_pending_tasks_instructions()
                    return {
                        "status": "error",
                        "error_code": "MULTIPLE_SUSPENDED_TASKS",
                        "message": "存在多个暂存任务，请指定 task_id",
                        "instructions": instructions
                    }
                task_id = suspended[0]["id"]
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
                api.headers.update(self.session_manager.get_headers())
                
                response = await api.request(
                    'POST',
                    f'projects/{project_id}/tasks/{task_id}/resume/'
                )
            
            # 4. 如果后端恢复成功，执行本地文件恢复
            if response['status'] == 'success':
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

                    # 获取任务组标题（优先从本地，其次从响应）
                    task_title = restored_group.get("title") if restored_group else None
                    if not task_title:
                        task_title = response.get("data", {}).get("title", "")

                    project_info["in_progress_task"] = {
                        "id": task_id,
                        "title": task_title,
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
                    # 先从response["data"]中提取需要的信息
                    title = response["data"]["title"]
                    resumed_at = response["data"]["resumed_at"]

                    restored_info = {
                        "id": task_id,
                        "title": title,
                        "files_count": files_count,
                        "restored_at": resumed_at
                    }

                    # 删除data字段
                    if "data" in response:
                        del response["data"]

                    # 更新响应中的本地信息
                    response["restored_task"] = restored_info
                    if previous_task_info:
                        response["previous_task"] = previous_task_info

                    # 添加引导信息
                    phase_status = self.file_manager.get_current_task_phase_status()
                    if not phase_status.get("has_current_task_phase"):
                        raise ValueError("无法获取恢复后任务的阶段说明文件")
                    latest_phase_file = phase_status.get("latest_task_phase_file")
                    inferred_phase_type = self._extract_phase_type_from_filename(latest_phase_file)
                    resumed_phase_label = self._format_phase_label(inferred_phase_type)
                    next_hint_text = f"👉 使用 `next` 获取 {resumed_phase_label} 的任务阶段说明"
                    response["instructions"] = [
                        self._create_instruction(
                            "1。等待用户反馈\n2。基于用户反馈行动",
                            [
                                "✅ **任务已成功恢复**",
                                f"- 任务: `{title}`",
                                f"- 文件数量: {files_count}",
                                "",
                                next_hint_text
                            ],
                            result="success",
                        )
                    ]

                except Exception as e:
                    # 恢复操作失败应该报错
                    return {
                        "status": "error",
                        "error_code": "LOCAL_RESTORE_ERROR",
                        "message": f"Failed to restore task files locally: {str(e)}"
                    }

            # 构造简化的返回对象
            if response['status'] == 'success':
                return {
                    "status": "success",
                    "message": response['message'],
                    "instructions": response.get("instructions", [])
                }
            else:
                # 对于非成功的响应，简化返回
                return {
                    "status": response['status'],
                    "error_code": response['error_code'],
                    "message": response['message']
                }

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
                api.headers.update(self.session_manager.get_headers())
                
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
                api.headers.update(self.session_manager.get_headers())
                
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
                api.headers.update(self.session_manager.get_headers())
                
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

    def _get_current_task_phase_type(self) -> str:
        """从本地获取当前任务阶段类型

        Returns:
            str: 任务阶段类型 (UNDERSTANDING/PLANNING/IMPLEMENTING/VALIDATION/FIXING/RETROSPECTIVE)

        Raises:
            RuntimeError: 如果无法获取项目信息或当前没有活跃任务
        """
        try:
            project_info = self.file_manager.read_project_info()
            if not project_info:
                raise RuntimeError("无法获取项目信息，请确保项目上下文存在")

            in_progress = project_info.get("in_progress_task")
            if not isinstance(in_progress, dict):
                raise RuntimeError("当前没有进行中的任务阶段")

            current_task_phase = in_progress.get("current_task_phase")
            if not isinstance(current_task_phase, dict):
                raise RuntimeError("当前没有进行中的任务阶段")

            phase_type = current_task_phase.get("type")

            if not phase_type:
                raise RuntimeError("当前没有进行中的任务阶段")

            return phase_type
        except Exception as e:
            raise RuntimeError(f"获取任务阶段类型失败: {str(e)}")

    @staticmethod
    def _format_phase_label(phase_type: Optional[str]) -> str:
        """根据阶段类型生成带中文说明的阶段标签"""
        if not phase_type:
            raise ValueError("无法确定任务阶段类型")
        mapping = {
            "UNDERSTANDING": "UNDERSTANDING（任务理解阶段）",
            "PLANNING": "PLANNING（方案规划阶段）",
            "IMPLEMENTING": "IMPLEMENTING（实现阶段）",
            "VALIDATION": "VALIDATION（验证阶段）",
            "FIXING": "FIXING（修复阶段）",
            "RETROSPECTIVE": "RETROSPECTIVE（复盘阶段）",
        }
        upper = phase_type.upper()
        if upper not in mapping:
            raise ValueError(f"未知的任务阶段类型：{phase_type}")
        return mapping[upper]

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
        """根据当前阶段推断下一个阶段类型"""
        if not current_phase_type:
            raise ValueError("无法推断下一任务阶段：当前阶段未知")
        phase = current_phase_type.upper()
        if phase == "UNDERSTANDING":
            return "PLANNING"
        if phase == "PLANNING":
            return "IMPLEMENTING"
        if phase == "IMPLEMENTING":
            return "VALIDATION"
        if phase == "FIXING":
            return "VALIDATION"
        if phase == "VALIDATION":
            if validation_passed is False:
                return "FIXING"
            return "RETROSPECTIVE"
        raise ValueError(f"无法推断下一任务阶段：未知阶段 {current_phase_type}")

    async def _get_pending_tasks_instructions(
        self,
        return_as_string: bool = False
    ) -> Union[List[Dict[str, Any]], str]:
        """获取基于项目状态的下一步指引（进行中/暂存/待处理/无任务）。

        Args:
            return_as_string: 为 True 时直接返回拼接后的 to_ai 字符串。
        """
        # 获取项目状态（严格校验）
        status_response = await self.get_project_status(detailed=True)
        if status_response["status"] != "success":
            raise ValueError(f"Project status error: {status_response}")

        data = status_response["data"]
        pending_tasks = data["pending_tasks"]
        suspended_tasks = data["suspended_tasks"]
        in_progress = data.get("current_in_progress_task")

        instructions: List[Dict[str, Any]] = []

        # 若存在进行中的任务，优先提示“任务 + 阶段”，并且不再列出暂存/待处理列表（只聚焦继续当前任务）。
        if in_progress:
            task_id = in_progress["id"]
            title = in_progress.get("title", "")
            # 从本地读取当前阶段类型（若存在则显示）
            try:
                project_info_local = self.file_manager.read_project_info() or {}
                in_prog_local = project_info_local.get("in_progress_task") or {}
                current_phase_local = in_prog_local.get("current_task_phase") or {}
                phase_type = current_phase_local.get("type")
            except Exception:
                phase_type = None

            # 计算阶段说明文件路径
            status = self.file_manager.get_current_task_phase_status()
            phase_description_file = status.get("latest_task_phase_file")
            if not status.get("has_current_task_phase") or not phase_description_file:
                raise ValueError("无法获取当前任务阶段说明文件")
            phase_description_path = str(self.file_manager.current_task_dir / phase_description_file)

            # 若未能从本地记录获取阶段类型，尝试从文件名推断
            if not phase_type:
                phase_type = self._extract_phase_type_from_filename(phase_description_file)

            phase_type_label = self._format_phase_label(phase_type)

            user_message: List[str] = [
                f"当前进行中的任务：{title}（ID: `{task_id}`），任务阶段: {phase_type_label}",
            ]
            user_message.append(f"- 阶段说明: `{phase_description_path}`")
            user_message.append("❓是否要立即阅读任务阶段说明，按照里面的要求开始工作？")

            to_ai_text = "请提示当前进行中的任务与阶段"

            instructions.append(
                self._create_instruction(
                    to_ai_text,
                    user_message,
                    result="success",
                )
            )

        # 若无进行中任务，优先显示暂存任务
        if not in_progress and suspended_tasks:
            user_message = [f"**有 {len(suspended_tasks)} 个暂存任务，您可以恢复其中一个继续工作：**", ""]
            for i, task in enumerate(suspended_tasks, 1):
                title = task["title"]
                goal = task["goal"]
                task_id = task["id"]
                suspended_at = (task["suspended_at"] or "")[:10]

                user_message.append(f"👉 {i}. {title}")
                if goal:
                    user_message.append(f"   - 目标: {goal}")
                user_message.append(f"   - ID: `{task_id}`")
                if suspended_at:
                    user_message.append(f"   - 暂存于: {suspended_at}")
                user_message.append("")

            user_message.append("❓请选择要恢复的任务")

            instructions.append(
                self._create_instruction(
                    "请先展示暂存任务列表，并等待用户明确指示后再决定是否调用 `continue_suspended_task`",
                    user_message,
                    result="success",
                )
            )

        # 若无进行中任务，显示待处理任务
        if not in_progress and pending_tasks:
            user_message = [
                f"**{'另有 ' if suspended_tasks else ''}{len(pending_tasks)} 个待处理任务，您可以{'启动新的工作' if suspended_tasks else '选择一个启动'}：**",
                ""
            ]

            for i, task in enumerate(pending_tasks, 1):
                title = task["title"]
                goal = task["goal"]
                task_id = task["id"]

                user_message.append(f"👉 {i}. {title}")
                if goal:
                    user_message.append(f"   - 目标: {goal}")
                user_message.append(f"   - ID: `{task_id}`")
                user_message.append("")

            user_message.append("❓请做出选择")

            instructions.append(
                self._create_instruction(
                    "请先展示待处理任务列表，等待用户明确选择；在收到指示前不要调用任何工具。若用户指定任务，再根据指示调用 `start_task`",
                    user_message,
                    result="success",
                )
            )

        # 若三类均无：无进行中、无待处理、无暂存，才提示创建新任务
        if not in_progress and not suspended_tasks and not pending_tasks:
            instructions.append(
                self._create_instruction(
                    "请提示用户是否需要创建新任务，并等待用户反馈后再调用 `add_task`",
                    [
                        "**目前没有待处理或暂存的任务，您可以创建新任务：**",
                        "",
                        "❓是否要使用 `add_task` 创建新任务"
                    ],
                    result="success",
                )
            )

        if return_as_string:
            if not instructions:
                return ""

            parts: List[str] = []
            for item in instructions:
                if isinstance(item, dict):
                    parts.append(item.get("to_ai", ""))
                else:
                    parts.append(str(item))
            return "\n\n".join(part for part in parts if part)

        return instructions

    def _create_instruction(
        self,
        to_ai: str,
        user_message: List[str] = None,
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建标准格式的指令对象

        Args:
            to_ai: 给AI的指令（会自动添加"AI注意："前缀）
            user_message: 显示给用户的消息列表（可选）

        Returns:
            dict: 包含to_ai和可选user_message的指令对象
        """
        # 统一要求：严格原样显示 user_message 文本，禁止改写/拼接/翻译
        status_map = {
            "success": "执行成功",
            "failure": "执行失败",
            "warning": "执行后存在警告",
        }

        prefix_lines: List[str] = []
        if result:
            descriptor = status_map.get(result.lower(), result)
            prefix_lines.append(f"工具执行结果：{descriptor}")

        if user_message:
            prefix_lines.append("先原封不动地显示给用户user_messages，user_messages内容见后面说明")

        base_instruction = to_ai
        if prefix_lines:
            base_instruction = "\n".join(prefix_lines + [to_ai])

        if user_message:
            try:
                msg_block = "\n".join(user_message)
                base_instruction = (
                    f"{base_instruction}\n\nuser_messages 原文内容（请原封不动的显示）：\n{msg_block}"
                )
            except Exception:
                pass

        return f"AI注意：{base_instruction}"
