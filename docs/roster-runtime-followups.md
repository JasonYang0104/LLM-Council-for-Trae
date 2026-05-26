# CLC 后续推进讨论稿

## 文档用途

这份文档不是结论文档，而是接下来我们持续沟通的工作底稿。

建议用法：

- 你直接在对应章节下面追加问题、批注、反例或新要求。
- 我后续基于这个文件继续更新判断、方案和代码改动建议。
- 如果某一项从“讨论”进入“确定执行”，我会把状态从 `待讨论` 改成 `已确认` 或 `已落地`。

当前聚焦 5 个推进点：

1. `traecli -y` 默认化
2. candidate pool + quorum + chairman fallback
3. timeout / cutoff 策略放宽并结构化
4. 工具预算与长工具链失控治理
5. partial output 救回与报告展示

***

## 背景基线

基于当前 repo 里已经落盘的 benchmark / rerun 产物，现阶段可以先把问题分成两层：

- 模型本身是否有能力
- 模型在 CLC 的默认运行链路里，是否适合作为“必等阻塞项”

这两层不能混为一谈。

当前已经看到的关键信号：

- `GPT-5.4`、`openrouter-2o`、`Kimi-K2.6` 在真实复杂题上可能很强，但存在长尾或工具链风险。
- `MiniMax-M2.7` 的旧失败里，至少一部分是没有带 `traecli -y` 造成的误判。
- `GLM-5.1` 当前更像稳定的 `primary chairman`。
- `DeepSeek-V4-Pro`、`Qwen3.6-Plus` 当前更像稳定 `member`，也可作为 `fallback chairman` 候选。
- 当前 CLC 的 all-or-nothing 机制会把“强但不稳定”直接放大成“整轮失败”。

相关证据入口：

- `docs/model-benchmark-20260525/README.md`
- `docs/model-benchmark-20260525/recommended-rosters.md`
- `docs/model-benchmark-20260525/real-usecase-20260525/director-brief.md`
- `docs/model-benchmark-20260525/real-usecase-20260525/rerun-y-20260525/notes.md`
- `docs/model-benchmark-20260525/gpt-5.2-20260525/brief.md`

***

## 1. `traecli -y` 默认化

状态：`待讨论`

### 为什么要推进

当前已有硬证据表明：如果不用 `traecli -y`，会把一部分本可成功的 case 误打成失败。

这不是小优化，而是评测口径和实际运行口径是否一致的问题。

### 已有证据

- `rerun-y-20260525/notes.md` 显示：4 个旧失败 case 在 `-y` 复测后救回了 3 个。
- 复测中可见 `permission_mode: bypass_permissions`。
- 旧评测没有带 `-y`，因此不能把那部分失败直接归因为模型能力问题。

### 待拍板问题

1. CLC 是否默认一律带 `-y`？
2. 还是做成显式配置，例如：
   - 默认带 `-y`
   - 可通过参数关闭
   - artifact 中强制记录实际 `permission_mode`
3. benchmark 与正式 run 是否必须共用同一 provider 启动参数，避免口径分叉？

### 我当前建议

- 默认带 `-y`
- 保留显式关闭开关
- 在 artifact 和 HTML 里都展示 `permission_mode`

### 你的问题区

- 待补充

\>>> 评论：确认，但改为用“traecli -yolo”，这个指令更标准。但需要你确认指令情况。

\>>> 回复：已确认。当前本机 `traecli --help` 明确显示 `-y, --yolo`，说明 `traecli -yolo` 是真实可用的标准长参数，和 `-y` 等价。后续文档、评测脚本和 provider 设计里，我会统一把口径写成 `--yolo`，把 `-y` 只当简写。下一步还需要做两件事：一是确认 CLC provider 是否默认拼接 `--yolo`；二是把实际运行命令和 `permission_mode` 一起落进 artifact，避免再次出现“评测参数和真实口径不一致”。

***

## 2. candidate pool + quorum + chairman fallback

状态：`待讨论`

### 为什么要推进

你已经明确提出了一个更像产品方向的思路：

