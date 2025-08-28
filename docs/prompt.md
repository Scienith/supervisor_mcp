# 通过Supervisor进行任务管理
这个项目的任务通过supervisor MCP获得任务，并且在任务完成后，通过supervisor系统进行上报，获取后续任务。

## supervisor本地目录概述
Scienith Supervisor MCP 服务使用两个主要目录来管理项目：`.supervisor`（私有管理区域）和 `supervisor_workspace`（工作区域）。这种设计确保了项目隔离、状态管理和工作区的清晰分离。

### `.supervisor` 目录（私有管理区域）

这是 MCP 服务的**私有管理区域**，供MCP程序代码查询数据和状态，用户和 AI 不应直接操作这些文件。

### `supervisor_workspace` 目录（工作区域）
这是 AI 和用户的**协作工作区域**，包含所有可见和可操作的文件。

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

## Lazy执行的tool
login，setup工具可以用lazy执行的
如果已经login过，或者setup过，之后MCP服务启动时，会自动尝试加载已经登录过的用户信息和保存过的项目信息，不需要每次都重新login和setup。只有当发现鉴权失败，或者无法找到project信息时，才需要去调用login工具和setup工具。