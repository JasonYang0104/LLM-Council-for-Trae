# LCT 体验升级 · 架构实现方案（交执行 Agent）

日期：2026-06-06　·　决策来源：`DECISIONS.md` ADR-0001（先读它）　·　视觉基准：`docs/lct-experience-upgrade-mockup-20260606.html`

---

## 写在前面：这份方案怎么用

这不是一份逐条照抄的施工单。我假设你是一位聪明的工程专家，所以我给你的是**意图、背景、目标和边界**，把"怎么实现"留给你。你需要先理解我们为什么这么改，再自己收敛出清晰的落地路径。

两类内容请区别对待：

- **意图与自由度**：凡是讲"为什么、想达到什么效果"的地方，你有充分的实现自由。数据结构的字段名、函数怎么拆、交互怎么写，你定。
- **Spec 与不变量（不可偏离）**：凡标注「约束」「不变量」「红线」的地方，是这次升级的可信与兼容底线，必须满足；凡引用了**核心文件**的地方，那个文件是事实源，改动前先读它。

如果你在实现中发现某条约束与现有代码冲突、或意图描述不足以决策，请停下来对齐，不要猜。

---

## 一、背景：你在改的是什么

`LLM-Council-for-Trae`（LCT）是一个本地 CLI：用 `traecli` 调多个模型，让它们先各自独立回答（Stage 1）、再匿名互评排序（Stage 2）、最后由主席模型综合成一份最终答案（Stage 3），并确定性导出 HTML 报告。它已经可用，有完整的 artifact store、`validate` 交付门槛和可审计证据链。

这次**不是 runtime 重写，也不是协议变更**。我们只升级四处"用户看得见、摸得着"的体验，核心诉求是一句话：**让用户更容易理解、控制和信任结果，同时不破坏任何现有可用链路。**

贯穿全篇的哲学（你做每个取舍时都用它校准）：**可信优先、可审计不可删、不编造、向后兼容。**

四个升级点：

1. **报告顶部卡片**说人话——把工程黑话 `Quorum 4/3` 换成用户真正关心的"哪些模型参与了结果"。
2. **主席答案可追溯**——主席从"自由发挥的综合者"重新定位成"资深编辑/客观记者"，忠实整理成员素材、逐段署名来源、真有分歧才显式呈现，自己的想法一律标为"编者注"。
3. **输入改写规则更精确**——什么时候原样转交用户问题、什么时候允许 Agent 结构化重组，边界要清晰且可事后审计。
4. **用户自选模型产品化**——默认不打扰；用户想挑时给清单；挑超过 4 个时按既定优先级裁剪而非盲取；挑错名字要拦住而不是静默乱跑。

---

## 二、全局红线（任何阶段都不能破）

这些在 `DECISIONS.md` §9 和上游 brief 里都有，这里再钉一遍，因为这次会动展示层、Skill 和模型选择，最容易顺手破坏它们：

- 非交互路径 `run --input _lct_question.md --default-models --json` 行为不变。
- 显式路径 `run --members A,B,C --chairman D --json` 在**成员数 ≤4 时**行为不变。
- runtime override 路径 `--runtime-command coco run/validate` 不变。
- `validate <run_id> --json` 的门槛字段与 `verdict` 逻辑不变；所有新增校验都是 **additive + legacy 兼容**（缺新字段的旧 run 不能被判坏）。
- HTML export 只读 artifacts，**不调用模型、不在导出阶段重算或改写**。
- 外层执行职责（notes/validate/Git/PR）不得进入 `_lct_question.md`。
- `lct_search_allowed` 与 `lct_search_used` 必须分开；`backfill_candidates` 仍只来自 terminal manifest 的 `metadata.quorum.backfill_candidates`。

---

## 三、分阶段方案

三个阶段从零风险到高风险递进，**不要塞进同一个 PR**；若必须同轮，拆独立 commit，让 `validate` 和测试逐层通过。

### 阶段一 · 零协议风险（展示层 + 文档 + 测试）

#### ①　报告顶部「成员模型」卡片

**意图。** 顶部摘要区现在对普通用户不友好。`render_summary_cards`（`src/llm_council_for_trae/html_export.py`，约 834 行）在 quorum 存在时渲染的是 `Quorum 状态 / 4 · 3 / normal quorum / 有效成员：…`。`4 / 3` 实际是 `effective_valid_members / min_valid_members`，工程师能懂，用户只想知道"谁参与了最终结果"。

**目标（声明式）。** 让顶部摘要一眼回答"参与最终结果的是哪些模型"，而不是暴露 quorum 阈值。

