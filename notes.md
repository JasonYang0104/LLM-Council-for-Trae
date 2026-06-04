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

- `0dea435 docs: start search delivery handoff notes`

## 阶段 1：设计方案与测试方案

### 阶段目标

- 正式沉淀搜索调用 / 生效计数的数据定义。
- 明确 conversion error 不应把 run 判成不可用。
- 明确 HTML、manifest、validate、Skill / README 的数据流和兼容策略。
- 先写测试方案，后续实现按红绿切片推进。

### 关键证据

- v10 `lct-20260604-114802` 的 D 成员有 9 次 `WebSearch` tool call。
- 同一 stream JSON 有 9 个 matching `tool_result` event。
- 同一 session log 有 9 次 `failed to convert ADK output to model format`，tool 为 `WebSearch`。
- 因此 `tool_result` 只能证明输出回到 traecli 事件流，不能单独证明模型成功消费。第一版必须结合 session log conversion error 扣减。

### 规范未覆盖但需要明确的执行决定

- `lct_web_tool_effective_calls = min(lct_web_tool_calls, max(0, matched_web_tool_results - conversion_errors))`。
- conversion error 逻辑计数优先使用 `failed to convert ADK output to model format`，避免和 `unsupported tool output conversion` / `BuildNotification failed` 重复计数。
- legacy artifact 缺少搜索交付字段时，HTML 生效次数保守显示 0；不把调用次数复制成生效次数。
- validate warning 不改变 `complete_ok_final` 或 `usable_degraded_final`。

### 阶段验证

- 通过：`git diff --check`

### Commit

- `02f91c1 docs: design search delivery and index provenance`

## 阶段 2：TDD 红灯测试

### 阶段目标

- 用测试证明当前实现仍把 Web 工具调用和搜索结果生效混在一起。
- 用测试证明 provider 尚未解析 Web tool result 和 session log conversion error。
- 用测试证明 manifest stage record、HTML、validate 和文档契约都缺本轮字段。

### 新增/修改的测试

- `test_search_summary_distinguishes_calls_from_effective_calls`
- `test_parse_stream_json_tracks_web_tool_results_separately`
- `test_parse_session_log_counts_web_conversion_errors_once`
- `test_model_call_result_serializes_search_delivery_fields`
- `test_tool_policy_record_persists_search_delivery_fields`
- `test_html_search_card_shows_calls_and_effective_calls`
- `test_validate_warns_when_web_tool_delivery_is_lower_than_calls`
- `test_readme_and_skills_require_manifest_sourced_backfill_candidates`
- `test_skills_index_contract_includes_search_delivery_fields`

### 红灯证据

- 失败命令：`PYTHONPATH=src python3 -m unittest tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_distinguishes_calls_from_effective_calls tests.test_core.CouncilCoreTests.test_parse_stream_json_tracks_web_tool_results_separately tests.test_core.CouncilCoreTests.test_parse_session_log_counts_web_conversion_errors_once tests.test_core.CouncilCoreTests.test_model_call_result_serializes_search_delivery_fields tests.test_core.CouncilCoreTests.test_tool_policy_record_persists_search_delivery_fields tests.test_core.CouncilCoreTests.test_html_search_card_shows_calls_and_effective_calls tests.test_core.CouncilCoreTests.test_validate_warns_when_web_tool_delivery_is_lower_than_calls tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_and_skills_require_manifest_sourced_backfill_candidates tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_skills_index_contract_includes_search_delivery_fields -v`
- 结果：9 个测试运行，当前旧实现出现 5 个 failure、7 个 error。
- 失败点符合预期：
  - `summarize_search_usage()` 缺 `lct_web_tool_result_calls` / `lct_web_tool_effective_calls`。
  - `parse_stream_json()` 缺 `tool_result_calls`。
  - `parse_session_log_search_delivery` 尚不存在。
  - `ModelCallResult` 尚不接受搜索交付字段。
  - `tool_policy_record()` 没有把搜索交付字段写入 stage record。
  - HTML 搜索卡片仍显示旧文案“允许 / 实际使用 / Web 工具调用”。
  - `validate_run()` 缺顶层 warning。
  - README / canonical Skill / `.trae` Skill 缺 `metadata.quorum.backfill_candidates` 来源契约。
- 通过：`git diff --check`

### Commit

- `1007220 test: cover search delivery and index provenance gaps`

## 阶段 3：provider / manifest 搜索生效证据

### 阶段目标

- `parse_stream_json()` 解析 WebSearch / WebFetch 的 matching `tool_result` event。
- 解析复制后的 `session.log`，把 Web 工具 output conversion error 折叠成逻辑错误次数。
- `ModelCallResult.to_json()` 持久化搜索交付字段。
- `tool_policy_record()` 把搜索交付字段传播到 manifest stage records。

### 实现决定

