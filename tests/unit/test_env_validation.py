"""
测试.env文件验证功能
"""
import os
import pytest
import tempfile
from unittest.mock import patch, mock_open
from config import Config


class TestEnvValidation:
    """测试环境变量和.env文件验证"""
    
    def setup_method(self):
        """每个测试前重置配置"""
        Config().reset()
        # 清除环境变量，确保测试.env文件加载
        if 'SUPERVISOR_API_URL' in os.environ:
            del os.environ['SUPERVISOR_API_URL']
    
    def test_missing_env_file_should_use_default(self):
        """测试：当.env文件不存在时应该使用默认值"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 切换到临时目录，确保没有.env文件
            with patch('os.getcwd', return_value=temp_dir):
                with patch('os.path.exists') as mock_exists:
                    mock_exists.return_value = False  # .env文件不存在

                    # 应该使用默认值而不是抛出错误
                    api_url = Config().api_url
                    assert api_url == "http://localhost:8000/api/v1"
    
    def test_empty_env_file_should_use_default(self):
        """测试：当.env文件为空时应该使用默认值"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('os.getcwd', return_value=temp_dir):
                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', mock_open(read_data="")):
                        # 空的.env文件应该使用默认值
                        api_url = Config().api_url
                        assert api_url == "http://localhost:8000/api/v1"
    
    def test_env_file_without_api_url_should_use_default(self):
        """测试：当.env文件中没有SUPERVISOR_API_URL时应该使用默认值"""
        env_content = """
        # Some other config
        OTHER_CONFIG=value
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('os.getcwd', return_value=temp_dir):
                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', mock_open(read_data=env_content)):
                        # 没有API_URL应该使用默认值
                        api_url = Config().api_url
                        assert api_url == "http://localhost:8000/api/v1"
    
    def test_valid_env_file_should_load_correctly(self):
        """测试：有效的.env文件应该正确加载"""
        # 需要模拟MCP服务的目录结构
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建src目录来模拟MCP的结构
            src_dir = os.path.join(temp_dir, 'src')
            os.makedirs(src_dir, exist_ok=True)

            # 创建.env文件在MCP根目录
            env_path = os.path.join(temp_dir, '.env')
            with open(env_path, 'w') as f:
                f.write("SUPERVISOR_API_URL=http://8.133.22.242:8000/api/v1\n")

            # 模拟config.py在src目录下
            with patch('os.path.dirname') as mock_dirname:
                with patch('os.path.abspath') as mock_abspath:
                    # 设置返回值
                    config_path = os.path.join(src_dir, 'config.py')

                    # abspath会被调用两次：一次是__file__，一次是规范化路径
                    mock_abspath.side_effect = [
                        config_path,  # 第一次调用：os.path.abspath(__file__)
                        env_path      # 第二次调用：os.path.abspath(计算出的env路径)
                    ]
                    mock_dirname.return_value = src_dir

                    Config().reset()  # 重置以重新加载
                    api_url = Config().api_url
                    assert api_url == "http://8.133.22.242:8000/api/v1"
    
    def test_environment_variable_takes_precedence_over_env_file(self):
        """测试：环境变量应该优先于.env文件"""
        env_content = """SUPERVISOR_API_URL=http://from-env-file:8000/api/v1
"""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建真实的.env文件
            env_file_path = os.path.join(temp_dir, '.env')
            with open(env_file_path, 'w') as f:
                f.write(env_content)
            
            with patch('os.getcwd', return_value=temp_dir):
                with patch.dict('os.environ', {'SUPERVISOR_API_URL': 'http://from-env-var:8000/api/v1'}):
                    config = Config()
                    assert config.api_url == "http://from-env-var:8000/api/v1"