# GPT-5.2 单模型复测简报

## 结论

`GPT-5.2` 这轮表现很好，可以进入 CLC 候选池，并且值得作为 `GPT-5.4` 的低风险替代候选继续验证。

本轮用两组任务测试：

- 原 benchmark：4 个 council 基础任务，每个重复 2 次，共 8 次。
- 真实用例：用户指定的 3 个长问题，共 3 次。

结果：

```text
total: 11
success: 11
failed: 0
canonical parse_ok: 8/8
real usecase success: 3/3
model mismatch: 0
runtime: traecli --yolo
permission_mode: bypass_permissions
```

置信度：中高。

样本数仍不算大，但这轮信号很干净：没有 timeout、没有空答、没有 model mismatch，且最难的 `usecase_2` 没有复现 `GPT-5.4` 的工具链发散问题。

## 关键数据

| suite | case | status | latency | response | tool calls | parse |
|---|---|---:|---:|---:|---:|---:|
| 原 benchmark | 8 cases | 8/8 ok | p50 24.22s / max 28.61s | - | 1/case | 8/8 |
| 真实用例 1 | 关系判断与提问策略 | ok | 64.81s | 3,085 chars | 1 | ok |
| 真实用例 2 | 非开发者黑客松技术栈调研 | ok | 257.54s | 7,264 chars | 11 | ok |
| 真实用例 3 | local AI 趋势与投资推演 | ok | 111.66s | 6,231 chars | 1 | ok |

## 对比 GPT-5.4 / MiniMax 复测的意义

这轮最有价值的对比点是 `usecase_2`。

`GPT-5.4` 在 `traecli --yolo + 660s` 下跑同一个 `usecase_2` 仍失败：

```text
latency: 666.18s
tool_calls: 60
error: context deadline exceeded
```

`GPT-5.2` 同题成功：

```text
latency: 257.54s
tool_calls: 11
error: null
```

这说明 `GPT-5.2` 在开放式调研任务上更克制，没有把搜索/抓取链条无限展开。它未必比 `GPT-5.4` 上限更高，但在 CLC 默认链路里，它可能更适合作为“稳定产出型 GPT member”。

## 初步定位

建议把 `GPT-5.2` 放进下一轮候选策略：

```text
candidate member:
  yes

fallback chairman:
  can test

default blocking member:
  not yet final; needs at least one full council run

research stress model:
  yes
```

暂不建议立刻把它定为 primary chairman。原因不是这轮表现差，而是本轮只是单模型直接调用，还没有验证完整 Stage 1 / Stage 2 / Stage 3 council 流程里的主席综合稳定性。

## 暴露出的正向信号

1. 原 benchmark 8/8 成功，结构化 JSON、ranking、chairman markers 都通过。
2. 真实长用例 3/3 成功。
3. `usecase_2` 只用了 11 次工具调用，明显低于 `GPT-5.4` 失败 case 的 60 次。
4. 没有 queue marker、没有人工授权阻断、没有 model mismatch。
5. `traecli --yolo` 下明确进入 `bypass_permissions`。

## 仍需补的验证

1. 用 `GPT-5.2` 做一次完整 council run，而不是只做 direct model call。
2. 人工抽查 3 个真实用例的回答质量，尤其是事实准确性和引用质量。
3. 和 `GLM-5.1`、`Qwen3.6-Plus`、`DeepSeek-V4-Pro` 做同口径 `traecli --yolo` 复测后再重排默认 roster。
4. 如果要让 `GPT-5.2` 参与默认阻塞链路，还要验证它在高并发、多 member 同跑时是否稳定。

## 产物

- `results.jsonl`：11 条逐 case 结果。
- `combined-scorecard.csv`：原 benchmark + 真实用例逐 case 表。
- `canonical-scorecard.csv`：原 benchmark 聚合分数。
- `notes.md`：运行中观察记录。
- `responses/`：每个 case 的模型回答。
- `raw/`：每次 `traecli` 调用的 stream / stderr / session artifacts。
