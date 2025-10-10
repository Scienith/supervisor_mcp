# 代码风格与约定

- 语言与版本：Python 3.8+；遵循 PEP 8；4 空格缩进。
- 命名约定：
  - 模块/文件：`snake_case`
  - 类：`PascalCase`
  - 函数/变量：`snake_case`
- 类型与文档：公共函数建议提供类型标注与 docstring；偏好体量小、纯函数式的辅助工具。
- 模块职责：
  - I/O 与进程接线留在 `server.py` / `service.py`。
  - 文件相关逻辑集中在 `file_manager.py` 等专用模块中，避免散落。
- 可选格式化：允许使用 `black`、`isort`（非强制）。
- 测试规范：
  - 测试框架：`pytest`、`pytest-asyncio`、`pytest-mock`。
  - 异步测试使用 `@pytest.mark.asyncio`。
  - 测试文件位置/命名：`tests/**/test_*.py`；聚焦单元粒度并善用 mock。
  - 目标覆盖率：> 80%。
- 提交与 PR：优先使用 Conventional Commits（历史可能混用）；PR 需包含描述/动机、关联 issue、测试与必要文档更新。