- 8 个模型都可以进入候选池
- 但不要把它们都设为必等
- 达到 quorum 后继续推进
- 主席模型失败时，fallback chairman 接上

这比“只挑 2 个默认 member”更符合真实复杂问题场景。

### 已有证据

- 真实用例评测显示：有些模型强，但会慢；有些模型能完成，但容易出现工具链收口问题。
- 当前 all-or-nothing 实现下，只要少数模型超时或失败，整轮就容易失败。
- `recommended-rosters.md` 里已经形成了候选池 + 降级运行的初步思路。

### 已确认边界

- fallback chairman 不允许拿压缩后的 Stage 1 / Stage 2 核心证据替代原始材料。
- 新主席模型必须拿到完整前序 artifacts。
- 前主席模型若失败，只能把其尝试结果作为“参考信息”，不能当事实输入。

### 待拍板问题

1. 默认 `candidate pool` 是否就是当前 8 个模型全量？
2. `min_valid_members` 设 3 还是 4？
3. 迟到但最终成功的 member，是否进入最终 HTML 展示但不进入本轮 Stage 2？
4. `fallback chairman` 顺序是否先按当前建议：
   - `Qwen3.6-Plus`
   - `DeepSeek-V4-Pro`
   - `openrouter-2o`
5. `GPT-5.4` 是否默认作为 non-blocking 高质量候选，而不是必等 member？

### 我当前建议

- `candidate pool = 8` 个候选模型
- `min_valid_members = 4`
- `target_valid_members = 5`
- `primary chairman = GLM-5.1`
- `fallback chairman = Qwen3.6-Plus -> DeepSeek-V4-Pro -> openrouter-2o`

### 你的问题区

- 待补充

\>>> 评论：8个模型是8家供应商，如果我指定的8个模型不稳，那就考虑降级的同供应商模型。

比如GPT 5.4不行，那就考虑GPT 5.2，GPT 5.2也是不错的。

每个模型不稳定的模型都要找到同厂商的可用模型。因此需要你先盘点，之后再起评测。

以及主席模型的挑选要更严谨些，`openrouter-2o`可能不是好的选择，因为我自用时发现了不稳定，还需要再测

\>>> 回复：同意，而且我建议把这件事从“模型名单”升级成“供应商梯队表”。也就是说，后续不是只维护 8 个点名模型，而是维护一张 `primary -> fallback_same_vendor -> fallback_cross_vendor` 的映射表。比如 OpenAI 线先看 `GPT-5.4 -> GPT-5.2`，其他供应商也各自找一个同厂商降级备选。这样一来，默认运行时就不是“某模型失败就整条断掉”，而是先尝试同供应商降级，再决定是否跨供应商补位。你提到 `openrouter-2o` 自用不稳，这个信息我先采纳为风险信号：在新的主席候选表里，先把它从高优先级 fallback chairman 降到“待复测观察位”，不直接作为推荐 fallback。下一步我会先做一版供应商盘点清单，再决定补测哪些同厂商模型，而不是直接开跑。

\>>> 评论2：列在这里我看看，以及写上你认为要考虑备选的厂家是哪些，备选模型是哪些。

列一个完整的列表，用于我们后续重新评测。评测对象包括之前没出问题的厂商的模型。

\>>> 回复2：可以，先给一版“基于当前 runtime 快照、适合进入下一轮重评测”的完整清单。这里我故意分成两层：第一层是你已经点名或现有评测覆盖过的 primary；第二层是我建议一起纳入的同厂商 fallback。这样后续评测就不只是验证“8 个点名模型”，而是在验证“8 条供应商线路是否各自有可降级的稳定模型”。按当前 `runtime-models.json` 能确认到的可选项，我建议如下：

