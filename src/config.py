"""
Scienith Supervisor MCP Service 配置管理
"""
import os
from typing import Optional


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
    
    def reset(self):
        """重置配置（仅用于测试）"""
        self._api_url = None
        self._project_path = None


config = Config()