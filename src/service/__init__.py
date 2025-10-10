"""
service 包：对外暴露 MCPService 及用于测试打桩的 get_api_client。
暂时保持原有导入路径稳定：from service import MCPService
测试兼容：允许 patch('service.get_api_client')。
"""

# 为测试兼容保留 get_api_client 的包级导出（原先在模块级可被 patch）
from server import get_api_client  # noqa: F401
from .mcp_service import MCPService

__all__ = [
    "MCPService",
    "get_api_client",
]
