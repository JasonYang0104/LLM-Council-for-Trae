# CLC 模型 roster 推荐

## 结论

推荐当前默认配置：

```text
members: DeepSeek-V4-Pro, Qwen3.6-Plus
chairman: GLM-5.1
timeout: 240
```

置信度：中。

原因很简单：这是本轮唯一通过复杂输入 full council、并通过 `validate` 的组合。不要把单模型短任务 scorecard 的机器推荐直接升为默认 roster；短任务稳定不等于三阶段复杂链路稳定。

## 完整链路验证

| run\_id                              | members                                    | chairman  | timeout | result | validate | HTML                                                                        |
| ------------------------------------ | ------------------------------------------ | --------- | ------: | ------ | -------- | --------------------------------------------------------------------------- |
| `model-bench-deepseek-qwen-20260525` | `DeepSeek-V4-Pro`, `Qwen3.6-Plus`          | `GLM-5.1` |    240s | pass   | ok       | `.coco-llm-council/runs/model-bench-deepseek-qwen-20260525/html/index.html` |
| `model-bench-fast-20260525`          | `MiniMax-M2.7`, `openrouter-2o`            | `GLM-5.1` |    150s | fail   | skipped  | none                                                                        |
| `model-bench-analysis-20260525`      | `MiniMax-M2.7`, `openrouter-2o`, `GPT-5.4` | `GLM-5.1` |    150s | fail   | skipped  | none                                                                        |
| `model-bench-conservative-20260525`  | `MiniMax-M2.7`, `GPT-5.4`                  | `GLM-5.1` |    180s | fail   | skipped  | none                                                                        |
| `model-bench-builtins-20260525`      | `MiniMax-M2.7`, `DeepSeek-V4-Pro`          | `GLM-5.1` |    180s | fail   | skipped  | none                                                                        |
| `model-bench-glm-deepseek-20260525`  | `GLM-5.1`, `DeepSeek-V4-Pro`               | `GLM-5.1` |    240s | fail   | skipped  | none                                                                        |

成功 run 的阶段时间：

```text
runtime_check_start: 2026-05-25T07:44:26Z
stage1_start:        2026-05-25T07:44:36Z
stage2_start:        2026-05-25T07:47:06Z
stage3_start:        2026-05-25T07:48:12Z
manifest updated:    2026-05-25T07:50:17Z
```

说明：完整 run 总耗时约 5 分 51 秒，Stage 1 约 2 分 30 秒，Stage 2 约 1 分 6 秒，Stage 3 约 2 分 5 秒。它不是“快”，但比失败组合更适合作为当前默认。

## 单模型 benchmark 摘要

本轮 `results.jsonl` 共 64 条 live 调用：8 个候选模型 × 4 个任务 × 2 次重复。聚合结果见 `scorecard.csv`。

| model                    | samples | success | parse | p95 latency | 关键问题                                                                  |
| ------------------------ | ------: | ------: | ----: | ----------: | --------------------------------------------------------------------- |
| `MiniMax-M2.7`           |       8 |    1.00 |  1.00 |      35.37s | 短任务漂亮，但复杂 full council 中 Stage 1 失败                                   |
| `openrouter-2o`          |       8 |    1.00 |  1.00 |      44.89s | 短任务漂亮，但复杂 full council 中 Stage 1 失败；模型描述仍含 `Unavailable for L4 repos` |
| `GPT-5.4`                |       8 |    1.00 |  1.00 |      76.98s | 单测可用，但复杂 full council 中多次 Stage 1 失败；不适合默认 member                     |
| `Kimi-K2.6`              |       8 |    1.00 |  1.00 |     120.93s | 长尾太重，不适合默认 member                                                     |
| `DeepSeek-V4-Pro`        |       8 |    1.00 |  0.88 |      36.53s | 一次 JSON 格式不合格；Stage 2 和 full-chain 表现可用                               |
| `GLM-5.1`                |       8 |    1.00 |  0.88 |      33.58s | 一次 JSON 格式不合格；作为 chairman 通过 full-chain，作为复杂 Stage 1 member 失败        |
| `Qwen3.6-Plus`           |       8 |    1.00 |  0.88 |      45.22s | 一次 JSON 格式不合格；Stage 2 和 full-chain 表现可用                               |
| `Gemini-3.1-Pro-Preview` |       8 |    0.88 |  1.00 |      73.30s | 一次 actual model mismatch，不能进默认                                        |

## 默认 member 数量

推荐默认 member 数量：2。

理由：

- 2-member council 已经能完成 Stage 1、Stage 2、Stage 3 和 HTML export。
- 3-member 组合在本轮复杂输入中失败，主要被 `GPT-5.4` 和 `openrouter-2o` 长尾/运行时错误拖垮。
- 在没有更多 full-chain 成功样本前，把默认扩到 3-4 个 member 是不负责任的。

