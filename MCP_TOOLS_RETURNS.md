# MCP 工具返回值参考文档

本文档详细列出了所有 MCP 工具的返回字段。

## 1. 认证相关工具

### `ping`
**返回字段**：
```json
{
  "status": "ok",
  "message": "MCP server is running",
  "timestamp": 1234567890.123,
  "server_name": "Scienith Supervisor MCP"
}
```

### `login` (已废弃)
**成功返回**：
```json
{
  "success": true,
  "user_id": "用户ID",
  "username": "用户名"
}
```
**失败返回**：
```json
{
  "success": false,
  "error_code": "AUTH_001",
  "message": "错误信息"
}
```

### `login_with_project` ⭐
**成功返回**：
```json
{
  "success": true,
  "user_id": "用户ID",
  "username": "用户名",
  "project": {
    "project_id": "项目ID",
    "project_name": "项目名称",
    "templates_downloaded": 5  // 下载的模板数量
  }
}
```
**失败返回**：
```json
{
  "success": false,
  "error_code": "错误代码",
  "message": "错误信息"
}
```

### `logout`
**成功返回**：
```json
{
  "success": true,
  "message": "成功登出"
}
```
**失败返回**：
```json
{
  "success": false,
  "message": "错误信息"
}
```

## 2. 项目管理工具

### `health`
**正常返回**：
```json
{
  "status": "healthy",
  "message": "All systems operational",
  "checks": {
    "api_connection": true,
    "authentication": true,
    "project_context": true,
    "api_url": "http://localhost:8000/api/v1"
  }
}
```
**部分失败返回**：
```json
{
  "status": "degraded",
  "message": "Some systems are not functioning properly",
  "checks": {
    "api_connection": false,
    "authentication": false,
    "project_context": true,
    "api_url": "http://localhost:8000/api/v1"
  }
}
```

### `create_project`
**成功返回**：
```json
{
  "status": "success",
  "project_id": "项目UUID",
  "project_name": "项目名称",
  "sop_steps_count": 10,
  "initial_tasks": 3,
  "message": "项目创建成功"
}
```
**失败返回**：
```json
{
  "status": "error",
  "error": "错误信息"
}
```

### `setup_workspace` (已废弃)
**成功返回**：
```json
{
  "success": true,
  "message": "工作区初始化成功",
  "project": {
    "project_id": "项目ID",
    "project_name": "项目名称"
  },
  "templates_downloaded": 5
}
```

## 3. 任务执行工具

### `next`
**有任务时返回**：
```json
{
  "status": "success",
  "task_phase": {
    "id": "任务阶段ID",
    "title": "任务标题",
    "type": "UNDERSTANDING|PLANNING|IMPLEMENTING|VALIDATION|FIXING|RETROSPECTIVE",
    "status": "任务状态",
    "task_id": "所属任务组ID",
    "order": 1,
    "description": "任务阶段详情已保存到本地文件：\n文件路径：supervisor_workspace/current_task/01_understanding_instructions.md\n请查看该文件获取完整的任务阶段说明和要求。"
  }
}
```
**无任务时返回**：
```json
{
  "status": "no_available_tasks",
  "message": "当前没有可执行的任务"
}
```
**验证错误返回**：
```json
{
  "status": "error",
  "error_code": "TASK_VALIDATION_ERROR",
  "error": "错误详情",
  "task_id": "相关任务ID"
}
```

### `report`
**成功返回**：
```json
{
  "status": "success",
  "data": {
    "id": "任务阶段ID",
    "title": "任务标题",
    "status": "COMPLETED",
    "result": "提交的结果数据"
  }
}
```
**失败返回**：
```json
{
  "error": "错误信息",
  "error_code": "VALIDATION_ERROR"
}
```

### `pre_analyze`
**成功返回**：
```json
{
  "status": "success",
  "analysis": {
    "user_requirement": "用户原始需求",
    "recommended_steps": [
      {
        "step_identifier": "SOP步骤标识",
        "step_name": "步骤名称",
        "relevance_score": 0.95,
        "reason": "推荐原因"
      }
    ],
    "suggested_task_title": "建议的任务标题",
    "suggested_task_goal": "建议的任务目标"
  }
}
```

## 4. 任务组管理工具

### `add_task`
**成功返回**：
```json
{
  "status": "success",
  "data": {
    "task_id": "新建任务组ID",
    "title": "任务标题",
    "goal": "任务目标",
    "sop_step_identifier": "SOP步骤标识",
    "status": "PENDING",
    "created_at": "2024-01-20T10:30:00Z"
  }
}
```
**失败返回**：
```json
{
  "status": "error",
  "message": "错误信息"
}
```

