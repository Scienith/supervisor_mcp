"""
契约测试配置文件

提供契约测试的全局配置、fixture和工具
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock


# 测试标记配置
pytest_plugins = []


def pytest_configure(config):
    """pytest配置钩子"""
    # 注册自定义标记
    config.addinivalue_line(
        "markers", "contract: 契约测试，验证FAKE/REAL实现的行为一致性"
    )
    config.addinivalue_line(
        "markers", "maturity_stub: 针对STUB状态的测试（通常skip）"
    )
    config.addinivalue_line(
        "markers", "maturity_fake: 针对FAKE状态的测试"
    )
    config.addinivalue_line(
        "markers", "maturity_real: 针对REAL状态的测试"
    )
    config.addinivalue_line(
        "markers", "round_trip: 往返一致性测试"
    )
    config.addinivalue_line(
        "markers", "invariant: 不变量测试"
    )
    config.addinivalue_line(
        "markers", "boundary: 边界条件测试"
    )
    config.addinivalue_line(
        "markers", "error_handling: 错误处理测试"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试收集结果"""
    # 为契约测试目录下的所有测试自动添加contract标记
    for item in items:
        if "contracts" in str(item.fspath):
            item.add_marker(pytest.mark.contract)


# 通用fixture
@pytest.fixture
def valid_test_data():
    """提供有效的测试数据"""
    return {
        "string_input": "test_string",
        "integer_input": 42,
        "list_input": [1, 2, 3],
        "dict_input": {"key": "value"},
        "boolean_input": True,
        "optional_input": None
    }


@pytest.fixture
def invalid_test_data():
    """提供无效的测试数据"""
    return {
        "empty_string": "",
        "negative_integer": -1,
        "empty_list": [],
        "empty_dict": {},
        "null_value": None,
        "wrong_type": "should_be_integer"
    }


@pytest.fixture
def boundary_test_data():
    """提供边界值测试数据"""
    return {
        "min_integer": 0,
        "max_integer": 2**31 - 1,
        "min_string": "a",
        "max_string": "x" * 1000,
        "single_item_list": [1],
        "large_list": list(range(1000))
    }


@pytest.fixture
def mock_external_dependencies():
    """模拟外部依赖"""
    return {
        "database": Mock(),
        "api_client": Mock(),
        "cache": Mock(),
        "logger": Mock(),
        "config": Mock()
    }


@pytest.fixture
def error_scenarios():
    """错误场景数据"""
    return {
        "validation_error": {
            "input": {"invalid": "data"},
            "expected_error": ValueError,
            "error_message": "Invalid input data"
        },
        "not_found_error": {
            "input": {"id": "non_existent"},
            "expected_error": KeyError,
            "error_message": "Resource not found"
        },
        "permission_error": {
            "input": {"user": "unauthorized"},
            "expected_error": PermissionError,
            "error_message": "Access denied"
        }
    }


@pytest.fixture
def performance_constraints():
    """性能约束配置"""
    return {
        "max_execution_time": 1.0,  # 秒
        "max_memory_usage": 100,    # MB
        "max_api_calls": 10,        # 最大API调用次数
        "max_db_queries": 5         # 最大数据库查询次数
    }


# 成熟度相关的fixture
@pytest.fixture
def maturity_checker():
    """成熟度检查器"""
    def check_maturity(contract_unit, expected_maturity=None):
        """检查契约单元的成熟度"""
        impl_info = getattr(contract_unit, '__impl__', {})
        actual_maturity = impl_info.get('maturity', 'STUB')
        
        if expected_maturity and actual_maturity != expected_maturity:
            pytest.skip(f"Contract maturity {actual_maturity} != expected {expected_maturity}")
        
        return actual_maturity
    
    return check_maturity


