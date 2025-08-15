"""
简化的pytest配置文件 - 用于MCP独立测试
"""
import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Mock环境变量避免测试依赖真实配置
os.environ.setdefault("SUPERVISOR_API_URL", "http://test.example.com/api/v1")

# 添加项目源代码目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

@pytest.fixture
def temp_project_dir():
    """创建临时项目目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def mock_api_client():
    """创建模拟的API客户端"""
    from unittest.mock import AsyncMock
    
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    return client

@pytest.fixture
def file_manager(temp_project_dir):
    """创建FileManager实例"""
    from file_manager import FileManager
    return FileManager(base_path=temp_project_dir)