- `tool_result_calls` 当前只记录 WebSearch / WebFetch result；非 Web 工具不混入 `lct_web_*` 口径。
- `parse_session_log_search_delivery()` 优先统计 `failed to convert ADK output to model format`，只有没有这类行时才退回 `unsupported tool output conversion`，避免同一转换失败重复计数。
- `web_tool_effective_calls_count` 在 provider 正常路径中按 `matched_results - conversion_errors` 计算，并限制不超过 Web 工具调用数。
- stage record 同时写入底层字段和 LCT alias：`web_tool_effective_calls_count` 与 `lct_web_tool_effective_calls`。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_core.CouncilCoreTests.test_parse_stream_json_tracks_web_tool_results_separately tests.test_core.CouncilCoreTests.test_parse_session_log_counts_web_conversion_errors_once tests.test_core.CouncilCoreTests.test_model_call_result_serializes_search_delivery_fields tests.test_core.CouncilCoreTests.test_tool_policy_record_persists_search_delivery_fields -v`
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`git diff --check`

### Commit

- `be7a285 feat: record effective web tool delivery evidence`

## 阶段 4：HTML / validate 搜索生效展示

### 阶段目标

- `summarize_search_usage()` 产出调用次数、tool result 次数、conversion error 次数和调用生效次数。
- HTML 搜索工具卡片只展示“调用次数”和“调用生效次数”。
- validate 对调用次数大于生效次数的 run 输出 warning，不改变可用 final verdict。

### 实现决定

- HTML 不再展示“允许 / 实际使用 / Web 工具调用 / 总工具调用”，避免把 policy allowed、tool call observed 和 result delivered 混在首屏。
- `summarize_search_usage()` 对没有显式 effective 字段的 stage record 按同一公式派生：`matched_results - conversion_errors`，并限制不超过本 stage Web call 数。
- `validate_run()` 新增顶层 `warnings`，`failures` 仍只包含硬失败 check。`search_tool_output_conversion` warning 的 `ok` 为 true，`severity` 为 `warning`。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_exposes_lct_aliases tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_distinguishes_calls_from_effective_calls tests.test_core.CouncilCoreTests.test_search_summary_separates_allowed_from_used tests.test_core.CouncilCoreTests.test_html_search_card_shows_calls_and_effective_calls tests.test_core.CouncilCoreTests.test_validate_warns_when_web_tool_delivery_is_lower_than_calls tests.test_core.CouncilCoreTests.test_validate_and_export_html_from_artifacts -v`
- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`git diff --check`

### Commit

- `82a386d feat: display effective search calls in html and validate`

## 阶段 5：Skill / README index contract 修正

### 阶段目标

- README、canonical Skill 和 `.trae` Skill 都明确 `backfill_candidates` 的唯一来源。
- 根目录索引字段加入 `lct_web_tool_effective_calls` 和 `lct_search_conversion_errors`。
- 文档禁止从默认成员阵容、`models --recommend --json` primary roster 或有效 Stage 1 成员猜测候补池。

### 实现决定

- `$RUN_ID-index.md` / `<run_id>-index.md` 的 `backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`。
- 如果 terminal manifest 缺该字段，索引写 `backfill_candidates: not recorded`。
- `.trae` Skill 增加一行 `$RUN_ID-index.md` 字段清单，使它和 canonical Skill 的索引契约结构一致，便于测试锁定。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_quickstart_index_contract_includes_input_and_search_evidence tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_and_skills_require_manifest_sourced_backfill_candidates tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_skills_index_contract_includes_search_delivery_fields -v`
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_distinguishes_calls_from_effective_calls tests.test_core.CouncilCoreTests.test_parse_stream_json_tracks_web_tool_results_separately tests.test_core.CouncilCoreTests.test_html_search_card_shows_calls_and_effective_calls tests.test_core.CouncilCoreTests.test_validate_warns_when_web_tool_delivery_is_lower_than_calls -v`
- 通过：`git diff --check`

### Commit

- `c985dfc docs: require manifest-sourced backfill candidates`

## 阶段 6：subagent reviewer 反馈处理

### Reviewer 结论

- Helmholtz：P1 / blocker 无。P3 指出 `summarize_search_usage()` 对 Web tool call 使用全局 id 去重，但 persisted effective 逐 record 相加，极端情况下可能 `effective > calls`。
- Locke：blocker 无。P3 指出 docs contract 测试没有锁住“不得从实际有效 Stage 1 成员猜测候补池”。

### 处理决定

- `summarize_search_usage()` 的 Web tool call 去重 scope 改为 per stage record，同一 record 内重复 id 去重，不同 record / session 的同名 id 不互相吞掉。
- persisted effective 先按本 record 的 observed calls clamp，最终汇总再 clamp 到 observed aggregate calls，保证 `lct_web_tool_effective_calls <= lct_web_tool_calls`。
- docs contract 测试和测试计划都加入 `不得从实际有效 Stage 1 成员` 必含短语，避免以后文档回退但测试仍通过。

### 阶段验证

- 通过：`PYTHONPATH=src python3 -m unittest tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_distinguishes_calls_from_effective_calls tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_deduplicates_web_tool_calls_per_stage_record tests.test_lct_model_productization.LctModelProductizationTests.test_search_summary_clamps_persisted_effective_calls_to_observed_calls -v`
- 通过：`PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_and_skills_require_manifest_sourced_backfill_candidates -v`
- 通过：`git diff --check`

### Commit

- `e30b723 fix: harden search summary and index contract tests`

## 阶段 7：最终 brief 与全量验证

### 阶段目标

- 生成 PM director 风格简报 Markdown 和 HTML。
- 复跑完整验证，确认 reviewer hardening 和 brief 产物都纳入验收。
- 记录 live runtime availability，不发起新的完整 council benchmark。

### 产物

- `docs/lct-search-delivery-and-index-brief-20260604.md`
- `docs/lct-search-delivery-and-index-brief-20260604.html`

### Live 检查

- 通过：`PYTHONPATH=src llm-council-for-trae doctor --json`
  - exit 0，payload `ok=true`。
  - `traecli doctor` 内部有 MCP connecting warning 和 update server warning；无 runtime error。
  - model list count：21。
- 通过：`PYTHONPATH=src llm-council-for-trae models --recommend --json`
  - exit 0。
  - recommendation members：`Kimi-K2.6`、`MiniMax-M2.7`、`GPT-5.2`、`DeepSeek-V4-Pro`。
  - chairman：`Kimi-K2.6`。

### 全量验证

- 通过：`PYTHONPATH=src python3 -m compileall src`
- 通过：`make test`（202 tests OK，输出 `degraded_ok`）
- 通过：`git diff --check`

### Commit

- `docs: add search delivery implementation brief`
