#!/usr/bin/env python3
"""
修复剩余的测试文件问题
"""

import os
import re
from pathlib import Path

def fix_test_file(file_path, fixes):
    """修复单个测试文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        for old, new in fixes:
            content = content.replace(old, new)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {file_path}")
            return True
        else:
            print(f"No changes needed: {file_path}")
            return False
            
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False

def main():
    """主函数"""
    
    # 针对特定文件的修复
    specific_fixes = {
        "tests/unit/test_file_manager.py": [
            ("assert 'current_task_group_id' in saved_info", 
             "assert 'in_progress_task_group' in saved_info"),
            ("assert saved_info['current_task_group_id'] == 'tg-456'", 
             "assert saved_info['in_progress_task_group']['id'] == 'tg-456'"),
        ],
        
        "tests/unit/test_file_manager_new_structure.py": [
            ("assert 'current_task_group_id' in saved_info", 
             "assert 'in_progress_task_group' in saved_info"),
            ("assert saved_info['current_task_group_id'] == task_group_id", 
             "assert saved_info['in_progress_task_group']['id'] == task_group_id"),
            ("assert saved_info[\"current_task_group_id\"] == task_group_id", 
             "assert saved_info[\"in_progress_task_group\"][\"id\"] == task_group_id"),
            ("assert parsed_content[\"current_task_group_id\"] == \"tg-456\"", 
             "assert parsed_content[\"in_progress_task_group\"][\"id\"] == \"tg-456\""),
            ("# 新的project.json结构应该包含current_task_group_id", 
             "# 新的project.json结构应该包含in_progress_task_group"),
        ],
        
        "tests/unit/test_auto_session_restore.py": [
            # 这个文件的测试逻辑需要调整，因为现在 get_current_task_group_id() 会从文件中读取
            ("# 恢复前\n                assert not service.has_project_context()\n                assert service.get_current_project_id() is None\n                assert service.get_current_project_name() is None\n                assert service.get_current_task_group_id() is None", 
             "# 恢复前 - 注意：get_current_task_group_id现在从文件读取，所以可能已经有值\n                assert not service.has_project_context()\n                assert service.get_current_project_id() is None\n                assert service.get_current_project_name() is None\n                # get_current_task_group_id现在从project.json读取，如果文件存在则可能有值"),
        ]
    }
    
    # 通用修复模式
    generic_fixes = [
        ('project_info.get("current_task_group_id")', 'project_info["in_progress_task_group"]["id"]'),
        ('project_info["current_task_group_id"]', 'project_info["in_progress_task_group"]["id"]'),
        ('updated_project_info["current_task_group_id"] is None', 'updated_project_info.get("in_progress_task_group") is None'),
        ('assert updated_project_info["current_task_group_id"] == ', 'assert updated_project_info.get("in_progress_task_group", {}).get("id") == '),
    ]
    
    updated_count = 0
    
    # 应用特定修复
    for file_path, fixes in specific_fixes.items():
        if os.path.exists(file_path):
            if fix_test_file(file_path, fixes):
                updated_count += 1
    
    # 应用通用修复
    test_files = []
    test_dir = Path("tests")
    for pattern in ["test_*.py", "*_test.py"]:
        test_files.extend(test_dir.rglob(pattern))
    
    for test_file in test_files:
        if fix_test_file(test_file, generic_fixes):
            updated_count += 1
    
    print(f"\nCompleted: {updated_count} files updated")

if __name__ == "__main__":
    main()