## Chairman 选择逻辑

当前推荐 `GLM-5.1` 作为 chairman。

证据：

- 单模型 chairman 任务 2/2 成功。
- full-chain run `model-bench-deepseek-qwen-20260525` 的 Stage 3 `expected_model=GLM-5.1`、`actual_model=GLM-5.1`，`status=ok`。
- `validate` 全部通过，HTML 已生成。

边界：

- `GLM-5.1` 不适合直接放进复杂 Stage 1 默认 member，本轮 `model-bench-glm-deepseek-20260525` 在 `GLM-5.1` Stage 1 失败。
- chairman 可用不等于 member 可用。角色要分开判断。

## 候选模型处置

- `DeepSeek-V4-Pro`: 进入默认 member。复杂输入 full-chain 通过；单模型任务成功率 1.00。JSON 格式有一次不合格，后续如果 CLC 引入结构化 Stage 1，需要重新评估。
- `Qwen3.6-Plus`: 进入默认 member。复杂输入 full-chain 通过；Stage 2 ranking 可解析。JSON 格式有一次不合格，不适合依赖严格 JSON 的位置。
- `GLM-5.1`: 进入默认 chairman，不进默认 member。主席综合稳定；复杂 Stage 1 member 失败。
- `GPT-5.4`: 不进默认 member。单模型短测过关，但复杂 full council 多次 Stage 1 失败或超时。可保留在 `research_stress`。
- `MiniMax-M2.7`: 不进默认 member。短任务低延迟且格式稳，但复杂 full council Stage 1 失败。可作为 fast smoke 候选继续测。
- `openrouter-2o`: 不进默认 member。短任务强，但复杂 full council 失败，且有 L4 repo / quota caveat。适合 research/stress 或环境明确支持时手动指定。
- `Kimi-K2.6`: 不进默认 member。单模型成功率可以，但 p95 约 120.93s，明显拖慢整轮 council。
- `Gemini-3.1-Pro-Preview`: 不进默认 member。出现 actual model mismatch，这是硬失败信号。

\>>> 评论：判断的标准是什么？是否考虑了问答质量。没考虑纳入的模型，最大的原因是什么，是有明显的表现不稳定还是怎么了？我的实际使用中`GPT-5.4`和`openrouter-2o`都是“很能打”的模型，没入选很奇怪。

\>>> 回复：标准要拆成两层看，否则会误解。第一层是“模型强不强”，第二层是“能不能作为 CLC 默认链路里的必等模型”。`GPT-5.4` 和 `openrouter-2o` 很能打，这点我不否认；问题是默认链路要追求稳定产出，而不是押注最强单点。旧评测主要看 full council 是否跑完、`validate` 是否通过、模型身份是否一致、Stage 2 排名是否可解析、延迟是否可控；问答质量只被粗略纳入，没有做足人工质量评估。所以旧结论偏保守。按评论3的 3 个真实长问题复测后，判断需要更新：不应再说“只推荐 2 个 member”，而应改成“8 个候选模型都并发使用，但不全部必等，达到 quorum 后继续推进”。`GPT-5.4` 没入选默认必等，不是因为质量弱，而是 3 个真实用例只成功 1 个，复杂题出现 600s 级失败和空输出；`openrouter-2o` 则应该重新纳入候选池，它 3/3 成功且输出有质量，只是慢，不能被 150-180s cutoff 误杀。最大的原因不是“明显智力不行”，而是稳定性、长尾和运行收口风险：强模型可以作为高质量候选或迟到加分项，但默认链路不能被它拖死。新的推荐是：member candidate pool 放 8 个模型；`GLM-5.1` 做 primary chairman；fallback chairman 用 `Qwen3.6-Plus -> DeepSeek-V4-Pro -> openrouter-2o`；`GPT-5.4`、`MiniMax-M2.7` 不做默认必等；`Gemini-3.1-Pro-Preview` 本轮表现好，但历史 identity mismatch 需要专项复测。

## 建议配置分层

```text
fast_default:
  members: DeepSeek-V4-Pro, Qwen3.6-Plus
  chairman: GLM-5.1
  timeout: 240
```

这个名字有点勉强：它是“当前唯一已验证默认组”，不是绝对快速组。

```text
analysis_default:
  members: DeepSeek-V4-Pro, Qwen3.6-Plus
  chairman: GLM-5.1
  timeout: 240
```

现阶段不要把 `GPT-5.4` 加入默认分析组，除非后续通过复杂 full-chain 重测。

```text
research_stress:
  members: DeepSeek-V4-Pro, Qwen3.6-Plus, GPT-5.4, MiniMax-M2.7, openrouter-2o, Kimi-K2.6
  chairman: GLM-5.1
  timeout: 300+
```

