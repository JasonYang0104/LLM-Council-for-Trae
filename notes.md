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

- `7d7fc53 fix: drain cancelled model tasks before backfill`

## Phase 2：Backfill candidate pool

### 阶段目标

- 增加确定性的 backfill candidate pool，为后续 Stage 1 / Stage 2 同 run 补位提供候补来源。
- 增加 CLI / config 字段，但本阶段不把候补池接入实际 run 流程。

### 新增/修改的测试

- 新增文件：`tests/test_auto_backfill_quorum.py`
- 新增：`test_backfill_candidates_filter_runtime_models_and_prefer_same_vendor_fallback`
  - 先红后绿；红态为 `build_backfill_candidates` 不存在。
  - 断言候补只来自 runtime models，排除 hard-banned / beta / queue heat 过高 / primary / attempted，并让 `MiniMax-M2.7` 的同 vendor fallback `MiniMax-M2.5` 排在普通推荐候补前。
- 新增：`test_explicit_backfill_candidates_keep_priority_but_still_filter_unsafe_and_attempted`
  - 断言显式 `--backfill-members` 保序优先，但仍过滤 unsafe、primary 和 attempted。
- 新增：`test_build_config_accepts_backfill_and_low_quorum_flags`
  - 断言 CLI 接受 `--backfill-members`、`--no-auto-backfill`、`--low-quorum-floor`，并写入 `CouncilConfig`。

### 实现决定

- 在 `model_selection.py` 增加 `build_backfill_candidates()`，默认顺序为：
  1. 失败模型的同 vendor fallback。
  2. `recommend_model_choice()` 的推荐成员顺序。
  3. 当前 runtime safe model 顺序。
- 显式候补不作为 unsafe override；仍会过滤 hard-ban、beta、hot queue、primary、attempted 和 chairman。
- 在 `CouncilConfig` 增加：
  - `backfill_members`
  - `stage1_auto_backfill`
  - `stage2_auto_backfill`
  - `allow_low_quorum`
  - `low_quorum_floor`
- CLI 新增：
  - `--backfill-members`
  - `--no-auto-backfill`
  - `--low-quorum-floor`

### 权衡与风险

- 本阶段没有生成 `metadata.quorum`，因为还没有实际 Stage 1 / Stage 2 backfill outcome；Phase 3/4 再写 provenance。
- 显式候补仍过滤 unsafe 模型，而不是允许用户强行 backfill 到 banned/beta/hot 模型；这保持了推荐体系的安全边界。
- 当前把 `chairman` 排除在候补成员之外，避免主席专用模型意外进入 member backfill；如果未来需要 chairman 同时作为 member，应通过 primary roster 明确表达。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum -v`（3 个测试）
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum tests.test_lct_model_productization tests.test_core.CouncilCoreTests.test_build_config_defaults_to_search_enabled_without_yolo tests.test_runtime_hardening.RuntimeHardeningTests.test_build_config_accepts_stage2_and_chairman_timeouts -v`（16 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（169 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- `b0d09f6 feat: add deterministic backfill candidate selection`

## Phase 3：Stage 1 auto-backfill

### 阶段目标

- 同一个 run 内保留已成功 Stage 1 输出。
- 当有效成员低于 `min_valid_members` 时，用 Phase 2 候补池追加 backfill record，不覆盖原 primary failure。
- backfill 耗尽但有效成员数达到 `low_quorum_floor` 时，允许继续 degraded，并写入 quorum metadata。

### 新增/修改的测试

- 新增：`test_run_full_council_stage1_backfill_appends_without_overwriting_failures`
  - 先红后绿；红态证明 A/B 成功、C/D 失败时不会自动补 E。
  - 绿态断言 C/D 失败 record 保留，E 作为 `Response E` 追加，`attempt_role=backfill`，且达到 normal quorum。
- 新增：`test_run_full_council_stage1_low_quorum_degraded_when_backfill_exhausted`
  - 先红后绿；红态为 2 个有效成员时直接 `failed`。
  - 绿态断言最终 `degraded_ok`，`metadata.quorum.low_quorum_used=true`，且 `backfill_attempted` 可审计。

### 实现决定

