#!/usr/bin/env python
"""
Scienith Supervisor MCP Service 启动脚本
"""

import sys
import os
from pathlib import Path

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from server import mcp_server
from config import config

if __name__ == "__main__":
    # 打印启动信息
    print(f"Starting MCP server...", file=sys.stderr)

    api_url = config.api_url
    print(f"API URL: {api_url}", file=sys.stderr)

    # 显示项目路径配置
    project_path = config.project_path
    print(f"Project Path: {project_path}", file=sys.stderr)
    print(
        f".supervisor directory will be created at: {project_path}/.supervisor",
        file=sys.stderr,
    )

    if "--http" in sys.argv:
        # HTTP模式 - 用于远程访问
        mcp_server.run(transport="http", host="0.0.0.0", port=8080, path="/mcp")
    else:
        # 默认STDIO模式 - 用于本地Claude Code
        mcp_server.run()
