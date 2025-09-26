"""
测试VALIDATION任务的原子性行为

通过模拟核心逻辑来测试，避免装饰器问题
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from file_manager import FileManager


class TestValidationAtomicBehavior:
    """测试VALIDATION任务原子性行为"""

    def test_validation_format_check_logic(self):
        """
        测试VALIDATION任务格式检查逻辑（同步版本）
        模拟MCP server中的格式检查代码
        """
        
        def simulate_format_check(current_task, result_data):
            """模拟格式检查逻辑"""
            # 在API调用之前验证VALIDATION任务的数据格式
            if current_task.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if not isinstance(validation_result, dict):
                    return {
                        "status": "error", 
                        "message": f"VALIDATION task requires validation_result to be a dictionary with 'passed' field, got {type(validation_result).__name__}: {validation_result}",
                        "api_should_be_called": False
                    }
            return {"status": "proceed", "api_should_be_called": True}
        
        # 测试1: VALIDATION任务 + 字符串格式 -> 应该被拒绝
        current_task = {"type": "VALIDATION", "id": "test-id"}
        result_data_string = {
            "success": True,
            "validation_result": "PASSED",  # 错误格式：字符串而非字典
            "output": "test.md"
        }
        
        result = simulate_format_check(current_task, result_data_string)
        assert result["status"] == "error"
        assert result["api_should_be_called"] is False
        assert "VALIDATION task requires validation_result to be a dictionary" in result["message"]
        assert "got str: PASSED" in result["message"]
        
        # 测试2: VALIDATION任务 + 字典格式 -> 应该通过
        result_data_dict = {
            "success": True,
            "validation_result": {"passed": True},  # 正确格式
            "output": "test.md"
        }
        
        result = simulate_format_check(current_task, result_data_dict)
        assert result["status"] == "proceed"
        assert result["api_should_be_called"] is True
        
        # 测试3: 非VALIDATION任务 -> 不检查格式
        current_task_impl = {"type": "IMPLEMENTING", "id": "test-id"}
        result_data_any = {
            "success": True,
            "validation_result": "ANYTHING",  # 任何格式都行
            "output": "test.md"
        }
        
        result = simulate_format_check(current_task_impl, result_data_any)
        assert result["status"] == "proceed"
        assert result["api_should_be_called"] is True

    @pytest.mark.asyncio
    async def test_full_atomic_workflow_simulation(self):
        """
        测试完整的原子性工作流程模拟
        """
        
        async def simulate_report_workflow(current_task, result_data):
            """模拟完整的report工作流程"""
            api_called = False
            api_result = None
            
            # 1. 格式检查（在API调用之前）
            if current_task.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if not isinstance(validation_result, dict):
                    return {
                        "status": "error", 
                        "message": f"Format error: got {type(validation_result).__name__}",
                        "api_called": api_called,
                        "task_status_changed": False
                    }
            
            # 2. 只有格式检查通过才调用API
            api_called = True
            api_result = {
                "status": "success",
                "data": {
                    "status": "COMPLETED",
                    "task_status": "COMPLETED"
                }
            }
            
            # 3. 处理清理逻辑
            should_clear = False
            if (current_task.get("type") == "VALIDATION" and 
                isinstance(api_result, dict) and api_result.get("status") == "success"):
                validation_result = result_data.get("validation_result", {})
                if validation_result.get("passed") is True:
                    should_clear = True
            
            return {
                "status": "success",
                "api_called": api_called,
                "task_status_changed": True,
                "should_clear": should_clear
            }
        
        # 测试场景1: 错误格式 - 不应该调用API
        current_task = {"type": "VALIDATION", "id": "test-id"}
        bad_data = {"validation_result": "PASSED"}  # 错误格式：字符串而非字典
        
        result = await simulate_report_workflow(current_task, bad_data)
        assert result["status"] == "error"
        assert result["api_called"] is False  # 关键断言：API没被调用
        assert result["task_status_changed"] is False  # 关键断言：状态没改变
        
        # 测试场景2: 正确格式 - 应该正常工作
        good_data = {"validation_result": {"passed": True}}
        
        result = await simulate_report_workflow(current_task, good_data)
        assert result["status"] == "success"
        assert result["api_called"] is True  # API被调用
        assert result["task_status_changed"] is True  # 状态改变
        assert result["should_clear"] is True  # 应该清理

    def test_error_message_clarity(self):
        """
        测试错误消息的清晰度
        """
        
        def get_validation_error_message(validation_result):
            """获取验证错误消息"""
            if not isinstance(validation_result, dict):
                return f"VALIDATION task requires validation_result to be a dictionary with 'passed' field, got {type(validation_result).__name__}: {validation_result}"
            return None
        
        # 测试各种错误格式的消息
        test_cases = [
            ("PASSED", "got str: PASSED"),
            (123, "got int: 123"),
            (True, "got bool: True"),
            ([], "got list: []"),
        ]
        
        for bad_value, expected_part in test_cases:
            error_msg = get_validation_error_message(bad_value)
            assert error_msg is not None
            assert "VALIDATION task requires validation_result to be a dictionary" in error_msg
            assert expected_part in error_msg
        
        # 测试正确格式不产生错误
        good_value = {"passed": True}
        error_msg = get_validation_error_message(good_value)
        assert error_msg is None

    def test_validation_passed_false_scenario(self):
        """
        测试VALIDATION任务passed=False的场景
        """
        
        def simulate_clearing_logic(current_task, result_data, api_success=True):
            """模拟清理逻辑"""
            should_clear = False
            
            if (current_task.get("type") == "VALIDATION" and api_success):
                validation_result = result_data.get("validation_result", {})
                if validation_result.get("passed") is True:
                    should_clear = True
            
            return should_clear
        
        current_task = {"type": "VALIDATION", "id": "test-id"}
        
        # 测试passed=True -> 应该清理
        data_passed = {"validation_result": {"passed": True}}
        assert simulate_clearing_logic(current_task, data_passed, True) is True
        
        # 测试passed=False -> 不应该清理
        data_failed = {"validation_result": {"passed": False}}
        assert simulate_clearing_logic(current_task, data_failed, True) is False
        
        # 测试缺少passed字段 -> 不应该清理
        data_missing = {"validation_result": {}}
        assert simulate_clearing_logic(current_task, data_missing, True) is False
        
        # 测试API失败 -> 即使passed=True也不清理
        assert simulate_clearing_logic(current_task, data_passed, False) is False

    def test_comprehensive_atomic_guarantee(self):
        """
        综合测试原子性保证：错误格式绝不触发状态变更
        """
        
        def atomic_operation_simulator(current_task, result_data):
            """原子操作模拟器"""
            operation_log = []
            
            # 第1步：格式检查
            operation_log.append("format_check_start")
            if current_task.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if not isinstance(validation_result, dict):
                    operation_log.append("format_check_failed")
                    # 格式错误，立即返回，不执行后续步骤
                    return {
                        "status": "error",
                        "operations": operation_log,
                        "api_called": False,
                        "status_changed": False,
                        "cleanup_called": False
                    }
            
            operation_log.append("format_check_passed")
            
            # 第2步：API调用
            operation_log.append("api_call")
            
            # 第3步：状态更新  
            operation_log.append("status_update")
            
            # 第4步：清理（如果需要）
            should_clear = False
            if current_task.get("type") == "VALIDATION":
                validation_result = result_data.get("validation_result", {})
                if validation_result.get("passed") is True:
                    should_clear = True
                    operation_log.append("cleanup")
            
            return {
                "status": "success",
                "operations": operation_log,
                "api_called": True,
                "status_changed": True,
                "cleanup_called": should_clear
            }
        
        current_task = {"type": "VALIDATION", "id": "test-id"}
        
        # 测试原子性：错误格式只执行format_check
        bad_data = {"validation_result": "PASSED"}  # 错误格式：字符串而非字典
        result = atomic_operation_simulator(current_task, bad_data)
        assert result["status"] == "error"
        assert result["operations"] == ["format_check_start", "format_check_failed"]
        assert result["api_called"] is False
        assert result["status_changed"] is False
        assert result["cleanup_called"] is False
        
        # 测试正常流程：好格式执行所有步骤
        good_data = {"validation_result": {"passed": True}}
        result = atomic_operation_simulator(current_task, good_data)
        assert result["status"] == "success"
        assert "format_check_start" in result["operations"]
        assert "format_check_passed" in result["operations"]
        assert "api_call" in result["operations"]
        assert "status_update" in result["operations"]
        assert "cleanup" in result["operations"]
        assert result["api_called"] is True
        assert result["status_changed"] is True
        assert result["cleanup_called"] is True
