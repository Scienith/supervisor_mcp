"""
Scienith Supervisor MCP Service 配置管理
"""
import os
from typing import Optional
from dotenv import load_dotenv


class Config:
    """全局配置管理类"""
    
    _instance: Optional["Config"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._api_url = None
        self._project_path = None
    
    @property
    def api_url(self) -> str:
        """获取API服务器地址"""
        if self._api_url is None:
            # 首先检查环境变量
            api_url = os.getenv("SUPERVISOR_API_URL")

            # 如果环境变量未设置，尝试加载MCP的.env文件
            if api_url is None:
                self._load_env_file()
                api_url = os.getenv("SUPERVISOR_API_URL")

            # 如果仍然没有，使用默认值
            if api_url is None:
                api_url = "http://localhost:8000/api/v1"
                print("Warning: SUPERVISOR_API_URL not configured, using default: http://localhost:8000/api/v1")

            self._api_url = api_url
        return self._api_url
    
    @api_url.setter
    def api_url(self, value: str):
        """设置API服务器地址（仅用于测试）"""
        self._api_url = value
    
    @property
    def project_path(self) -> str:
        """获取项目基础路径"""
        if self._project_path is None:
            self._project_path = os.getenv("SUPERVISOR_PROJECT_PATH", os.getcwd())
        return self._project_path
    
    @project_path.setter
    def project_path(self, value: str):
        """设置项目基础路径（仅用于测试）"""
        self._project_path = value
    
    def _load_env_file(self):
        """加载MCP服务自己的.env文件"""
        # 获取MCP服务所在目录（src目录的父目录）
        mcp_dir = os.path.dirname(os.path.abspath(__file__))
        env_file_path = os.path.join(mcp_dir, '..', '.env')
        env_file_path = os.path.abspath(env_file_path)

        # 检查.env文件是否存在
        if not os.path.exists(env_file_path):
            # 如果MCP的.env不存在，使用默认值而不是失败
            print(f"Warning: MCP .env file not found at {env_file_path}, using defaults")
            return

        # 加载MCP的.env文件
        load_dotenv(env_file_path)

        # 验证必需的配置是否存在（更宽松的处理）
        if not os.getenv("SUPERVISOR_API_URL"):
            # 设置默认值
            os.environ["SUPERVISOR_API_URL"] = "http://localhost:8000/api/v1"
            print("Warning: SUPERVISOR_API_URL not found in .env file, using default: http://localhost:8000/api/v1")
    
    def reset(self):
        """重置配置（仅用于测试）"""
        self._api_url = None
        self._project_path = None


config = Config()