stress 组只用于研究，不作为默认。它可能慢，也可能失败。

## 下一步

如果要把 CLI 默认常量真正改掉，建议下一轮 TDD 修改：

- `DEFAULT_MEMBERS = ["DeepSeek-V4-Pro", "Qwen3.6-Plus"]`
- `DEFAULT_CHAIRMAN = "GLM-5.1"`
- 更新 `model_selection` 推荐逻辑，让推荐优先使用 benchmark 结论，而不是旧的静态偏好。
- 增加一条测试：当前 8 候选都存在时，推荐 roster 应返回 `DeepSeek-V4-Pro,Qwen3.6-Plus / GLM-5.1`。

本轮没有直接改 CLI 默认值，因为交接目标是“用数据决定”，不是在一次 benchmark 后顺手改生产默认。

<br />

\>>> 评论2：有没有明显不能用的模型？我在考虑点名的8个模型都用上，但是：

- 挑选一个可靠的主席模型
- 对成员模型的处理成果做最大时间上的截断（具体阈值怎么定没想好）；对主席模型做备选（主席模型如果异常了就让备选模型接上，继续推进）
- 主席模型也可以是成员模型的，在选型上不隔离，实际运行上隔离

\>>> 回复2：退一层看，这个思路比“只选 2 个默认 member”更像正确的产品方向：不是把 8 个模型硬塞进同一个 all-or-nothing run，而是把 CLC 从“固定小 roster”升级成“候选池 + quorum + degradation”。结论先说：没有一个模型应被永久判死刑，但有几个模型不适合在当前实现里无保护地放进默认链路。`Gemini-3.1-Pro-Preview` 是最接近“明显不能默认用”的，因为本轮出现过 actual model mismatch；这类错误会直接破坏 artifact 可信度，优先级比回答质量更高。`Kimi-K2.6` 不是不能用，而是长尾过重，适合 stress/research，不适合作为默认必等成员。`GPT-5.4` 和 `openrouter-2o` 不是能力问题，而是复杂 full council 下的运行稳定性和外部约束问题：它们可以很强，但默认链路不能让一个强模型拖死整轮。你的“8 个模型都用上，但成员结果截断、主席有备选”的方向是合理的，我会把它设计成：Stage 1 并发启动 8 个候选，设置 member soft cutoff，超过 cutoff 的模型标为 `dropped_timeout`，不阻塞后续；只要达到最低有效成员数，比如 `min_stage1_responses=2` 或 `3`，就进入 Stage 2；Stage 2 只评审已产出回答的成员，避免把失败/空响应也送去互评；Stage 3 由 primary chairman 综合，如果 primary 失败，再把同一份压缩后的 Stage 1/2 artifacts 交给 fallback chairman。主席模型可以同时是成员候选，但运行上必须用独立 session、独立 stage artifact，不能复用成员回答替代主席综合。按现有数据，我会先设：primary chairman=`GLM-5.1`，fallback chairman=`DeepSeek-V4-Pro`, `Qwen3.6-Plus`；member candidate pool=全部 8 个；默认 `min_stage1_responses=3`，低成本模式可设 2；member soft cutoff 初始取 150s，hard kill 180s；Stage 2 cutoff 90-120s；chairman primary timeout 240s，fallback timeout 180-240s。这个阈值不是拍脑袋的最终值，而是基于本轮 full run 看到的阶段耗时和失败样本的保守初值，下一轮应该把它做成配置并用 benchmark 回归。实现上需要改的模块也清楚：`council.py` 现在的 `asyncio.gather` 和 `update_manifest_status` 是全成全败，需要改成“收集成功成员 + 记录 dropped 成员 + quorum 判断”；`provider.py` 已经支持单次 `query_timeout`，但还缺 member soft cutoff 语义；`validation.py` 要允许 `degraded_ok` 这种状态，并校验 dropped 成员有明确原因；`html_export.py` 要把 dropped/failed 成员展示出来，不能假装它们不存在；`model_selection.py` 不应再返回一个小名单，而应返回 candidate pool、chairman primary/fallback、quorum 和 timeout policy。这样 8 个模型都能用上，同时不会让 `GPT-5.4`、`openrouter-2o`、`Kimi-K2.6` 这类强但有长尾或环境风险的模型成为单点阻塞。

\>>> 评论3：