**约束。**
- 该卡片标题用「成员模型」，内容取 `metadata.quorum.effective_stage1_members`，缺失时回退 `config.members`。
- 卡片内**不得出现** `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：` 这类技术文案。
- **quorum 与 backfill 证据一个都不能删**：当前被删卡片里寄生着 `backfill_attempted` 等字段（约 850-859 行），它们必须仍能在证据层找到——`render_metadata`（约 1051 行）、`render_alerts`（约 1064 行，degrade banner 行为不变）、或 manifest JSON 附录。这是 §9.8 backfill provenance 保护项，别顺手清掉。

**自由度。** 卡片网格如何排、是否保留"最高排序成员"卡、措辞润色，你定。整页风格已成熟（`html_export.py` 的 `:root` 设计 tokens、`.summary-strip/.summary-card`），沿用即可。

**文件。** 仅 `src/llm_council_for_trae/html_export.py`。

**验收。** 给一个 4 有效成员、`min_valid_members=3` 的 fixture manifest：报告顶部标题为「成员模型」、列出有效成员、无 quorum 黑话；证据/metadata 区仍能查到 quorum 细节。对齐 brief §11.1。

#### ③　输入改写规则写精确

**意图。** `skills/llm-council-for-trae/SKILL.md` 的 `Input Preparation`（约 37-104 行）已经有 raw / structured / fact pack / operator envelope 四态，方向对，但触发边界不够精确，容易误判。

**目标（声明式）。** 让这几类表达稳定走对模式：
- "使用 LCT 回答 …"、"不要改写/按原文/只用原始输入"、"评估 LCT 对原问题的理解" → `raw original input`，只追加 `Report topic`。
- "先想我真正需要什么"、"站在架构师角度评估"、"要 fact pack/最新资料/来源" → `structured by Agent`，但必须保留 `Original input`，fact pack 直接内嵌并标来源。
- 执行职责（notes.md / validate / Git / PR）永远是 operator envelope，**绝不进 council input**。

**约束。**
- 维持"矩阵式关键词规则"，**不下沉到 CLI，不引入 ML 分类**（输入意图判断本质是外层 Agent 的职责，CLI 须保持 runtime/Agent 无关）。
- 必须有负向用例：`详细分析`、`深入一点`、`给完整方案` **不得**单凭字面触发结构化改写。
- index 必须记录 `Input mode`、`agent_added_context`、`agent_fact_pack_path`，让事后能判断输入是否被改造。

**自由度。** 关键词集合、矩阵如何在 Skill 里表达、措辞，你定。

**文件。** `skills/llm-council-for-trae/SKILL.md` + 文档契约测试（仿 `tests/test_global_install_skill_docs.py`）。

**验收。** brief §11.3 的用例。

#### ④a　模型选择的触发边界（仅文档）

**意图。** 把"什么时候才询问/展示模型清单"讲清楚，避免默认打扰用户。

**目标（声明式）。** 用户没表达选模型意图 → 不询问、走默认 4 成员；用户明确要挑成员/指定主席 → 展示当前 `traecli models --json` 清单；匹配只接受 exact / case-insensitive / 菜单编号，**不做模糊匹配**（选错模型代价高）。

**约束。** 这一节只写进 Skill/Agent workflow；真正的裁剪与校验逻辑在阶段二落到 CLI。`AskUserQuestionTool` 只能是可选体验，必须有纯文本 fallback。

**文件。** `skills/llm-council-for-trae/SKILL.md`。

---

### 阶段二 · 用户自选模型产品化（CLI 内核 + 文档）

**意图。** 现在 CLI 对 `--members` 是 `split_csv` 全盘接受（`src/llm_council_for_trae/cli.py`，约 248 行），**没有任何 >4 裁剪**；`target_valid_members=4` 只是 quorum 目标不是成员上限。匹配函数 `resolve_model_token`（`src/llm_council_for_trae/model_selection.py`，约 275 行）已经支持 exact/case-insensitive/编号，正好等于我们要的，不用动它。缺的是：把用户的自选**归一化到恰好 4 个成员**（不足补足、超过裁剪）、来源记录、以及与现有兜底/校验的衔接。这些放在 CLI 的自选归一化入口，因为非交互 Agent 路径也要走、且要落 manifest 供审计——只写 Skill 不够。

**目标（声明式）。** 把用户的选择当"种子 + 偏好"，归一化成**恰好 4 个成员**的 run config：不足按优先级补足、超过按优先级裁剪、挑错名字仍拦、运行中失败由现有兜底顶上、摘要只呈现有效成员、全过程留痕。**不打扰、不阻断、不静默出错。**