@pytest.fixture
def contract_inspector():
    """契约单元检查器"""
    def inspect_contract(contract_unit):
        """检查契约单元的基本信息"""
        impl_info = getattr(contract_unit, '__impl__', {})
        
        return {
            "maturity": impl_info.get('maturity', 'UNKNOWN'),
            "notes": impl_info.get('notes', ''),
            "has_docstring": bool(contract_unit.__doc__),
            "method_count": len([attr for attr in dir(contract_unit) 
                               if callable(getattr(contract_unit, attr)) 
                               and not attr.startswith('_')]),
            "class_name": contract_unit.__class__.__name__
        }
    
    return inspect_contract


# 测试数据生成器
@pytest.fixture
def test_data_generator():
    """测试数据生成器"""
    class TestDataGenerator:
        @staticmethod
        def generate_valid_samples(count: int = 5) -> List[Dict[str, Any]]:
            """生成有效样本数据"""
            return [
                {"id": i, "name": f"test_{i}", "active": True}
                for i in range(count)
            ]
        
        @staticmethod
        def generate_invalid_samples() -> List[Dict[str, Any]]:
            """生成无效样本数据"""
            return [
                {},  # 空对象
                {"id": None},  # 缺少必需字段
                {"id": -1, "name": ""},  # 无效值
                {"id": "not_a_number"},  # 类型错误
            ]
        
        @staticmethod
        def generate_edge_cases() -> List[Dict[str, Any]]:
            """生成边界情况数据"""
            return [
                {"id": 0, "name": "a"},  # 最小值
                {"id": 2**31-1, "name": "x"*255},  # 最大值
                {"id": 1, "name": "test", "extra": "field"},  # 额外字段
            ]
    
    return TestDataGenerator()


# 断言辅助工具
@pytest.fixture
def assertion_helpers():
    """断言辅助工具"""
    class AssertionHelpers:
        @staticmethod
        def assert_contract_compliance(result, expected_type, required_fields=None):
            """断言结果符合契约"""
            assert isinstance(result, expected_type), f"Expected {expected_type}, got {type(result)}"
            
            if required_fields:
                for field in required_fields:
                    assert hasattr(result, field) or field in result, f"Missing required field: {field}"
        
        @staticmethod
        def assert_error_with_message(func, expected_error, expected_message_part, *args, **kwargs):
            """断言函数抛出包含特定消息的异常"""
            with pytest.raises(expected_error) as exc_info:
                func(*args, **kwargs)
            
            assert expected_message_part in str(exc_info.value), \
                f"Expected error message to contain '{expected_message_part}', got '{str(exc_info.value)}'"
        
        @staticmethod
        def assert_performance(func, max_time, *args, **kwargs):
            """断言函数执行性能"""
            import time
            start = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start
            
            assert duration <= max_time, f"Function took {duration:.3f}s, expected <= {max_time}s"
            return result
    
    return AssertionHelpers()


# 清理和资源管理
@pytest.fixture(autouse=True)
def cleanup_resources():
    """自动清理资源"""
    # 测试前准备
    yield
    # 测试后清理
    # 这里可以添加通用的清理逻辑


# 参数化测试辅助
@pytest.fixture
def parametrize_helper():
    """参数化测试辅助工具"""
    def create_test_cases(test_data_dict):
        """从测试数据字典创建参数化测试用例"""
        return pytest.mark.parametrize(
            "test_input,expected", 
            list(test_data_dict.items())
        )
    
    return create_test_cases


# 契约测试专用的模拟工具
@pytest.fixture
def contract_mocks():
    """契约测试专用的模拟对象"""
    class ContractMocks:
        def __init__(self):
            self.external_service = Mock()
            self.database = Mock() 
            self.cache = Mock()
            self.logger = Mock()
            
        def setup_success_scenario(self):
            """设置成功场景的模拟"""
            self.external_service.call.return_value = {"status": "success"}
            self.database.query.return_value = [{"id": 1, "name": "test"}]
            self.cache.get.return_value = None
            
        def setup_error_scenario(self):
            """设置错误场景的模拟"""
            self.external_service.call.side_effect = ConnectionError("Network error")
            self.database.query.side_effect = Exception("Database error")
            
        def verify_interactions(self):
            """验证模拟对象的交互"""
            assert self.external_service.call.called
            assert self.database.query.called
    
    return ContractMocks()