- 新增 `backfill_stage1_responses()`：只在 `stage1_auto_backfill=True` 时执行；候补调用使用新的 file label，按当前 stage record 数递增。
- Primary Stage 1 record 增加 `attempt_role=primary`、`attempt_index=1`；backfill record 增加 `attempt_role=backfill`。
- 新增 `stage1_record_is_valid()`：有效 Stage 1 必须 `status=ok` 且没有 forbidden tool calls。
- 新增 `metadata.quorum`：
  - `min_valid_members`
  - `target_valid_members`
  - `low_quorum_floor`
  - `effective_valid_members`
  - `normal_quorum_met`
  - `low_quorum_used`
  - `backfill_used`
  - `primary_members`
  - `candidate_source`
  - `backfill_candidates`
  - `backfill_attempted`
  - `effective_stage1_members`

### 权衡与风险

- 为了不打碎既有测试，本阶段保留旧的同模型 retry 行为；当 `stage1_max_retries>0` 时，同模型 retry 仍可能覆盖原 slot。新 backfill 语义已保证追加、不覆盖。是否把 retry 也改成 append 需要后续单独处理。
- Phase 3 暂不改 Stage 2 reviewer eligibility；即使 Stage 1 有 backfill 成员，Stage 2 仍会在 Phase 4 前沿用旧 reviewer 行为。
- `metadata.quorum` 已写入 manifest，但 validate / HTML 还不会强检查或展示；这留给 Phase 5。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum -v`（5 个测试）
- 通过：旧 Stage 1/quorum 定向测试（5 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（171 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- `aba731c feat: backfill failed stage1 members in-run`

## Phase 4：Stage 2 reviewer eligibility 与 backfill

### 阶段目标

- Stage 2 的 review subjects 和 reviewers 默认都来自有效 Stage 1 成员。
- Stage 1 failed / contaminated 成员不再默认参与 Stage 2 reviewer。
- Stage 2 reviewer 失败后，如有效 review 数低于目标且仍有候补，先补一个 Stage 1 answer，再让该候补补交 Stage 2 review。

### 新增/修改的测试

- 新增：`test_stage2_reviewers_default_to_valid_stage1_models`
  - 先红后绿；红态证明旧代码仍调用 Stage 1 failed 的 M3 做 reviewer。
  - 绿态断言 Stage 2 只调用 M1/M2，`label_to_model` 也只包含有效 Stage 1 answers。
- 新增：`test_run_full_council_stage2_reviewer_failure_backfills_new_reviewer`
  - 先红后绿；红态证明 Stage 2 reviewer M2 失败后不会补 M4。
  - 绿态断言 M4 先跑 Stage 1 `Response D`，再跑 Stage 2 reviewer，并写入 `metadata.stage2_reviewers.backfill_reviewers=["M4"]`。
- 修改：`test_stage2_timeout_keeps_completed_reviews_and_marks_pending_failed`
  - 测试 fixture 按新 contract 显式提供 M1/M2 两个有效 Stage 1 record；不再期待只因 `config.members` 有 M2 就启动 M2 reviewer。

### 实现决定

- `stage2_collect_rankings()` 增加可选 `reviewers` 参数：
  - 默认 `review_subjects = valid Stage 1 records`
  - 默认 `reviewers = review_subjects`
  - backfill reviewer 场景可以只让新增 Stage 1 record 补交 review。
- Stage 2 review record 增加：
  - `reviewer_eligible`
  - `reviewer_source`
  - `review_subject_count`
  - `attempt_role`
- `run_full_council()` 增加 `metadata.stage2_reviewers`，记录 reviewer target、valid reviewers、failed reviewers、backfill reviewers 和 attempted backfill。
- Stage 2 reviewer backfill 只在 `0 < valid_stage2 < reviewer_target` 时触发；如果没有任何有效 review，仍保留现有 failed/fallback 语义，避免把完全失败伪装成可恢复。

### 权衡与风险

- 新 backfill reviewer 的 ranking 可能覆盖 `stage2/review.prompt.md` 这份共享 prompt 文件；目前 manifest/stage records 可审计，但 prompt sidecar 还不是多批次结构。后续如要完整复盘每批 Stage 2 prompt，可拆成 batch-specific prompt path。
- 新增 Stage 1 backfill 成员可作为 review subject，但旧 reviewer 不会为新增 subject 重新 review；这是 MVP 权衡。Phase 5 validate/HTML 会显式展示 backfill 和 reviewer provenance，避免用户误以为所有 reviewer 都评审了完全相同集合。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum -v`（7 个测试）
- 通过：Stage 2 timeout / metrics / all-failed 定向测试（3 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（173 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- `ce0c1ad feat: backfill stage2 reviewers from effective members`

