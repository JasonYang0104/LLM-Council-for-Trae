# M2 任务卡：ModelRuntime port 与 runtime_backend 轴（交执行 Agent）

- 日期：2026-06-11
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §3（M0–M5 路线）
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m2-20260611`，分支 `codex/lct-acp-m2-runtime-port-20260611`（从 `main @ c6a7591` 切出）
- 流程约束：纯本地，不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 回滚锚点：tag `pre-acp-m1`（M1 合并前）；本阶段合并前将打 `pre-acp-m2`。

## 背景与基线事实

- `main @ c6a7591`：M1 已合入，`make test` 314 个 unittest 全绿（含 17 个 direct contract tests ＋ 2 个 golden tests）。
- 移植源（只读，共享 object store）：分支 `codex/lct-acp-runtime-p0-p1-20260604`，重点 commit `98890bd ref: extract model runtime port`（P1 状态）。注意：研究线后续 commit（`2668359`/`bfa7be9`/`deb9119`）属 M3/M4 范围，**本阶段不移植**。
- 研究线 notes.md Phase 3 节记录了 P1 的红绿过程与 golden 重生成原因，先读。

## 目标

引入 runtime 抽象与显式 backend 选择轴，direct 行为零变化（以 M1 contract tests 不改断言通过为机器证据），为 M3 offline ACP adapter 提供工厂挂载点。

## 移植内容

1. `CouncilConfig` 新增字段：`runtime_backend: str = "direct"`、`acp_startup_timeout: int = 30`；`config_to_json()` 持久化两字段。
2. CLI `run` 新增：`--runtime-backend`（choices `direct`/`acp`，默认 `direct`）、`--acp-startup-timeout`（默认 30）。
3. `provider.py` 新增 `ModelRuntime` protocol（最小接口：async `query_model(...) -> ModelCallResult`，签名以研究线为准）＋ `DirectTraeCliRuntime = TraeCliProvider` 显式别名。
4. `council.py` 新增 `build_model_runtime(...)` 工厂，`run_full_council()` 的 runtime 构造点收敛到该工厂：
   - `direct` → 现有 `TraeCliProvider`（行为零变化）。
   - `acp` → **本阶段 fail-fast**：`ValueError("runtime_backend=acp is not implemented yet")`（M3 才接 adapter）。
   - 未知 backend → `ValueError`。
   - `runtime_backend=acp` × `provider_mode=subagent` → fail-fast。
5. stage 编排函数（stage1/stage2/stage3 collect/backfill/synthesize）的 provider 类型标注从 `TraeCliProvider` 收窄为 `ModelRuntime`。
6. 移植 `tests/contract/test_runtime_backend_contract.py`，取 `98890bd` 时点版本（默认值冻结、CLI 进 config、config JSON 持久化、subagent×acp fail-fast、`DirectTraeCliRuntime is TraeCliProvider`、acp fail-fast）；研究线后续对该文件的 P2/P3 修订不带入。

## 边界（不得越过）

1. **M1 的 17 个 contract tests 与 2 个 golden tests 不改任何断言**。唯一允许的例外：`tests/golden/direct_full_run/snapshot.json` 重生成，且差异**只能**由 `runtime_backend` / `acp_startup_timeout` 进入 `config.json` / `manifest.config`（及由此引起的 HTML 字符数变化）构成——研究线 Phase 3 记录的正是这一形态。重生成原因与逐字段差异写进 commit message。
2. **`EXPECTED_META_KEYS`（37 键）不得变**：M2 不加任何 meta 字段（ACP evidence 字段属 M4）。
3. 不实现任何 ACP adapter / transcript parser / live transport。
4. `src/` 改动范围限于：`CouncilConfig` 所在模块、`cli.py`、`provider.py`、`council.py`；不新建 src 模块。
5. 旧 profile / 旧 config JSON 不含 `runtime_backend` 时按 `direct` 处理（不失败）。

## 验收标准

1. `make test` 全绿，总数 = 314 ＋ 新增（研究线 P1 为 6 个新 test，以实测为准）。
2. M1 contract tests 全绿且 `git diff main..HEAD -- tests/contract/test_direct_*.py tests/contract/test_tool_*.py tests/contract/test_meta_keyset_golden.py tests/contract/test_cancellation_contract.py tests/support/runtime_contract.py` 为空（断言未动的机器证明；golden snapshot 与 `test_runtime_backend_contract.py` 除外）。
3. golden 连跑两次零漂移。
4. `git diff --check` 通过。
5. notes.md 追加 M2 节：红绿过程、golden 差异逐字段列表、与研究线 P1 的适配差异。
6. 提交粒度：建议两 commit（先红测试 → 产品代码补齐转绿），message 前缀 `ref:` / `test:`，停在分支。

## 汇报要求

最终测试总数与新增数、golden 逐字段差异、M1 测试零改动证明的命令输出、所有验收命令 pass/fail、commit SHA、遗留风险。任何验收未过如实报告。
