# CLC 真实用例模型复测简报

## 结论先行

本轮用 3 个真实长问题重测 8 个候选模型后，旧结论需要调整。

新的判断不是“只用 2 个 member”，而是：

```text
member candidate pool:
  openrouter-2o
  GPT-5.4
  GLM-5.1
  DeepSeek-V4-Pro
  Kimi-K2.6
  Qwen3.6-Plus
  MiniMax-M2.7
  Gemini-3.1-Pro-Preview

默认运行策略:
  全部并发启动
  不把全部模型设为必等
  达到 quorum 后继续推进
  失败/超时模型保留为 evidence，不阻断整轮

chairman:
  primary: GLM-5.1
  fallback: Qwen3.6-Plus, DeepSeek-V4-Pro, openrouter-2o
  observe: Gemini-3.1-Pro-Preview
```

置信度：中高。

理由：真实用例证明“8 个都用上”是合理方向，但不能继续沿用当前 all-or-nothing 模式。`GPT-5.4` 和 `MiniMax-M2.7` 在复杂真实用例下 600s 仍失败；`openrouter-2o`、`Kimi-K2.6` 能完成但长尾明显；`Gemini-3.1-Pro-Preview` 这轮表现比旧评测好，不能再按一次 mismatch 直接排除，但历史 actual model mismatch 仍是硬风险，需要单独复测身份一致性和 chairman 场景。

## 本轮评测是什么

输入来自 `recommended-rosters.md` 的评论3，覆盖三类真实任务：

| 用例          | 任务类型                   | 代表压力              |
| ----------- | ---------------------- | ----------------- |
| `usecase_1` | 关系判断与提问策略              | 深度咨询、边界感、可操作话术    |
| `usecase_2` | 非开发者 + AI Agent 黑客松技术栈 | 需要调研、比较、明确推荐、资料引用 |
| `usecase_3` | local AI 产业趋势与投资/开发推演  | 长文战略判断、事实校正、宏观类比  |

执行口径：

- 8 个候选模型全部跑。
- 每个模型每个用例 1 次，共 24 次 live `traecli` 调用。
- 单次 timeout 放宽到 600s。
- 记录 `status`、`latency_seconds`、`response_chars`、`actual_model`、空答、错配和是否有资料/不确定性表达。

产物：

- `results.jsonl`
- `scorecard.csv`
- `summary.json`
- `responses/<usecase>/<model>.md`

## 数据总览

| model                    | success | failed | empty | p50 latency | max latency | 结论                                 |
| ------------------------ | ------: | -----: | ----: | ----------: | ----------: | ---------------------------------- |
| `Gemini-3.1-Pro-Preview` |     3/3 |      0 |     0 |      91.80s |     117.98s | 这轮最快，适合 fast fallback，但回答深度偏保守     |
| `Qwen3.6-Plus`           |     3/3 |      0 |     0 |     109.82s |     290.77s | 稳定，适合默认 member / fallback chairman |
| `DeepSeek-V4-Pro`        |     3/3 |      0 |     0 |     126.38s |     343.46s | 稳定，适合默认 member / fallback chairman |
| `GLM-5.1`                |     3/3 |      0 |     0 |     199.37s |     372.26s | 最适合 primary chairman               |
| `openrouter-2o`          |     3/3 |      0 |     0 |     330.71s |     458.14s | 能打，但慢；适合作为高质量候选，不适合必等              |
| `Kimi-K2.6`              |     3/3 |      0 |     0 |     404.94s |     408.86s | 能完成但长尾重，不适合必等                      |
| `GPT-5.4`                |     1/3 |      2 |     1 |     605.63s |     605.88s | 能力强，但复杂题收口不稳，不适合默认必等               |
| `MiniMax-M2.7`           |     1/3 |      2 |     1 |     605.35s |     605.72s | 长任务风险高，不适合默认必等                     |

## 回答评论3里的关键问题

### 1. 有没有明显不能用的模型？

没有“永久不能用”的模型，但有“不能作为默认必等成员”的模型。

更直白地说：

- “不能用”是能力判断。
- “不能必等”是系统运行判断。

本轮看，`GPT-5.4`、`MiniMax-M2.7` 属于不能必等。它们不是弱，而是在复杂真实问题上容易把整轮拖到 600s 上限，且返回 `traecli result error`。当前 CLC 如果等它们，整轮就会失败。

`openrouter-2o` 不该被排除。它 3/3 成功，回答也有信息量；问题是慢，`usecase_1` 330s、`usecase_2` 458s。它适合“高质量慢模型候选”，不适合“所有场景都必须等它”。

