# LCT 搜索生效计数与索引补位候选修正实施记录

日期：2026-06-04
分支：`codex/lct-search-delivery-index-20260604`
开始时间：2026-06-04 16:49:33 CST

## 阶段 0：启动与基线确认

### 阶段目标

- 从最新 `origin/main` 创建本轮执行分支。
- 读取 handoff 指定的项目入口、设计文档和关键代码入口。
- 建立本轮中文运行记录。
- 跑 fresh baseline verification，确认后续红绿循环的起点可信。

### 已读文档

- `README.md`
- `docs/design.md`
- `docs/lct-ux-evidence-hardening-design-20260602.md`
- `docs/lct-auto-backfill-quorum-design-20260603.md`
- `docs/lct-input-boundary-docs-design-20260604.md`
- `docs/lct-input-boundary-docs-test-plan-20260604.md`
- `docs/lct-search-delivery-and-index-handoff-20260604.md`

### 初始观察

- 当前分支从 `origin/main` 创建：`codex/lct-search-delivery-index-20260604`。
- 本轮 handoff 文件在启动时是未跟踪文件，但它位于 `docs/` 下且是本轮正式输入资产，因此纳入本分支版本控制。
- 当前 `provider.py` 只从 assistant message 统计 `tool_calls`，没有把 tool result 是否成功交付拆成独立证据。
- 当前 `html_export.py` 的搜索卡片展示“允许 / 实际使用 / Web 工具调用 / 总工具调用”，仍容易把调用发生误读为调用生效。
- 当前 `validation.py` 有结构化 checks，但没有 WebSearch / WebFetch 输出转换失败的 warning check。
- 当前 Skill 和 README 已要求拆分 LCT 内部搜索与外层 Agent 搜索，但 `backfill_candidates` 来源还没有被强约束为 terminal manifest 的 `metadata.quorum.backfill_candidates`。

### 本轮边界

- 不重新跑完整 live benchmark。
- 不改默认模型阵容。
- 不改写 v10 既有 run artifact。
- 不把 conversion error 升级为 artifact 硬失败；本轮把它作为审计 warning。
- `notes.md` 只记录本轮关键取舍、验证和 commit，不写流水账。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（191 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- 待提交：`docs: start search delivery handoff notes`
