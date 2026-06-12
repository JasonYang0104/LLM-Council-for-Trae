# M4 任务卡：ACP evidence 字段、validate 防伪与 HTML 五态（交执行 Agent）

- 日期：2026-06-11
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §3；研究线 `docs/acp-runtime-design-20260604.md` 的 Validation Contract / Artifact Contract / HTML 节
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m4-20260611`，分支 `codex/lct-acp-m4-evidence-gate-20260611`（从 `main @ c9b4536` 切出）
- 流程约束：纯本地，不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 回滚锚点：`pre-acp-m3` 已打；本阶段合并前打 `pre-acp-m4`。

## 背景与基线事实

- `main @ c9b4536`：M1–M3 已合入，`make test` 335 个 unittest 全绿；offline ACP adapter 与 transcript parser 在位。
- 移植源（只读，共享 object store）：commit `bfa7be9 feat: validate ACP runtime evidence`（P3 主体）＋ `deb9119 fix: keep ACP orchestration evidence provenance`（orchestration sidecar provenance follow-up）。研究线 notes.md Phase 5 节与 Review follow-up 节先读。
- `c52a92e`（handoff brief 文档命名）不移植。

## 目标

ACP evidence 进入 ModelCallResult / meta / manifest stage records；validate 不能被伪造 ACP artifact 绕过；HTML 面向用户展示五态（Allowed / Disabled / Requested / Denied / Used）；orchestration 层不再向 ACP call 补写 direct sidecar。

## 移植内容

1. **`ModelCallResult.to_json()` 新增 7 字段**：`runtime_backend`、`enforcement_method`、`enforcement_proof`、`disabled_tools`、`tool_permission_requests`、`acp_transcript_path`、`acp_startup_status`。direct 默认值：`runtime_backend="direct"`、`enforcement_method="direct_disallowed_tool_post_check"`、`enforcement_proof="post_run_contamination_check"`、`acp_startup_status="not_applicable"`。
2. **`EXPECTED_META_KEYS` 显式扩列 37 → 44**（这是 M1 契约测试的设计意图：新增字段必须显式过门，commit message 列出 7 个新键）。
3. `tool_policy_record()` 将 evidence 字段写入 manifest stage records；`schema_contract.py` 扩展 stage meta schema（legacy optional 兼容）。
4. **`validation.py` ACP evidence hard gate**（研究线 Validation Contract 全单照搬）：cross-gate（manifest config / stage record / meta 任一声明 ACP 即触发，防 `enforcement_method` 单点绕过）、transcript 路径安全（拒绝绝对路径 / `../`）、最小协议结构、meta 与 transcript 的 permission request 一致性、forbidden allow / forbidden used 拒绝、枚举语义校验；ACP run 不再强制要求 `.traecli.stream.jsonl`；direct / legacy artifact 不受影响。
5. **HTML 五态展示**：summary / trace 增 runtime backend、enforcement method、disabled / requested / denied / forbidden 计数、transcript path；direct / legacy 显示 `not_applicable`（**不得显示 0**——没有 ACP 证据 ≠ ACP 证明无请求）。
6. **orchestration provenance（deb9119 内容）**：`ensure_stage1_stream_sidecar()` 与 Stage 2 synthetic sidecar 只对 direct call 补写；runtime path helpers（direct 用 `.traecli.stream.jsonl`/`.traecli.stderr.log`，ACP 用 `.acp.transcript.jsonl`/`.acp.stderr.log`）；`synthetic_failed_call()` 在 `runtime_backend="acp"` 时写 ACP evidence defaults（含 `permission_mode="acp_permission_broker"`）。
7. 移植测试：`tests/contract/test_acp_evidence_validation.py`（研究线 11 个用例）＋ `test_runtime_backend_contract.py` 的 deb9119 修订（synthetic call / sidecar 分流断言）。

## 边界（不得越过）

1. 现有字段不删、不改类型；新增字段全部 optional，进 schema / validation 兼容集合（legacy run 缺字段不失败）。
2. M1 contract tests 除 `tests/support/runtime_contract.py` 的 `EXPECTED_META_KEYS` 显式扩列外零改动；golden 重生成的差异只能由 7 个新 direct 默认字段 ＋ HTML `not_applicable` 展示构成，逐项写 commit message。
3. 不实现 live transport；不改 direct 的 forbidden post-check 语义（backend 无关的拒绝逻辑保持）。
4. validate 校验范围如实声明：结构与证据一致性，不声称验证「ACP 已隐藏 schema」这类未观察状态。

## 验收标准

1. `make test` 全绿，总数 = 335 ＋ 新增（研究线 P3 为 11 ＋ runtime_backend 修订，以实测为准）。
2. forged-evidence 负向测试全绿（伪造 transcript / 路径逃逸 / 声明不一致全被拒）。
3. direct golden 重生成差异仅含上述两类；连跑两次零漂移。
4. M1 测试文件（除 runtime_contract.py 扩列）零改动；`git diff --check` 通过。
5. notes.md 追加 M4 节（红绿、golden 逐字段差异、与研究线适配差异）。
6. 红绿两 commit（test: / feat:），停在分支。

## 汇报要求

简体中文：最终测试总数与新增数、EXPECTED_META_KEYS 扩列清单、golden 逐字段差异、五态展示实现位置、所有验收命令实际结果、commit SHA、遗留风险。如实报告。