```text
1. OpenAI 线
   primary:
   - GPT-5.4
   fallback_same_vendor:
   - GPT-5.2
   observe_only:
   - GPT-5.5
   说明:
   - GPT-5.2 已有 repo 内正向证据，应该进入正式重评测
   - GPT-5.5 当前快照里有较高 Queue heat，先放观察位，不直接进默认主评测

2. Zhipu / GLM 线
   primary:
   - GLM-5.1
   fallback_same_vendor:
   - GLM-5
   reserve:
   - GLM-5V-Turbo
   说明:
   - `GLM-5V-Turbo` 更偏多模态保底，不建议作为纯文本 council 的第一备选

3. DeepSeek 线
   primary:
   - DeepSeek-V4-Pro
   fallback_same_vendor:
   - DeepSeek-V4-Flash

4. Qwen 线
   primary:
   - Qwen3.6-Plus
   fallback_same_vendor:
   - Qwen3.5-Plus

5. Kimi / Moonshot 线
   primary:
   - Kimi-K2.6
   fallback_same_vendor:
   - Kimi-K2.5

6. MiniMax 线
   primary:
   - MiniMax-M2.7
   fallback_same_vendor:
   - MiniMax-M2.5

7. Gemini / Google 线
   primary:
   - Gemini-3.1-Pro-Preview
   fallback_same_vendor:
   - Gemini-3-Flash-Preview

8. OpenRouter 通道线
   primary:
   - openrouter-2o
   fallback_same_channel:
   - openrouter-1o
   - openrouter-1
   说明:
   - 这条线我先不把它当“稳定厂商线”，更像“聚合通道线”
   - 由于你反馈过自用不稳，且快照里带 quota / repo caveat，主席位先不推荐
```

如果把“下一轮正式重评测名单”写成一个更可执行的版本，我建议是：

```text
第一层：原 8 个 primary 全部重测
- GPT-5.4
- GLM-5.1
- DeepSeek-V4-Pro
- Qwen3.6-Plus
- Kimi-K2.6
- MiniMax-M2.7
- Gemini-3.1-Pro-Preview
- openrouter-2o

第二层：同厂商 fallback 一并重测
- GPT-5.2
- GLM-5
- DeepSeek-V4-Flash
- Qwen3.5-Plus
- Kimi-K2.5
- MiniMax-M2.5
- Gemini-3-Flash-Preview
- openrouter-1o
```

这版名单的好处是：

- 覆盖了之前没出问题的厂商，不会只盯着失败模型补测
- 每条供应商线都至少有一个同厂商降级位
- 主席选择会更严谨，因为可以按“同厂商 primary/fallback”单独比较，而不是把所有模型混成一个池

我当前额外建议：

- `primary chairman` 候选先重点看：`GLM-5.1`、`GPT-5.2`、`Qwen3.6-Plus`
- `fallback chairman` 候选先重点看：`GLM-5`、`DeepSeek-V4-Pro`、`Qwen3.5-Plus`
- `openrouter-*` 暂时只做 member / observer 线，不进入主席优先名单，等复测后再说

如果你认可，我下一步就把这份“供应商梯队评测名单”整理成文档里的固定清单，后续评测都按这份名单展开。

***

## 3. timeout / cutoff 策略

状态：`待讨论`

### 为什么要推进

旧的 `150s / 180s` cutoff 已经明显过短，会误伤真实复杂题。

如果未来问题更复杂，固定死短超时只会继续误杀强模型。

### 已有证据

- 真实用例里，多个成功回答都落在 `290s-458s` 区间。
- `GPT-5.4` 的 `usecase_2` 是另一类问题：不是简单“慢”，而是长工具链发散到了 deadline。
- 因此 timeout 需要分层，而不是一个数字打天下。

### 待拍板问题

1. 我们要不要区分：
   - soft checkpoint
   - quorum checkpoint
   - hard timeout
2. member 和 chairman 的 timeout 是否独立？
3. 复杂研究题是否允许显式切换到“长思考模式”？

### 我当前建议

初始建议值：

```text
member soft checkpoint: 300s
member quorum checkpoint: 480s
member hard timeout: 660s
chairman primary timeout: 720s
chairman fallback timeout: 720s
```

这不是永久常量，而是下一轮回归验证的起点。

### 你的问题区

\>>> 评论：当前看策略上是ok，但需要另起新评测后，根据结果+这次结果再定具体阈值。

