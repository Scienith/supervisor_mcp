"""
MCP本地文件管理器
负责管理.supervisor/目录下的所有文件操作
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional


class FileManager:
    """本地文件管理器"""

    def __init__(self, base_path: Optional[str] = None):
        """
        初始化文件管理器

        Args:
            base_path: 基础路径，优先级：
                1. 传入的 base_path 参数
                2. 当前目录的 .supervisor/project.json 中的 project_path
                3. SUPERVISOR_PROJECT_PATH 环境变量（显式配置）
                4. ORIGINAL_PWD 环境变量（Claude Code 启动时的原始目录）
                5. PWD 环境变量（备用方案）
                6. 当前工作目录（fallback）
        """
        if base_path:
            self.base_path = Path(base_path)
        else:
            # 尝试从当前目录的 .supervisor/project.json 恢复路径
            current_dir = Path(os.getcwd())
            project_file = current_dir / ".supervisor" / "project.json"
            
            if project_file.exists():
                try:
                    with open(project_file, "r", encoding="utf-8") as f:
                        project_info = json.load(f)
                        if "project_path" in project_info:
                            self.base_path = Path(project_info["project_path"])
                        else:
                            # project.json 存在但没有 project_path，使用当前目录
                            self.base_path = current_dir
                except Exception:
                    self.base_path = None
            else:
                self.base_path = None
            
            # 如果没有从 project.json 恢复，继续尝试其他方式
            if self.base_path is None:
                if project_path := os.environ.get("SUPERVISOR_PROJECT_PATH"):
                    self.base_path = Path(project_path)
                elif original_pwd := os.environ.get("ORIGINAL_PWD"):  # Claude Code 启动时的原始目录
                    self.base_path = Path(original_pwd)
                elif pwd := os.environ.get("PWD"):  # 备用方案
                    self.base_path = Path(pwd)
                else:
                    self.base_path = Path(os.getcwd())

        # 私有区域 - 用户和AI都不应该直接操作
        self.supervisor_dir = self.base_path / ".supervisor"
        self.suspended_tasks_dir = self.supervisor_dir / "suspended_tasks"
        
        # 工作区域 - AI和用户可以访问
        self.workspace_dir = self.base_path / "supervisor_workspace"
        self.templates_dir = self.workspace_dir / "templates"
        self.sop_dir = self.workspace_dir / "sop"
        self.current_task_dir = self.workspace_dir / "current_task"

    def create_supervisor_directory(self) -> None:
        """创建.supervisor目录结构和工作区"""
        # 创建私有区域
        self.supervisor_dir.mkdir(parents=True, exist_ok=True)
        self.suspended_tasks_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建工作区域
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.sop_dir.mkdir(parents=True, exist_ok=True)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        # 注意：不再预先创建 templates 目录，因为模板现在放在 sop/ 目录下

    def save_user_info(self, user_info: Dict[str, Any]) -> None:
        """
        保存用户信息到user.json
        会先读取现有内容，然后更新，避免覆盖已有信息

        Args:
            user_info: 用户信息字典（包含user_id, username, access_token等）
        """
        # 确保.supervisor目录存在
        self.create_supervisor_directory()
        
        user_file = self.supervisor_dir / "user.json"
        
        # 读取现有的用户信息（如果存在）
        existing_info = {}
        if user_file.exists():
            try:
                with open(user_file, "r", encoding="utf-8") as f:
                    existing_info = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_info = {}
        
        # 更新现有信息，保留原有字段
        existing_info.update(user_info)
            
        with open(user_file, "w", encoding="utf-8") as f:
            json.dump(existing_info, f, ensure_ascii=False, indent=2)

    def read_user_info(self) -> Dict[str, Any]:
        """
        读取用户信息

        Returns:
            用户信息字典

        Raises:
            FileNotFoundError: 当user.json不存在时
        """
        user_file = self.supervisor_dir / "user.json"
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"user.json not found. Please login first."
            )

    def save_project_info(self, project_info: Dict[str, Any]) -> None:
        """
        保存项目信息到project.json
        会先读取现有内容，然后更新，避免覆盖已有信息

        Args:
            project_info: 项目信息字典（包含project_path等项目元数据）
        """
        project_file = self.supervisor_dir / "project.json"
        
        # 读取现有的项目信息（如果存在）
        existing_info = {}
        if project_file.exists():
            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    existing_info = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # 如果文件损坏或不存在，使用空字典
                existing_info = {}
        
        # 更新现有信息，保留原有字段
        existing_info.update(project_info)
        
        # 确保包含关键配置信息
        if "project_path" not in existing_info:
            existing_info["project_path"] = str(self.base_path)
            
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(existing_info, f, ensure_ascii=False, indent=2)

    def read_project_info(self) -> Dict[str, Any]:
        """
        读取项目信息从project.json

        Returns:
            项目信息字典

        Raises:
            FileNotFoundError: 当project.json不存在时
        """
        project_file = self.supervisor_dir / "project.json"
        try:
            with open(project_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"project.json not found. Please run 'setup_workspace' first."
            )

    def save_current_task_phase(
        self, full_data: Dict[str, Any], task_id: str, task_phase_order: int = None
    ) -> None:
        """
        保存当前任务阶段信息到当前任务组目录下的 {prefix}_{task_phase_type}_instructions.md

        Args:
            full_data: 包含任务阶段和描述的完整数据
            task_id: 任务组ID
            task_phase_order: 任务阶段序号，必须提供（MCP server会传入正确的序号）
        """
        # 获取任务阶段类型用于文件命名
        task_phase_data = full_data.get("task_phase", {})
        task_phase_type = task_phase_data.get("type", "unknown").lower()

        # 使用当前任务组工作目录
        self.current_task_dir.mkdir(parents=True, exist_ok=True)

        # 简化：直接使用传入的任务阶段序号，不再调用API
        if task_phase_order is not None:
            prefix = f"{task_phase_order:02d}"
        else:
            # 如果没有提供序号，使用简单的本地文件计数
            # 统计current_task目录中现有的编号文件数量
            existing_files = list(self.current_task_dir.glob("[0-9][0-9]_*_instructions.md"))
            prefix = f"{len(existing_files) + 1:02d}"

        task_phase_file = self.current_task_dir / f"{prefix}_{task_phase_type}_instructions.md"

        task_phase_data = full_data.get("task_phase", {})

        # 获取任务阶段描述，支持标准API格式
        content = ""

        # Get task phase data from the full data structure
        if "task_phase" in full_data:
            task_phase_data = full_data["task_phase"]

        # 标准格式：从task_phase.description字段获取（API返回的标准格式）
        if "task_phase" in full_data and "description" in full_data["task_phase"]:
            content = full_data["task_phase"]["description"]
        # 如果没有description，表示数据格式有问题
        else:
            raise ValueError(
                f"Invalid task phase data format: missing 'task_phase.description' field. Got keys: {list(full_data.get('task_phase', {}).keys())}"
            )

        # 确保目录存在（只在目录不存在时尝试创建）
        if not task_phase_file.parent.exists():
            try:
                task_phase_file.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, FileNotFoundError):
                # 如果无法创建目录（如测试中的假路径），跳过目录创建
                pass

        with open(task_phase_file, "w", encoding="utf-8") as f:
            f.write(content)

        # 更新项目信息中的当前任务阶段数据
        try:
            project_info = self.read_project_info()
        except FileNotFoundError:
            project_info = {}

        # 更新进行中任务组的当前任务阶段信息
        if "in_progress_task" not in project_info:
            project_info["in_progress_task"] = {
                "id": task_id,
                "title": "",
                "status": "IN_PROGRESS"
            }
        
        # 确保任务组ID匹配
        if project_info["in_progress_task"].get("id") != task_id:
            project_info["in_progress_task"]["id"] = task_id

        # 更新进行中任务组的当前任务阶段信息
        project_info["in_progress_task"]["current_task_phase"] = {
            "id": task_phase_data.get("id"),
            "title": task_phase_data.get("title"),
            "type": task_phase_data.get("type"),
            "status": task_phase_data.get("status"),
            "task_id": task_phase_data.get("task_id"),
            "project_id": task_phase_data.get("project_id"),
        }

        self.save_project_info(project_info)

    def cleanup_task_files(self, task_id: str) -> None:
        """
        清理指定任务组完成后的文件
        只有当整个任务组完成（验收任务全部通过，上报成功）时才调用

        Args:
            task_id: 要清理的任务组ID
        """
        # 清理当前任务组工作目录 (supervisor_workspace/current_task)
        if self.current_task_dir.exists():
            shutil.rmtree(self.current_task_dir)
            self.current_task_dir.mkdir(parents=True, exist_ok=True)

        # 注意：不删除暂存的任务组文件，因为任务组完成不代表它之前被暂存过
        # suspended_dir 应该只在 continue_suspended 时才清理

        # 清理项目信息中的任务组记录
        try:
            project_info = self.read_project_info()
            # 如果这是当前进行中的任务组，清理进行中任务组
            in_progress_group = project_info.get("in_progress_task")
            if in_progress_group and in_progress_group.get("id") == task_id:
                project_info["in_progress_task"] = None
                self.save_project_info(project_info)
        except FileNotFoundError:
            pass

    def read_current_task_phase(self, task_id: str) -> Dict[str, Any]:
        """
        读取指定任务组的当前任务阶段信息

        Args:
            task_id: 任务组ID

        Returns:
