"""
FastMCP服务器实现（精简版）
通过HTTP API调用Django服务；工具注册分离到子模块。
"""

import os
import logging
from fastmcp import FastMCP
from logging_config import configure_logging, get_logger

# 向后兼容：保持以下名称可被测试打桩
from server_api import API_BASE_URL, get_api_client, APIClient, AutoCloseAPIClient
from file_manager import FileManager

from server_tools_auth import register as register_auth
from server_tools_project import register as register_project
from server_tools_tasks import register as register_tasks
from server_tools_sop import register as register_sop
from server_tools_testing import register as register_testing


# 配置日志（写入 logs/supervisor_mcp.log）
configure_logging()
_logger = get_logger("server")

# 创建MCP服务器实例
mcp_server = FastMCP("Scienith Supervisor MCP")


# 全局服务实例
_mcp_service = None


def get_mcp_service():
    """获取MCP服务实例（单例模式）"""
    global _mcp_service
    if _mcp_service is None:
        from service import MCPService

        _mcp_service = MCPService()
    return _mcp_service


def reset_mcp_service():
    """重置MCP服务实例（用于测试）"""
    global _mcp_service
    _mcp_service = None


# 注册所有工具（工具函数在各自模块内定义并注册到 mcp_server）
register_auth(mcp_server)
register_project(mcp_server)
register_tasks(mcp_server)
register_sop(mcp_server)
register_testing(mcp_server)


def create_server():
    """创建并返回MCP服务器实例"""
    return mcp_server


# 注意：API连接检查会在服务器启动后进行
if __name__ == "__main__":
    import sys

    print("Starting MCP server...", file=sys.stderr)
    print(f"API URL: {API_BASE_URL}", file=sys.stderr)
    project_path = os.environ.get("SUPERVISOR_PROJECT_PATH", os.getcwd())
    print(f"Project Path: {project_path}", file=sys.stderr)
    print(
        f".supervisor directory will be created at: {project_path}/.supervisor",
        file=sys.stderr,
    )
    _logger.info("MCP server starting", extra={"api_url": API_BASE_URL, "project_path": project_path})

    if "--http" in sys.argv:
        mcp_server.run(transport="http", host="0.0.0.0", port=8080, path="/mcp")
    else:
        mcp_server.run()