**约束（简化后的解析规则，必须实现）。**
- 用户选择一律归一化到**恰好 4 个成员**（可用模型总数不足 4 时补到上限，且 ≥ 默认最低有效数 3）：
  - **不足 4** → 按 `PREFERRED_MEMBERS`（`model_selection.py`，约 10-21 行）优先级，从用户没选的可用模型补足到 4（并集去重）。
  - **超过 4** → 按同一优先级裁剪到 4；用户选了但不在优先级内的模型排在最后、优先被裁。
  - **正好 4** → 原样使用。
- **运行中成员失败** → 走**现有 auto-backfill**（兜底池默认 = 优先级 roster；用户显式 `--backfill-members` 时用显式池）顶上失败名额。这是现有行为，自选路径同样启用，**无需新增逻辑**。
- 摘要卡只呈现**有效成员**（见①的 fallback 收紧）；**本期不为"选了但运行失败"的成员单独做提示**（审计信息仍留在 metadata）。
- 仍保留的硬校验：最终 members/chairman 必须存在于当前 `traecli models --json`；**不存在/拼错的名字仍要拦或追问，不得静默替换**（brief §7.4 红线）。
- chairman 单独校验，指定主席不自动替换 members（除非用户明确要求）；匹配维持 exact / case-insensitive / 编号，**不加 fuzzy/alias**。

**留痕（声明式，字段形态交你定）。** manifest 要能审计地记录：用户请求了什么、解析成了什么、裁剪掉了什么、最终 config 是什么、有没有用到交互。brief §4 列了一组建议字段可参考，但**具体字段命名与结构由你决定**，约束只是"可审计地覆盖请求/解析/裁剪/最终结果"。裁剪发生时，交互环境建议让用户确认、非交互环境必须在 index 记录。

**不变路径（不变量）。** 归一化到 4（补足/裁剪）**只发生在自选体验路径**——交互菜单或 Agent 辅助选择，经 `resolve_run_model_choice` / 新增归一化入口（见审查裁决 A1）。`--default-models`、**原生 `--members A,B,C` 直接 CLI 参数**（automation/power 路径，brief §9 保护"给几个跑几个"）、`profile`、`subagent` 路径维持现有精确语义，**不自动补足/裁剪**。

**自由度。** provenance 字段命名与结构、追问交互的实现、`AskUserQuestionTool` 怎么接（可选、须文本 fallback），你定。

**文件。** `src/llm_council_for_trae/model_selection.py`、`cli.py`、`validation.py`（additive 校验）、`skills/llm-council-for-trae/SKILL.md`。优先级与主席备选链另见 `roster.py`。

**验收。** brief §11.4 相关用例（按本简化规则调整）。重点覆盖：自选 <4 → 优先级补足到 4、自选 >4 → 优先级裁剪到 4、失败 → 现有兜底顶上且摘要显示有效成员、不存在模型名仍被拦、原生 `--members`/`--default-models` 路径不变。现有 `tests/test_lct_model_productization.py` 只覆盖了 recommendation 的 cap-at-4，**补足/裁剪/provenance 是你要补的主战场**。

---

### 阶段三 · 主席贡献说明（最重、现在默认开启）

这是整个升级里最难、信任风险最高的一块。第一版曾作为默认关闭的灰度能力落地；2026-06-06 后续裁决已经把它升级为默认开启的产品能力：默认请求主席输出 contribution map，HTML 优先用 sidecar blocks 渲染来源；调用方只在明确关闭时传 `--no-chairman-contribution-map`，release / E2E strict gate 才传 `--require-chairman-contribution-map`。**完整决策见 `DECISIONS.md` ADR-0001 决策 2，视觉基准见 `docs/lct-experience-upgrade-mockup-20260606.html`（已沿用现有 `html_export.py` 风格）。** 下面是给你的意图收敛和必须守的不变量。

**意图与定位。** 主席的角色是**资深编辑 / 客观记者**，核心价值是"可信"——让读者永远能分清"成员真说的（素材）"和"主席自己加的（评注）"，防止单一主席模型用自身观点劫持多模型的集体结论。它默认做忠实整理，自己的判断一律隔离成"编者注"。

主席的三个核心输入你要喂全：Stage 1 各答案、Stage 2 同侪互评、**Stage 2 综合排序**（`aggregate_rankings`）。现 `build_stage3_prompt`（`src/llm_council_for_trae/council.py`，约 794-854 行）已经喂入综合排序并要求"显式融合 top-ranked responses"，你在它基础上演进，别丢掉这条。