\>>> 回复：同意。这里先不把 `300 / 480 / 660 / 720` 当最终阈值，而只当下一轮评测的初始采样点。更准确的做法是：新评测里把阶段耗时、首个可用回答时间、达到 quorum 的时间、最终 hard timeout 命中情况都记下来，然后和这次已有结果合并，按分布再反推阈值。这样得到的是“数据驱动阈值”，不是拍脑袋常量。也就是说，当前先定策略框架，不急着定死数字。

***

## 4. 工具预算与长工具链治理

状态：`待讨论`

### 为什么要推进

从现在的 evidence 看，复杂题失败不一定是模型“不会答”，而常常是：

- 搜索过多
- 抓取过多
- turn 数过多
- token 膨胀过多
- 最后 runtime 没有干净结束

如果不控制工具预算，强模型也可能被拖成坏链路。

### 已有证据

`GPT-5.4 / usecase_2` 复测里已经出现：

```text
tool_calls: 60
input_tokens: 1,228,128
num_turns: 24
```

这已经不是“回答慢一点”，而是“工具型任务失控”。

### 待拍板问题

1. 是否需要 provider 级预算项：
   - `max_tool_calls_per_member`
   - `max_turns_per_member`
   - `max_search_calls`
   - `max_fetch_calls`
2. 预算打满时，状态记为：
   - `dropped_tool_budget`
   - 还是 `failed_runtime`
3. 对 research 类问题，是放宽预算，还是做双模式：
   - default mode
   - deep research mode

### 我当前建议

- 预算超限应有单独状态，不应和普通 runtime failure 混在一起
- 先做“统计 + 展示”，再做“硬限制”
- 优先把 budget 纳入 artifact、HTML、validate，而不是先盲目一刀切

### 你的问题区

\>>> 评论：设定预算并达到了上限，这些模型表现是什么样的呢？是约束模型不会达到从而正常进行，还是直接退出终止？这两种方式哪种更稳定且适合我们。

\>>> 回复：这要分两层看。第一层是“软约束”，比如在 prompt 或 provider 策略里暗示少搜、少抓、少 turn，希望模型自行收敛；第二层是“硬约束”，真的达到预算上限后由 runtime 直接终止。就稳定性而言，单靠软约束不够，因为强模型在开放式调研题上仍可能持续扩张工具链；但一上来就硬杀也太粗暴，容易误伤本来快要收口的高质量回答。更适合 CLC 的方案是分阶段：先做可观测的软预算和预警，例如超过阈值后标红、记录 `tool_budget_near_limit`；如果继续突破真正上限，再硬终止并记成单独状态，例如 `dropped_tool_budget`。这样比“完全放任”更稳，也比“一刀切立即杀掉”更适合我们，因为它保留了高质量模型的收口机会，同时避免整轮被无限拖死。

\>>> 评论2：ok，但我认为这点能否用第一性原理考虑，怎么设计更合理简洁，用zoom out技能思考。

\>>> 回复2：可以，我先不用“预算”这个实现词，而用第一性原理来重述。我们真正要解决的，不是“限制模型”，而是“保护 council 主链路在有限时间内稳定产出结果”。从这个视角看，复杂工具链只是成本，不是目标；目标始终是：在可接受时间内拿到足够好的候选回答并推进下一阶段。所以更简洁的设计不应该是一堆细碎阈值，而应该只有两层机制：

```text
1. 探索预算
   允许模型为了提高答案质量去搜索和抓取，但探索不能无限扩张

2. 产出责任
   一旦探索已经足够，模型要么交付当前最好答案，要么退出主链路，不得无限占用 council 时间
```

对应到实现上，我建议产品层只保留一个简单原则：

```text
任何 member 都只有两个阶段：
- explore
- deliver
```

而不是让用户面对一堆 `max_search_calls / max_fetch_calls / max_turns`。

内部实现可以复杂，但对产品策略应保持简洁：

- 在 `explore` 阶段允许工具调用
- 到达某个内部阈值后，系统强制切到 `deliver`
- 如果模型仍不能交付，就把它标记为 dropped，不继续阻塞

