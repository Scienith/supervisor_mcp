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
        # 项目上下文信息
        self.current_project_id: Optional[str] = None
        self.current_project_name: Optional[str] = None
        if file_manager is None:
            raise ValueError("FileManager instance is required")
        self.file_manager = file_manager
        
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
        # 清除项目上下文
        self.current_project_id = None
        self.current_project_name = None
        
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
        
        # 恢复项目上下文信息
        try:
            project_info = self.file_manager.read_project_info()
            self.current_project_id = project_info.get('project_id')
            self.current_project_name = project_info.get('project_name')
            
            if self.current_project_id:
                import sys
                print(f"Auto-restored project context: {self.current_project_name} (ID: {self.current_project_id})", 
                      file=sys.stderr)
        except FileNotFoundError:
            # 项目信息文件不存在，保持无项目状态
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
    
    # 项目上下文管理方法
    def get_current_project_id(self) -> Optional[str]:
        """获取当前项目ID（如果已恢复）"""
        return self.current_project_id
    
    def get_current_project_name(self) -> Optional[str]:
        """获取当前项目名称（如果已恢复）"""
        return self.current_project_name
    
    def has_project_context(self) -> bool:
        """检查是否有项目上下文"""
        return self.current_project_id is not None
    
    def set_project_context(self, project_id: str, project_name: str = None) -> None:
        """设置项目上下文"""
        self.current_project_id = project_id
        self.current_project_name = project_name