**目标（声明式）。**
- 最终答案是一篇**适中结构化的编辑式综述**：用章节标题组织（标题是编辑的结构整理、**不署名**），正文好读、不做过度提纲。
- **每段正文都带一条来源**，四类之一：单一成员（附同侪排名）、多成员共识（≥2 在场成员）、编者注（主席原创、须基于成员素材延伸、视觉隔离）、综合整理（拆不到具体成员）。
- **真有分歧才用独立"分歧块"**呈现两个对立观点各自的成员来源 + 同侪排名 + 编者注；无实质分歧不编造对立。分歧块是独立展示构造，不是四类来源标签之一。
- 来源旁的"同侪#n"由 `aggregate_rankings` 确定性带出，是主席改不了的可验证锚点。

**不变量（必须满足，机制不限）。**
- 每段正文与其来源必须**可靠对应**，HTML 导出阶段不得错位。（用块序列、锚点映射还是别的对齐机制，你定。）
- 来源/分歧引用的成员必须**真在场、可校验**；标"多成员共识"须 ≥2 在场成员；拆不到就标"综合整理"，**不得为凑署名硬安单一模型**。
- `validate` 校验引用合法性（成员在场、共识 ≥2、类型合法）。`requested=true, required=false` 是默认路径：缺附属文件或结构非法只记录 warning，HTML fallback 到现有 `render_markdown`（`html_export.py`，约 658 行），不能把可读 final answer 判死。`required=true` 才把缺失、schema 非法、成员引用非法或 consensus 成员少于 2 判为 failure。缺 `metadata.chairman_contribution` 的 legacy run 不失败；显式 disabled 不要求 sidecar。
- HTML 不调模型、不在导出阶段重算归因。

**红线。**
- **排名 ≠ 贡献**：系统只并排展示同侪排名，绝不自动判定"排名高=贡献大"。
- **呈现的是观点分歧，不是模型评比**：不得变成"GPT 比 DeepSeek 强"的排行。
- 保守措辞、**禁止百分比**、判断不了就用"综合整理/无法归因"做退路。
- **默认开启、显式关闭、显式强校验**：默认 requested；`--no-chairman-contribution-map` 关闭；`--require-chairman-contribution-map` 打开 strict gate。

**自由度（按你前述要求放权）。** 结构化展示的具体数据形态——附属文件的字段名、枚举写法、正文与来源的对齐机制——**完全交你定夺**。架构只约束上面的不变量和红线，不规定模板。先在内部跑一批看分歧与归因质量，再决定是 prompt-only、sidecar，还是加确定性辅助。

**文件。** `src/llm_council_for_trae/council.py`（`build_stage3_prompt`）、`store.py`（拆附属文件）、`validation.py` + `schema_contract.py`（additive 校验，复用 `validate_schema(..., optional=...)` 模式，约 164 行）、`html_export.py`（渲染来源条/分歧块/编者注 callout，沿用现有风格）。

**验收。** brief §11.2 全部用例 + 本节不变量。新增验收：默认 config / 默认 Stage 3 prompt 必须请求 contribution map；`--chairman-contribution-map` 保持兼容；`--no-chairman-contribution-map` 关闭；`--require-chairman-contribution-map` 将缺失或非法 sidecar 升级为 validate failure；默认 requested 但 not required 的缺失或非法 sidecar 只产生 warning。

---

## 四、全局回归与验收

任何阶段实现完成前必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如触及 live runtime / 模型选择 / Skill path，且 live runtime 可用，补：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

live runtime 不可用时**必须明确标记 skipped，不得用 fixture/单测冒充 live**。

第二章的全局红线在每个阶段收尾时都要回归确认，尤其是"展示层改动没有删掉 quorum/backfill/search 证据"。

---

## 五、实施顺序与交付方式

按阶段一 → 二 → 三推进，风险从低到高。每个升级点都先对齐意图、再落实现、最后过验收与回归。三个阶段独立成 PR 或独立 commit，`validate` 与测试逐层绿。

涉及长期影响（新附属文件、CLI 行为变更、新增 manifest 字段）的落地，请在 `DECISIONS.md` 追加或细化对应条目，标明你最终选定的数据形态与理由——ADR-0001 已记录架构决策，你补的是实现层决策。

---

## 附录：执行前架构审查补充（2026-06-06）

结论：本规格可以进入分阶段实现，但执行前要把下面几个架构边界固化，否则最容易破坏当前已可用链路。以下是架构问题，不是新增需求。

### A1. 显式 `--members` 兼容性与 `<3` fail-closed 的边界必须先分层

