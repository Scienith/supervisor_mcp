"""
MCP本地文件管理器（精简）：
核心类 FileManager 保留在本文件，具体方法实现拆分至 file_manager_mixins。
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from file_manager_mixins import (
    UserInfoMixin,
    ProjectInfoMixin,
    TaskFilesMixin,
    TemplateMixin,
)


class FileManager(UserInfoMixin, ProjectInfoMixin, TaskFilesMixin, TemplateMixin):
    """本地文件管理器（组合多个Mixin实现）"""

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

    # 其余用户/项目/任务/模板相关方法由 Mixin 提供

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

    def clear_current_task_phase(self, task_id: str = None) -> None:
        """清除当前任务阶段缓存"""
        try:
            project_info = self.read_project_info()
        except FileNotFoundError:
            return

        in_progress_group = project_info.get("in_progress_task")
        if not in_progress_group:
            return

        if task_id and in_progress_group.get("id") != task_id:
            return

        if "current_task_phase" in in_progress_group:
            del in_progress_group["current_task_phase"]
            self.save_project_info(project_info)

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
        
    # list_suspended_tasks 使用 mixin 实现