包含task_phase和context的字典

        Raises:
            FileNotFoundError: 当数字前缀的指令文件不存在时
        """
        # 查找当前任务组目录中的指令文件
        numbered_files = list(self.current_task_dir.glob("[0-9][0-9]_*_instructions.md"))

        if not numbered_files:
            raise FileNotFoundError(
                f"No numbered prefix instruction files found in current task group. Please run 'next' first."
            )

        # 按数字前缀排序，使用序号最小的文件
        numbered_files.sort(key=lambda f: f.name)
        task_phase_file = numbered_files[0]

        # 返回一个简单的标记，表示任务阶段文件存在
        # 实际的任务阶段信息已经在 Markdown 文件中
        return {"status": "task_phase_loaded", "file": str(task_phase_file)}

    def read_current_task_phase_data(self, task_id: str = None) -> Dict[str, Any]:
        """
        读取当前任务阶段的数据（供report功能使用）

        Args:
            task_id: 任务组ID，如果不提供则使用当前活跃的任务组

        Returns:
任务阶段数据字典

        Raises:
            FileNotFoundError: 当项目信息不存在时
ValueError: 当没有当前任务阶段时
        """
        project_info = self.read_project_info()

        if task_id is None:
            in_progress_group = project_info.get("in_progress_task")
            if not in_progress_group:
                raise ValueError("No current task phase found. Please run 'next' first.")
            task_id = in_progress_group["id"]
            if not task_id:
                raise ValueError(
                    "No current task phase group found. Please run 'next' first."
                )

        # 检查当前进行中的任务组
        in_progress_group = project_info.get("in_progress_task")
        if not in_progress_group or in_progress_group.get("id") != task_id:
            raise ValueError(f"No task phase data found for task group {task_id}.")

        return in_progress_group.get("current_task_phase", {})

    def has_user_info(self) -> bool:
        """检查用户信息文件是否存在"""
        return (self.supervisor_dir / "user.json").exists()

    def has_project_info(self) -> bool:
        """检查项目信息文件是否存在"""
        return (self.supervisor_dir / "project.json").exists()

    def has_current_task_phase(self, task_id: str = None) -> bool:
        """检查是否有当前任务阶段信息"""
        try:
            project_info = self.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            return in_progress_group and "current_task_phase" in in_progress_group
        except:
            return False

    # 移除了get_task_completed_count方法
    # 原因：不需要异步API调用，FileManager应该只处理本地文件操作

    def initialize_project_structure(self, initialization_data: Dict[str, Any]) -> None:
        """
        初始化项目结构，创建必要的目录

        Args:
            initialization_data: 从API获取的初始化数据，包含：
                - templates: 模板文件列表（每个包含name, path, step_identifier）
                - directories: 需要创建的目录列表
        """
        # 创建基础目录
        self.create_supervisor_directory()

        # 注意：不再预先创建 templates 目录，因为模板现在放在 sop/ 目录下
        # docs目录和交付物目录不预先创建，由AI agent根据需要动态创建

        # 返回模板列表供后续下载
        return initialization_data.get("templates", [])

    async def download_template(
        self, api_client, template_info: Dict[str, Any]
    ) -> bool:
        """
        下载单个模板文件

        Args:
            api_client: API客户端
            template_info: 模板信息（包含name, path, step_identifier，可选content）

        Returns:
            是否下载成功
        """
        try:
            # API设计：projects/{id}/templates/ 直接返回完整的模板内容
            # 验证content字段的存在和有效性
            if "content" not in template_info:
                raise Exception(f"模板 {template_info.get('name', 'unknown')} 缺少content字段")
            
            content = template_info["content"]
            if not content:
                raise Exception(f"模板 {template_info.get('name', 'unknown')} 的content字段为空")

            # 保存到supervisor_workspace/目录下（支持sop/路径结构）
            template_path = template_info["path"]
            
            # 如果路径以 "sop/" 开头，保存到工作区根目录
            # 否则保存到 templates 目录（向后兼容）
            if template_path.startswith("sop/"):
                target_path = self.workspace_dir / template_path
            else:
                # 传统模板路径处理（去掉"templates/"前缀如果有的话）
                if template_path.startswith("templates/"):
                    relative_path = template_path[len("templates/"):]
                else:
                    relative_path = template_path
                target_path = self.templates_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 模板文件可以直接覆盖，不需要保护
            if target_path.exists():
                print(f"🔄 覆盖模板文件: {target_path}")

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            return True
        except Exception:
            return False

    async def save_sop_config(self, stage: str, step_identifier: str, config_data: dict) -> bool:
        """
        保存SOP步骤的config.json文件到supervisor_workspace/sop/目录
        
        Args:
            stage: 阶段名称
            step_identifier: 步骤标识符 
            config_data: 配置数据
            
        Returns:
            是否保存成功
        """
        try:
            import json
            
            # 创建目标目录: supervisor_workspace/sop/{stage}/{step_identifier}/
            config_dir = self.sop_dir / stage / step_identifier
            config_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存config.json
            config_file = config_dir / "config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Failed to save SOP config for {stage}/{step_identifier}: {e}")
            return False

    def suspend_current_task(self, task_id: str) -> None:
        """
        暂存当前任务组的文件到suspended_tasks目录
        
        Args:
            task_id: 要暂存的任务组ID
        """
        if not self.current_task_dir.exists():
            return
            
        # 创建暂存目录
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        suspended_dir.mkdir(parents=True, exist_ok=True)
        
        # 移动所有文件到暂存目录
        for item in self.current_task_dir.iterdir():
            target = suspended_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
        
        # 清空当前任务组目录
        shutil.rmtree(self.current_task_dir)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
    
    def restore_task(self, task_id: str) -> bool:
        """
        从暂存目录恢复任务组文件到当前工作目录
        
        Args:
            task_id: 要恢复的任务组ID
            
        Returns:
            bool: 是否成功恢复
        """
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        if not suspended_dir.exists():
            return False
            
        # 清空当前任务组目录
        if self.current_task_dir.exists():
            shutil.rmtree(self.current_task_dir)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        
        # 恢复文件
        for item in suspended_dir.iterdir():
            target = self.current_task_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
                
        # 删除暂存目录
        shutil.rmtree(suspended_dir)
        return True
        
    def switch_task_directory(self, task_id: str) -> None:
        """
        切换到指定任务组的工作目录

        Args:
            task_id: 任务组ID
        """
        # 更新项目信息中的进行中任务组
        try:
            project_info = self.read_project_info()
            # 设置或更新进行中任务组
            project_info["in_progress_task"] = {
                "id": task_id,
                "title": project_info.get("in_progress_task", {}).get("title", ""),
                "status": "IN_PROGRESS"
            }
            self.save_project_info(project_info)
        except FileNotFoundError:
            # 如果项目信息不存在，创建基本结构
            project_info = {
                "in_progress_task": {
                    "id": task_id,
                    "title": "",
                    "status": "IN_PROGRESS"
                }
            }
            self.save_project_info(project_info)

    def get_current_task_phase_status(self, task_id: str = None) -> Dict[str, Any]:
        """
        获取当前任务组的任务阶段状态

        Args:
            task_id: 任务组ID（不使用，保持兼容性）

        Returns:
