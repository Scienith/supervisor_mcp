"""
MCP服务器入口
直接运行server.py中的MCP服务器
"""

if __name__ == "__main__":
    import sys
    import os
    import logging
    
    # 设置环境变量以确保快速启动
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    
    # 抑制FastMCP的详细输出，只显示错误
    if "--verbose" not in sys.argv and "--debug" not in sys.argv:
        # 完全抑制FastMCP的横幅和日志输出
        logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
        logging.getLogger("anyio").setLevel(logging.CRITICAL)
        logging.getLogger("mcp").setLevel(logging.CRITICAL)
        logging.getLogger().setLevel(logging.CRITICAL)
        
        # 重定向stderr以抑制FastMCP横幅
        import io
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()
    
    # 导入服务器（延迟导入以加快启动）
    from .server import mcp_server
    
    if "--http" in sys.argv:
        # HTTP模式 - 用于远程访问
        mcp_server.run(
            transport="http",
            host="0.0.0.0",
            port=8080,
            path="/mcp"
        )
    else:
        # 默认STDIO模式 - 用于本地Claude Code
        # 抑制启动横幅以避免干扰Claude Code
        try:
            mcp_server.run()
        except KeyboardInterrupt:
            # 优雅地处理中断
            sys.exit(0)
        finally:
            # 恢复stderr（如果被重定向了）
            if "--verbose" not in sys.argv and "--debug" not in sys.argv:
                if 'original_stderr' in locals():
                    sys.stderr = original_stderr