当前代码里，`resolve_run_model_choice()` 对显式 `--members/--chairman` 直接返回 `None`，随后 `build_config()` 走 `split_csv(args.members)`。也就是说，显式 CLI 参数现在绕过交互选择层。

本规格同时写了两条容易被执行 Agent 混淆的约束：

- "`--default-models` 与成员数 ≤4 的显式 `--members` 路径必须字节级不变"；
- "`<3` members → 交互追问 / 非交互 fail-closed"。

最终裁决是：

- `--default-models` 不变；
- 原生 `--members` / `--chairman` 是 power-user 精确路径，给几个跑几个，不补足、不裁剪；
- agent-assisted 自选路径使用 `--selected-members` / `--selected-chairman`，才会补足/裁剪到 4 并写 provenance；
- `--selected-chairman` 当前不能单独出现；如果用户只想指定主席且成员保持默认，必须明确改用原生 `--members/--chairman` 并说明该路径是精确语义；
- 这个行为边界必须有单测和 manifest provenance，避免看起来像 silent fallback。

不要把 `<3` 逻辑写成一个无差别后置校验，导致 profile、subagent legacy、测试 fixture 或默认路径被误伤。建议新增一个明确的模型选择归一化入口，例如 `normalize_user_model_selection(...)`，只服务 direct provider 的用户选择路径；profile/subagent 路径另走自己的兼容边界。

### A2. `AskUserQuestionTool` 只能在外层 Agent/Skill，不能进入 LCT core

现有 `docs/design.md` 已明确：CLC/LCT core 不依赖 Trae-CN DOM、selector、UI 工具或 `AskUserQuestion`，CLI 自己只能通过 TTY 提问；无交互宿主必须用 `--default-models`、显式参数或 profile。

因此阶段二实现时要保持三层分工：

- outer Agent/Skill：识别用户表达了"我要选模型"，可选调用 `AskUserQuestionTool`，并有纯文本 fallback；
- CLI TTY：继续支持当前 stdin/stderr 菜单；
- CLI non-interactive：不追问，fail-closed 并输出可机器消费的错误。

不要在 core 里 import 或模拟 `AskUserQuestionTool`。如果要在 manifest 记录交互方式，记录的是 `interaction_surface`，例如 `agent_ask_user_question` / `cli_tty` / `none`，而不是把某个宿主工具变成运行依赖。

### A3. 模型选择 provenance 不能只挂在 CLI 临时对象上

当前 `ModelChoice` 只有 `members/chairman/source`，而本规格要求记录"用户请求了什么、解析成什么、裁剪掉什么、最终 config 是什么、有没有交互"。这些信息如果只保存在 `args.selected_model_choice`，进入 `run_full_council()` 后就很难稳定写进 manifest。

建议在实现前确定一个持久数据通道：

- 要么扩展 `CouncilConfig` 增加 `model_selection_provenance`；
- 要么让 `cmd_run()` 在创建 store 后、进入 council 前写一个 preflight manifest/metadata，再由 `run_full_council()` 合并；
- 不建议散落在 `cli.py`、`model_selection.py`、`council.py` 三处分别拼字段。

验收标准应包含：默认路径无新增噪音；发生裁剪、少于 3、含非排名模型、用户确认时，manifest 都能复盘。

### A4. summary card 的 fallback 只应用于 legacy 缺字段，不应用于新 run 的空有效列表

阶段一要求「成员模型」取 `metadata.quorum.effective_stage1_members`，缺失时回退 `config.members`。这个方向对，但要补一条执行约束：

- 如果整个 `metadata.quorum` 缺失，说明是 legacy run，可以回退 `config.members`；
- 如果 `metadata.quorum` 存在但 `effective_stage1_members` 为空或缺失，不应直接显示 `config.members`，否则会把失败成员显示成参与结果的成员。

新 run 下，`effective_stage1_members` 应是事实源；配置成员、失败成员、backfill、low quorum 仍保留在 metadata/evidence，而不是顶部卡片。

### A5. 主席贡献说明必须先选定"块模型"，不能只靠 Markdown 段落事后猜

阶段三最危险的点不是样式，而是"段落和来源可靠对应"。当前 Stage 3 只产出 `stage3/final.md` 与 `stage3/final.json`，`html_export.py` 对 Markdown 做确定性渲染。如果在 HTML export 阶段按空行切段再套来源，很容易因为主席输出格式变化而错位。

执行前必须先选一个块级 contract：

