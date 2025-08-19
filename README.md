# Scienith Supervisor MCP Service

独立的MCP（Model Context Protocol）服务，用于AI IDE与Scienith Supervisor系统的集成。

## 快速开始

### 1. 首次安装

#### 配置环境变量（可选）

如果需要使用非默认的API服务器地址，请复制并编辑配置文件：

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件，设置您的API服务器地址
# 例如：SUPERVISOR_API_URL=https://api.scienith.com/api/v1
nano .env
```

如果不创建`.env`文件，系统将使用默认配置（API地址：http://localhost:8000/api/v1）。

#### 设置脚本权限

赋予启动脚本执行权限：

```bash
chmod +x /Users/junjiecai/Desktop/scientith_projects/scienith_supervisor_mcp/start_mcp.sh
```

### 2. 项目隔离机制

每个项目独立配置，互不干扰：

- **工作目录**：`.supervisor`目录在AI agent的当前工作目录创建
- **API配置**：每个项目的`project_info.json`保存自己的API服务器地址
- **多项目支持**：同一个MCP服务可以管理多个不同的项目

### 3. 自动启动

MCP服务由AI agent自动启动，无需手动操作。AI agent会在当前工作目录初始化项目。

## IDE集成配置

配置后，AI agent会在需要时自动启动MCP服务。

### Claude Code

在Claude Code的MCP设置中添加：

```json
{
  "mcpServers": {
    "scienith-supervisor": {
      "command": "/Users/junjiecai/Desktop/scientith_projects/scienith_supervisor_mcp/start_mcp.sh"
    }
  }
}
```

### Codeium/Codex

在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.scienith-supervisor]
command = "/Users/junjiecai/Desktop/scientith_projects/scienith_supervisor_mcp/start_mcp.sh"
```

### Cursor

在Cursor的MCP配置中添加类似Claude Code的配置。

**注意：** AI agent会在其当前工作目录创建`.supervisor`文件夹，因此同一个MCP服务可以管理多个不同的项目。

## MCP工具说明

### 认证管理

#### login
用户登录认证
```
参数:
- username: 用户名
- password: 密码
返回: 登录成功后的用户信息
```

#### logout
清除当前登录会话
```
返回: 登出状态
```

### 项目管理

#### create_project
创建新项目并初始化本地工作区
```
参数:
- project_name: 项目名称
- description: 项目描述（可选）
- working_directory: 工作目录（可选）
返回: 项目ID和初始化信息
```

#### setup_workspace
为已有项目设置本地工作区
```
参数:
- project_id: 已存在项目的ID
- working_directory: 工作目录（可选）
返回: 工作区设置状态
```

#### get_project_status
查询项目当前状态和进度
```
参数:
- project_id: 项目ID
- detailed: 是否返回详细信息（默认False）
返回: 项目状态、进度、任务组统计等
```

### 任务管理

#### next
获取下一个待执行任务
```
参数:
- project_id: 项目ID
返回: 任务详情和执行上下文
```

#### report
提交任务执行结果
```
参数:
- task_id: 任务ID
- result_data: 结果数据
  - success: 是否成功
  - output: 产出文件路径
  - notes: 备注说明
  - validation_result: 验证结果（VALIDATION任务需要）
返回: 提交状态
```

### 任务组管理

#### pre_analyze
分析用户需求并提供SOP步骤指导
```
参数:
- user_requirement: 用户需求描述
返回: 分析结果和可用SOP步骤
```

#### add_task_group
创建新的执行任务组
```
参数:
- title: 任务组标题
- goal: 任务组目标
- sop_step_identifier: SOP步骤标识符
返回: 创建的任务组信息
```

#### list_task_groups
获取可切换的任务组列表
```
参数:
- project_id: 项目ID
返回: 当前任务组、可切换任务组、已取消任务组
```

#### start
启动指定的PENDING状态任务组
```
参数:
- project_id: 项目ID  
- task_group_id: 要启动的任务组ID
返回: 启动结果和任务组状态
```

#### suspend
暂存当前IN_PROGRESS状态的任务组
```
参数:
- project_id: 项目ID
返回: 暂存结果和任务组信息
```

#### continue_suspended
恢复指定的SUSPENDED状态任务组
```
参数:
- project_id: 项目ID
- task_group_id: 要恢复的任务组ID
返回: 恢复结果和任务组状态
```

#### cancel_task_group
取消指定任务组
```
参数:
- project_id: 项目ID
- task_group_id: 要取消的任务组ID
- cancellation_reason: 取消原因（可选）
返回: 取消操作结果
```

### 健康检查

#### ping
快速检查MCP服务状态
```
返回: 服务运行状态
```

#### health
检查服务健康状态
```
返回: 详细健康信息
```

## 工作流示例

### 新项目初始化

```python
# 1. 登录系统
login("username", "password")

# 2. 创建新项目（指定API服务器地址）
result = create_project(
    project_name="智能客服系统",
    description="基于AI的客服解决方案",
    api_url="http://192.168.1.100:8000/api/v1"  # 项目专属的API服务器
)
project_id = result["data"]["project_id"]

# 3. 获取首个任务（自动使用项目配置的API）
task = next(project_id)

# 4. 执行任务...

# 5. 提交任务结果
report(task["task"]["id"], {
    "success": True,
    "output": "/docs/requirements.md",
    "notes": "需求分析完成"
})
```

### 已有项目继续工作

```python
# 1. 登录
login("username", "password")

# 2. 设置本地工作区（可以指定不同的API服务器）
setup_workspace(
    project_id="existing-project-id",
    api_url="http://192.168.1.200:8000/api/v1"  # 可选，覆盖默认配置
)

# 3. 获取当前任务（使用project_info.json中的API配置）
task = next("existing-project-id")

# 4. 继续工作流程...
```

### 任务组管理流程

```python
# 1. 分析用户需求
analysis = pre_analyze("实现用户头像上传功能")

# 2. 创建任务组
task_group = add_task_group(
    "用户头像上传",
    "实现头像上传、裁剪、存储功能",
    "implement"
)

# 3. 启动任务组
start(project_id, task_group_id)

# 如需暂存当前任务组再启动新的：
# suspend(project_id)  # 暂存当前任务组
# start(project_id, new_task_group_id)  # 启动新任务组

# 恢复暂存的任务组：
# continue_suspended(project_id, suspended_task_group_id)

# 4. 查看所有任务组
groups = list_task_groups(project_id)
```

## 目录结构

```
scienith_supervisor_mcp/
├── src/                 # 源代码
│   ├── __init__.py     # 包初始化
│   ├── server.py       # MCP服务器实现
│   ├── service.py      # 服务层（认证、API调用）
│   ├── file_manager.py # 本地文件管理
│   ├── session.py      # 会话管理
│   └── validators.py   # 数据验证
├── config.json         # 配置文件
├── start_mcp.sh        # 启动脚本
├── run.py             # Python入口
├── requirements.txt   # 依赖包
└── README.md         # 本文档
```

## 故障排除

### 服务无法启动
1. 检查Python版本（需要3.8+）
2. 确认config.json配置正确
3. 验证Supervisor后端服务是否运行

### 连接失败
1. 检查`supervisor_api_url`是否正确
2. 确认网络连接正常
3. 验证防火墙设置

### 认证失败
1. 确认用户名密码正确
2. 检查用户权限设置
3. 验证Token有效期

### 文件操作失败
1. 检查`supervisor_project_path`路径存在
2. 确认目录写入权限
3. 验证磁盘空间充足

## 手动安装（如果启动脚本失败）

```bash
# 1. 创建虚拟环境
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行服务
python run.py
```