任务阶段状态字典
        """
        current_task_phase_files = list(self.current_task_dir.glob("*_instructions.md"))

        if current_task_phase_files:
            # 找到最新的任务阶段文件
            latest_file = max(current_task_phase_files, key=lambda f: f.stat().st_mtime)

            return {
                "has_current_task_phase": True,
                "latest_task_phase_file": str(latest_file.name),
                "task_phase_count": len(current_task_phase_files),
            }
        else:
            return {"has_current_task_phase": False, "task_phase_count": 0}


    def get_template_path(self, filename: str) -> Path:
        """
        获取模板文件的完整路径

        Args:
            filename: 模板文件名

        Returns:
            模板文件的完整路径
        """
        return self.templates_dir / filename
    
    def is_task_suspended(self, task_id: str) -> bool:
        """
        检查指定任务组是否被暂存
        
        Args:
            task_id: 任务组ID
            
        Returns:
            bool: 是否被暂存
        """
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        return suspended_dir.exists()
        
    def list_suspended_tasks(self) -> list:
        """
        列出所有暂存的任务组
        
        Returns:
            list: 暂存的任务组ID列表
        """
        if not self.suspended_tasks_dir.exists():
            return []
            
        suspended_dirs = [d.name.replace("task_", "") 
                         for d in self.suspended_tasks_dir.iterdir() 
                         if d.is_dir() and d.name.startswith("task_")]
        return suspended_dirs
