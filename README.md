# Scienith Supervisor MCP Service

独立的 MCP（Model Context Protocol）服务，用于在本地 IDE/Agent 与 Scienith Supervisor 平台之间桥接调用能力。

本 README 已对齐当前代码与实际用法：启动方式、工具列表与参数、环境配置、典型工作流均与仓库实现一致。

## 快速开始

### 环境准备

```bash
# 建议使用虚拟环境
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

可选（测试环境）：

```bash
pip install -r test-requirements.txt
pytest -q
# 或覆盖率
pytest --cov=src --cov-report=term-missing
```

### 运行服务

正常使用下无需手动启动服务，Codex 会按需通过 stdio 自动拉起并连接 MCP（见“IDE 集成”）。

### 认证与配置

- 后端 API 地址：
  - 通过环境变量或本仓库 `.env` 中的 `SUPERVISOR_API_URL` 配置。
  - 未配置时默认使用 `http://localhost:8000/api/v1`。

- 一站式登录与项目初始化：
  - 使用工具 `login_with_project(working_directory: str)`，它会从“目标项目”的 `.env` 读取以下字段：
    - `SUPERVISOR_USERNAME`
    - `SUPERVISOR_PASSWORD`
    - `SUPERVISOR_PROJECT_ID`
  - 该工具每次都会使用用户名/密码向后端重新登录（不复用本地 user.json 的缓存 token）。
  - 请确保传入的 `working_directory` 是目标项目根目录的绝对路径，且该目录存在上述 `.env`。
  - 注意：本仓库的 `.env.example` 仅作示例。实际使用时，应在你的“项目仓库”根目录创建 `.env` 并填入凭据，切勿将凭据提交到版本库。

### 项目隔离

- 工具会在“目标项目”的根目录下创建 `.supervisor/` 与 `supervisor_workspace/`（用于任务阶段说明、输出等），互不影响其他项目。
- 同一 MCP 服务可同时服务多个不同项目（由 Agent 传入不同 `working_directory`）。

## IDE 集成

在 Codex 中配置后，将由 Codex 按需通过 stdio 自动启动本服务，无需手动运行 `python run.py`。

- 配置文件位置：`~/.codex/config.toml`
- 将命令指向本仓库的 `start_mcp.sh`（建议使用绝对路径），并确保脚本具有可执行权限（`chmod +x`）。

- Claude Code（示例）

```json
{
  "mcpServers": {
    "scienith-supervisor": {
      "command": "/ABSOLUTE/PATH/TO/scienith_supervisor_mcp/start_mcp.sh"
    }
  }
}
```

- Codex（示例）

```toml
[mcp_servers.scienith-supervisor]
command = "/ABSOLUTE/PATH/TO/scienith_supervisor_mcp/start_mcp.sh"
```

- Cursor：按其 MCP 支持方式配置为执行上述脚本命令。

说明：`.supervisor/` 与 `supervisor_workspace/` 会在 Agent 指定的“项目工作目录”内生成，而不是在本仓库内。

## 可用工具（与实现一致）

以下为 `src/server.py` 中注册的工具清单与参数说明：

- 健康/连通性
  - `ping()`：快速检查 MCP 服务器是否运行
  - `health()`：轻量健康检查

- 认证
  - `login_with_project(working_directory: str)`：
    - 从 `working_directory` 下的 `.env` 读取 `SUPERVISOR_USERNAME`、`SUPERVISOR_PASSWORD`、`SUPERVISOR_PROJECT_ID`
    - 用于“一站式登录并初始化项目工作区”
  - `logout()`：登出并清除会话

- 项目
  - `create_project(project_name: str, description?: str, working_directory?: str)`：新建项目并初始化本地工作区
  - `get_project_status(detailed: bool = False)`：查询项目状态（detailed=true 返回详细信息）

- 任务执行
  - `next()`：获取当前应执行的下一个任务阶段（会在本地生成/更新阶段说明文件）
  - `report(task_phase_id?: str, result_data: dict)`：上报阶段结果
    - VALIDATION 阶段：`result_data` 必须为 `{"passed": true/false}` 且不得包含其他字段
    - 其他阶段：请传 `{}` 或省略
  - `finish_task()`：将当前进行中的任务组直接标记为完成

- 任务组
  - `add_task(title: str, goal: str, sop_step_identifier: str)`：创建 IMPLEMENTING 任务组
  - `start(task_id: str)`：启动处于 PENDING 的任务组
  - `suspend()`：暂存当前进行中的任务组到本地
  - `continue_suspended(task_id: str)`：恢复指定的暂存任务组
  - `cancel_task(task_id?: str, cancellation_reason?: str)`：取消任务组（未提供 task_id 时默认取消当前进行中的任务组）

- SOP 模板/规则同步
  - `update_step_rules(stage: str, step_identifier: str)`：更新步骤规则
  - `update_output_template(stage: str, step_identifier: str, output_name: str)`：更新步骤输出模板

## ToolResult 返回规范（CLI 对接）

所有 MCP 工具统一返回 FastMCP 的 `ToolResult`，包含两部分：

- content（模型可见）
  - 聚合为一条以 `to_ai: ...` 开头的文本，保留完整提示与说明，便于模型理解上下文。
  - 注意：content 仅用于呈现与上下文传递，不建议据此自动执行。

- structured_content（客户端可执行）
  - `policy`: `{ require_sequential: true, idempotency_key: string, side_effects: "none" }`
  - `actions`: 按顺序依次执行的命令列表；每执行一条，先将结果展示给用户，再继续下一条。

同时，服务器在内部还维护两种“指令形式”（主要供包装逻辑生成 actions 使用）：

