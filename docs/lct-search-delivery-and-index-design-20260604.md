# LCT Search Delivery and Index Provenance Design

日期：2026-06-04
范围：provider stream parsing、session log conversion audit、manifest stage records、HTML summary、validate warning、Skill / README index contract

## 一句话结论

本轮把“搜索工具调用发生”和“搜索结果成功进入模型上下文”拆成两个可审计数字。HTML 首屏只展示 `调用次数` 和 `调用生效次数`；详细原因进入 stage meta、manifest、validate warning 和 metadata 附录。根目录 `<run_id>-index.md` 的 `backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`，缺失时写 `not recorded`，不得猜。

## 背景

v10 live run `lct-20260604-114802` 暴露了一个审计口径问题：D 成员 `stage1/D.meta.json` 记录 9 次 `WebSearch` tool call，stream JSON 也有对应 `tool_result` event，但 `stage1/D.traecli.session.log` 对同一批 `WebSearch` 输出记录了 9 次 `failed to convert ADK output to model format`。这说明现有“调用发生 = 搜索使用成功”的口径过强。

这不是 final 可用性的硬失败。该 run 的 validate verdict 是 `complete_ok_final`，主席最终答案没有明显依赖 D 的低可信搜索源。问题在于报告和索引没有告诉后续 reviewer：搜索调用发生了，但工具输出交付给模型的有效性被 runtime conversion error 削弱。

## 非目标

- 不改变 council protocol。
- 不改默认模型阵容。
- 不把 WebSearch / WebFetch conversion error 升级为 `invalid_artifacts`。
- 不重跑完整 benchmark。
- 不改写旧 v10 artifact。
- 不把 HTML export 和 Stage 3 chairman synthesis 合并。

## 字段定义

### `lct_web_tool_calls`

观察到的 LCT 内部 Web 工具调用次数。Web 工具只包括：

- `WebSearch`
- `WebFetch`

来源优先级：

1. stage record / meta 中的 `tool_calls`，按 tool call id 去重。
2. 如果没有结构化 `tool_calls`，不从 `tool_calls_count` 推断 Web 调用，因为 `tool_calls_count` 不能区分 Web 工具和其他工具。

### `lct_web_tool_result_calls`

stream JSON 中观察到、且 `tool_use_id` 能匹配 WebSearch / WebFetch call id 的 tool result event 数量。它表示工具输出回到了 traecli 事件流，但不单独证明模型成功消费。

当前可识别形状：

```json
{
  "type": "user",
  "subtype": "tool_result",
  "tool_name": "WebSearch",
  "tool_use_id": "call_..."
}
```

### `lct_search_conversion_errors`

session log 中与 WebSearch / WebFetch 输出转换失败相关的逻辑错误次数。第一版按以下规则计数：

1. 优先统计 JSON log 中 `msg == "failed to convert ADK output to model format"` 且 `tool` 是 WebSearch / WebFetch 的行。
2. 如果没有第 1 类行，再统计 `msg == "unsupported tool output conversion"` 且 `tool` 是 WebSearch / WebFetch 的行。
3. 不同时叠加 `unsupported tool output conversion`、`failed to convert ADK output to model format` 和 `BuildNotification failed`，避免同一次转换失败被计成 2-3 次。

v10 D 成员按这个定义是 9 次 conversion error。

### `lct_web_tool_effective_calls`

有证据证明 Web 工具结果成功进入模型上下文的次数。

第一版采用保守可审计公式：

```text
matched_web_tool_results = 与 Web tool call id 匹配的 tool_result 数量
conversion_errors = WebSearch / WebFetch 输出转换失败逻辑错误次数
lct_web_tool_effective_calls = min(lct_web_tool_calls, max(0, matched_web_tool_results - conversion_errors))
```

含义：

- 有 matching `tool_result`，但同批 session log 记录同等数量 conversion error，生效次数为 0。
- 有 tool call 但没有 matching `tool_result`，生效次数为 0。
- 有 matching `tool_result` 且没有 conversion error，生效次数等于 matching result 数，但不超过调用次数。
- legacy artifact 缺少 stream/session log 证据时，生效次数为 0，并通过 warning / metadata 说明“无法证明生效”，不把调用次数直接复制成生效次数。

## 数据流

### Provider

`parse_stream_json()` 继续解析 assistant tool calls，同时新增：

- `tool_result_calls`
- `web_tool_result_calls_count`
- `web_tool_result_call_ids`

`_query_model_once()` 在 `copy_traecli_session_files()` 后读取复制到 run artifact 的 `*.traecli.session.log`，解析 Web tool conversion error，并把结果写入 `ModelCallResult`：

```json
{
  "tool_result_calls": [...],
  "web_tool_result_calls_count": 9,
  "web_tool_result_call_ids": ["call_..."],
  "tool_output_conversion_errors": [...],
  "lct_search_conversion_errors": 9,
  "web_tool_effective_calls_count": 0
}
```

### Manifest stage records

`tool_policy_record(call)` 把 provider 新字段同步到 Stage 1 / Stage 2 / Stage 3 records。这样 HTML、validate 和 later Agent 都只读 manifest，不需要重新扫原始 stream/session log。

兼容策略：

- 新字段对旧 artifact 可选。
- 旧 artifact 缺字段时，HTML `调用生效次数` 显示 0。
- validate 不因旧字段缺失失败。

### HTML

`render_summary_cards()` 的搜索工具卡片改为只展示：

```text
搜索工具
调用次数：9
调用生效次数：0
```

不再在卡片中展示“允许：是 / 实际使用：是 / 总工具调用”。原因是首屏卡片的任务是回答用户最关心的审计问题：搜索工具有没有被调用，以及结果有没有可证明地交付给模型。更长解释进入 metadata / warning。

### Validate

validate 新增非阻断 warning check：

```text
name: search_tool_output_conversion
ok: true
severity: warning
message: "WebSearch/WebFetch tool calls observed, but effective delivery is lower than calls"
```

触发条件：

- `lct_web_tool_calls > 0`
- 且 `lct_web_tool_effective_calls < lct_web_tool_calls`

validate payload 增加顶层 `warnings` 列表；旧调用方仍可只看 `failures`。这个 warning 不改变 `complete_ok_final` / `usable_degraded_final` verdict。

## 根目录 index 契约

`<run_id>-index.md` 的 `backfill_candidates` 只能来自 terminal manifest：

```text
manifest.metadata.quorum.backfill_candidates
```

不得使用：

- 默认成员阵容。
- `models --recommend --json` 的 primary roster。
- 当前实际参与 Stage 1 的有效成员。
- 外层 Agent 自己猜的 fallback 列表。

如果 terminal manifest 没有 `metadata.quorum.backfill_candidates`，索引写：

```text
backfill_candidates: not recorded
```

这个字段是事后复盘“同一个 run 内可用候补池”的证据，不是模型推荐结果，也不是最终有效成员列表。

## 风险与取舍

- `tool_result` event 只能证明工具输出进入 traecli 事件流，不能无条件证明模型消费成功；所以必须结合 session log conversion error。
- session log conversion error 当前没有 tool_use_id，只能按同一 stage call 的逻辑错误次数扣减。若未来 runtime 提供 per-call conversion id，可把公式升级为逐 id 匹配。
- legacy artifact 的生效次数会偏保守为 0。相比误报“调用全部生效”，这更符合审计目标。
- validate warning 不阻断 final，是因为搜索交付缺陷可能只影响某个成员的证据质量，不必然导致 Stage 3 final 不可用。
