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
                2. SUPERVISOR_PROJECT_PATH 环境变量
                3. 当前工作目录
        """
        if base_path:
            self.base_path = Path(base_path)
        elif project_path := os.environ.get("SUPERVISOR_PROJECT_PATH"):
            self.base_path = Path(project_path)
        else:
            self.base_path = Path(os.getcwd())

        # 私有区域 - 用户和AI都不应该直接操作
        self.supervisor_dir = self.base_path / ".supervisor"
        self.suspended_task_groups_dir = self.supervisor_dir / "suspended_task_groups"
        
        # 工作区域 - AI和用户可以访问
        self.workspace_dir = self.base_path / "supervisor_workspace"
        self.templates_dir = self.workspace_dir / "templates"
        self.current_task_group_dir = self.workspace_dir / "current_task_group"

    def create_supervisor_directory(self) -> None:
        """创建.supervisor目录结构和工作区"""
        # 创建私有区域
        self.supervisor_dir.mkdir(parents=True, exist_ok=True)
        self.suspended_task_groups_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建工作区域
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.current_task_group_dir.mkdir(parents=True, exist_ok=True)

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

    def save_current_task(
        self, full_data: Dict[str, Any], task_group_id: str, task_order: int = None
    ) -> None:
        """
        保存当前任务信息到当前任务组目录下的 {prefix}_{task_type}_instructions.md

        Args:
            full_data: 包含任务和描述的完整数据
            task_group_id: 任务组ID
            task_order: 任务序号，必须提供（MCP server会传入正确的序号）
        """
        # 获取任务类型用于文件命名
        task_data = full_data.get("task", {})
        task_type = task_data.get("type", "unknown").lower()

        # 使用当前任务组工作目录
        self.current_task_group_dir.mkdir(parents=True, exist_ok=True)

        # 简化：直接使用传入的任务序号，不再调用API
        if task_order is not None:
            prefix = f"{task_order:02d}"
        else:
            # 如果没有提供序号，使用简单的本地文件计数
            # 统计current_task_group目录中现有的编号文件数量
            existing_files = list(self.current_task_group_dir.glob("[0-9][0-9]_*_instructions.md"))
            prefix = f"{len(existing_files) + 1:02d}"

        task_file = self.current_task_group_dir / f"{prefix}_{task_type}_instructions.md"

        task_data = full_data.get("task", {})

        # 获取任务描述，支持标准API格式
        content = ""

        # Get task data from the full data structure
        if "task" in full_data:
            task_data = full_data["task"]

        # 标准格式：从task.description字段获取（API返回的标准格式）
        if "task" in full_data and "description" in full_data["task"]:
            content = full_data["task"]["description"]
        # 如果没有description，表示数据格式有问题
        else:
            raise ValueError(
                f"Invalid task data format: missing 'task.description' field. Got keys: {list(full_data.get('task', {}).keys())}"
            )

        # 确保目录存在（只在目录不存在时尝试创建）
        if not task_file.parent.exists():
            try:
                task_file.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, FileNotFoundError):
                # 如果无法创建目录（如测试中的假路径），跳过目录创建
                pass

        with open(task_file, "w", encoding="utf-8") as f:
            f.write(content)

        # 更新项目信息中的当前任务数据
        try:
            project_info = self.read_project_info()
        except FileNotFoundError:
            project_info = {}

        # 更新项目信息中的当前任务组ID
        project_info["current_task_group_id"] = task_group_id

        # 更新任务组信息
        if "task_groups" not in project_info:
            project_info["task_groups"] = {}

        project_info["task_groups"][task_group_id] = {
            "current_task": {
                "id": task_data.get("id"),
                "title": task_data.get("title"),
                "type": task_data.get("type"),
                "status": task_data.get("status"),
                "task_group_id": task_data.get("task_group_id"),
                "project_id": task_data.get("project_id"),
            }
        }

        self.save_project_info(project_info)

    def save_task_result(
        self,
        task_type: str,
        result_content: str,
        task_group_id: str,
        task_order: int = None,
    ) -> None:
        """
        保存任务结果到当前任务组目录下的 {prefix}_{task_type}_results.md
        注意：implementing类型不保存结果文件，因为有专门的目录存放文档

        Args:
            task_type: 任务类型 (understanding, planning, validation, fixing)
            result_content: 结果内容
            task_group_id: 任务组ID
            task_order: 任务序号（可选）
        """
        # implementing阶段的结果有专门的目录去放文档，不需要在任务组目录中保存
        if task_type.lower() == "implementing":
            return

        task_type_lower = task_type.lower()

        # 简化：根据现有instruction文件推断序号
        if task_order is not None:
            prefix = f"{task_order:02d}"
        else:
            # 查找对应的instruction文件来确定序号
            instruction_files = list(
                self.current_task_group_dir.glob(f"[0-9][0-9]_{task_type_lower}_instructions.md")
            )
            if instruction_files:
                # 使用instruction文件的序号
                instruction_file = instruction_files[0]
                prefix = instruction_file.name[:2]  # 取前两位数字
            else:
                # 如果找不到对应的instruction文件，使用简单计数
                existing_files = list(self.current_task_group_dir.glob("[0-9][0-9]_*_results.md"))
                prefix = f"{len(existing_files) + 1:02d}"

        result_file = self.current_task_group_dir / f"{prefix}_{task_type_lower}_results.md"

        # 确保目录存在
        if not result_file.parent.exists():
            try:
                result_file.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, FileNotFoundError):
                pass

        with open(result_file, "w", encoding="utf-8") as f:
            f.write(result_content)

    def cleanup_task_group_files(self, task_group_id: str) -> None:
        """
        清理指定任务组完成后的文件
        只有当整个任务组完成（验收任务全部通过，上报成功）时才调用

        Args:
            task_group_id: 要清理的任务组ID
        """
        # 清理当前任务组工作目录
        if self.current_task_group_dir.exists():
            shutil.rmtree(self.current_task_group_dir)
            self.current_task_group_dir.mkdir(parents=True, exist_ok=True)
        
        # 清理暂存的任务组文件
        suspended_dir = self.suspended_task_groups_dir / f"task_group_{task_group_id}"
        if suspended_dir.exists():
            shutil.rmtree(suspended_dir)

        # 清理项目信息中的任务组记录
        try:
            project_info = self.read_project_info()
            if (
                "task_groups" in project_info
                and task_group_id in project_info["task_groups"]
            ):
                del project_info["task_groups"][task_group_id]

                # 如果这是当前任务组，清理当前任务组ID
                if project_info.get("current_task_group_id") == task_group_id:
                    project_info["current_task_group_id"] = None

                self.save_project_info(project_info)
        except FileNotFoundError:
            pass

    def read_current_task(self, task_group_id: str) -> Dict[str, Any]:
        """
        读取指定任务组的当前任务信息

        Args:
            task_group_id: 任务组ID

        Returns:
            包含task和context的字典

        Raises:
            FileNotFoundError: 当数字前缀的指令文件不存在时
        """
        # 查找当前任务组目录中的指令文件
        numbered_files = list(self.current_task_group_dir.glob("[0-9][0-9]_*_instructions.md"))

        if not numbered_files:
            raise FileNotFoundError(
                f"No numbered prefix instruction files found in current task group. Please run 'next' first."
            )

        # 按数字前缀排序，使用序号最小的文件
        numbered_files.sort(key=lambda f: f.name)
        task_file = numbered_files[0]

        # 返回一个简单的标记，表示任务文件存在
        # 实际的任务信息已经在 Markdown 文件中
        return {"status": "task_loaded", "file": str(task_file)}

    def read_current_task_data(self, task_group_id: str = None) -> Dict[str, Any]:
        """
        读取当前任务的数据（供report功能使用）

        Args:
            task_group_id: 任务组ID，如果不提供则使用当前活跃的任务组

        Returns:
            任务数据字典

        Raises:
            FileNotFoundError: 当项目信息不存在时
            ValueError: 当没有当前任务时
        """
        project_info = self.read_project_info()

        if task_group_id is None:
            task_group_id = project_info.get("current_task_group_id")
            if not task_group_id:
                raise ValueError(
                    "No current task group found. Please run 'next' first."
                )

        if (
            "task_groups" not in project_info
            or task_group_id not in project_info["task_groups"]
        ):
            raise ValueError(f"No task data found for task group {task_group_id}.")

        return project_info["task_groups"][task_group_id].get("current_task", {})

    def has_user_info(self) -> bool:
        """检查用户信息文件是否存在"""
        return (self.supervisor_dir / "user.json").exists()

    def has_project_info(self) -> bool:
        """检查项目信息文件是否存在"""
        return (self.supervisor_dir / "project.json").exists()

    def has_current_task(self, task_group_id: str = None) -> bool:
        """检查当前任务组是否有任务文件（只支持数字前缀命名）"""
        # 查找当前任务组目录中的指令文件
        numbered_files = list(self.current_task_group_dir.glob("[0-9][0-9]_*_instructions.md"))
        return len(numbered_files) > 0

    # 移除了get_task_group_completed_count方法
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

        # 创建模板目录
        self.templates_dir.mkdir(exist_ok=True)

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

            # 保存到指定路径，带文件保护机制
            target_path = self.base_path / template_info["path"]
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 模板文件可以直接覆盖，不需要保护
            if target_path.exists():
                print(f"🔄 覆盖模板文件: {target_path}")

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            return True
        except Exception:
            return False


    def suspend_current_task_group(self, task_group_id: str) -> None:
        """
        暂存当前任务组的文件到suspended_task_groups目录
        
        Args:
            task_group_id: 要暂存的任务组ID
        """
        if not self.current_task_group_dir.exists():
            return
            
        # 创建暂存目录
        suspended_dir = self.suspended_task_groups_dir / f"task_group_{task_group_id}"
        suspended_dir.mkdir(parents=True, exist_ok=True)
        
        # 移动所有文件到暂存目录
        for item in self.current_task_group_dir.iterdir():
            target = suspended_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
        
        # 清空当前任务组目录
        shutil.rmtree(self.current_task_group_dir)
        self.current_task_group_dir.mkdir(parents=True, exist_ok=True)
    
    def restore_task_group(self, task_group_id: str) -> bool:
        """
        从暂存目录恢复任务组文件到当前工作目录
        
        Args:
            task_group_id: 要恢复的任务组ID
            
        Returns:
            bool: 是否成功恢复
        """
        suspended_dir = self.suspended_task_groups_dir / f"task_group_{task_group_id}"
        if not suspended_dir.exists():
            return False
            
        # 清空当前任务组目录
        if self.current_task_group_dir.exists():
            shutil.rmtree(self.current_task_group_dir)
        self.current_task_group_dir.mkdir(parents=True, exist_ok=True)
        
        # 恢复文件
        for item in suspended_dir.iterdir():
            target = self.current_task_group_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
                
        # 删除暂存目录
        shutil.rmtree(suspended_dir)
        return True
        
    def switch_task_group_directory(self, task_group_id: str) -> None:
        """
        切换到指定任务组的工作目录

        Args:
            task_group_id: 任务组ID
        """
        # 更新项目信息中的当前任务组ID
        try:
            project_info = self.read_project_info()
            project_info["current_task_group_id"] = task_group_id
            self.save_project_info(project_info)
        except FileNotFoundError:
            # 如果项目信息不存在，创建基本结构
            project_info = {"current_task_group_id": task_group_id, "task_groups": {}}
            self.save_project_info(project_info)

    def get_current_task_status(self, task_group_id: str = None) -> Dict[str, Any]:
        """
        获取当前任务组的任务状态

        Args:
            task_group_id: 任务组ID（不使用，保持兼容性）

        Returns:
            任务状态字典
        """
        current_task_files = list(self.current_task_group_dir.glob("*_instructions.md"))

        if current_task_files:
            # 找到最新的任务文件
            latest_file = max(current_task_files, key=lambda f: f.stat().st_mtime)

            return {
                "has_current_task": True,
                "latest_task_file": str(latest_file.name),
                "task_count": len(current_task_files),
            }
        else:
            return {"has_current_task": False, "task_count": 0}

    def update_task_group_status(
        self, task_group_id: str, status: Dict[str, Any]
    ) -> None:
        """
        更新任务组状态信息

        Args:
            task_group_id: 任务组ID
            status: 状态信息
        """
        project_info = self.read_project_info()
        if "task_groups" not in project_info:
            project_info["task_groups"] = {}

        project_info["task_groups"][task_group_id] = status
        self.save_project_info(project_info)

    def get_template_path(self, filename: str) -> Path:
        """
        获取模板文件的完整路径

        Args:
            filename: 模板文件名

        Returns:
            模板文件的完整路径
        """
        return self.templates_dir / filename
    
    def is_task_group_suspended(self, task_group_id: str) -> bool:
        """
        检查指定任务组是否被暂存
        
        Args:
            task_group_id: 任务组ID
            
        Returns:
            bool: 是否被暂存
        """
        suspended_dir = self.suspended_task_groups_dir / f"task_group_{task_group_id}"
        return suspended_dir.exists()
        
    def list_suspended_task_groups(self) -> list:
        """
        列出所有暂存的任务组
        
        Returns:
            list: 暂存的任务组ID列表
        """
        if not self.suspended_task_groups_dir.exists():
            return []
            
        suspended_dirs = [d.name.replace("task_group_", "") 
                         for d in self.suspended_task_groups_dir.iterdir() 
                         if d.is_dir() and d.name.startswith("task_group_")]
        return suspended_dirs