`Gemini-3.1-Pro-Preview` 旧评测出现过 actual model mismatch，但这轮 3/3 成功且没有错配。它不能再被归类为明显不可用。更合理的定位是 fast reviewer 或观察席 fallback：速度很好，但在进入默认 chairman fallback 之前，要先补一次 identity / chairman 专项复测。

### 2. 之前说的“稳定性问题”到底是什么？

用 PM 语言讲，就是三种风险：

| 风险    | 不是说什么   | 真正含义                      | 本轮例子                                         |
| ----- | ------- | ------------------------- | -------------------------------------------- |
| 长尾风险  | 不是模型笨   | 回答时间不可控，会拖死整轮             | `openrouter-2o`、`Kimi-K2.6` 成功但慢             |
| 收口风险  | 不是没输出能力 | 已经生成或思考很久，但 runtime 没干净结束 | `GPT-5.4` 在 usecase 2 产出 11k 字但状态失败          |
| 空失败风险 | 不是答得差   | 到 timeout 仍无可用回答          | `GPT-5.4` usecase 3、`MiniMax-M2.7` usecase 2 |

这就是为什么“我实际使用中很能打”和“不能作为默认必等模型”可以同时成立。强模型如果经常超时，默认链路就必须把它当加分项，而不是阻塞项。

### 3. Chairman fallback 时，能不能压缩前序信息？

不应该压缩已完成阶段的信息。

新的主席模型必须拿到同样完整的 Stage 1 / Stage 2 artifacts，包括：

- 原始用户问题。
- 所有已完成 member 的完整回答。
- 所有已完成 reviewer 的完整 ranking 和 review。
- aggregate ranking。
- 失败/超时成员的状态和原因。

可以压缩的只有“失败主席模型的信息”，而且必须明确标注为参考信息，不作为事实输入：

```text
previous_chairman_attempt:
  model: GPT-5.4
  status: timeout
  partial_output_summary: ...
  use_for_reference_only: true
```

原因：主席换人不是“接力写作”，而是“重新裁决”。新主席必须基于同一份完整证据独立综合，否则会把前主席的偏差继续传染下去。

### 4. `DeepSeek-V4-Pro` / `Qwen3.6-Plus` 能不能做 fallback chairman？

可以做 fallback，但不建议现在直接做 primary。

可信依据：

- 两者真实用例 3/3 成功。
- 两者在战略推演题 `usecase_3` 都能产出结构化长文。
- 两者延迟都低于 `GLM-5.1` 在部分任务上的长尾。
- 两者没有 actual model mismatch。

边界：

- `Qwen3.6-Plus` 在旧短测里有 JSON 格式不合格问题；这不影响自然语言主席综合，但影响严格结构化输出。
- `DeepSeek-V4-Pro` 质量稳，但在部分题上不像 `GLM-5.1` 那样主动做“裁决型综合”。
- `Gemini-3.1-Pro-Preview` 这轮速度最好，但历史 identity mismatch 还没被专项排除，所以先放观察席。

建议：

```text
primary chairman:
  GLM-5.1

fallback chairman order:
  1. Qwen3.6-Plus
  2. DeepSeek-V4-Pro
  3. openrouter-2o

not recommended as default chairman:
  GPT-5.4: 复杂真实用例 2/3 失败
  MiniMax-M2.7: 复杂真实用例 2/3 失败
  Kimi-K2.6: 成功但长尾重
  Gemini-3.1-Pro-Preview: 这轮最快，但历史 identity mismatch 需要专项复测
```

### 5. cutoff 应该怎么定？

旧的 150s / 180s 太激进，会误伤真实复杂问题。

这轮数据给出的更合理初值：

```text
member soft checkpoint:
  300s

member quorum checkpoint:
  480s

member hard timeout:
  660s

chairman primary timeout:
  720s

chairman fallback timeout:
  720s
```

解释：

- `usecase_2` 是最真实的复杂调研题，多个成功模型需要 290s-458s。
- 如果 300s 就硬截断，会丢掉 `DeepSeek-V4-Pro`、`GLM-5.1`、`Kimi-K2.6`、`openrouter-2o`。
- 480s 能覆盖本轮大多数成功复杂回答。
- 600s 附近出现的主要是失败或未干净收口，因此 hard timeout 设到 660s 比较合理。

运行策略不要是“到点全杀”，而应该是：