## Phase 5：Manifest / validation / HTML / final 可见性

### 阶段目标

- low quorum、backfill、主席备选不能只埋在 manifest 内部。
- validate 能拒绝“low quorum 却标 ok”的伪健康结果。
- HTML 首屏 summary / alert 显示有效成员数、backfill、主席备选。

### 新增/修改的测试

- 修改反向测试为正向测试：
  - `test_html_summary_shows_quorum_status_card`
  - `test_html_summary_shows_chairman_fallback_card`
  - `test_html_low_quorum_degraded_banner_visible`
- 新增：
  - `test_validate_rejects_low_quorum_with_status_ok`
  - `test_validate_accepts_low_quorum_when_marked_degraded`
  - `test_validate_rejects_backfill_record_missing_attempt_role`

### 实现决定

- `render_summary_cards()` 读取 `metadata.quorum`：
  - 显示 `effective_valid_members / min_valid_members`
  - 显示 `low quorum` / `normal quorum`
  - 显示 effective Stage 1 members
  - 显示 auto-backfill attempted models
- `render_summary_cards()` 读取 `metadata.chairman`：
  - 如果 `fallback_used` 或 `fallback_from` 存在，显示“主席备选”卡片。
- `render_alerts()` 接受完整 manifest：
  - 当 `manifest.status=degraded_ok` 且 `low_quorum_used=true`，在 final answer 前显示 `Quorum 降级` warning banner。
- `validate_run()` 增加 `quorum_semantic_checks()`：
  - `low_quorum_used=true` 时，manifest status 必须是 `degraded_ok`。
  - 存在 backfill attempted model 时，对应 Stage 1 record 必须有 `attempt_role=backfill`。
  - 标记 `reviewer_eligible=true` 的 Stage 2 reviewer 必须拥有有效 Stage 1 answer。

### 权衡与风险

- 新 semantic checks 只在存在 `metadata.quorum` 时启用，避免旧 artifact 因缺新字段整体失败。
- HTML title contract 未改；quorum/backfill/fallback 文案只进入 alert/summary，不进入 `<title>` 或最终答案正文。
- `render_alerts()` 暂时只展示 low quorum banner，不展示所有 warning/failure，避免恢复旧版噪音型 failure 面板；具体 failure 仍在 evidence metadata 中可见。

### 阶段验证

- 通过：Phase 5 HTML / validate 定向测试（6 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（176 个 unittest 通过）
- 通过：`git diff --check`

### Commit

- `bbf7ca1 feat: surface backfill and low-quorum provenance`

## Phase 6：README / Skill 工作流对齐

### 阶段目标

- 删除 README 和两份 Skill 文档里的“默认失败后整轮 recommended rerun”旧口径。
- 把用户级 LCT 工作流改为同一个 run 内 auto-backfill，并明确 `--backfill-members`、backfill candidates、low quorum 和主席备选的汇报字段。
- 明确 fact pack / notes.md 边界：fact pack 直接嵌入 _lct_question.md；`notes.md` 只由外层 Agent 维护，模型不要创建或修改 notes。

### 新增/修改的测试

- 新增：`test_skills_no_longer_instruct_full_recommended_rerun_as_primary_recovery`
  - 先红后绿；红态证明 README / canonical Skill / `.trae` Skill 仍包含 `$RUN_ID-recommended`、recommended rerun 字段和旧的“不是 CLI 内部行为”口径。
  - 绿态断言三份文档都包含“同一个 run”、`auto-backfill`、`backfill candidates`、`--backfill-members`、`不整轮重跑`。
- 新增：`test_skills_require_auto_backfill_and_effective_member_reporting`
  - 锁定三份文档必须要求记录 `valid_stage1_models`、`quorum_default`、`quorum_effective`、`low_quorum_used`、`backfill_attempts`、`stage2_reviewers`、`chairman_fallback_used`。
