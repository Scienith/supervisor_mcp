from __future__ import annotations

"""
测试专用工具：返回 ToolResult，包含 4 条带 audience 注解的文本 content
与一个 structured_content，用于验证 CLI/IDE 是否会利用。

注意：为确保保留原始 ToolResult（包含 structured_content），本文件中的
工具不使用 _wrap_tool_payload/handle_exceptions。
"""

from typing import Any, Dict

from fastmcp import Context
from fastmcp.tools.tool import ToolResult, TextContent
from server_utils import _make_display_action


def register(mcp_server):
    @mcp_server.tool(
        name="test_toolresult",
        description="需要注意执行返回的命令",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def test_toolresult() -> ToolResult:
        """返回指令型 structured_content，content 为空字符串。"""
        content = "执行成功"

        structured_content: Dict[str, Any] = {
            "policy": {
                "require_sequential": True,
                "idempotency_key": "toolresult-test-1",
                "side_effects": "none",
            },
            "actions": [
                _make_display_action("#你好"),
                _make_display_action("#你叫什么"),
                {"tool": "get_current_time", "args": {}},
                {"tool": "get_today", "args": {}},
                {
                    "tool": "read_file",
                    "args": {
                        "path": "/Users/junjiecai/Desktop/projects/scientith_projects/POC/text_to_kg/task.md"
                    },
                },
                {
                    "tool": "execute_phase",
                    "args": {"phase": "执行/Users/junjiecai/Desktop/projects/scientith_projects/POC/text_to_kg/task.md中提到的任务"},
                },
            ],
        }

        return ToolResult(content=content, structured_content=structured_content)