- 推荐：主席输出结构化 blocks，store 写 `stage3/contribution_map.json`，HTML 从同一块序列渲染正文和来源；
- 可接受：`final.md` 中使用稳定锚点，sidecar 用锚点映射；
- 不推荐：HTML export 事后按自然段猜测归因。

无论选哪种，`validate` 只校验结构合法与引用合法，不声称能验证"真实贡献程度"。无法可靠归因时使用"综合整理/无法归因"，不要硬配单一成员。

### A6. requested / required / disabled 标记要先定义，否则 legacy 兼容测试会模糊

阶段三第一版要求默认关闭、灰度验证；2026-06-06 后续裁决已经改为默认 requested，并新增显式 disabled 与 strict required。执行 Agent 可以调整字段名，但必须满足：

- 默认：manifest 或 `final.json` 明确声明 contribution map `requested=true, required=false`，Stage 3 prompt 请求 sidecar；
- 显式关闭：`--no-chairman-contribution-map` 后 `requested=false`，完全走现有 `final.md` Markdown 渲染，不要求 sidecar；
- 默认 requested 且成功：写出 sidecar，HTML 使用 blocks 渲染；
- 默认 requested 但 sidecar 缺失/非法：`validate` 只记录 warning，HTML fallback Markdown，不把可读 final answer 判死；
- strict：`--require-chairman-contribution-map` 后 `requested=true, required=true`，sidecar 缺失或非法时 `validate` 失败；
- legacy run 缺 metadata / sidecar：不失败。

建议把这个实现层决策补进 `DECISIONS.md`，因为它会影响公共 artifact contract。

### A7. Skill 文档有多份安装形态，阶段一改文档时要明确同步边界

仓库内事实源是 `skills/llm-council-for-trae/SKILL.md`，同时本机还有全局安装副本（例如 `~/.LCT/skills/llm-council-for-trae/SKILL.md` 与 `~/.agents/skills/llm-council-for-trae/SKILL.md`）。阶段一如果只改仓库内 Skill，测试能绿，但本机实际调用可能仍读旧副本。

建议执行计划写清：

- PR/commit 只改仓库事实源与文档契约测试；
- 如要让本机立即生效，另跑安装同步命令并单独记录验证；
- 不要把"仓库 Skill 已更新"说成"全局 Skill 已生效"，除非实际安装验证过。

---

## 架构师裁决：回应执行前审查（2026-06-06）

先说总结论：**A1–A7 七点全部采纳，没有一条是阻断性分歧，可以进入实现。** 这是一次到位的执行前审查——你核对的代码事实（`resolve_run_model_choice`/`build_config`/`split_csv(args.members)` 链路、`docs/design.md` 的 core 无 UI 依赖原则、`ModelChoice`/`CouncilConfig` 现状）我已逐一确认属实。下面给你逐条裁决与边界固化。

**A1 · 显式 `--members` 与 `<3` 分层 —— 采纳。** 新增的「`<3` 保护 / `>4` 裁剪 / 含非排名模型」逻辑只走一条**专属归一化入口**（你建议的 `normalize_user_model_selection(...)` 很合适），且只服务 direct-provider 的用户选择路径。`profile`、`subagent`、`--default-models`、**原生 `--members`**、测试 fixture 各自维持现有兼容边界，**绝不写成无差别后置校验**。判定边界钉死（简化后）：**自选路径**不论选几个都归一化到 4——不足按优先级补足、超过按优先级裁剪；**原生 `--members` 维持精确语义、不补不裁**（§9）。归一化是真实行为变更，必须配单测 + manifest provenance，让它读起来明确不是 silent fallback。

**A2 · `AskUserQuestionTool` 不进 core —— 采纳。** 三层分工就按你写的：outer Agent/Skill 识别"我要选模型"意图、可选调用该工具、并有纯文本 fallback；CLI TTY 维持现有 stdin/stderr 菜单；CLI 非交互 fail-closed、输出可机器消费的错误。**core 不 import、不模拟该工具**（与 `docs/design.md` 一致）。manifest 记录的是 `interaction_surface`（取值如 `agent_ask_user_question` / `cli_tty` / `none`），而不是把某个宿主工具变成运行依赖。

**A3 · provenance 要有持久通道 —— 采纳。** 不能只挂在 `args.selected_model_choice` 临时对象、也不许散在 `cli.py`/`model_selection.py`/`council.py` 三处拼字段。**推荐扩展 `CouncilConfig` 增一个 `model_selection_provenance` 结构体**（单一事实源最干净，能稳定随 config 进 manifest）；若改用 preflight metadata 再合并也可接受，但要保证 run 中途失败时仍能复盘。字段命名与结构仍交你定，约束是「持久 + 可复盘 + 默认路径零新增噪音」。