### `cancel_task`
**成功返回**：
```json
{
  "status": "success",
  "message": "任务组已成功取消: 任务标题",
  "cancelled_task": {
    "id": "任务ID",
    "title": "任务标题",
    "status": "CANCELLED",
    "cancelled_at": "2024-01-20T10:30:00Z",
    "cancellation_reason": "取消原因"
  },
  "auto_switched_to": {  // 如果自动切换到新任务
    "id": "新任务ID",
    "title": "新任务标题",
    "status": "IN_PROGRESS"
  }
}
```
**已取消返回**：
```json
{
  "status": "info",
  "message": "该任务已经是取消状态"
}
```

### `finish_task` 🆕
**成功返回**：
```json
{
  "status": "success",
  "message": "任务已成功标记为完成",
  "data": {
    "task_id": "任务ID",
    "title": "任务标题",
    "previous_status": "IN_PROGRESS",
    "new_status": "COMPLETED",
    "completed_at": "2024-01-20T10:30:00Z"
  }
}
```
**已完成返回（幂等）**：
```json
{
  "status": "info",
  "message": "任务已经处于完成状态",
  "data": {
    "task_id": "任务ID",
    "title": "任务标题",
    "status": "COMPLETED"
  }
}
```
**错误返回**：
```json
{
  "status": "error",
  "error_code": "INVALID_STATUS",
  "message": "任务状态不满足完成条件"
}
```

### `start`
**成功返回**：
```json
{
  "status": "success",
  "data": {
    "task_id": "任务ID",
    "title": "任务标题",
    "previous_status": "PENDING",
    "new_status": "IN_PROGRESS",
    "started_at": "2024-01-20T10:30:00Z"
  },
  "message": "任务已成功启动"
}
```
**冲突返回**：
```json
{
  "status": "error",
  "error_code": "CONFLICT_IN_PROGRESS",
  "message": "项目中已有进行中的任务：其他任务标题"
}
```

### `suspend`
**成功返回**：
```json
{
  "status": "success",
  "data": {
    "task_id": "任务ID",
    "title": "任务标题",
    "previous_status": "IN_PROGRESS",
    "new_status": "SUSPENDED",
    "suspended_at": "2024-01-20T10:30:00Z"
  },
  "message": "任务已成功暂存"
}
```
**无任务返回**：
```json
{
  "status": "info",
  "message": "当前没有正在进行的任务可以暂存"
}
```

### `continue_suspended`
**成功返回**：
```json
{
  "status": "success",
  "data": {
    "task_id": "任务ID",
    "title": "任务标题",
    "previous_status": "SUSPENDED",
    "new_status": "IN_PROGRESS",
    "resumed_at": "2024-01-20T10:30:00Z"
  },
  "message": "任务已成功恢复"
}
```

## 5. SOP 配置工具

### `update_step_rules`
**成功返回**：
```json
{
  "status": "success",
  "message": "Rules updated successfully"
}
```
**失败返回**：
```json
{
  "status": "error",
  "message": "更新规则失败: 错误详情",
  "code": "UPDATE_FAILED"
}
```

### `update_output_template`
**成功返回**：
```json
{
  "status": "success",
  "message": "Template updated successfully"
}
```
**失败返回**：
```json
{
  "status": "error",
  "message": "更新模板失败: 错误详情",
  "code": "UPDATE_FAILED"
}
```

## 通用错误返回格式

### 认证错误
```json
{
  "status": "error",
  "error_code": "AUTH_001",
  "message": "请先登录"
}
```

### 项目上下文缺失
```json
{
  "status": "error",
  "message": "No project context found. Please run setup_workspace or create_project first."
}
```

### 权限错误
```json
{
  "status": "error",
  "error_code": "PERMISSION_DENIED",
  "message": "无权限执行此操作"
}
```

### 资源未找到
```json
{
  "status": "error",
  "error_code": "NOT_FOUND",
  "message": "资源不存在"
}
```

## 返回状态码说明

### status 字段值
- `"success"` - 操作成功
- `"error"` - 操作失败
- `"info"` - 信息提示（通常用于幂等操作）
- `"no_available_tasks"` - 特定于 next 工具，无可用任务
- `"healthy"` / `"degraded"` - 特定于 health 工具

### error_code 常见值
- `AUTH_001` - 认证失败
- `PERMISSION_DENIED` - 权限不足
- `NOT_FOUND` - 资源未找到
- `VALIDATION_ERROR` - 验证错误
- `TASK_VALIDATION_ERROR` - 任务验证错误
- `INVALID_STATUS` - 状态无效
- `CONFLICT_IN_PROGRESS` - 存在进行中的冲突任务
- `UPDATE_FAILED` - 更新失败

## 重要提示

1. **所有工具都不返回 `summary` 字段**
2. **大部分成功响应包含 `status: "success"`**
3. **错误响应通常包含 `error_code` 和 `message`**
4. **某些操作返回 `data` 字段包含详细信息**
5. **文件保存信息通常在 `description` 字段中说明**