- “`Gemini-3.1-Pro-Preview` 是最接近“明显不能默认用”的，因为本轮出现过 actual model mismatch；这类错误会直接破坏 artifact 可信度，优先级比回答质量更高。`Kimi-K2.6` 不是不能用，而是长尾过重，适合 stress/research，不适合作为默认必等成员。`GPT-5.4` 和 `openrouter-2o` 不是能力问题，而是复杂 full council 下的运行稳定性和外部约束问题：它们可以很强，但默认链路不能让一个强模型拖死整轮。”这部分看不懂，不清楚问题到底是什么。展开讲讲，用你认为我会容易理解的方式
- “Stage 3 由 primary chairman 综合，如果 primary 失败，再把同一份压缩后的 Stage 1/2 artifacts 交给 fallback chairman。”如果出现主席模型的交接，不准压缩之前已完成阶段的内容，可以压缩前主席模型的信息（但是明确是仅作参考），新的主席模型要给到充足的同样的信息。
- “fallback chairman=`DeepSeek-V4-Pro`, `Qwen3.6-Plus`”这俩我其实不太放心，用的不多，有什么可信的依据吗？能胜任主席模型吗
- cutoff阈值我没看结果，但一定要放款的。因为我们可能会问到复杂的问题，回答时间会很长。这样吧你直接用以下三个用例，再去评测下这些模型的表现吧。这些真实用例，可能更能说明问题。
  - 测试用例
  - <1>

    我认为判断一个人是否可靠值得深交值得信赖的一个判断方式，是看这个人是否有和谐的夫妻关系或者伴侣关系。但这点在和人初次接触时，比较难以判断，因此我的问题是如何能通过优雅不冒犯的方式，通过提问和观察的方式来获取到这个信号呢？应该怎么问怎么操作怎么观察？假设有两个场景，一个是日常生活上的社交，一个是工作中作为面试官面试求职者。



    慢慢来，全面地，深入地，详细地，错综复杂地，彻底地，think before answring，ultrathink

    \
    \</1>





    <2>

    请你作为一名熟悉 AI coding、前端工程、黑客松交付和非开发者工具设计的资深技术顾问，帮我调研并判断：



    在公司内部黑客松场景中，一批对开发不熟练的非开发者同事，会使用 Trae-CN（ 类似Cursor ）这类支持 skill 等Agent配套的coding Agent，从想法开始，经过需求澄清、PRD、原型、修改确认、开发交付，最终做出一个可本地运行、可演示的 Web MVP / 内部工具 / 数据看板 / 表单流程 / AI 小工具。



    问题：这类“非开发者 + AI Agent + 黑客松开发套件”的默认技术栈应该选什么？



    请按以下要求调研和输出：


    - 搜索并参考开发者多的平台，比如hacker news、Reddit、Github、X等等
    - 请优先参考官方文档、AI IDE 实践经验、成熟开发者讨论、黑客松或 MVP 开发经验。
    - 不要只看“专业开发者喜欢什么”，重点看“非开发者在 AI Agent 帮助下能否稳定做出来、能否继续改、能否排错、能否演示”。
    - 请特别分析 AI Agent 生成和修改代码时，不同技术栈的优劣：项目结构是否简单、错误是否容易被 Agent 自动修复、依赖是否稳定、启动命令是否简单、UI 是否容易做得好看、是否容易本地演示。
    - 请区分“默认技术栈”和“触发条件下切换的备选技术栈”。
    - 请指出哪些路线看似简单，但经过多轮修改后会变难。
    - 请给出明确推荐，不要平均主义。
    - 请给出置信度：高 / 中 / 低。请列出能推翻你推荐的证据或条件。
    - 列出你参考的主要资料链接，并简要说明每个资料支持了什么判断。


    慢慢来，全面地，深入地，详细地，错综复杂地，彻底地，think before answring，ultrathink



    \</2>





    <3>

    预感 local AI，

    本地推理大模型和agent，

    个人/家用消费级，

    大概会在今年下半年到明年上半年爆发。



    model 可能是 

    qwen-4-35B 、27B、Nemotron-4-120B、500B。



    硬件可能是 mac studio M5 、

    Rtx 7000 pro

    小概率是 amd intc 华为的显卡



    agent 端覆盖：医疗、财务、个人待办、职场"""





    先对以上言论进行客观评估，先给出正面/负面支持的信号或依据，再给你的最终结论。



    之后再假设这一天已经来了，推演后续在行业发展、企业等宏观层面分析，哪些公司有收益能因此得出哪些投资建议，将历史上的类似情况和企业做对标参考，做对照类比分析；以及后续对于个人开发者来说，生态若发展良好，可以提前考虑调研开发的方向有哪些，同样是结合历史上类似时刻，给出有明确参考价值的产品/项目是什么。



    在你回答之前，请先思考我真正需要的是什么，而不仅仅是看我表面上说了什么。我已说的是我想到的，我没说的不代表是我不需要的，你要做充分的意图理解。



    慢慢来，全面地，深入地，详细地，错综复杂地，彻底地，think before answring，ultrathink



    \</3>