这样设计比单纯“软约束”更稳，因为它最终有强制收口；也比“一达到预算立刻杀掉”更合理，因为它给了模型一个最后交卷窗口。换句话说，最简洁的第一性原理版本不是“限制工具次数”，而是“限制探索阶段的无限膨胀，并强制进入交付阶段”。这更贴近我们要的产品结果，也更容易和 quorum 机制结合。

如果后面落实到工程，我会尽量把外部配置面收敛成少量概念，例如：

```text
member_mode:
- normal
- deep_research

member_stage_policy:
- explore_window
- deliver_window
```

底层细颗粒度指标我会保留给内部 trace 分析和调参用，不把它们暴露成一堆你需要关心的产品参数。

***

## 5. partial output 救回与报告展示

状态：`待讨论`

### 为什么要推进

当前有些 case 虽然最终 status 是失败，但中间其实已经产出了可观内容。

如果只看最终 parsed response，会把有价值的中间产物直接丢掉，不利于：

- 人工复盘
- 失败归因
- 后续 fallback chairman 接管
- 用户理解“失败到底失败在哪”

### 已有证据

- 旧 `GPT-5.4 / usecase_2` 曾有 11k+ chars partial output 但最终失败
- 旧 `MiniMax-M2.7 / usecase_3` 曾有 16k+ chars partial output 但最终失败
- 当前 artifact 还没有系统地区分：
  - 最终响应长度
  - 中间 assistant 内容总量
  - 是否可恢复 partial output

### 待拍板问题

1. 是否新增字段：
   - `final_response_chars`
   - `assistant_content_chars_total`
   - `last_assistant_content_chars`
   - `raw_partial_recoverable`
2. fallback chairman 是否需要看到 recovered partial output？
3. HTML 是否显式展示：
   - 成功成员
   - dropped 成员
   - failed with partial output 成员

### 我当前建议

- recovered partial output 只作为诊断和参考材料，不直接混入正式 Stage 1 有效回答集合
- HTML 必须把失败但有 partial output 的成员展示出来
- validate 需要校验 partial output 的来源和标注是否完整

### 你的问题区

\>>> 评论：评测除了看结果，要重点看过程trace是必要的必须的，具体的参数我不想关注，请你自行定义。这些定义是给你用的，你需要摸清楚现状，甚至你可以直接去看会话的运行完整日志（若能找到的话）而不是开头定义，即事后拿着最完整原始的记录做过程分析。

\>>> 回复：同意，而且这会成为后续评测的默认方法。你不用盯参数细节，我来定义一套过程分析口径，但分析时不会只看摘要字段，而是优先回到最原始记录，包括 `events.jsonl`、`*.coco.stream.jsonl`、`*.session.log`、`*.session.json`、`stderr.log` 这一层。如果能拿到完整会话日志，就以完整日志为准，再回填出结构化指标。换句话说，后续评测结论要尽量建立在“原始 trace -> 过程还原 -> 结构化归因”这条链路上，而不是只看最后的 `success/fail`。我会把这项要求落实成一套固定分析维度，例如：是否排队、是否授权阻断、首 token 时间、工具调用序列、最后一次有效 assistant 输出、失败前最后一个 runtime 事件、partial output 是否可救回。你不需要看这些字段名，但我会用它们把过程摸清楚。

***

## 建议的执行顺序

这是我当前建议的实现顺序，不代表最终必须这样做：

1. 先改 `provider`，把 `traecli -y` 和 `permission_mode` 记录补齐
2. 再做 timeout / budget 的指标落盘
3. 再把 Stage 1 改成 quorum 模式
4. 再做 chairman fallback
5. 最后补 HTML / validate 对 degraded run 和 partial output 的展示

原因：

- 先把 runtime 口径校正，否则后面所有结论都有噪音
- 先把观测做全，再决定怎么限制
- quorum / fallback 属于更大的行为变更，最好建立在更可信的 runtime evidence 上

***

## 你可以直接这样继续

你后续可以直接在这份文档里用下面这种格式继续提问：

```text
>>> 问题：
你这里说的 XXX，我不认同，因为 ...

>>> 新要求：
请把 YYY 改成 ...

>>> 决策：
这一项先按 ZZZ 做
```

我会基于这份文件继续更新，而不是每次重新整理上下文。
