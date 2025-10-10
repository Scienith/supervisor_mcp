"""
分析相关（pre_analyze）。

- pre_analyze

说明：
- 外部 API 统一通过 `service.get_api_client()` 获取，兼容测试的打桩方式。
- 通过 `service_obj` 访问 MCPService 的 file_manager、session_manager、辅助方法等。
"""
from __future__ import annotations

from typing import Any, Dict

import service


async def pre_analyze(service_obj, user_requirement: str) -> Dict[str, Any]:
    if not service_obj.session_manager.is_authenticated():
        return {"success": False, "error_code": "AUTH_001", "message": "请先登录"}
    try:
        if not service_obj.file_manager.has_project_info():
            return {"status": "error", "message": "项目未初始化，请先执行 init 工具初始化项目"}

        project_data = service_obj.file_manager.read_project_info()
        project_id = project_data.get("project_id")
        if not project_id:
            return {"status": "error", "message": "项目信息中缺少 project_id，请重新初始化项目"}

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            sop_response = await api.request("GET", "sop/graph/")

        if sop_response.get("status") == "error":
            return {
                "status": "error",
                "message": f"无法获取SOP配置信息: {sop_response.get('message', '未知错误')}",
            }

        steps_data = sop_response.get("steps", {})
        dependencies = sop_response.get("dependencies", [])

        dependency_map = {}
        for dep in dependencies:
            from_step = dep.get("from")
            to_step = dep.get("to")
            if to_step not in dependency_map:
                dependency_map[to_step] = []
            dependency_map[to_step].append(from_step)

        stages = {}
        for identifier, step in steps_data.items():
            stage = step.get("stage", "其他")
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(
                {
                    "identifier": identifier,
                    "name": step.get("name", identifier),
                    "description": step.get("description", ""),
                    "dependencies": dependency_map.get(identifier, []),
                }
            )

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

        sop_steps_info = "**可用SOP步骤**（按阶段分组）：\n\n"
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

        other_stages = set(stages.keys()) - set(stage_order)
        for stage_name in sorted(other_stages):
            if stages[stage_name]:
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
        return {"status": "error", "message": f"需求分析失败: {str(e)}"}

