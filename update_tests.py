#!/usr/bin/env python3
"""
批量更新测试文件中的 current_task_group_id 引用
将 current_task_group_id 替换为 in_progress_task_group 结构
"""

import os
import re
from pathlib import Path

def update_test_file(file_path):
    """更新单个测试文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 1. 更新简单的 current_task_group_id 赋值
        # "current_task_group_id": "value" -> 新结构
        def replace_assignment(match):
            value = match.group(1)
            if value == "None" or value == "null":
                return '"in_progress_task_group": None'
            else:
                return f'"in_progress_task_group": {{\n                "id": {value},\n                "title": "测试任务组",\n                "status": "IN_PROGRESS"\n            }}'
        
        # 匹配 "current_task_group_id": "value" 或 "current_task_group_id": None
        pattern = r'"current_task_group_id":\s*([^,\n}]+)'
        content = re.sub(pattern, replace_assignment, content)
        
        # 2. 更新 get/access 模式
        # project_info.get("current_task_group_id") -> project_info["in_progress_task_group"]["id"]
        content = re.sub(
            r'project_info\.get\("current_task_group_id"\)',
            'project_info["in_progress_task_group"]["id"]',
            content
        )
        
        # 3. 更新 assert 语句中的访问
        # assert service.get_current_task_group_id() == "value"
        # 这个保持不变，因为 get_current_task_group_id 方法已经更新了
        
        # 4. 更新直接访问模式
        # project_info["current_task_group_id"]
        content = re.sub(
            r'project_info\["current_task_group_id"\]',
            'project_info["in_progress_task_group"]["id"]',
            content
        )
        
        # 5. 更新带有 is None 检查的模式
        content = re.sub(
            r'updated_project_info\["current_task_group_id"\] is None',
            'updated_project_info.get("in_progress_task_group") is None',
            content
        )
        
        # 6. 更新等于比较的模式
        # updated_project_info["current_task_group_id"] == "value"
        def replace_comparison(match):
            value = match.group(1)
            return f'updated_project_info.get("in_progress_task_group", {{}}).get("id") == {value}'
            
        pattern = r'updated_project_info\["current_task_group_id"\] == ([^,\n\]]+)'
        content = re.sub(pattern, replace_comparison, content)
        
        # 只有内容发生变化才写入文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated: {file_path}")
            return True
        else:
            print(f"No changes needed: {file_path}")
            return False
            
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
        return False

def main():
    """主函数"""
    test_dir = Path("tests")
    
    # 找到所有测试文件
    test_files = []
    for pattern in ["test_*.py", "*_test.py"]:
        test_files.extend(test_dir.rglob(pattern))
    
    updated_count = 0
    total_count = len(test_files)
    
    print(f"Found {total_count} test files")
    print("Updating test files...")
    
    for test_file in test_files:
        if update_test_file(test_file):
            updated_count += 1
    
    print(f"\nCompleted: {updated_count}/{total_count} files updated")

if __name__ == "__main__":
    main()