- `instructions_v2`（结构化，推荐）
  - 每条指令是一个对象：`{ to_ai, user_message[], result?, kind, phase? }`
  - `kind` 取值：
    - `display`：需要直接展示给用户的内容
    - `execute`：基于用户反馈的执行动作（映射为 `execute_phase`）
  - `phase`：当 `kind=execute` 时，描述要执行的动作/阶段（自然语言即可）

- `instructions`（字符串，兼容）
  - 由 `instructions_v2` 的 `to_ai` 字段集合派生，便于不解析结构化内容的客户端直接展示。

actions 生成规则（服务器已内置）
- display 指令 → 生成 `{ tool: "display_original_text", args: { text: <合并 user_message 或回退 to_ai> } }`
- execute 指令 → 生成 `{ tool: "execute_phase", args: { phase: <phase 或 to_ai> } }`
- 若文本中包含 `supervisor_workspace/...` 路径，会自动补充相应的 `{ tool: "read_file", args: { path } }`

示例：`next` 的典型 actions（执行顺序）
- 存在任务说明（wrote_task_desc = true）时：
  1) `display`（提示任务说明与阶段说明的文件路径）
  2) `read_file { path: "supervisor_workspace/current_task/task_description.md" }`
  3) `read_file { path: "supervisor_workspace/current_task/XX_<phase>_instructions.md" }`
  4) `execute_phase { phase: "执行 <PHASE> 阶段" }`

- 不存在任务说明时：
  1) `display`（提示阶段说明的文件路径）
  2) `read_file { path: "supervisor_workspace/current_task/XX_<phase>_instructions.md" }`
  3) `execute_phase { phase: "执行 <PHASE> 阶段" }`

客户端（CLI）建议实现
- 仅根据 `structured_content.actions` 顺序执行；每步执行完毕将结果显示给用户。
- `display_original_text`：将 `text` 原文渲染到 UI。
- `read_file`：调用本端/对端的读文件工具；结果可再次 `display_original_text` 给用户。
- `execute_phase`：将 `phase` 作为自然语言任务指示，触发相应阶段的自动化或下一步工具调用。
- 如遇未识别的动作，直接将其文本 `display_original_text` 给用户，并请求指示。

说明
- 本仓库所有工具都会提供 `instructions_v2`；`instructions` 作为兼容展示用途保留。
- 服务器端会尽力从结构化指令生成 actions；仅在极端回退场景下才会依据文本做有限推断（无需依赖）。

## 典型工作流

以下示例展示了从登录到执行任务的常见流程。注意：示例调用展示的是 MCP 工具的语义流程，具体触发由 IDE/Agent 端完成。

```python
# 0) 在你的项目根目录创建 .env（包含 SUPERVISOR_USERNAME / SUPERVISOR_PASSWORD / SUPERVISOR_PROJECT_ID）
# 1) 登录并初始化本地工作区（读取项目 .env）
login_with_project("/abs/path/to/your/project")

# 2) （可选）创建新项目
create_project(project_name="智能客服系统", description="基于AI的客服系统")

# 3) （可选）创建任务组
add_task("头像上传", "实现上传/裁剪/存储", "implement")

# 4) 启动任务组并进入执行
start("tg_xxx")          # 启动某个任务组
next()                   # 拉取第一个任务阶段（会生成阶段说明文件）

# 5) 提交结果
report(result_data={})   # 非 VALIDATION 阶段
# 或
report(result_data={"passed": True})  # VALIDATION 阶段

# 6) 如需直接完成任务组
finish_task()

# 7) 任务切换
suspend()
continue_suspended("tg_xxx")
cancel_task("tg_yyy", cancellation_reason="需求变更")
```

## 目录结构

```
scienith_supervisor_mcp/
├── src/                   # 源码
│   ├── server.py          # MCP 服务器与工具注册
│   ├── service.py         # 业务逻辑与 API 调用
│   ├── file_manager.py    # 本地文件/工作区管理
│   ├── session.py         # 会话与上下文
│   ├── config.py          # 配置读取（含 SUPERVISOR_API_URL）
│   └── validators.py      # 数据校验
├── tests/                 # 测试（pytest）
├── run.py                 # 启动入口（支持 --http）
├── start_mcp.sh           # 启动脚本（加载仓库 .env）
├── .env.example           # 示例配置（请勿提交真实凭据）
├── requirements.txt       # 依赖
└── README.md              # 本文档
```

说明：`.supervisor/` 与 `supervisor_workspace/` 会在“项目仓库”内创建与更新。

## 故障排除

- 服务无法启动
  - 确认 Python 版本 ≥ 3.8
  - 确认依赖安装完成（`pip install -r requirements.txt`）

- API 连接问题
  - 未配置 `SUPERVISOR_API_URL` 时将使用默认 `http://localhost:8000/api/v1`
  - 如需指定后端，请在本仓库 `.env` 或环境变量中设置 `SUPERVISOR_API_URL`

- 登录失败或无项目上下文
  - 确认使用了 `login_with_project("/绝对/项目路径")`
  - 确认“项目仓库”根目录存在 `.env` 且包含 `SUPERVISOR_USERNAME`、`SUPERVISOR_PASSWORD`、`SUPERVISOR_PROJECT_ID`

- 提交结果时报错
  - VALIDATION 阶段 `result_data` 必须且只能包含 `{"passed": true/false}`
  - 其他阶段请传 `{}` 或省略 `result_data`

## 开发与测试

- 代码风格：Python 3.8+，PEP 8，4 空格缩进；模块/函数/变量使用 snake_case，类使用 PascalCase。欢迎使用 `black` / `isort`（非必需）。
- 运行测试：`pytest -q`；覆盖率：`pytest --cov=src --cov-report=term-missing`。
- 安全：不要提交任何敏感信息；`.env` 应位于 `.gitignore`。
