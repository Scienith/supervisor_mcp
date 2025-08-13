"""
Scienith Supervisor MCP Service
独立的MCP服务，用于AI IDE与Supervisor系统的集成
"""
from server import mcp_server, create_server

__all__ = ['mcp_server', 'create_server']