**A4 · summary card fallback 收紧 —— 采纳，并据此修正阶段一约束。** 把①的 fallback 细化为：**仅当 `metadata.quorum` 整体缺失（legacy run）才回退 `config.members`**；若 `quorum` 存在但 `effective_stage1_members` 为空/缺失，**不得**显示 `config.members`（那会把失败成员冒充参与者），应如实呈现（空 / 降级提示），失败成员、backfill、low quorum 留在 metadata/evidence。新 run 下 `effective_stage1_members` 是唯一事实源。（我已同步更新 `DECISIONS.md` 决策 1。）

**A5 · 贡献说明先定块模型 —— 采纳，重申不变量。** 「段落 ↔ 来源可靠对应」是阶段三第一风险，不是样式问题。**实现前必须先选定块级 contract，不允许在 HTML export 阶段按空行/自然段事后套来源。** 推荐：主席输出结构化 blocks → store 写 `stage3/contribution_map.json` → HTML 从同一块序列渲染正文与来源；用稳定锚点映射亦可接受；事后猜测明确禁止。`validate` 只校验结构合法与引用合法，**不声称能验证"真实贡献程度"**；拆不到用"综合整理/无法归因"，不硬配单一成员。

**A6 · feature flag 与启用标记先定义 —— 采纳。** 启用契约四态固化：未开启 → 完全走现有 `final.md` markdown 渲染、不要求 sidecar；开启且成功 → manifest 或 `final.json` 明确声明 contribution map enabled 且写出 sidecar；开启但 sidecar 缺失/非法 → `validate` 失败；legacy run 缺 sidecar → 不失败。字段名你定，但这属于**公共 artifact contract**，落地时**必须把这个实现层决策补进 `DECISIONS.md`**。

**A7 · Skill 多副本同步边界 —— 采纳。** 仓库内 `skills/llm-council-for-trae/SKILL.md` 是唯一事实源；PR/commit 只改它 + 文档契约测试。本机全局副本（`~/.LCT/...`、`~/.agents/...`）的生效另跑安装同步命令并**单独记录验证**；**不得把"仓库 Skill 已更新"等同于"全局 Skill 已生效"**，除非实测验证过。

裁决到此。A4 我已改进上文阶段一与 `DECISIONS.md`；A6 待你选定字段后回写 `DECISIONS.md`。其余按上述边界直接实现即可，遇到与现有代码的新冲突仍按"停下来对齐、不要猜"处理。

---

## 第二轮执行前架构审查补充（2026-06-06）

结论：新版已解决 A1–A7 的大部分歧义，但还剩一个会直接影响实现的公共接口缺口。执行前必须补齐，否则"自选体验路径归一化到 4"和"原生 `--members` 给几个跑几个"无法同时成立。

### B1. 非交互自选路径缺少可区分的 CLI 入口

新版阶段二已经把边界改清楚：归一化到 4 只发生在"自选体验路径"，原生 `--members A,B,C` 直接 CLI 参数维持现有精确语义、不补不裁。这是正确方向。

但当前 CLI 入口只有这些状态：

- 无 `--members/--chairman/profile/default-models` + TTY：进入 `select_model_choice_interactively()`；
- 无上述参数 + 非 TTY：直接报错；
- 传 `--members/--chairman`：`resolve_run_model_choice()` 返回 `None`，`build_config()` 直接 `split_csv(args.members)`；
- `--default-models` / `profile`：各走现有路径。

因此，**非交互 Agent 辅助选择**现在没有一个能表达"这是用户自选种子，请归一化到 4 并记录 provenance"的 CLI surface。如果外层 Agent 最后还是只能传 `--members`，CLI 无法判断这是：

- power user 原生命令：给几个跑几个；
- 还是 Agent/AskUserQuestion 代用户选择：应补足/裁剪到 4。

推荐补一个显式 opt-in 入口，避免破坏原生 `--members`：

- 方案 1（推荐）：新增一个布尔开关，例如 `--normalize-selected-members`。只有同时传 `--members` 且该开关为 true 时，才把 `--members` 当用户自选种子归一化到 4；默认 false，原生 `--members` 完全不变。
- 方案 2：新增单独参数，例如 `--selected-members` / `--selected-chairman`，专门代表自选体验路径；`--members` 继续保持 raw。
- 不推荐：让 `--members >4` 自动裁剪、`--members <4` 自动补足。这会和新版"原生 `--members` 精确语义"冲突，也会破坏 automation/power user 心智。

