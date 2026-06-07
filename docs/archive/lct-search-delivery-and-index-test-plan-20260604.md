# LCT Search Delivery and Index Provenance Test Plan

日期：2026-06-04
范围：TDD tests for provider, manifest propagation, HTML, validation, README / Skill index contract

## 测试目标

本轮测试要锁住两个行为：

1. WebSearch / WebFetch 的调用次数和生效次数必须分开，conversion error 不得被包装成成功搜索。
2. `<run_id>-index.md` 的 `backfill_candidates` 来源必须是 terminal manifest 的 `metadata.quorum.backfill_candidates`，缺失时写 `not recorded`。

## TDD 策略

按垂直切片推进，不一次性写完所有测试：

1. 先写 HTML summary 测试，让用户可见口径红灯。
2. 再写 provider parser / session log 测试，让数据来源红灯。
3. 再写 council manifest propagation 测试，让 stage record 红灯。
4. 再写 validate warning 测试，让校验面红灯。
5. 最后写 docs / Skill contract 测试，让 index 来源红灯。

每个切片先运行目标测试观察失败，再做最小实现让它变绿。为了避免提交历史留下故意失败节点，红灯证据记录在 `notes.md`，提交时包含对应绿灯实现。

## 行为覆盖

### 1. HTML 搜索卡片

建议位置：`tests/test_core.py`

新增或修改测试：

```text
test_html_search_card_shows_calls_and_effective_calls
```

fixture：

- manifest stage record 有 2 个 WebSearch calls。
- 有 2 个 matching tool_result events 对应的派生字段。
- 有 2 个 conversion errors。

断言：

- HTML 包含 `搜索工具`。
- HTML 包含 `调用次数：2`。
- HTML 包含 `调用生效次数：0`。
- HTML 不再包含旧卡片文案 `允许：`、`实际使用：`、`Web 工具调用：`。

同时更新现有 HTML 测试中对旧文案的断言。

### 2. Search summary 派生字段

建议位置：`tests/test_lct_model_productization.py` 或 `tests/test_core.py`

新增测试：

```text
test_search_summary_distinguishes_calls_from_effective_calls
```

fixture：

- `tool_calls` 有 2 个 WebSearch。
- `web_tool_result_call_ids` 有 2 个匹配 id。
- `lct_search_conversion_errors` 为 1 或 2。

断言：

- `lct_web_tool_calls == 2`
- `lct_web_tool_result_calls == 2`
- `lct_search_conversion_errors == 2`
- `lct_web_tool_effective_calls == 0`

再覆盖 partial case：

- 2 个 calls。
- 2 个 matching results。
- 1 个 conversion error。
- effective 为 1。

### 3. Provider stream parser

建议位置：`tests/test_core.py`

新增测试：

```text
test_parse_stream_json_tracks_web_tool_results_separately
```

构造 stream JSON：

- assistant message 发起 `WebSearch` call id `tc1`。
- user `tool_result` 带 `tool_name=WebSearch`、`tool_use_id=tc1`。
- 另一个 non-matching 或 non-web tool_result 不应计入 Web result。

断言：

- `tool_calls_count == 1`
- `tool_calls[0].name == "WebSearch"`
- `tool_result_calls` 包含 `tc1`。
- `web_tool_result_calls_count == 1`
- `web_tool_result_call_ids == ["tc1"]`

### 4. Session log conversion parser

建议位置：`tests/test_core.py` 或新增 provider-focused 测试

新增测试：

```text
test_parse_session_log_counts_web_conversion_errors_once
```

构造 JSON session log：

- 一组 `unsupported tool output conversion`
- 一组 `failed to convert ADK output to model format`
- 一组 `BuildNotification failed`
- tool 为 `WebSearch`

断言：

- conversion error 逻辑计数为 1，不是 3。

再覆盖：

- 两组 WebSearch conversion failure 计为 2。
- 非 Web 工具 conversion failure 不计入 `lct_search_conversion_errors`。

### 5. Provider result serialization

建议位置：`tests/test_core.py`

新增测试：

```text
test_model_call_result_serializes_search_delivery_fields
```

构造 `ModelCallResult`，断言 `to_json()` 输出：

- `tool_result_calls`
- `web_tool_result_calls_count`
- `web_tool_result_call_ids`
- `tool_output_conversion_errors`
- `lct_search_conversion_errors`
- `web_tool_effective_calls_count`

### 6. Council manifest propagation

建议位置：`tests/test_core.py` 或 `tests/test_runtime_hardening.py`

新增测试：

```text
test_tool_policy_record_persists_search_delivery_fields
```

用 fake `ModelCallResult` 经过 `tool_policy_record(call)`，断言 stage record 里有搜索交付字段。这样 Stage 1 / 2 / 3 只要沿用 `tool_policy_record`，manifest propagation 自动覆盖。

### 7. Validate warning

建议位置：`tests/test_core.py` 或 `tests/test_validation.py`

新增测试：

```text
test_validate_warns_when_web_tool_delivery_is_lower_than_calls
```

构造完整最小 artifact：

- manifest status 为 `ok`。
- Stage 1 record `status=ok`。
- `lct_web_tool_calls=2`。
- `lct_web_tool_effective_calls=0`。

断言：

- `validate_run()` 的 `status == "ok"`。
- `verdict == "complete_ok_final"`。
- 顶层 `warnings` 或 checks 中出现 `search_tool_output_conversion`。
- `failures` 为空。

### 8. README / Skill index contract

建议位置：`tests/test_global_install_skill_docs.py`

新增测试：

```text
test_readme_and_skills_require_manifest_sourced_backfill_candidates
```

覆盖文件：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`

必含短语：

- `metadata.quorum.backfill_candidates`
- `terminal manifest`
- `not recorded`
- `不得从默认成员阵容`
- `不得从 models --recommend --json 的 primary roster`
- `不得从实际有效 Stage 1 成员`

### 9. Root index 字段扩展

同一 docs contract 测试还应要求 Skill 的 `$RUN_ID-index.md` 字段列表包含：

- `lct_web_tool_effective_calls`
- `lct_search_conversion_errors`
- `backfill_candidates`

如果 README quickstart 的字段行太长，可以拆成专门列表，但测试要锁定字段存在。

## 目标命令

红绿切片常用命令：

```bash
PYTHONPATH=src python3 -m unittest tests.test_core.CouncilCoreTests.test_html_search_card_shows_calls_and_effective_calls -v
PYTHONPATH=src python3 -m unittest tests.test_core.CouncilCoreTests.test_parse_stream_json_tracks_web_tool_results_separately -v
PYTHONPATH=src python3 -m unittest tests.test_core.CouncilCoreTests.test_parse_session_log_counts_web_conversion_errors_once -v
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_and_skills_require_manifest_sourced_backfill_candidates -v
```

阶段性验证：

```bash
PYTHONPATH=src python3 -m unittest tests.test_core tests.test_lct_model_productization tests.test_global_install_skill_docs -v
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

最终验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

`traecli` 可用时追加：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
```

## 验收标准

- HTML 搜索卡片只显示调用次数和调用生效次数。
- v10 类似场景能被表达为 `调用次数：9`、`调用生效次数：0`。
- manifest stage records 带有搜索交付字段，validate 和 HTML 不需要重新读取 raw log。
- validate 对 conversion issue 给 warning，不改变可用 final verdict。
- README、canonical Skill、`.trae` Skill 都明确 `backfill_candidates` 来源于 terminal manifest `metadata.quorum.backfill_candidates`，缺失时写 `not recorded`。
- 完整测试和 whitespace 检查通过。
