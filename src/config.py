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
            
            # 如果环境变量未设置，尝试加载.env文件
            if api_url is None:
                self._load_env_file()
                api_url = os.getenv("SUPERVISOR_API_URL")
                
            if api_url is None:
                raise ValueError("SUPERVISOR_API_URL environment variable is required but not set")
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
        """加载.env文件"""
        env_file_path = os.path.join(os.getcwd(), '.env')
        
        # 检查.env文件是否存在
        if not os.path.exists(env_file_path):
            raise FileNotFoundError(f".env file not found at {env_file_path}")
        
        # 加载.env文件
        load_dotenv(env_file_path)
        
        # 验证必需的配置是否存在
        if not os.getenv("SUPERVISOR_API_URL"):
            raise ValueError("SUPERVISOR_API_URL not found in .env file")
    
    def reset(self):
        """重置配置（仅用于测试）"""
        self._api_url = None
        self._project_path = None


config = Config()