不管选哪种，manifest provenance 至少要能区分：

- `selection_surface=cli_raw_members`：原生 `--members`，无归一化；
- `selection_surface=cli_tty_custom`：TTY 自定义选择，经归一化；
- `selection_surface=agent_assisted`：外层 Agent/AskUserQuestion/文本 fallback 选择，经归一化；
- `selection_surface=default_models` / `profile`：现有路径，不归一化。

### B2. `DECISIONS.md` 的影响范围仍有一句与新版裁决冲突

`DECISIONS.md` 当前同时表达了两件事：

- 决策 4：原生 `--members` 直接 CLI 参数维持精确语义，不自动补足/裁剪；
- 影响范围：`run` 对 `--members >4` 引入裁剪行为。

这两句不能同时成立。若采纳新版裁决，影响范围应改成类似：

> 公共接口：新增自选归一化入口；原生 `--members` 行为不变。自选归一化入口对用户选择的 members 执行补足/裁剪并写入 provenance。

否则执行 Agent 很可能按"看到 `--members >4` 就裁剪"实现，直接打穿 B1 的兼容边界。

### B3. A1 原审查段落已被新版裁决部分覆盖，执行时以裁决和阶段二正文为准

A1 原文里的“原生 `--members` 直接按成员数触发裁剪或保护”的旧说法已经作废。新版裁决已经把它改成"原生 `--members` 不补不裁，自选体验路径才归一化"。

执行 Agent 阅读时应以三处为准：

1. 阶段二正文的"不变路径（不变量）"；
2. "架构师裁决"里的 A1；
3. 本节 B1/B2。

不要按 A1 的旧裁剪说法实现。

---

## 架构师裁决（第二轮）：回应 B1–B3（2026-06-06）

总述：B1 是真实的公共接口缺口，采纳并定方向；B2 是我决策文档里一处自相矛盾，已修；B3 是 precedence 确认。三点都属接口设计与文档一致性，无需用户拍板，按授权我直接定。当前 CLI 入口状态（`resolve_run_model_choice` 返回 `None` 时 `build_config` 走 `split_csv(args.members)`、TTY 走 `select_model_choice_interactively`）已核对，B1 描述属实。

**B1 · 自选路径需要可区分的 CLI 入口 —— 采纳，方向定死。**

- **原生 `--members` 永不归一化**：给几个跑几个，§9 保护不动。这是硬不变量。
- 自选体验路径用**独立 opt-in 通道**接入归一化，**不复用、不重载 `--members` 的语义**。
- 选型：**采纳方案 2 思路（独立参数）而非方案 1（布尔开关重载 `--members`）**。理由：独立通道语义干净、自文档化，避免"一个布尔开关改另一个参数含义"这类耦合 bug，且天然对齐 A1 的专属归一化入口 `normalize_user_model_selection(...)`。
- **具体参数命名交你定**（`--selected-members` / `--selected-chairman` 或等价物），只要满足不变量：
  1. 原生 `--members`/`--chairman` 行为零变化；
  2. 自选通道是显式 opt-in，且喂入 A1 的归一化入口（补足/裁剪到 4）；
  3. TTY 自定义选择（`select_model_choice_interactively`）也走**同一个**归一化函数，不要两套逻辑；
  4. `--default-models` / `profile` / `subagent` 不归一化。
- provenance 必须记录 `selection_surface`，能区分这五类：`cli_raw_members`（原生 `--members`，无归一化）、`cli_tty_custom`（TTY 自定义，经归一化）、`agent_assisted`（外层 Agent/AskUserQuestion/文本 fallback，经归一化）、`default_models`、`profile`。字段名你定，但区分粒度不能少于这五类。

**B2 · `DECISIONS.md` 影响范围自相矛盾 —— 采纳，已修。** 旧"`run` 对 `--members >4` 引入裁剪行为"与新版"原生 `--members` 不变"冲突，已改为"新增自选归一化入口；原生 `--members` 行为不变；归一化入口对自选 members 补足/裁剪并写 `selection_surface` provenance"。执行**不要**按"看到 `--members >4` 就裁剪"实现。

**B3 · A1 旧句作废、以新裁决为准 —— 确认。** 实现时的事实源优先级：①阶段二正文「不变路径（不变量）」② 第一轮裁决 A1（已更新）③ 本轮 B1/B2。第一轮**审查段** A1 里关于原生 `--members` 直接触发裁剪或保护的旧措辞**正式作废**，不据此实现。

裁决到此。B1 我已把方向与不变量定死、命名留给你；B2 已修 `DECISIONS.md`。可以进实现。
