# M1 任务卡：移植 direct baseline contract tests（交执行 Agent）

- 日期：2026-06-11
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §3（M0–M5 路线）
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m1-20260611`，分支 `codex/lct-acp-m1-direct-baseline-20260611`（从 `main @ 04a1b9b` 切出）
- 流程约束（用户裁决 2026-06-11）：**纯本地，不推 GitHub、不开 PR**。完成后停在分支等架构师 review，不自行合并 main。

## 背景与基线事实

- `main @ 04a1b9b` 基线：`make test` 295 个 unittest 全绿（2026-06-11 本机实测）。
- 移植源：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-disabled-tool-research-20260603`，分支 `codex/lct-acp-runtime-p0-p1-20260604`，重点 commit `5c88617 test: freeze direct runtime baseline`（研究目录与主 repo 共享 object store，可直接 cherry-pick / checkout 文件）。
- 研究线测试落点：`tests/contract/`（8 个文件）＋ `tests/support/`（fake runtime / fake subprocess / golden normalizer / meta key set）＋ `tests/test_golden_direct_run.py` ＋ `tests/golden/direct_full_run/snapshot.json`。
- 备份：`/Users/bytedance/Documents/AI Coder/lct-acp-research-backup-20260611.bundle`（bundle verify 通过，complete history）。

## 目标

把研究线 P0 direct baseline contract tests 移植到当前 main，冻结 direct runtime 当前行为，为 M2（ModelRuntime port）及后续所有改动提供零漂移机器证据。

## 边界（不得越过）

1. **不改 `src/` 任何产品代码**。M1 是纯测试移植；若测试暴露产品行为与研究线记录不同，按当前 main 行为冻结（P0 原则：冻结事实，不修产品），差异记入 notes.md。
2. 不引入 `runtime_backend` / `ModelRuntime` / ACP 任何代码或测试（那是 M2/M3）。
3. 不修改现有 295 个测试的任何断言。
4. golden snapshot 不得照抄研究线版本：当前 main 的 config / meta / HTML 字段集已变（contribution_map 链路、repair attempts 等 56 commits），必须在当前 main 上重新生成，并在 commit message 中列出与研究线快照的字段差异。

## 移植内容（验收时逐项核对）

研究线 `5c88617` 的全部测试资产，适配当前 main：

- `tests/contract/test_tool_policy_golden.py` — 四种 member_tool_mode 的 allowed/disallowed 全列表
- `tests/contract/test_direct_command_golden.py` — `_build_command()` 完整 argv 顺序 ＋ `--yolo` 行为
- `tests/contract/test_meta_keyset_golden.py` — `ModelCallResult.to_json()` key set 冻结
- `tests/contract/test_direct_spawn_contract.py` — spawn kwargs、runtime cwd、`start_new_session`、env override
- `tests/contract/test_direct_status_matrix.py` — `_query_model_once()` 状态优先级（非零退出/空响应/model mismatch/forbidden tool/tool-budget kill）
- `tests/contract/test_direct_retry_matrix.py` — `query_model()` retry / no-retry 规则
- `tests/contract/test_cancellation_contract.py` — CancelledError 传播、进程 kill、failed meta、不写伪成功
- `tests/contract/test_tool_state_invariants.py` — search allowed / used / forbidden 不塌缩
- `tests/test_golden_direct_run.py` ＋ `tests/support/` ＋ `tests/golden/direct_full_run/snapshot.json` — fake runtime 全链路 golden，连跑两次零漂移

研究线红绿记录中的已知坑（notes.md Phase 2 节）直接吸收：cancellation 测试须在 TemporaryDirectory 生命周期内读证据；argv 断言精确检查 `--query-timeout` 及其值；status matrix 测 `_query_model_once()` 而非 `query_model()`（retry 由 retry matrix 单独冻结）。

## 验收标准

1. `make test` 全绿，总数 = 295 ＋ 新增数（预期新增约 19：17 contract ＋ 2 golden，以实测为准）。
2. `PYTHONPATH=src:tests python3 -m unittest discover -s tests/contract -v` 独立全绿。
3. golden 连跑两次零漂移（`tests/test_golden_direct_run.py` 自带断言）。
4. `git diff main..HEAD -- src/` 为空（零产品代码变更的机器证明）。
5. `git diff --check` 通过。
6. notes.md（worktree 内）记录：红绿过程、与研究线快照的字段差异、适配中发现的 main 行为变化。
7. 提交粒度：单 commit `test: freeze direct runtime baseline`（或红绿两 commit），停在分支。

## 交付物

分支 `codex/lct-acp-m1-direct-baseline-20260611` 上的 commits ＋ notes.md 记录。架构师 review 通过后再议合入 main（本地 merge，仍不推 GitHub）。
