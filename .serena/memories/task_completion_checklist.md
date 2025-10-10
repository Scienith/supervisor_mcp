# 任务完成检查清单

- 测试通过与覆盖率
  - 运行 `pytest -q`，确保全部通过。
  - 使用 `pytest --cov=src --cov-report=term-missing` 检查覆盖率，目标 > 80%。
- 变更影响与文档
  - 若改动影响工具行为或用户体验：更新 `docs/` 或 `README` 相关说明。
  - 若涉及新配置：同步更新 `.env.example` 与文档。
- 代码质量
  - 遵循 PEP 8 与本仓库风格约定；可选执行 `black .`、`isort .`。
  - 保持变更最小化与聚焦，避免无关重构。
- 安全与配置
  - 不提交任何机密信息；本地使用 `.env`（参考 `.env.example`）。
  - 关键变量：`SUPERVISOR_API_URL`；`login_with_project` 需 `SUPERVISOR_USERNAME`、`SUPERVISOR_PASSWORD`、`SUPERVISOR_PROJECT_ID`。
- 提交与 PR
  - 提交信息尽量使用 Conventional Commits，如 `feat: ...`、`fix: ...`。
  - PR 包含：清晰描述/动机、关联 issue、相应测试、必要的日志/截图与文档更新。