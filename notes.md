# LCT Auto-Backfill 实施记录

日期：2026-06-03
分支：`codex/lct-auto-backfill-plan-20260603`

## Phase 0：规格落地与基线

### 阶段目标

- 确认当前分支和未提交规格文档。
- 阅读 `AGENTS.md`、主设计文档和实现交接文档。
- 建立本轮执行记录，后续每阶段记录测试、决策、风险、验证命令和 commit。

### 初始观察

- 当前分支符合交接预期：`codex/lct-auto-backfill-plan-20260603`。
- `docs/lct-auto-backfill-quorum-design-20260603.md` 和 `docs/lct-auto-backfill-implementation-handoff-20260603.md` 处于未提交状态。
- 既有代码里 Stage 2 timeout 已有取消后 gather 收口；Stage 1 在 hard timeout / quorum checkpoint 后取消 pending task，但没有等待 provider cleanup 完成。
- 既有 Stage 2 reviewer 仍来自 `config.members`，不是有效 Stage 1 成员集合；这会导致失败成员默认继续参与 reviewer。

### 规范未覆盖但需要明确的执行决定

- 本轮实现先保持同 run 内 auto-backfill，不做跨 run merge。
- `notes.md` 只由执行 Agent 维护；不交给 LCT 成员模型写入或改写。
- 仓库已有 `notes.md` 是上一轮 title/global-install/UX hardening 的历史执行记录；本轮 handoff 明确要求维护当前运行中的 `notes.md`，因此将它重置为本轮 auto-backfill 执行记录。旧内容仍在 git 历史中，不作为本轮交接入口。
- Phase 7 的 stale run terminalize 和 forbidden tool fail-fast 如果拖慢核心 auto-backfill，会作为后续风险明确写入 brief，而不是稀释 Phase 1-6 的完成质量。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（163 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- `785476d docs: add auto-backfill implementation plan`

## Phase 1：Runtime cleanup 测试与最小实现

### 阶段目标

- 让 Stage 1 在 quorum checkpoint 或 hard timeout 取消 pending model task 后，等待 provider cleanup 完成再返回。
- Stage 2 collector 在外部取消或 timeout 后也统一 drain pending task。
- 为 provider timeout / cancel / tool-budget kill 路径记录 termination metadata，供后续 manifest / validate / HTML 使用。

### 新增/修改的测试

- 新增：`test_stage1_quorum_checkpoint_drains_cancelled_provider_cleanup`
  - 先红后绿；红态证明 Stage 1 返回时 fake provider 的取消 cleanup 尚未执行。
  - 绿态断言 cleanup flag 完成，且 fake provider 未写 meta 时由 orchestrator 补写 `stage1/B.meta.json`。
- 新增：`test_model_call_result_serializes_termination_metadata`
  - 锁定 `ModelCallResult.to_json()` 输出 termination metadata。
- 新增：`test_provider_timeout_records_termination_metadata`
  - 锁定 provider timeout 后返回 failed result，并记录 `termination_reason=timeout`、`terminated=true`、`final_returncode`。

### 实现决定

- 在 `council.py` 增加 `cancel_and_drain()`，Stage 1 / Stage 2 对 pending task 统一 `cancel()` 后 `gather(..., return_exceptions=True)`。
- Stage 1 在写 stage record 前检查 `stage1/{label}.meta.json`，如果 provider 没写过，则补写 synthetic failed meta；如果 provider 已写真实 meta，不覆盖 pid/pgid 等证据。
- `terminate_process_tree()` 从“只做动作”改成“动作 + 返回 metadata”，保留旧调用方式兼容：调用方可以忽略返回值。
- provider timeout 和 cancel 路径都会写 stream/stderr/meta sidecar。cancel 路径仍 re-raise，让 orchestrator 维持现有 synthetic failed record 语义。

### 权衡与风险

- 本阶段没有处理 preflight 的 `os.system` 路径；这是既有 pipe hang 约束，不属于 direct model call cleanup。
- 本阶段没有做全局 process sweeping，也没有 kill 非本 run 拥有的进程。
- `termination` 字段目前作为新增兼容字段进入 meta 和 stage record；Phase 5 再把它纳入 validate / HTML 的用户面展示。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_runtime_hardening -v`（24 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（166 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- 待提交：`fix: drain cancelled model tasks before backfill`
