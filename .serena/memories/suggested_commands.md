# 常用命令清单（建议）

## 环境与依赖
- 创建虚拟环境并安装依赖：
  - `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- 测试依赖：
  - `pip install -r test-requirements.txt`

## 运行服务
- Stdio 模式：
  - `python run.py`
- HTTP 模式（服务地址 `0.0.0.0:8080/mcp`）：
  - `python run.py --http`
- 脚本启动（自动加载 `.env` 若存在）：
  - `./start_mcp.sh`

## 测试与覆盖率
- 运行测试：
  - `pytest -q`
- 覆盖率报告：
  - `pytest --cov=src --cov-report=term-missing`

## 可选格式化
- `black .`
- `isort .`

## 常用系统工具（macOS/Darwin）
- 目录/文件：`ls`、`cd`、`pwd`、`find`、`rg`（ripgrep，优先于 `grep`）
- 文本处理：`sed`（macOS 需要 `-i ''` 就地修改）、`awk`
- 其他：`python -V`、`pip -V`、`which python`、`env | sort`