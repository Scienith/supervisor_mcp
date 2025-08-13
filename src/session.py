"""
MCP会话管理器
"""
from typing import Optional, Dict, Any


class SessionManager:
    """MCP会话管理器"""
    
    def __init__(self):
        self.current_user_token: Optional[str] = None
        self.current_user_id: Optional[str] = None
    
    def login(self, user_id: str, token: str) -> None:
        """设置登录会话"""
        self.current_user_id = user_id
        self.current_user_token = token
    
    def logout(self) -> None:
        """清除登录会话"""
        self.current_user_id = None
        self.current_user_token = None
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.current_user_token is not None and self.current_user_id is not None
    
    def get_headers(self) -> Dict[str, str]:
        """获取API请求认证头"""
        headers = {}
        if self.current_user_token:
            headers['Authorization'] = f'Token {self.current_user_token}'
        return headers