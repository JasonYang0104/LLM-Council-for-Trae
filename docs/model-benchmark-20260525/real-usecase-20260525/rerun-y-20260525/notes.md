# `traecli --yolo` 失败 case 复测运行 notes

## 运行背景

目标：针对上一轮真实用例评测里 `GPT-5.4` / `MiniMax-M2.7` 的失败 case，按评论回复里的策略重跑，确认异常到底是模型能力、慢、排队、授权、工具链，还是 `traecli` 启动参数缺 `-y` 导致。

本次只重跑 4 个旧失败组合：

| usecase | model | 旧结果 |
|---|---|---|
| `usecase_2` | `GPT-5.4` | 605.63s failed，11,477 chars partial output |
| `usecase_3` | `GPT-5.4` | 605.88s failed，0 chars |
| `usecase_2` | `MiniMax-M2.7` | 605.72s failed，0 chars |
| `usecase_3` | `MiniMax-M2.7` | 605.35s failed，16,614 chars partial output |

复测策略：

```text
runtime: traecli --yolo
query_timeout: 660s
outer_timeout: 735s
concurrency: 2
output_dir: docs/model-benchmark-20260525/real-usecase-20260525/rerun-y-20260525
```

先用 `traecli --yolo --version` 做 smoke test，确认 `-y` 参数可被当前 runtime 接受：

```text
coco version 0.120.32
build date: 2026-05-18T10:01:36Z
build commit: 1066fe26cab49cbcea6cf9d4c257cda74e6437bb
```

## 运行中观察

### 1. 不是典型排队

4 个复测 case 的 stream/meta 扫描里，`queue` / `queued` / `排队` marker 都是 0。到目前为止没有证据说明旧失败是排队造成。

### 2. `-y` 确实改变了权限模式

`GPT-5.4 usecase_2` 的最终 result 行里出现：

```text
permission_mode: bypass_permissions
```

这说明 `traecli --yolo` 至少在运行层面进入了免授权权限模式。上一轮 artifact 里的 session metadata 是 `permission_mode: default`，因此上一轮不能作为完整权限模式下的模型结论。

### 3. 授权不是这批失败的主要解释

session log 里没有看到 `authorize` / `approval` / `confirm` / `denied` 这类需要人工授权的直接阻断信号。

注意：stream scanner 里有 `permission_marker_count`，但主要来自 system init/status 的 `permission_mode` 字段，不代表授权弹窗。

### 4. 真正高频问题是工具输出转换和长工具链收口

复测后仍可见大量 runtime 层错误：

```text
failed to convert ADK output to model format
BuildNotification failed
unsupported tool output conversion
read SSE / context deadline exceeded
```

这些错误不一定直接导致所有 case 失败，因为 `GPT-5.4 usecase_3` 和 `MiniMax-M2.7 usecase_2` 在有工具转换错误的情况下仍成功结束。但它们是当前 live `traecli` 工具型长任务里最需要复盘的稳定性风险。

## 复测结果

| case | status | latency | response | 对比旧结果 | 结论 |
|---|---:|---:|---:|---|---|
| `GPT-5.4 / usecase_2` | failed | 666.18s | 23 chars | 旧：605.63s failed，11,477 chars | `-y` 没救回；仍是长工具链 + deadline |
| `GPT-5.4 / usecase_3` | ok | 415.67s | 18,560 chars | 旧：605.88s failed，0 chars | `-y` 明显救回 |
| `MiniMax-M2.7 / usecase_2` | ok | 313.41s | 5,551 chars | 旧：605.72s failed，0 chars | `-y` 明显救回 |
| `MiniMax-M2.7 / usecase_3` | ok | 114.54s | 5,176 chars | 旧：605.35s failed，16,614 chars but failed | `-y` 明显救回 |

汇总：

```text
total: 4
success: 3
failed: 1
```

## 单 case 诊断

### `GPT-5.4 / usecase_2`

状态：仍失败。

关键证据：

```text
latency_seconds: 666.18
result_subtype: error_during_execution
error: failed to call agent: model 'GPT-5.4': context deadline exceeded; context deadline exceeded
tool_calls: 60
tool_results: 60
failed to convert: 86
BuildNotification failed: 43
deadline exceeded: 3
queue markers: 0
authorize / approval / confirm / denied: 0
```

判断：这不是权限问题，也不是排队问题。它是 `GPT-5.4` 在 `usecase_2` 这种资料调研型问题里主动展开了过长工具链，输入 token 被推到极高，最后在 `660s` 仍没有干净结束。

这说明 `GPT-5.4` 不是不能用，但不适合在“开放式联网调研 + 必等 + 固定 timeout”模式下裸跑。需要限制工具预算、限制 turn 数、或者把它放在 non-blocking / high-quality late answer 位置。

### `GPT-5.4 / usecase_3`

状态：成功。

关键证据：

```text
latency_seconds: 415.67
response_chars: 18,560
result_subtype: success
tool_calls: 16
tool_results: 16
failed to convert: 30
BuildNotification failed: 15
deadline exceeded: 0
queue markers: 0
```

