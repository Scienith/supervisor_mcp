import pytest

from fastmcp.tools.tool import ToolResult, TextContent
from server import mcp_server


@pytest.mark.asyncio
async def test_toolresult_content_and_structured():
    tools = await mcp_server.get_tools()
    assert "test_toolresult" in tools

    result = await tools["test_toolresult"].run({})

    # 返回类型为 ToolResult
    assert isinstance(result, ToolResult)

    # content 校验：空字符串（将被包装为单条空文本内容）
    assert isinstance(result.content, list)
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "执行成功"

    # structured_content 校验
    sc = result.structured_content
    assert isinstance(sc, dict)
    assert "policy" in sc
    assert "actions" in sc and isinstance(sc["actions"], list)
    assert len(sc["actions"]) == 6
    a0, a1, a2, a3, a4, a5 = sc["actions"]
    assert a0["tool"] == "display_original_text" and a0.get("args", {}).get("text") == "#你好"
    assert a1["tool"] == "display_original_text" and a1.get("args", {}).get("text") == "#你叫什么"
    assert a2["tool"] == "get_current_time"
    assert a3["tool"] == "get_today"
    assert a4["tool"] == "read_file" and a4.get("args", {}).get("path") == \
        "/Users/junjiecai/Desktop/projects/scientith_projects/POC/text_to_kg/task.md"
    assert a5["tool"] == "execute_phase" and a5.get("args", {}).get("phase") == \
        "执行/Users/junjiecai/Desktop/projects/scientith_projects/POC/text_to_kg/task.md中提到的任务"
