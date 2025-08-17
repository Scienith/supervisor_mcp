"""
MCP会话管理器
"""
from typing import Optional, Dict, Any
from file_manager import FileManager


class SessionManager:
    """MCP会话管理器"""
    
    def __init__(self, file_manager: Optional[FileManager] = None):
        self.current_user_token: Optional[str] = None
        self.current_user_id: Optional[str] = None
        self.current_username: Optional[str] = None
        self.file_manager = file_manager or FileManager()
        
        # 尝试从本地恢复用户会话
        self._restore_session()
    
    def login(self, user_id: str, token: str, username: str = None) -> None:
        """设置登录会话并保存到本地"""
        self.current_user_id = user_id
        self.current_user_token = token
        self.current_username = username
        
        # 保存到本地文件
        user_info = {
            "user_id": user_id,
            "access_token": token
        }
        if username:
            user_info["username"] = username
            
        self.file_manager.save_user_info(user_info)
    
    def logout(self) -> None:
        """清除登录会话和本地文件"""
        self.current_user_id = None
        self.current_user_token = None
        self.current_username = None
        
        # 删除本地用户信息文件
        user_file = self.file_manager.supervisor_dir / "user.json"
        if user_file.exists():
            user_file.unlink()
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.current_user_token is not None and self.current_user_id is not None
    
    def get_headers(self) -> Dict[str, str]:
        """获取API请求认证头"""
        headers = {}
        if self.current_user_token:
            headers['Authorization'] = f'Token {self.current_user_token}'
        return headers
    
    def _restore_session(self) -> None:
        """从本地文件恢复用户会话"""
        try:
            user_info = self.file_manager.read_user_info()
            self.current_user_id = user_info.get("user_id")
            self.current_user_token = user_info.get("access_token")
            self.current_username = user_info.get("username")
        except FileNotFoundError:
            # 用户信息文件不存在，保持未登录状态
            pass
    
    def get_current_user_info(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息"""
        if not self.is_authenticated():
            return None
            
        return {
            "user_id": self.current_user_id,
            "username": self.current_username,
            "access_token": self.current_user_token
        }