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

- 待提交：`feat: surface backfill and low-quorum provenance`