```text
0-300s:
  收集 fast responses，不推进除非已经达到高质量 quorum

300-480s:
  继续等复杂研究型回答

480s:
  如果已有 >=4 个有效 member，允许推进 Stage 2
  未完成模型继续跑到 hard timeout，但不阻塞主链路

660s:
  未完成 member 标记 dropped_timeout 或 failed_runtime
```

## 推荐的新 CLC 运行策略

### Stage 1

全部 8 个候选 member 并发启动。

有效回答标准：

- `status=ok`
- 非空
- `actual_model == expected_model`
- response 字数超过最低阈值，例如 800 字

quorum：

```text
min_valid_members: 4
target_valid_members: 5
max_wait_for_more_members: 480s
hard_timeout: 660s
```

如果 480s 时已有 4 个有效回答，进入 Stage 2。迟到模型如果随后成功，可以进入 artifact，但不进入本轮 Stage 2。

### Stage 2

只让有效 member 参与互评。失败、空答、错配、超时成员不参与 ranking。

建议 reviewer pool 不必等全部 member，可选：

```text
reviewers:
  fastest 4 valid members
  plus primary chairman if not already included
```

这样能控制 Stage 2 成本，避免 8 个成员全互评导致组合爆炸。

### Stage 3

primary chairman 先跑：

```text
GLM-5.1
```

如果失败：

```text
Qwen3.6-Plus -> DeepSeek-V4-Pro -> openrouter-2o
```

fallback chairman 必须拿完整 Stage 1 / Stage 2 artifacts。不能压缩前序成员回答和互评结果。

## 模型分层建议

| 层级           | 模型                                                                     | 用法                                 |
| ------------ | ---------------------------------------------------------------------- | ---------------------------------- |
| 默认有效 member  | `DeepSeek-V4-Pro`, `Qwen3.6-Plus`, `GLM-5.1`, `Gemini-3.1-Pro-Preview` | 可靠拿 quorum；`Gemini` 需补 identity 复测 |
| 慢但有价值 member | `openrouter-2o`, `Kimi-K2.6`                                           | 允许参与，但不必等                          |
| 高风险强模型       | `GPT-5.4`                                                              | 不必等；成功则作为加分回答                      |
| 暂不推荐默认       | `MiniMax-M2.7`                                                         | 长任务失败率高，保留 research/stress         |

## 对旧结论的修正

需要改掉的旧判断：

- “`Gemini-3.1-Pro-Preview` 明显不能默认用”不成立。本轮 3/3 成功，没有错配。
- “`openrouter-2o` 不进默认”需要改成“不做必等，但应进入候选池”。
- “只推荐 2 个 member”过窄。真实场景更适合 8 候选并发 + quorum。
- “150s / 180s cutoff”太短。真实复杂问题至少需要 480s 级别窗口。

仍然保留的判断：

- `GLM-5.1` 适合 primary chairman。
- `DeepSeek-V4-Pro` / `Qwen3.6-Plus` 适合稳定 member。
- `GPT-5.4` 很强，但不适合作为默认必等模型。
- 当前 CLC 的 all-or-nothing 机制需要改，否则模型越多，整轮失败概率越高。

## 下一步建议

产品策略：

1. 不要把默认配置理解成“选 2 个最强模型”。
2. 默认应该是“8 个候选 + quorum + fallback chairman”。
3. PM 视角的成功标准是“每次都能产出可用 council 结果”，不是“每个模型都必须完成”。

工程改造：

1. `council.py`: Stage 1 / Stage 2 从 `asyncio.gather` 全成全败改成 quorum 收集。
2. `provider.py`: 区分 per-call hard timeout 和 stage-level soft checkpoint。
3. `validation.py`: 新增 `degraded_ok`，允许部分成员 dropped，但要求原因完整可追溯。
4. `html_export.py`: 展示成功成员、迟到成员、失败成员和主席 fallback 过程。
5. `model_selection.py`: 从“小 roster 推荐”升级为 candidate pool + quorum policy + chairman fallback policy。

验收条件：

- 8 个候选同时启动。
- 任意 2 个成员失败时，只要 quorum 满足，run 不失败。
- chairman primary 失败时，fallback 接管，且拿到完整 Stage 1 / Stage 2 artifacts。
- 对失败但有 partial output 的模型，artifact 要救回原文，并标注为 `failed_with_partial_output`，不能简单丢弃。
- HTML 报告明确展示哪些模型成功、哪些超时、哪些失败，不能隐藏失败。

<br />