- 新增：`test_skills_require_fact_pack_inline_and_notes_md_boundary`
  - 锁定两份 Skill 必须要求 fact pack 直接嵌入 _lct_question.md，`notes.md` 只由外层 Agent 维护，模型不要创建或修改 notes。

### 实现决定

- README Quickstart 改为：先记录 `models --recommend --json` 作为 backfill candidates 来源，run 使用 `--default-models` / `--json`，auto-backfill 默认启用；默认成员失败时 CLI 在同一个 run 内追加候补，不整轮重跑。
- canonical Skill 的 Run / Report / Hard Constraints 改为同 run auto-backfill 主路径；删除整轮推荐阵容 run 的命令和输出字段。
- `.trae` Skill 同步更新 Step 1 / 2 / 3 / 结果解读 / 产物索引，避免项目级 Skill 和全局 Skill 口径分叉。
- README Project Docs 增加 auto-backfill design / handoff 入口。

### 权衡与风险

- 文档中保留 `models --recommend --json`，但它现在只是候补来源，不再代表默认失败后的新 run。
- `--members` 仍作为用户明确自定义 primary roster 时的能力保留；默认恢复路径不使用它。

### 阶段验证

- 通过：新增 Phase 6 文档契约测试（3 个测试）
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs -v`（16 个测试）

### Commit

- `90ae5b7 docs: align skill workflow with auto-backfill`

## Phase 7：Stale run / forbidden tool fail-fast 处理决定

### 阶段目标

- 评估是否把 stale run terminalization 和 forbidden tool fail-fast 纳入本轮。

### 实现决定

- 本轮不追加 Phase 7 代码实现，作为后续 PR 保留。
- 理由：Phase 1 已覆盖 timeout / cancellation cleanup 和 termination metadata；Phase 3-6 已完成 auto-backfill 主路径、low quorum 可见性和 Skill 口径。Phase 7 属于额外 P1 防线，handoff 明确允许时间不足时后续处理，但必须在 `notes.md` 和最终 brief 写清。

### 保留风险

- Stale run：当前 validate 仍偏 read-only；对 interrupted run 的主动 terminalize 能力尚未落地。
- Forbidden tool fail-fast：当前 provider 会检测 forbidden tool call 并把 attempt 标记 failed，但“发现后尽快终止模型进程”的更激进 fail-fast 仍未实现。

### Commit

- 无代码提交；风险进入最终 PM director brief。

## Phase 8：最终 PM Director Brief

### 阶段目标

- 生成 `docs/lct-auto-backfill-implementation-brief-20260603.md`。
- 生成 `docs/lct-auto-backfill-implementation-brief-20260603.html`。
- 让读者在遗忘上下文的情况下，快速理解本轮为什么做、改了什么、如何验证、还剩什么风险。

### 最终验证

- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（179 个 unittest 通过）
- 通过：`git diff --check`
- 通过：`PYTHONPATH=src python3 -m llm_council_for_trae.cli doctor --json`
  - `ok: true`
  - `traecli` version：`0.120.32`
  - warnings：MCP servers connecting、upgrade server timeout；没有 doctor error，符合本项目 MCP-only / upgrade warning 可继续边界。
- 通过：`PYTHONPATH=src python3 -m llm_council_for_trae.cli models --recommend --json`
  - runtime models：21
  - recommendation members：Kimi-K2.6、MiniMax-M2.7、GPT-5.2、DeepSeek-V4-Pro
  - recommendation chairman：Kimi-K2.6
- 通过 live smoke：
  - 命令：`PYTHONPATH=src python3 -m llm_council_for_trae.cli run --input examples/question.md --default-models --run-id live-auto-backfill-20260603-final --timeout 180 --json`
  - run_id：`live-auto-backfill-20260603-final`
  - run status：`ok`
  - degraded：`false`
  - failures：`[]`
  - HTML：`.llm-council-for-trae/runs/live-auto-backfill-20260603-final/html/index.html`
- 通过 validate：
  - 命令：`PYTHONPATH=src python3 -m llm_council_for_trae.cli validate live-auto-backfill-20260603-final --json`
  - status：`ok`
  - terminal：`true`
  - usable_final：`true`
  - verdict：`complete_ok_final`
  - failed_stage_records：`[]`

### Commit

- `1815539 docs: add auto-backfill implementation brief`
- 当前最终验证证据将随下一条记录提交。

## Stage 2 Reviewer-Only Backfill：本轮 Phase 0 起点

### 阶段目标

- 按 `docs/lct-stage2-reviewer-only-backfill-handoff-20260603.md` 继续收紧 Stage 2 backfill 语义。
- 确认上一轮 reviewer feedback 指出的 branch-level whitespace 问题已经修复。
- 将本轮 handoff 文档纳入分支，避免最终工作树残留未跟踪规格文件。

### 初始观察

- 当前分支：`codex/lct-auto-backfill-plan-20260603`。
- 当前 HEAD 包含 `1d4fd8a docs: fix auto-backfill branch whitespace`。
- `git diff --check main..HEAD` 通过；本轮后续最终验证继续使用 branch-level whitespace 检查。
- 当前实现仍是旧语义：Stage 2 reviewer 不足时调用 `backfill_stage1_responses()`，候补模型先生成 Stage 1 answer，再作为 reviewer。

### 本轮冻结口径

- Stage 1 quorum 不足时，继续使用 Stage 1 member backfill。
- Stage 1 已满足 quorum、仅 Stage 2 reviewer 失败时，候补模型只作为 reviewer，不生成 Stage 1 answer，不进入 `label_to_model` subjects。
- `notes.md` 继续只由外层 Agent 维护；不让 LCT 成员模型创建或修改。

### 阶段验证

- 通过：`git diff --check main..HEAD`

### Commit

- `4748f0e docs: add reviewer-only backfill handoff`

## Stage 2 Reviewer-Only Backfill：Phase 1 红测

### 阶段目标

- 用测试锁定 reviewer-only backfill 新语义：Stage 1 已满足 quorum 时，Stage 2 reviewer 失败只补 reviewer，不补 Stage 1 answer。

### 测试变更

- 修改旧测试 `test_run_full_council_stage2_reviewer_failure_backfills_new_reviewer`，重命名为 `test_run_full_council_stage2_reviewer_failure_backfills_reviewer_only_when_stage1_quorum_met`。
- 新断言覆盖：
  - calls 中不得出现 `("stage1", "M4", "D")`。
  - calls 中必须出现 `("stage2", "M4", "R4")`。
  - `manifest["stages"]["stage1"]` 仍只有 M1/M2/M3。
  - `stage2/label_to_model.json` 仍只映射 Response A/B/C。
  - M4 review record 标记 `reviewer_source=stage2_reviewer_backfill`。
  - `metadata.quorum.effective_stage1_members` 不包含 M4。

### 红测证据

- 失败命令：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum.AutoBackfillQuorumTests.test_run_full_council_stage2_reviewer_failure_backfills_reviewer_only_when_stage1_quorum_met -v`
- 失败原因：当前实现仍会调用 `("stage1", "M4", "D")`，然后调用 `("stage2", "M4", "D")`。

