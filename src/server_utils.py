"""
Server 端工具函数：
- _is_success_payload
- _format_details_text
- _build_instruction_text
- _wrap_tool_payload
- handle_exceptions
"""
from __future__ import annotations

import json
import asyncio
import functools
from typing import Any, Dict

_SUCCESS_STATUSES = {"success", "ok", "info"}


def _is_success_payload(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if "success" in payload:
        return bool(payload["success"])
    status = payload.get("status")
    if status is None:
        return False
    return str(status).lower() in _SUCCESS_STATUSES


def _format_details_text(details: Dict[str, Any]) -> str:
    if not details:
        return ""
    return json.dumps(details, ensure_ascii=False, indent=2)


def _build_instruction_text(
    payload: Dict[str, Any],
    success: bool,
    success_default: str,
    failure_default: str,
) -> str:
    parts = []

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())

    instructions = payload.get("instructions")
    if instructions:
        if isinstance(instructions, list):
            for item in instructions:
                if isinstance(item, dict) and "to_ai" in item:
                    parts.append(str(item["to_ai"]).strip())
                elif item is not None:
                    text = str(item).strip()
                    if text:
                        parts.append(text)
        else:
            text = str(instructions).strip()
            if text:
                parts.append(text)

    excluded_keys = {"success", "status", "message", "instructions"}
    details = {
        key: value
        for key, value in payload.items()
        if key not in excluded_keys and value not in (None, "")
    }
    details_text = _format_details_text(details)
    if details_text:
        parts.append(f"详情:\n{details_text}")

    if parts:
        return "\n\n".join(part for part in parts if part)

    return success_default if success else failure_default


def _wrap_tool_payload(
    payload: Dict[str, Any],
    success_default: str = "操作成功",
    failure_default: str = "操作失败",
) -> Dict[str, Any]:
    if payload is None:
        return {"success": False, "instructions_to_ai": failure_default}

    if not isinstance(payload, dict):
        text = str(payload)
        return {"success": True, "instructions_to_ai": text or success_default}

    success = _is_success_payload(payload)
    instructions_text = _build_instruction_text(
        payload,
        success,
        success_default,
        failure_default,
    )
    return {
        "success": success,
        "instructions_to_ai": instructions_text,
    }


def handle_exceptions(func):
    """为MCP工具添加异常处理装饰器"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            return _wrap_tool_payload(
                {"status": "error", "message": "操作已取消"},
                failure_default="操作已取消",
            )
        except Exception as e:
            return _wrap_tool_payload(
                {
                    "status": "error",
                    "message": f"工具执行失败: {str(e)}",
                    "error_type": type(e).__name__,
                },
                failure_default="工具执行失败",
            )

    return wrapper

