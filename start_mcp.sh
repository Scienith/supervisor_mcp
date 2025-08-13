#!/bin/bash
# Scienith Supervisor MCP 启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 切换到MCP项目目录
cd "$SCRIPT_DIR"

# 如果存在.env文件，则加载环境变量
if [ -f ".env" ]; then
    echo "Loading configuration from .env file..." >&2
    # 读取.env文件并导出环境变量
    export $(grep -v '^#' .env | xargs)
fi

# 检查虚拟环境是否存在，如果不存在则创建
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..." >&2
    python3 -m venv venv
    echo "Installing dependencies..." >&2
    source venv/bin/activate
    pip install -r requirements.txt
else
    # 激活虚拟环境
    source venv/bin/activate
fi

# 设置项目路径为当前工作目录（AI agent启动的位置）
export SUPERVISOR_PROJECT_PATH="$(pwd)"

# API URL使用默认值（项目初始化时会配置具体的URL）
export SUPERVISOR_API_URL="${SUPERVISOR_API_URL:-http://localhost:8000/api/v1}"

# 输出配置信息到stderr（不影响stdio通信）
echo "Starting Scienith Supervisor MCP Service..." >&2
echo "API URL: $SUPERVISOR_API_URL" >&2
echo "Project Path: $SUPERVISOR_PROJECT_PATH" >&2

# 启动MCP服务
exec python run.py "$@"