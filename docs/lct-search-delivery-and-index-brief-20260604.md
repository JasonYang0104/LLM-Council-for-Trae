# LCT 搜索生效计数与索引补位候选修正简报

日期：2026-06-04  
分支：`codex/lct-search-delivery-index-20260604`  
置信度：高

## 结论

本轮已把 v10 live E2E 复盘暴露的两个审计缺口收束到代码、测试、文档和 Skill 契约里：

1. HTML 搜索卡片不再把“允许搜索”“观察到 tool call”和“搜索结果生效”混成一个口径。现在只展示 `调用次数` 和 `调用生效次数`。
2. LCT manifest stage records 会持久化 WebSearch / WebFetch 的 result 交付证据、conversion error 和 effective call 计数。
3. `validate` 对“调用次数大于调用生效次数”的 run 给 warning，但不把已有可用 final 判失败。
4. `<run_id>-index.md` 的 `backfill_candidates` 来源被固定为 terminal manifest 的 `metadata.quorum.backfill_candidates`；缺失时写 `not recorded`，不得从默认成员阵容、`models --recommend --json` primary roster 或实际有效 Stage 1 成员猜测。

这次没有重跑 v10，也没有做新的 live council benchmark。原因很简单：本轮目标是修审计口径和索引契约，不是评测模型表现。旧 v10 artifacts 保持为复盘证据，不改写。

## 实现摘要

### P1：搜索调用和生效拆分

核心数据流已经闭合：

- `src/llm_council_for_trae/provider.py`
  - `parse_stream_json()` 解析 WebSearch / WebFetch 的 `tool_result` event。
  - `parse_session_log_search_delivery()` 从复制后的 `session.log` 统计 Web tool output conversion failures。
  - `ModelCallResult` 持久化 `web_tool_result_calls_count`、`web_tool_result_call_ids`、`lct_search_conversion_errors`、`web_tool_effective_calls_count`。
- `src/llm_council_for_trae/council.py`
  - `tool_policy_record()` 把上述字段传播到 manifest stage records。
- `src/llm_council_for_trae/html_export.py`
  - `summarize_search_usage()` 产出 `lct_web_tool_calls`、`lct_web_tool_result_calls`、`lct_search_conversion_errors`、`lct_web_tool_effective_calls`。
  - HTML summary card 改为只展示 `调用次数：N` 和 `调用生效次数：M`。
  - reviewer 反馈后，Web tool call 去重 scope 改为 per stage record，并把 persisted effective clamp 到 observed calls，避免出现 `effective > calls`。
- `src/llm_council_for_trae/validation.py`
  - `validate_run()` 新增顶层 `warnings`。
  - 有 WebSearch / WebFetch 调用但 effective 低于 calls 时，输出 `search_tool_output_conversion` warning，不改变 usable final verdict。

### P2：索引补位候选来源固定

已更新：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`
- `tests/test_global_install_skill_docs.py`

冻结规则：

```text
backfill_candidates 必须来自 terminal manifest 的 metadata.quorum.backfill_candidates。
如果 terminal manifest 没有记录该字段，写 backfill_candidates: not recorded。
不得从默认成员阵容、models --recommend --json 的 primary roster、实际有效 Stage 1 成员猜测候补池。
```

## 验证证据

阶段性验证已覆盖：

- 基线：`PYTHONPATH=src python3 -m compileall src`、`make test`、`git diff --check`
- TDD red tests：先确认旧实现缺字段、缺 warning、缺文档契约。
- Targeted green tests：
  - Web tool result 解析。
  - session log conversion error 计数。
  - `ModelCallResult` serialization。
  - manifest stage record 字段传播。
  - HTML 搜索卡片文案。
  - validate warning。
  - README / Skill index contract。
  - reviewer 追加的 per-record dedupe 和 effective clamp 回归测试。
- Live runtime availability：
  - `PYTHONPATH=src llm-council-for-trae doctor --json`：exit 0，`ok=true`；`traecli doctor` 内部有 MCP / update warnings，无 runtime error。
  - `PYTHONPATH=src llm-council-for-trae models --recommend --json`：exit 0，返回 21 个模型，推荐成员为 `Kimi-K2.6`、`MiniMax-M2.7`、`GPT-5.2`、`DeepSeek-V4-Pro`，主席为 `Kimi-K2.6`。
- Final full verification：
  - `PYTHONPATH=src python3 -m compileall src`：pass。
  - `make test`：pass，202 tests OK。
  - `git diff --check`：pass。

## 提交链

- `0dea435 docs: start search delivery handoff notes`
- `02f91c1 docs: design search delivery and index provenance`
- `1007220 test: cover search delivery and index provenance gaps`
- `be7a285 feat: record effective web tool delivery evidence`
- `82a386d feat: display effective search calls in html and validate`
- `c985dfc docs: require manifest-sourced backfill candidates`
- `e30b723 fix: harden search summary and index contract tests`
- `docs: add search delivery implementation brief`

## 未做事项

- 没有重跑完整 live council。当前 live checks 只证明 `traecli`、doctor 和 model recommendation 可用。
- 没有改写 v10 artifacts。旧 run 是复盘证据，不应被新实现覆盖。
- 没有改变模型阵容、quorum policy 或 chairman fallback policy。
- 没有把 WebSearch conversion warning 升级成 hard failure；这是刻意选择，因为 conversion issue 代表搜索交付审计风险，不等于已有 final 必然不可用。