\>>> 评论：我需要知道你提到的GPT和minimax的问题，具体是什么，是结果出来的慢，还是出现了“排队”，还是工具调用等原因卡住了，还是需要授权。\
ps：有个关键点，我们的traecli需要用“traecli --yolo”启动，获取到完整的不需要授权的权限。\
所以你先对之前的异常case进行分析，看看到底是哪里有问题了。再说能否解决，还是定其他策略。

\>>> 回复：你这个质疑是对的。复查 raw artifact 后，原简报里把 `GPT-5.4` / `MiniMax-M2.7` 直接归因成“模型不适合默认必等”说得过满，必须收回一部分。

先说事实：

| case | status | latency | output | raw 里看到的主要信号 | 初步归因 |
|---|---:|---:|---:|---|---|
| `usecase_2 / GPT-5.4` | failed | 605.63s | 11,477 chars | 大量 `WebSearch` / `WebFetch`，多次 `failed to convert ADK output to model format`，最后 `result error_during_execution` | 不是排队，也不是无输出；更像工具结果转换/事件流处理错误 + 到 600s 未干净收口 |
| `usecase_3 / GPT-5.4` | failed | 605.88s | 0 chars | 连续 `WebFetch` / `WebSearch` 后 `result error_during_execution` | 工具调用链过长后失败；没有证据显示是授权弹窗 |
| `usecase_2 / MiniMax-M2.7` | failed | 605.72s | 0 chars | 多轮 `WebFetch` / `WebSearch`，后续只有 system reminder/status，最后 `result error_during_execution` | 工具调用后没有形成最终回答；更像 agent loop / 工具链收口失败 |
| `usecase_3 / MiniMax-M2.7` | failed | 605.35s | 16,614 chars | 已经生成长文，但最后仍是 `result error_during_execution`；session log 末尾有 `read SSE: context deadline exceeded` | 有可救回 partial output，但 runtime 没以 success 结束 |

最关键的更正：本轮复测命令确实没有带 `-y`。meta 里记录的实际命令是：

```text
traecli -p <prompt> -c model.name=<model> --output-format stream-json --query-timeout 600s --session-id <id>
```

不是：

```text
traecli --yolo -p <prompt> ...
```

同时 session metadata 里是 `permission_mode: default`。所以这轮数据不能证明“在完整免授权权限下 GPT / MiniMax 仍然失败”。它只能证明：在当前默认权限模式 + 长问题 + 允许工具调用的条件下，`GPT-5.4` 和 `MiniMax-M2.7` 更容易进入工具链/事件流/收口异常。

目前没有看到典型“排队”证据，也没有看到需要用户手动点击授权的明确提示；stderr 为空，raw stream 里也没有 `permission denied` / `authorize` / `confirm` 这类直接授权阻断。更像是两个问题叠加：

1. `traecli` 启动参数缺 `-y`，导致权限模式不是我们真实想测的模式。
2. 异常 case 都大量使用 `WebSearch` / `WebFetch`，raw log 里反复出现 `failed to convert ADK output to model format`、`BuildNotification failed`、`result error_during_execution`、`read SSE: context deadline exceeded`。这说明失败点很可能在工具结果转换、事件上传/流处理或 agent 收口，而不只是“模型慢”。

能不能解决：可以，先不要急着定最终模型策略。正确动作应该是：

1. 先改评测/CLC provider，把 `traecli --yolo` 作为默认启动方式，或至少新增显式 `--auto-approve` / `--permission-mode` 配置，并把实际 command 写进 artifact。
2. 对这 4 个异常 case 原样重跑：`GPT-5.4 usecase_2`、`GPT-5.4 usecase_3`、`MiniMax-M2.7 usecase_2`、`MiniMax-M2.7 usecase_3`。
3. 重跑时同时记录：是否有排队等待、首 token 时间、工具调用次数、最后一次工具调用时间、是否有 `result error_during_execution`、是否有 partial output。
4. 如果 `-y` 后成功率明显恢复，原来的“不能必等”结论要改成“默认权限配置导致误杀”；如果 `-y` 后仍在 600s 附近失败，才可以确认它们在复杂工具型长任务里不适合作为默认必等成员。

所以当前我会把结论修正为：`GPT-5.4` / `MiniMax-M2.7` 暂时不能作为“已证伪的模型问题”处理，只能作为“默认权限模式下的异常样本”。产品策略上仍建议 quorum，原因是 quorum 能同时覆盖模型慢、工具卡、runtime 错误、权限配置遗漏这些真实风险；但模型分层结论必须等 `traecli --yolo` 复测后再最终定。