### Commit

- `edbba4a test: define stage2 reviewer-only backfill contract`

## Stage 2 Reviewer-Only Backfill：Phase 2 实现

### 阶段目标

- 当 Stage 1 已满足 quorum、Stage 2 reviewer 失败时，只补 reviewer，不新增候选答案。

### 实现变更

- 新增 `backfill_stage2_reviewers()`：
  - 使用既有 `build_backfill_candidates()` 生成候补。
  - 排除 primary members、已有 Stage 1 attempts、已有 / 失败 Stage 2 reviewers 和 chairman。
  - 生成轻量 reviewer record，`file_label` 使用 `R4` 这类 reviewer-only label。
- `stage2_collect_rankings()` 支持 reviewer-only record：
  - review subjects 仍固定为有效 Stage 1 answers。
  - reviewer-only record 不需要 `response`，也不会成为 subject。
  - review record 标记 `reviewer_source=stage2_reviewer_backfill`、`attempt_role=reviewer_backfill`。
- `run_full_council()` 的 Stage 2 backfill 不再调用 `backfill_stage1_responses()`；quorum metadata 不再被 reviewer-only D 污染。

### 权衡与风险

- reviewer-only label 选择 `R4`，显式区分 reviewer 文件和 `Response D`。这会新增 stage2 artifact label 格式，但避免 subject / reviewer 混淆。
- 本阶段先让核心行为测试转绿；validate 和 HTML 更细语义在 Phase 3 更新。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum.AutoBackfillQuorumTests.test_run_full_council_stage2_reviewer_failure_backfills_reviewer_only_when_stage1_quorum_met -v`
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum -v`（7 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`git diff --check main`

