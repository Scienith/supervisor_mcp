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
from typing import Any, Dict, List
from fastmcp.tools.tool import ToolResult, TextContent
import re
from logging_config import get_logger

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


def _make_display_action(text: str) -> Dict[str, Any]:
    """构造统一的 display_original_text 动作。

    - 约定始终携带 instruction，提示前端“原封不动地显示”。
    - text 为需要呈现给用户的原文（通常由 user_message 合并或 to_ai fallback）。
    """
    return {
        "tool": "display_original_text",
        "args": {"text": text},
        "instruction": "原封不动的显示text文本，不要做出任何修改",
    }


def _derive_actions_from_text(text: str) -> List[Dict[str, Any]]:
    """Best-effort 从说明文本中提取可执行的 actions。
    - 提取当前工作区下的文件路径，生成 read_file 动作
    - 识别常见工具名（next/finish_task/start/suspend/cancel_task），生成调用动作
    - 默认首条加入 display，把完整说明渲染给用户
    """
    actions: List[Dict[str, Any]] = []

    def push_unique(act: Dict[str, Any]):
        if act not in actions:
            actions.append(act)

    # 先显示完整说明
    brief = text if len(text) <= 8000 else text[:8000]
    push_unique(_make_display_action(brief))

    # 提取路径（匹配 supervisor_workspace/... 或绝对路径中含 supervisor_workspace/...）
    for m in re.finditer(r"([\w./-]*supervisor_workspace/[\w./-]+)", text):
        path = m.group(1)
        push_unique({"tool": "read_file", "args": {"path": path}})

    # 常见动作关键词
    if "`next`" in text or " 使用 next" in text:
        push_unique({"tool": "next", "args": {}})
    if "`finish_task" in text or " finish_task" in text:
        push_unique({"tool": "finish_task", "args": {}})
    if "`start`" in text or " 使用 start" in text:
        push_unique({"tool": "start", "args": {}})
    if "`suspend`" in text or " 使用 suspend" in text:
        push_unique({"tool": "suspend", "args": {}})
    if "`cancel_task`" in text or " cancel_task" in text:
        push_unique({"tool": "cancel_task", "args": {}})

    return actions


def _instructions_to_actions(instructions: Any) -> List[Dict[str, Any]]:
    """将结构化 instructions 转换为 actions。
    - 支持 dict 项：{to_ai, user_message[], kind, phase}
    - display: 生成 display 动作，并尝试从文本中提取 read_file
    - execute: 生成 execute_phase 动作
    - 其他/未知：忽略，由回退逻辑处理
    """
    acts: List[Dict[str, Any]] = []

    def push_unique(act: Dict[str, Any]):
        if act not in acts:
            acts.append(act)

    if not isinstance(instructions, list):
        return []

    # 预扫描：是否已有显式 execute 指令
    has_explicit_execute = any(
        isinstance(x, dict) and (x.get("kind") == "execute") for x in instructions
    )

    for item in instructions:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") or "display"
        to_ai = item.get("to_ai") or ""
        user_msg = item.get("user_message") or []

        if kind == "display":
            # 仅展示 user_message；不再回退到 to_ai，避免把“AI提醒”暴露给用户
            try:
                text = "\n".join([str(x) for x in user_msg if x])
            except Exception:
                text = ""
            if text.strip():
                push_unique(_make_display_action(text))

            # 不再自动追加任何“根据用户的选择行动”的 execute 指令，完全依赖上游显式提供
            # 从文本中提取 read_file 动作
            for t in ([to_ai] + user_msg):
                for act in _derive_actions_from_text(str(t)):
                    if act.get("tool") == "read_file":
                        push_unique(act)

        elif kind == "execute":
            phase = item.get("phase") or to_ai
            push_unique({"tool": "execute_phase", "args": {"phase": str(phase)}})

    return acts


def _wrap_tool_result(
    payload: Dict[str, Any],
    success_default: str = "操作成功",
    failure_default: str = "操作失败",
) -> ToolResult:
    """将原有 payload 包装为 ToolResult，
    - content: 单条文本，包含 to_ai: 指令汇总
    - structured_content: policy + actions（从文本中尽力提取）
    """
    if payload is None:
        text = failure_default
        # 统一简化 content：仅显示执行结果
        content = [TextContent(type="text", text="执行失败")]
        return ToolResult(content=content, structured_content={
            "policy": {"require_sequential": True, "idempotency_key": "wrap-none", "side_effects": "none"},
            "actions": _derive_actions_from_text(text),
        })

    if not isinstance(payload, dict):
        text = str(payload) or success_default
        content = [TextContent(type="text", text="执行成功")]
        return ToolResult(content=content, structured_content={
            "policy": {"require_sequential": True, "idempotency_key": "wrap-str", "side_effects": "none"},
            "actions": _derive_actions_from_text(text),
        })

    success = _is_success_payload(payload)

    # 失败场景：始终只返回一条错误展示动作（不保留任何成功路径的 actions）
    if not success:
        brief = str(payload.get("message") or failure_default)
        extras: List[str] = []
        if payload.get("error_code"):
            extras.append(f"错误码: {payload.get('error_code')}")
        if payload.get("hint"):
            extras.append(f"提示: {payload.get('hint')}")
        if payload.get("error_type"):
            extras.append(f"错误类型: {payload.get('error_type')}")
        suffix = (" （" + "；".join(extras) + ")") if extras else ""
        content = [TextContent(type="text", text=f"执行失败：{brief}{suffix}")]
        lines = [f"❌ {brief}"]
        if payload.get("error_code"):
            lines.append(f"- 错误码: {payload.get('error_code')}")
        if payload.get("hint"):
            lines.append(f"- 提示: {payload.get('hint')}")
        if payload.get("error_type"):
            lines.append(f"- 错误类型: {payload.get('error_type')}")
        return ToolResult(content=content, structured_content={
            "policy": {"require_sequential": True, "idempotency_key": "wrap-error", "side_effects": "none"},
            "actions": [_make_display_action("\n".join(lines))],
        })

    # 成功场景：仅使用结构化指令生成 actions（禁止 fallback）
    try:
        structured_instr = payload.get("instructions_v2")
        actions = _instructions_to_actions(structured_instr) if structured_instr else []
    except Exception:
        actions = []
    if not actions:
        raise ValueError("缺少结构化指令（instructions_v2/actions）")

    content = [TextContent(type="text", text="执行成功")]
    return ToolResult(content=content, structured_content={
        "policy": {"require_sequential": True, "idempotency_key": "wrap-dict", "side_effects": "none"},
        "actions": actions,
    })


def handle_exceptions(func):
    """为MCP工具添加异常处理装饰器"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            return _wrap_tool_result(
                {"status": "error", "message": "操作已取消"},
                failure_default="操作已取消",
            )
        except Exception as e:
            logger = get_logger("tools")
            logger.exception("Tool %s failed", getattr(func, "__name__", "<unknown>"))
            return _wrap_tool_result(
                {
                    "status": "error",
                    "message": f"工具执行失败: {str(e)}",
                    "error_type": type(e).__name__,
                },
                failure_default="工具执行失败",
            )

    return wrapper
