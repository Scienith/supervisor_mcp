"""
FileManager 的功能按职责拆分为多个 Mixin，便于维护与精简主文件。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any


class UserInfoMixin:
    def save_user_info(self, user_info: Dict[str, Any]) -> None:
        self.create_supervisor_directory()
        user_file = self.supervisor_dir / "user.json"
        existing_info = {}
        if user_file.exists():
            try:
                with open(user_file, "r", encoding="utf-8") as f:
                    existing_info = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_info = {}
        existing_info.update(user_info)
        with open(user_file, "w", encoding="utf-8") as f:
            json.dump(existing_info, f, ensure_ascii=False, indent=2)

    def read_user_info(self) -> Dict[str, Any]:
        user_file = self.supervisor_dir / "user.json"
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError("user.json not found. Please login first.")

    def has_user_info(self) -> bool:
        return (self.supervisor_dir / "user.json").exists()


class ProjectInfoMixin:
    def save_project_info(self, project_info: Dict[str, Any]) -> None:
        project_file = self.supervisor_dir / "project.json"
        existing_info = {}
        if project_file.exists():
            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    existing_info = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_info = {}
        existing_info.update(project_info)
        if "project_path" not in existing_info:
            existing_info["project_path"] = str(self.base_path)
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(existing_info, f, ensure_ascii=False, indent=2)

    def read_project_info(self) -> Dict[str, Any]:
        project_file = self.supervisor_dir / "project.json"
        try:
            with open(project_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                "project.json not found. Please run 'setup_workspace' first."
            )

    def has_project_info(self) -> bool:
        return (self.supervisor_dir / "project.json").exists()


class TaskFilesMixin:
    def save_current_task_phase(
        self, full_data: Dict[str, Any], task_id: str, task_phase_order: int = None
    ) -> None:
        task_phase_data = full_data.get("task_phase", {})
        task_phase_type = task_phase_data.get("type", "unknown").lower()
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        if task_phase_order is not None:
            prefix = f"{task_phase_order:02d}"
        else:
            existing_files = list(
                self.current_task_dir.glob("[0-9][0-9]_*_instructions.md")
            )
            prefix = f"{len(existing_files) + 1:02d}"
        task_phase_file = self.current_task_dir / f"{prefix}_{task_phase_type}_instructions.md"

        if "task_phase" in full_data and "description" in full_data["task_phase"]:
            content = full_data["task_phase"]["description"]
        else:
            raise ValueError(
                "Invalid task phase data format: missing 'task_phase.description' field."
            )

        if not task_phase_file.parent.exists():
            try:
                task_phase_file.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, FileNotFoundError):
                pass

        with open(task_phase_file, "w", encoding="utf-8") as f:
            f.write(content)

        try:
            project_info = self.read_project_info()
        except FileNotFoundError:
            project_info = {}

        if "in_progress_task" not in project_info:
            project_info["in_progress_task"] = {
                "id": task_id,
                "title": "",
                "status": "IN_PROGRESS",
            }
        if project_info["in_progress_task"].get("id") != task_id:
            project_info["in_progress_task"]["id"] = task_id

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
        if self.current_task_dir.exists():
            shutil.rmtree(self.current_task_dir)
            self.current_task_dir.mkdir(parents=True, exist_ok=True)
        try:
            project_info = self.read_project_info()
            in_progress_group = project_info.get("in_progress_task")
            if in_progress_group and in_progress_group.get("id") == task_id:
                project_info["in_progress_task"] = None
                self.save_project_info(project_info)
        except FileNotFoundError:
            pass

    def read_current_task_phase(self, task_id: str) -> Dict[str, Any]:
        numbered_files = list(
            self.current_task_dir.glob("[0-9][0-9]_*_instructions.md")
        )
        if not numbered_files:
            raise FileNotFoundError(
                "No numbered prefix instruction files found in current task group. Please run 'next' first."
            )
        numbered_files.sort(key=lambda f: f.name)
        task_phase_file = numbered_files[0]
        return {"status": "task_phase_loaded", "file": str(task_phase_file)}

    def read_current_task_phase_data(self, task_id: str = None) -> Dict[str, Any]:
        project_info = self.read_project_info()
        if task_id is None:
            in_progress_group = project_info.get("in_progress_task")
            if not in_progress_group:
                raise ValueError("No current task phase found. Please run 'next' first.")
            task_id = in_progress_group["id"]
            if not task_id:
                raise ValueError("No current task phase group found. Please run 'next' first.")
        in_progress_group = project_info.get("in_progress_task")
        if not in_progress_group or in_progress_group.get("id") != task_id:
            raise ValueError(f"No task phase data found for task group {task_id}.")
        return in_progress_group.get("current_task_phase", {})

    def switch_task_directory(self, task_id: str) -> None:
        try:
            project_info = self.read_project_info()
            project_info["in_progress_task"] = {
                "id": task_id,
                "title": project_info.get("in_progress_task", {}).get("title", ""),
                "status": "IN_PROGRESS",
            }
            self.save_project_info(project_info)
        except FileNotFoundError:
            project_info = {
                "in_progress_task": {"id": task_id, "title": "", "status": "IN_PROGRESS"}
            }
            self.save_project_info(project_info)

    def get_current_task_phase_status(self, task_id: str = None) -> Dict[str, Any]:
        current_task_phase_files = list(self.current_task_dir.glob("*_instructions.md"))
        if current_task_phase_files:
            latest_file = max(current_task_phase_files, key=lambda f: f.stat().st_mtime)
            return {
                "has_current_task_phase": True,
                "latest_task_phase_file": str(latest_file.name),
                "task_phase_count": len(current_task_phase_files),
            }
        else:
            return {"has_current_task_phase": False, "task_phase_count": 0}

    def suspend_current_task(self, task_id: str) -> None:
        if not self.current_task_dir.exists():
            return
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        suspended_dir.mkdir(parents=True, exist_ok=True)
        for item in self.current_task_dir.iterdir():
            target = suspended_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
        shutil.rmtree(self.current_task_dir)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)

    def restore_task(self, task_id: str) -> bool:
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        if not suspended_dir.exists():
            return False
        if self.current_task_dir.exists():
            shutil.rmtree(self.current_task_dir)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        for item in suspended_dir.iterdir():
            target = self.current_task_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
        shutil.rmtree(suspended_dir)
        return True

    def is_task_suspended(self, task_id: str) -> bool:
        suspended_dir = self.suspended_tasks_dir / f"task_{task_id}"
        return suspended_dir.exists()

    def list_suspended_tasks(self) -> list:
        if not self.suspended_tasks_dir.exists():
            return []
        return [
            d.name.replace("task_", "")
            for d in self.suspended_tasks_dir.iterdir()
            if d.is_dir() and d.name.startswith("task_")
        ]


class TemplateMixin:
    def get_template_path(self, filename: str) -> Path:
        return self.templates_dir / filename

    def save_template(self, template_info: Dict[str, Any]) -> bool:
        try:
            if "path" not in template_info:
                raise Exception("模板信息缺少 path 字段")
            if "content" not in template_info:
                raise Exception(f"模板 {template_info.get('name', 'unknown')} 缺少content字段")
            content = template_info["content"]
            if not content:
                raise Exception(f"模板 {template_info.get('name', 'unknown')} 的content字段为空")

            template_path = template_info["path"]
            if template_path.startswith("sop/"):
                target_path = self.workspace_dir / template_path
            else:
                if template_path.startswith("templates/"):
                    relative_path = template_path[len("templates/"):]
                else:
                    relative_path = template_path
                target_path = self.templates_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                print(f"🔄 覆盖模板文件: {target_path}")
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    async def save_sop_config(self, stage: str, step_identifier: str, config_data: dict) -> bool:
        try:
            config_dir = self.sop_dir / stage / step_identifier
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save SOP config for {stage}/{step_identifier}: {e}")
            return False
