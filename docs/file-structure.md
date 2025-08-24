# Scienith Supervisor MCP 文件结构说明

## 概述

Scienith Supervisor MCP 服务使用两个主要目录来管理项目：`.supervisor`（私有管理区域）和 `supervisor_workspace`（工作区域）。这种设计确保了项目隔离、状态管理和工作区的清晰分离。

## 1. `.supervisor` 目录（私有管理区域）

这是 MCP 服务的**私有管理区域**，供MCP代码查询数据和状态，用户和 AI 不应直接操作这些文件。

```
.supervisor/
├── project.json                    # 项目元数据和API配置
├── user.json                      # 用户认证信息和会话数据
└── suspended_task_groups/          # 暂停的任务组存储目录
    └── task_group_{id}/           # 每个暂停任务组的文件
```

### 用途说明

- **`project.json`**: 存储项目ID、API配置等核心元数据
- **`user.json`**: 存储用户认证信息和会话数据，用于自动会话恢复。
- **`suspended_task_groups/`**: 当任务组被暂停时，相关工作文件会移动到此处保存
- **维护项目状态**: 确保多项目之间的隔离和会话管理

## 2. `supervisor_workspace` 目录（工作区域）

这是 AI 和用户的**协作工作区域**，包含所有可见和可操作的文件。

```
supervisor_workspace/
├── current_task_group/             # 当前活跃任务组的工作文件
├── sop/                           # 标准操作程序（SOP）定义
│   ├── {stage}/                   # SOP阶段目录（如analysis、planning、implementing等）
│   │   └── {step_identifier}/     # 具体步骤目录
│   │       ├── config.json        # 步骤配置和规则
│   │       └── templates/         # 输出模板文件
│   │           └── {template}.md  # 具体模板文件
│   └── ...                       # 其他阶段和步骤
└── templates/                     # 全局模板文件（如有）
```

### 详细说明

#### `current_task_group/` 目录
- 存放当前正在执行的任务组相关文件
- AI 在此目录下创建和修改工作文件
- 任务组切换时，文件会相应移动或暂存

#### `sop/` 目录结构
每个 SOP 步骤包含：

**`config.json` 文件**：步骤的完整定义
- `identifier`: 步骤唯一标识符
- `name`: 步骤显示名称  
- `description`: 步骤描述
- `outputs`: 定义该步骤应产出的文件
- `rules`: 执行该步骤时的规则和约束

**`templates/` 目录**：输出文件的模板
- 包含该步骤各种输出的 Markdown 模板
- AI 基于这些模板创建具体的工作文件

#### SOP 阶段组织
- **`{stage}/`**: 各种SOP阶段目录，如 `analysis/`（分析）、`planning/`（规划）、`implementing/`（实现）等
- **`{step_identifier}/`**: 具体步骤的标识符目录，每个项目的步骤可能不同
- **支持多语言命名**: 阶段和步骤名称支持中文、英文等多种语言

## 3. 工作流程

### 项目生命周期
1. **项目初始化**: 创建 `.supervisor` 和 `supervisor_workspace` 目录结构
2. **SOP 下载**: 从服务器下载完整的 SOP 定义到 `sop/` 目录
3. **任务执行**: AI 在 `current_task_group/` 中基于模板创建和编辑文件
4. **任务切换**: 暂停的任务组文件移至 `.supervisor/suspended_task_groups/`
5. **状态同步**: 项目状态和进度信息存储在 `.supervisor/project.json`

### 文件操作规则
- **私有区域**（`.supervisor`）：仅 MCP 服务内部管理，用户不应直接修改
- **工作区域**（`supervisor_workspace`）：用户和 AI 可以自由访问和修改
- **模板系统**：AI 基于 `sop/*/templates/` 中的模板创建工作文件
- **项目隔离**：每个项目维护独立的文件结构，互不干扰


## 5. Lazy执行的tool
login，setup工具可以用lazy执行的测试
如果已经login过，或者setup过，之后MCP服务启动时，会自动尝试加载已经登录过的用户信息和保存过的项目信息，不需要每次都重新login和setup。只有当发现鉴权失败，或者无法找到project信息时，才需要去调用login工具和setup工具。