判断：上一轮这个 case 的空失败不能再算 GPT 模型能力问题。`-y` 加更长 timeout 后，它成功产出长文。仍需注意：工具转换错误存在，但没有阻断最终 success。

### `MiniMax-M2.7 / usecase_2`

状态：成功。

关键证据：

```text
latency_seconds: 313.41
response_chars: 5,551
result_subtype: success
tool_calls: 31
tool_results: 31
failed to convert: 56
BuildNotification failed: 28
deadline exceeded: 0
queue markers: 0
```

判断：上一轮空失败大概率不能归因为 MiniMax 本身。`-y` 后成功，说明它可以进入候选池；但工具转换错误仍多，且输出质量需要另行人工评估。

### `MiniMax-M2.7 / usecase_3`

状态：成功。

关键证据：

```text
latency_seconds: 114.54
response_chars: 5,176
result_subtype: success
tool_calls: 1
tool_results: 1
failed to convert: 0
BuildNotification failed: 0
deadline exceeded: 0
queue markers: 0
```

判断：这一 case 被 `-y` 完整救回，而且工具链极短。上一轮有 16,614 chars partial output 但 runtime failed，说明旧异常更像收口/权限/事件流问题，不是 MiniMax 没能力回答。

## 当前产品判断修正

旧简报里“`GPT-5.4` / `MiniMax-M2.7` 不适合默认必等”的表述需要进一步收敛：

1. `MiniMax-M2.7`：不能继续按旧结果打入“暂不推荐默认”。`-y` 后 2/2 成功，应重新纳入候选池，但需要补质量评估。
2. `GPT-5.4`：不是简单不可用。它在 `usecase_3` 被救回，但 `usecase_2` 仍失败。更准确定位是“高质量但工具链发散风险高”，不适合作为开放式联网调研任务的必等阻塞项。
3. quorum 策略仍然成立。理由不是“某两个模型弱”，而是 live runtime 有多类真实失败模式：工具链发散、tool output conversion、SSE deadline、partial output、权限模式差异。
4. `traecli --yolo` 应进入 CLC provider 默认命令或成为显式可配置项。否则评测和真实运行会继续误杀模型。

## 暴露出的工程问题

### 1. CLC provider 当前没有 `-y`

`src/coco_llm_council/provider.py` 当前拼接命令是：

```text
traecli -p <prompt> -c model.name=<model> --output-format stream-json --query-timeout <timeout>s --session-id <id>
```

需要改成默认带 `-y`，或提供显式配置：

```text
traecli --yolo -p <prompt> ...
```

### 2. 临时脚本的 command redaction 有 bug

本次脚本复用了 `safe_command(cmd)`。原函数假设 prompt 永远在 `cmd[2]`，但加了 `-y` 后参数位置变成：

```text
cmd[0] = traecli
cmd[1] = -y
cmd[2] = -p
cmd[3] = <prompt>
```

结果：artifact 里 `command` 字段错误地把 `-p` 替换成 `<prompt 2 chars>`，但真实 prompt 留在了 `cmd[3]`。这会污染 artifact，可读性和隐私边界都不对。

后续要把 redaction 改成按 `-p` 参数名定位，而不是按固定 index。

### 3. 需要区分 partial output 的价值

`GPT-5.4 / usecase_2` 本次失败只有 23 chars parsed response，但 raw stream 里可能仍有较多中间 assistant/tool 内容。旧结果里同 case 有 11,477 chars partial output。后续不能只看最终 parsed response，应该增加：

```text
final_response_chars
assistant_content_chars_total
last_assistant_content_chars
raw_partial_recoverable: true/false
```

### 4. 工具型任务需要工具预算

`GPT-5.4 / usecase_2` 本次有：

```text
tool_calls: 60
input_tokens: 1,228,128
num_turns: 24
```

这已经不是普通“模型慢”，而是工具型任务无限膨胀。对 CLC 来说，合理控制项至少包括：

```text
max_tool_calls_per_member
max_turns_per_member
max_search_calls
max_fetch_calls
tool_budget_exceeded -> dropped_tool_budget
```

## 下一步建议

短期：

1. 修 `TraeCliProvider`：默认支持 `-y`，并在 artifact 里记录 `permission_mode`。
2. 修 `safe_command`：按 `-p` 定位 prompt 并 redacts。
3. 用 `traecli --yolo` 重跑完整 8 模型 x 3 用例，或至少重跑所有旧失败/高风险模型。
4. 对 `MiniMax-M2.7` 成功输出做人工质量评估，确认是否只是“能结束”还是“真的可用”。

中期：

1. Stage 1 引入 quorum，不等全部模型。
2. 引入工具预算，避免 `GPT-5.4 / usecase_2` 这种 60 次工具调用拖死整轮。
3. 对 failed with partial output 做 artifact 救回，不要简单丢弃。
4. HTML 报告展示 `permission_mode`、tool calls、timeout、partial output 状态。

当前置信度：中高。`traecli --yolo` 对旧失败 case 有实质改善，这是硬证据；但还不能直接改成“MiniMax 默认核心 / GPT 默认必等”，因为样本只有 4 个异常重跑，且还没做输出质量评审。
