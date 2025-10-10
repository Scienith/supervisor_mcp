# MCP 工具参数参考文档

本文档列出了所有 MCP 工具及其接受的参数。

## 1. 认证相关工具

### `ping`
**用途**: 快速检查 MCP 服务器状态
**参数**: 无

### `login` (已废弃)
**用途**: 用户登录（推荐使用 login_with_project）
**参数**:
- `username` (str): 用户名
- `password` (str): 密码
- `working_directory` (str): 工作目录

### `login_with_project` ⭐ 推荐
**用途**: 一站式登录并初始化项目工作区（从项目 .env 文件读取认证信息）
**参数**:
- `working_directory` (str): 项目工作目录（必填）

**注意**: 需要在指定目录创建 `.env` 文件，包含：
- SUPERVISOR_USERNAME
- SUPERVISOR_PASSWORD
- SUPERVISOR_PROJECT_ID

### `logout`
**用途**: 用户登出
**参数**: 无

## 2. 项目管理工具

### `create_project`
**用途**: 创建新项目
**参数**:
- `project_name` (str): 项目名称
- `description` (str, 可选): 项目描述
- `sop_template_id` (str, 可选): SOP 模板 ID
- `custom_attributes` (dict, 可选): 自定义属性

### `setup_workspace` (已废弃)
**用途**: 初始化项目工作区（推荐使用 login_with_project）
**参数**:
- `project_id` (str): 项目 ID
- `working_directory` (str): 工作目录

### `health`
**用途**: 检查 MCP 服务器的健康状态
**参数**: 无

## 3. 任务执行工具

### `next`
**用途**: 获取下一个待执行的任务阶段
**参数**: 无

### `report`
**用途**: 提交已完成任务阶段的执行结果
**参数**:
- `task_phase_id` (str): 任务阶段 ID（从 next 获得）
- `result_data` (dict): 任务执行结果数据
  - 对于 VALIDATION 任务：必须包含 `{"validation_result": {"passed": true/false}}`
  - 其他任务：请传空字典 `{}`（或省略该参数）

**注意**:
- 在调用前必须先向 Supervisor 询问并确认当前阶段允许上报；不得跳过询问直接调用
- 不需要 `summary` 参数


### `pre_analyze`
**用途**: 分析用户需求并映射到合适的 SOP 步骤
**参数**:
- `user_requirement` (str): 用户需求描述

## 4. 任务组管理工具

### `add_task`
**用途**: 创建新的任务组
**参数**:
- `title` (str): 任务标题
- `goal` (str): 任务目标描述
- `sop_step_identifier` (str): SOP 步骤标识符

### `cancel_task`
**用途**: 取消指定的任务组
**参数**:
- `task_id` (str): 要取消的任务组 ID
- `cancellation_reason` (str, 可选): 取消原因

### `finish_task` 🆕
**用途**: 直接将任务标记为完成状态（跳过剩余阶段）
**参数**:
- `task_id` (str): 要完成的任务 ID

**注意**:
- 只要 IMPLEMENTING 阶段已经完成即可直接完成任务，后续未开始的阶段会被自动取消
- 若后端拒绝操作，工具会返回明确的失败原因和后续建议

### `start`
**用途**: 启动指定的任务组
**参数**:
- `task_id` (str): 要启动的任务组 ID

### `suspend`
**用途**: 暂存当前正在执行的任务
**参数**: 无

### `continue_suspended`
**用途**: 继续执行之前暂存的任务
**参数**:
- `task_id` (str): 要继续的任务组 ID

## 5. SOP 配置工具

### `update_step_rules`
**用途**: 更新 SOP 步骤的规则（基于复盘改进）
**参数**:
- `stage` (str): SOP 阶段（如 "exploration", "base", "growth"）
- `step_identifier` (str): 步骤标识符

**注意**: 从本地文件读取规则内容

### `update_output_template`
**用途**: 更新 SOP 步骤输出的模板内容
**参数**:
- `stage` (str): SOP 阶段
- `step_identifier` (str): 步骤标识符
- `output_name` (str): 输出名称

**注意**: 从本地文件读取模板内容

## 重要说明

### 关于 `summary` 参数
**当前所有工具都不需要 `summary` 参数**。后端 API 也没有要求这个字段。

### 认证要求
除了以下工具外，其他所有工具都需要先登录：
- `ping`
- `health`
- `login`
- `login_with_project`

### 项目上下文
大多数工具需要项目上下文（通过 `login_with_project` 或 `setup_workspace` 建立）。

### 工具使用流程
1. 使用 `login_with_project` 登录并初始化项目
2. 使用 `next` 获取任务
3. 执行任务
4. 使用 `report` 提交结果
5. 重复步骤 2-4 直到所有任务完成

### 任务跳过机制
有两种方式可以跳过剩余任务阶段：
1. 使用 `finish_task` 工具直接完成任务
2. 使用 `cancel_task` 取消任务（标记为取消而非完成）