### Commit

- `9284e82 feat: backfill stage2 reviewers without adding stage1 answers`

## Stage 2 Reviewer-Only Backfill：Phase 3 validate / HTML 可见性

### 阶段目标

- validate 接受合法 reviewer-only backfill，但拒绝 reviewer-only 模型混入 Stage 2 subject 映射。
- HTML summary 和 Stage 2 evidence 显示 reviewer-only provenance，避免用户误读为新增候选答案。

### 新增/修改的测试

- 新增：`test_validate_accepts_stage2_reviewer_only_backfill`
  - 构造 M1/M2/M3 三个有效 Stage 1 answers，M2 reviewer failed，M4 作为 `R4` reviewer-only backfill。
  - 断言 validate `status=ok`、`verdict=complete_ok_final`。
- 新增：`test_validate_rejects_stage2_reviewer_only_backfill_in_subject_mapping`
  - 构造 M4 / Response D 泄漏进 `label_to_model` 和 ranking 的坏 artifact。
  - 断言 validate 失败并出现 `stage2_reviewer_backfill_not_subject_R4`。
- 新增 HTML 测试：
  - summary card 显示 `Stage 2 reviewer backfill`、`reviewer-only`、subjects / reviewers 数。
  - Stage 2 tab 显示 `reviewer_source`、`attempt_role`、`review_subject_count`。
- 补强 Phase 1 行为测试：
  - `stage1/D.response.md` 不存在。
  - `stage2/D.review.json` 不存在。
  - `stage2/R4.review.json` 存在。

### 实现决定

- `validation.quorum_semantic_checks()` 按 `reviewer_source` 分支：
  - `stage1_ok` / `stage1_backfill` reviewer 必须有有效 Stage 1 answer。
  - `stage2_reviewer_backfill` reviewer 不要求 Stage 1 answer，但必须不出现在 `label_to_model` subject models 中，并且 parsed ranking 必须精确匹配 subject labels。
- HTML summary 新增 Stage 2 reviewer backfill card。
- Stage 2 tab 和 provider trace 显示 reviewer source / role / subject count。

### 阶段验证

- 通过：Phase 3 validate / HTML 定向测试（4 个测试）
- 通过：`tests.test_auto_backfill_quorum` + Phase 3 定向测试（11 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`git diff --check main`

### Commit

- `27a53c1 feat: validate and display reviewer-only backfill provenance`

## Stage 2 Reviewer-Only Backfill：Phase 4 docs / report fields

### 阶段目标

- 让 manifest、README、canonical Skill、`.trae` Skill 和 PM brief 都明确区分 Stage 1 member backfill 与 Stage 2 reviewer-only backfill。
- 修正旧 brief 中“Stage 2 reviewer 失败先补 Stage 1 answer”的过时表述。
- 把 whitespace 验证口径固定为 branch-level `git diff --check main..HEAD`。

### 红灯

- 新增 report field 断言后，相关行为测试先失败于 `KeyError: 'reviewer_count'`。
- 新增文档契约测试后，README、`.trae` Skill 和 brief 都缺少 `member backfill` / `reviewer-only backfill` 等新口径。

### 实现变更

- `metadata.stage2_reviewers` 新增：
  - `review_subject_labels`
  - `review_subject_models`
  - `reviewer_count`
  - `stage1_backfill_members`
  - `stage2_reviewer_backfill`
- README 增加 reviewer-only backfill 路径说明和 Project Docs 入口。
- canonical Skill 与 `.trae` Skill 增加交付索引字段：
  - `stage1_backfill_members`
  - `stage2_reviewer_backfill`
  - `review_subject_count`
  - `reviewer_count`
- Markdown / HTML director brief 改为 reviewer-only 语义，并删除 clean worktree `git diff --check` 作为最终证据的旧口径。

### 阶段验证

- 通过：新增 report field + docs 契约定向测试（2 个测试）
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_auto_backfill_quorum tests.test_global_install_skill_docs -v`（24 个测试）
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`git diff --check main..HEAD`
- 通过：`git diff --check`

### Commit

- 待提交：`docs: clarify reviewer-only backfill reporting`
