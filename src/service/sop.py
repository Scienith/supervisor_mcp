"""
SOP 相关工具函数模块：
- 更新 step 规则
- 更新 output 模板
- 读取本地 SOP 配置与模板

注意：保持通过 package 级 `service.get_api_client` 获取 API client，
以兼容测试对 `service.get_api_client` 的打桩。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import service  # 使用包级 get_api_client 以便测试 patch('service.get_api_client') 生效


async def update_step_rules(service_obj, stage: str, step_identifier: str) -> Dict[str, Any]:
    if not service_obj.session_manager.is_authenticated():
        return {
            "status": "error",
            "error_code": "AUTH_001",
            "message": "请先登录",
        }

    try:
        # 通过实例方法读取（便于测试对 MCPService._read_step_config 打桩）
        config_data = service_obj._read_step_config(stage, step_identifier)
        if config_data is None:
            return {
                "status": "error",
                "message": f"未找到配置文件: sop/{stage}/{step_identifier}/config.json",
            }

        rules = config_data.get("rules")
        step_id = config_data.get("step_id")

        if not rules:
            return {"status": "error", "message": "配置文件中未找到rules字段"}

        if not step_id:
            return {"status": "error", "message": "配置文件中未找到step_id字段"}

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            return await api.request(
                "PUT",
                f"steps/{step_id}/rules",
                json={"rules": rules},
            )

    except Exception as e:  # noqa: BLE001 - 保持与原逻辑一致
        return {"status": "error", "message": f"更新Step规则失败: {str(e)}"}


async def update_output_template(
    service_obj, stage: str, step_identifier: str, output_name: str
) -> Dict[str, Any]:
    if not service_obj.session_manager.is_authenticated():
        return {
            "status": "error",
            "error_code": "AUTH_001",
            "message": "请先登录",
        }

    try:
        # 通过实例方法读取（便于测试对 MCPService._read_output_config_and_template 打桩）
        output_data = service_obj._read_output_config_and_template(
            stage, step_identifier, output_name
        )
        if output_data is None:
            return {
                "status": "error",
                "message": f"未找到配置或模板: sop/{stage}/{step_identifier}/config.json 中名为 '{output_name}' 的output",
            }

        output_id = output_data.get("output_id")
        template_content = output_data.get("template_content")

        if not output_id:
            return {
                "status": "error",
                "message": f"Output '{output_name}' 中未找到output_id字段",
            }

        if template_content is None:
            return {
                "status": "error",
                "message": f"未找到Output '{output_name}' 对应的模板文件",
            }

        async with service.get_api_client() as api:
            api.headers.update(service_obj.session_manager.get_headers())
            # 注意：这里使用text/plain作为content-type
            api._client.headers["Content-Type"] = "text/plain"

            result = await api.request(
                "PUT", f"outputs/{output_id}/template", data=template_content
            )

            # 恢复JSON content-type
            api._client.headers["Content-Type"] = "application/json"
            return result

    except Exception as e:  # noqa: BLE001 - 保持与原逻辑一致
        return {"status": "error", "message": f"更新Output模板失败: {str(e)}"}


def _read_step_config(
    service_obj, stage: str, step_identifier: str
) -> Optional[Dict[str, Any]]:
    import json

    try:
        sop_dir = service_obj.file_manager.sop_dir
        config_file = sop_dir / stage / step_identifier / "config.json"

        if not config_file.exists():
            return None

        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:  # noqa: BLE001 - 保持与原逻辑一致
        return None


def _read_output_config_and_template(
    service_obj, stage: str, step_identifier: str, output_name: str
) -> Optional[Dict[str, Any]]:
    import json

    try:
        # 先读取配置文件
        config_data = _read_step_config(service_obj, stage, step_identifier)
        if not config_data:
            return None

        outputs = config_data.get("outputs", [])
        target_output = None
        for output in outputs:
            if output.get("name") == output_name:
                target_output = output
                break

        if not target_output:
            return None

        output_id = target_output.get("output_id")
        template_filename = target_output.get("template_filename")
        if not template_filename:
            return None

        sop_dir = service_obj.file_manager.sop_dir
        template_file = sop_dir / stage / step_identifier / "templates" / template_filename
        if not template_file.exists():
            return None

        with open(template_file, "r", encoding="utf-8") as f:
            template_content = f.read()

        return {"output_id": output_id, "template_content": template_content}

    except Exception:  # noqa: BLE001 - 保持与原逻辑一致
        return None
