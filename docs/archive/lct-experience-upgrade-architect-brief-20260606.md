# LCT Experience Upgrade Architect Brief

日期：2026-06-06

读者：第一次接触 `LLM-Council-for-Trae` 的架构师、评审者、PM owner。

## 1. 这份文档要解决什么

`LLM-Council-for-Trae` 已经可用：它能通过 `traecli` 调多个模型，跑三阶段 council 流程，保存 artifacts，执行 `validate`，并导出 HTML 报告。现在的问题不是“能不能跑”，而是“用户是否更容易理解、控制和信任结果”。

本次迭代不是 runtime 重写，也不是模型能力 benchmark。它是一次体验升级的架构评估输入，目标是让架构师先判断：怎么改才不会破坏现有可用链路，同时让用户更清楚地看见模型阵容、主席综述来源、输入是否被改造，以及用户指定模型时系统如何处理。

架构师不需要知道此前聊天历史。请按本文恢复上下文，并输出架构建议、风险、缺失信息和测试策略。不要直接写实现方案代码。

## 2. LCT 是什么

`LLM-Council-for-Trae`，简称 LCT，是一个本地 CLI。它复刻上游 `llm-council` 的核心三阶段协议：

1. Stage 1：多个 member models 独立回答同一个问题。
2. Stage 2：有效 member models 对匿名回答做互评和排序。
3. Stage 3：chairman model 阅读 Stage 1 与 Stage 2 artifacts，综合成 `stage3/final.md`。
4. HTML export：不再调用模型，只从已保存 artifacts 确定性渲染 HTML。

关键边界：

- 默认 runtime 是 `traecli`。
- 如果 `traecli models --json` 空列表、失败或超时，外层 Agent 可以在记录证据后显式使用 `--runtime-command coco`，但这不是 silent fallback。
- `validate <run_id> --json` 是交付门槛。run 返回、HTML 存在或 manifest 有状态，都不能替代 validate。
- 默认成员最多 4 个，最低 3 个有效 Stage 1 成员即可继续。这一点本次不改变。
- 当前默认成员是 `DeepSeek-V4-Pro`、`openrouter-1o`、`GPT-5.4`、`Gemini-3.1-Pro-Preview`，主席默认是 `DeepSeek-V4-Pro`。
- auto-backfill 只在同一个 run 内补足 quorum，不整轮重跑，不覆盖已经成功的 Stage 1 输出。

## 3. 当前 artifact 与责任边界

架构师需要先理解现有产物结构，否则会把“展示层体验”误改成“运行协议变更”。

### 3.1 现有 artifact store

每次 run 默认写到：

```text
.llm-council-for-trae/runs/<run_id>/
  input.md
  config.json
  manifest.json
  events.jsonl
  runtime/doctor.json
  runtime/traecli.models.json
  stage1/<label>.response.md
  stage1/<label>.meta.json
  stage2/<label>.review.md
  stage2/<label>.review.json
  stage2/aggregate.json
  stage2/label_to_model.json
  stage3/chairman.prompt.md
  stage3/final.md
  stage3/final.json
  stage3/final.meta.json
  html/index.html
  html/export.json
```

`manifest.json` 是 HTML 和 validate 的主要事实源。当前关键字段摘要如下：

```json
{
  "run_id": "lct-...",
  "status": "ok | degraded_ok | failed",
  "config": {
    "members": ["DeepSeek-V4-Pro", "openrouter-1o", "GPT-5.4", "Gemini-3.1-Pro-Preview"],
    "chairman": "DeepSeek-V4-Pro",
    "runtime_command": "traecli",
    "min_valid_members": 3,
    "target_valid_members": 4,
    "member_tool_mode": "search_enabled"
  },
  "metadata": {
    "quorum": {
      "min_valid_members": 3,
      "target_valid_members": 4,
      "effective_valid_members": 3,
      "normal_quorum_met": true,
      "low_quorum_used": false,
      "backfill_candidates": ["GPT-5.2", "openrouter-1"],
      "backfill_attempted": [],
      "effective_stage1_members": ["DeepSeek-V4-Pro", "openrouter-1o", "Gemini-3.1-Pro-Preview"]
    },
    "stage2_reviewers": {
      "review_subject_count": 3,
      "reviewer_count": 3,
      "valid_reviewers": ["DeepSeek-V4-Pro", "openrouter-1o", "Gemini-3.1-Pro-Preview"],
      "stage2_reviewer_backfill": []
    },
    "chairman": {
      "attempted": ["DeepSeek-V4-Pro"],
      "used": "DeepSeek-V4-Pro",
      "fallback_from": null,
      "failed_attempts": []
    }
  },
  "stages": {
    "stage1": [],
    "stage2": [],
    "stage3": {}
  },
  "warnings": [],
  "failures": []
}
```

根目录 `<run_id>-index.md` 是外层 Agent 为用户和 reviewer 复制出的可读索引，不是 CLI core 的唯一事实源。它通常记录：

```text
run status
validate verdict
Input mode
runtime_default_*
runtime_override_*
lct_search_allowed / lct_search_used
agent_external_search_used
valid_stage1_models
quorum_default / quorum_effective
backfill_candidates / backfill_attempts
stage2_reviewers
chairman_fallback_used
failed_models
artifact paths
```

`validate <run_id> --json` 当前返回交付门槛字段：

```json
{
  "status": "ok | degraded_ok | failed",
  "manifest_status": "ok | degraded_ok | failed",
  "terminal": true,
  "usable_final": true,
  "stage3_final_exists": true,
  "html_exists": true,
  "verdict": "complete_ok_final | usable_degraded_final | failed_no_final | invalid_artifacts",
  "failed_stage_records": []
}
```

### 3.2 各层职责边界

| 层级 | 现在负责什么 | 本次升级可放什么 | 不应放什么 |
|---|---|---|---|
| outer Agent / Skill | 理解用户意图、准备 `_lct_question.md`、运行 CLI、写根目录 final/index、向用户汇报 | 用户自选模型触发规则、AskUserQuestionTool 可选体验、输入改造判定、index provenance | 不应伪造 LCT 内部贡献，不应把执行职责写进 council input |
| LCT CLI | 解析参数、读 input、生成 config、调用 runtime、写 artifacts | 可选：模型 frontmatter、模型解析/校验、贡献 sidecar schema 生成流程 | 不依赖 AskUserQuestionTool，不依赖某个 Agent UI |
| council prompt | Stage 1/2/3 模型任务说明 | 可选：要求主席输出贡献说明或结构化附录 | 不让 HTML export 再调用模型，不让成员处理 notes/Git/validate |
| manifest / sidecar | 保存 run 事实和结构化 metadata | 新增 model_selection provenance、contribution map | 不删除历史 quorum/backfill/search 字段 |
| validate | 校验 artifacts 完整性、模型一致性、可交付性 | 新增可选 sidecar schema 校验，legacy run 兼容 | 不把缺少新字段的历史 run 判成坏 artifact |
| HTML export | 确定性渲染 artifacts | 简化 summary card，展示贡献说明 | 不调用模型，不改写主席答案 |

`search accounting` 和 `backfill provenance` 被列为保护项，是因为本次会触碰 HTML summary、index 和模型选择逻辑。如果改 summary card 或 index 字段时顺手删掉这些证据，后续 reviewer 会无法判断搜索是否真实发生、候补池来自哪里、有效成员是否来自 backfill。

## 4. 权威模型优先级和裁剪规则

当前成员整体优先级是：

```text
DeepSeek-V4-Pro
openrouter-1o
GPT-5.4
Gemini-3.1-Pro-Preview
GPT-5.2
openrouter-1
Kimi-K2.6
DeepSeek-V4-Flash
MiniMax-M2.7
Qwen3.6-Plus
```

这份优先级只用于自动推荐、默认 backfill，以及本次新增的“用户选择超过 4 个成员时裁剪”。它不是用户可见模型清单的替代品。最终可用性仍必须来自当前 `traecli models --json`。

建议产品规则：

- 用户没有表达模型选择意图：不触发询问，直接默认 4 成员。
- 用户明确要挑成员：展示当前可用模型清单。
- 用户直接给出模型名：先做匹配。可唯一匹配时不重复询问。
- 匹配方式第一版只支持 exact、case-insensitive、菜单编号。不要默认 fuzzy match，避免选错模型。
- 用户指定成员数为 3 或 4：按解析结果运行。
- 用户指定成员数超过 4：将用户指定集合与成员优先级求交，按上面的优先级取前 4 个；未进入前 4 的模型写入裁剪记录。
- 用户指定集合包含当前 `traecli models --json` 不存在的模型：交互环境中追问，非交互环境中 fail closed。
- 用户指定集合包含不在成员优先级里的可用模型：这是架构决策点。第一版建议不 silent drop；如果总数不超过 4，可允许显式模型进入，但必须记录 `selection_source=user_explicit_unranked`；如果总数超过 4，必须追问或 fail closed，不要猜它在优先级中的位置。
- 用户指定成员少于 3：交互环境中要求补足到至少 3 个；非交互环境中 fail closed。这样与“最低 3 个有效即可继续”的产品心智一致。
- chairman 单独校验。用户指定 chairman 只影响 chairman，不自动替换 members，除非用户明确表达。
- 如果裁剪发生，建议在交互环境中让用户确认裁剪结果；非交互环境必须在 index 中记录裁剪。

建议新增 provenance 字段：

```text
model_selection_mode: default | user_requested | explicit_args | input_frontmatter
model_selection_interaction: none | AskUserQuestionTool | text_fallback | cli_tty
user_requested_members: <models or none>
user_requested_chairman: <model or none>
resolved_members: <models>
resolved_chairman: <model>
model_resolution_status: ok | asked_user | failed
model_resolution_source: traecli models --json
model_selection_trimmed_members: <models or none>
model_selection_unresolved_members: <models or none>
```

## 5. 输入改造判定矩阵

当前“关键词”不应只是字符串匹配。建议用规则矩阵表达第一版行为。

| 用户表达 | 默认 Input mode | 是否允许加 Agent 结构化上下文 | 备注 |
|---|---|---|---|
| “使用 LCT 回答：...” | `raw original input` | 否 | 只追加 `Report topic` |
| “不要改写 / 按原文 / 只用原始输入” | `raw original input` | 否 | 最高优先级，禁止重构 |
| “评估 LCT 对原始问题的理解” | `raw original input` | 否 | 用于测试 LCT 本身 |
| “先思考我真正需要什么” | `structured by Agent` | 是 | 必须保留 `Original input` |
| “站在架构师角度评估 / 给架构建议” | `structured by Agent` | 是 | 但外层执行职责仍不得进 council input |
| “给完整方案 / 深入分析” | 默认 raw，必要时 structured | 需要结合上下文 | 不应单凭“深入”二字改写 |
| “先反驳我 / 提出最强反方” | 默认 raw，或 structured | 需要看是否要求 Agent 组织问题 | 不能伪造事实背景 |
| 用户要求 fact pack / 最新资料 / 来源 | `structured by Agent` | 是 | fact pack 必须带来源，直接嵌入 input |
| 用户要求维护 notes、运行 validate、写 PR | 不属于 council input | 否 | 这些是 operator envelope |

第一版实现不需要机器学习分类。可以把矩阵写进 Skill，并用文档契约测试覆盖高频触发语。架构师可评估是否需要把该矩阵升级为 CLI 可读的 input preparation policy。

## 6. 主席贡献说明的最低可信标准

主席贡献说明最危险的失败模式是“看起来透明，实际是模型自编贡献”。因此第一版不应要求精确百分比。

建议最低可接受形态：

```text
贡献说明：
- 共识观点：哪些结论被 2 个及以上有效 Stage 1 answers 支持。
- 主要采纳：最终答案某个章节主要吸收了哪些 Response label / model 的观点。
- 分歧处理：哪些成员观点互相冲突，主席如何取舍。
- 主席新增：哪些判断是主席在综合基础上的新增推理。
- 未明显采用：哪些有效成员观点没有进入最终答案，若可判断则说明原因。
```

允许的表达：

- “主要采纳 Response A / DeepSeek-V4-Pro 的论证框架”
- “Response B 与 Response D 都支持该风险判断”
- “主席在综合阶段新增了对适用边界的归纳”
- “从 artifacts 无法可靠判断该段落来自单一成员”

禁止的表达：

- 无证据百分比，例如“GPT-5.4 贡献 37%”
- 把 Stage 2 排名直接等同于最终贡献
- 引用不存在的 Response label 或 model
- 把失败成员说成有效贡献者，除非明确是 partial recoverable 且 artifacts 可验证
- 在 HTML export 阶段重新解释贡献来源

可选 sidecar 第一版可考虑：

```json
{
  "schema_version": 1,
  "source": "chairman_structured_output | deterministic_postprocess | mixed",
  "items": [
    {
      "final_section": "二、背景语境",
      "contribution_type": "shared_consensus | primarily_adopted | disagreement_resolved | chairman_synthesis | not_attributable",
      "source_responses": [
        {"label": "Response A", "model": "DeepSeek-V4-Pro"}
      ],
      "evidence_summary": "短说明，不放长引文",
      "confidence": "high | medium | low"
    }
  ]
}
```

validate 最低只应检查结构和引用合法性：

- `source_responses.label` 必须存在于有效 Stage 1 labels。
- `source_responses.model` 必须与 `label_to_model` 或 stage record 匹配。
- `contribution_type` 必须是枚举值。
- 缺少 sidecar 的 legacy run 不失败；新 run 如果声明启用 contribution map，则结构不合法才失败。

HTML 第一版只展示贡献说明，不把它混进 final answer 正文。final answer 仍以 `stage3/final.md` 为主。

## 7. 现有用户体验痛点

### 7.1 HTML summary card 的 quorum 文案难懂

当前 HTML 顶部 summary card 可能显示：

```text
Quorum 状态
4 / 3 · normal quorum

有效成员：DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Gemini-3.1-Pro-Preview
```

这里的 `4 / 3` 实际含义是：

```text
effective_valid_members / min_valid_members
```

即 4 个有效成员，最低要求是 3 个有效成员。这个表达对工程师可解释，但对普通用户不友好。用户关注的是“哪些模型参与了最终结果”，不是 quorum 阈值。

体验目标：

- summary card 标题改为 `成员模型`。
- 内容只展示有效 Stage 1 成员模型，例如：`DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Gemini-3.1-Pro-Preview`。
- 不在 summary card 展示 `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：` 这些技术文案。
- quorum 细节仍应保留在 artifacts、index、manifest、validate 或 evidence 区域，不能删除底层可审计能力。

### 7.2 主席综述难以看出模型贡献

当前 Stage 3 final 是主席综合答案。作为用户，读者很难判断：

- 哪些段落主要来自哪个 Stage 1 member 的观点。
- 哪些观点是多个模型共识。
- 哪些观点是主席自己的整合、裁剪或新增判断。
- 某个成员模型是否对最终答案有明显贡献。
- Stage 2 排序和主席最终采用之间是什么关系。

这不是要求做“机械拼接”或“模型排名展示”。主席仍应输出自然、完整、可读的综述答案。但用户需要更强的 provenance，可理解为“最终答案如何吸收各模型贡献”的解释层。

需要架构师重点评估：

- 贡献程度能否被可靠量化？如果不能，应该用什么保守表达替代。
- 是让 chairman prompt 要求输出贡献说明，还是增加结构化 sidecar，例如 `stage3/contribution_map.json`。
- 贡献说明应该放在 HTML 的正文内、正文后、证据层，还是三者拆开。
- 如何避免主席为了“归因”而编造模型贡献。
- 是否需要确定性后处理，用文本相似度或引用片段辅助，但不把它当真实因果贡献。

### 7.3 输入改造规则需要更精确

当前 Skill 的基本规则是：

- 默认保留用户原始实质问题。
- 只有用户明确要求思考真实意图、拆解问题、重构输入、加入 fact pack 或结构化输出时，才允许 `structured by Agent`。
- 用户明确说“不要改写”“按原文”“只用原始输入”时，必须 `raw original input`。

这个方向是正确的，但需要在两个场景下检查关键词是否够用、够准。

场景 A：用户只是要 LCT 回答一个问题。

示例：

```text
使用 LCT 回答："""这篇文章怎么看？"""
```

默认应为 `raw original input`。外层 Agent 不应把自己的分析、执行计划、notes 维护要求、Git 操作或测试职责写进 `_lct_question.md`。

场景 B：用户要求 Agent 在回答前做意图理解、产品设计或架构评估。

示例：

```text
在你回答之前，请先思考我真正需要的是什么，而不仅仅是看我表面上说了什么。
```

这类请求说明用户希望 Agent 先做任务澄清和结构化，可能允许 `structured by Agent`。但仍要区分：

- 哪些内容是给 council 成员看的问题输入。
- 哪些内容是外层 Agent 的执行职责。
- 哪些内容只是 PM/架构评估文档，不一定要进入 LCT run。

需要架构师评估：

- 仅靠关键词是否足够，还是需要“意图分类规则”。
- 哪些触发词应该明确进入 `structured by Agent`。
- 哪些触发词容易误伤，例如“详细分析”“深入一点”是否等于允许改写原问题。
- index 应如何记录 `Input mode` 和 `agent_added_context`，让事后审查能判断输入是否被改造。

### 7.4 用户自选模型需要产品化

当前 CLI 已支持：

```bash
--members
--chairman
--profile
--default-models
```

CLI 也有 TTY 交互式模型选择逻辑，会从当前 `traecli models --json` 读取模型清单，并在用户输入编号或名称时做匹配。

用户希望的新体验是：

- 默认不打扰用户。用户没有表达模型选择意图时，继续使用默认 4 成员和默认主席。
- 当用户明确表达“我要挑成员模型”“我要指定主席”“用某几个模型跑”时，外层 Agent 应展示当前可用模型清单。
- 在支持 `AskUserQuestionTool` 的环境中，可以用交互卡片让用户选模型。Trae-CN、Claude Code 可能有类似能力。
- 不支持 `AskUserQuestionTool` 的环境，应退化为普通文本列表或直接解析用户给出的模型名。
- 用户指定的模型必须能匹配当前 `traecli models --json` 清单。不能用不存在、已下线或拼错的模型名静默运行。
- LCT 仍然最多一次跑 4 个 member models。最低 3 个有效即可继续。这点不改变。
- 如果用户选择或输入超过 4 个成员模型，系统应按 LCT 已定义的成员优先级筛选前 4 个，而不是按用户输入顺序盲取前 4 个。
- chairman 是单独选择项。用户指定主席时，主席也必须匹配当前模型清单。

需要架构师评估：

- 这应该只写在 Skill/Agent workflow，还是要补 CLI 原生能力。
- `AskUserQuestionTool` 是否应该成为可选体验，而不是 LCT core 依赖。
- 模型匹配策略应支持哪些形式：exact、case-insensitive、编号、别名、模糊匹配。
- 超过 4 个成员时，如何向用户解释“按成员优先级取前 4 个”，以及是否需要让用户确认裁剪结果。
- 如何记录用户请求、解析结果、裁剪结果和最终 run config。

## 8. 本次迭代的非目标

以下内容不在本次体验升级范围内，除非架构师证明它是必需依赖：

- 不改变默认成员上限 4。
- 不改变最低有效成员数 3。
- 不改变默认 runtime。
- 不重写 Stage 1 / Stage 2 / Stage 3 核心流程。
- 不把 HTML export 和 chairman synthesis 混成一步。
- 不把 AskUserQuestionTool 做成 LCT core 必需依赖。
- 不删除 manifest、validate、index 里的 quorum 信息。
- 不把用户没有表达的模型偏好强行推断出来。
- 不把贡献度包装成精确数字，除非有可靠证据链。

## 9. 必须保护的现有能力

架构师需要把“保护已有能力”作为第一优先级。任何建议都必须说明如何避免破坏：

1. 非交互 Agent 路径：

```bash
llm-council-for-trae run --input _lct_question.md --default-models --json
```

2. 显式模型路径：

```bash
llm-council-for-trae run --input _lct_question.md --members A,B,C --chairman D --json
```

3. runtime override 路径：

```bash
llm-council-for-trae --runtime-command coco run ...
llm-council-for-trae --runtime-command coco validate ...
```

4. validate 门槛：

```bash
llm-council-for-trae validate <run_id> --json
```

5. HTML export 的确定性：HTML 只能读 artifacts，不能重新调用模型。

6. 输入边界：外层执行职责不得进入 `_lct_question.md`。

7. search accounting：`lct_search_allowed` 与 `lct_search_used` 必须分开。

8. backfill provenance：`backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`。

## 10. 期望架构师回答的问题

请架构师阅读本文后，输出一份架构评估，至少覆盖：

1. 对四个体验需求的理解是否完整。
2. 是否存在缺失信息或任务不清晰处。
3. 每个需求建议落在哪一层：
   - Skill / outer Agent workflow
   - CLI 参数与输入解析
   - council prompt
   - manifest / sidecar schema
   - validation
   - HTML export
   - tests
4. 哪些需求可以只通过文档和 Skill 改进完成，哪些必须改代码。
5. 贡献度/归因的可信表达方式。
6. 用户自选模型的交互与 fallback 设计。
7. 输入改造判断是否应从关键词升级为分类规则。
8. 回归风险和防护测试。
9. 分阶段实施建议。

架构师请不要直接提供代码 patch。此阶段只需要架构建议、风险和待澄清问题。

## 11. 建议的验收与回归测试

任何后续实现都必须至少覆盖以下测试面。

### 11.1 HTML summary card

- fixture manifest 有 4 个有效成员、`min_valid_members=3`。
- HTML summary card 显示标题 `成员模型`。
- summary card 内容显示有效成员模型列表。
- summary card 不显示 `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：`。
- evidence 或 metadata 区仍可找到 quorum 细节，确保可审计性未丢失。

### 11.2 主席贡献说明

- Stage 3 prompt 或 schema 测试要求主席提供贡献说明，且不能替代 final answer。
- 如果新增 sidecar，例如 `stage3/contribution_map.json`，validate 要检查结构完整性。
- 贡献说明必须使用保守措辞，例如“主要采纳”“部分吸收”“未明显采用”，除非有确定性证据，不输出精确百分比。
- HTML 能展示贡献说明，但不遮挡最终答案。
- legacy run 缺少贡献 sidecar 时，HTML/validate 仍向后兼容。

### 11.3 输入改造判断

- 用户只说“使用 LCT 回答”时，生成 `Input mode: raw original input`。
- 用户明确说“不要改写”时，必须 raw。
- 用户明确说“先思考我真正需要什么”时，可以 structured，但必须保留 `Original input`。
- 外层职责词如 `notes.md`、`validate`、`Git`、`PR` 不得进入 council input。
- index 必须记录 `Input mode`、`agent_added_context`、`agent_fact_pack_path`。

### 11.4 用户自选模型

- 用户未表达模型选择意图时，不触发 AskUserQuestion，不改变默认路径。
- 用户给出可唯一匹配模型名时，直接解析，不重复询问。
- 用户给出不存在模型名时，阻断或询问，不 silent fallback。
- 用户选择超过 4 个成员时，按成员优先级裁剪到 4 个。
- 裁剪结果写入 index 或 manifest metadata。
- chairman 指定独立校验。
- 所有最终 members/chairman 均来自当前 `traecli models --json`。

### 11.5 全量回归

实现完成前必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如触及 live runtime、model selection 或 Skill path，还应补：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live runtime 不可用，必须明确标记 skipped，不得用 fake runtime 冒充 live。

## 12. 交付建议

建议分三阶段推进，降低破坏风险：

### 阶段 1：无风险展示与 Skill 规则

- 简化 HTML summary card。
- 更新 Skill/README 的用户自选模型触发边界。
- 明确输入改造两个场景。
- 补文档契约测试。

### 阶段 2：模型选择交互产品化

- 外层 Agent workflow 增加用户自选模型流程。
- `AskUserQuestionTool` 作为可选体验。
- 无 AskUserQuestion 时用文本 fallback。
- 写入 index provenance。

### 阶段 3：主席贡献说明

- 先确定贡献表达的可信边界。
- 再决定是 prompt-only、sidecar schema，还是 deterministic assist。
- 补 validate 与 HTML 兼容测试。

不建议把三阶段一次性塞进同一个实现 PR。如果必须合并在一轮，也应拆成独立 commits，并让测试逐层通过。

## 13. 架构师最终输出格式

请架构师按以下格式回复：

```text
结论：可以推进 / 需要澄清后推进 / 不建议按当前描述推进

信息不足或任务不清晰：
1. ...

架构建议：
1. HTML summary card:
2. 主席贡献说明:
3. 输入改造规则:
4. 用户自选模型:

风险：
1. ...

必须保护的回归：
1. ...

建议实施阶段：
1. ...
```

请避免写具体代码实现。此阶段需要的是架构判断，不是 patch。

## 14. 初审反馈已补齐的内容

本文第一版已让一位“白纸架构师”角色做过只读审查。审查结论是“基本足够但需补充”。本版已补入以下内容：

- 当前 artifact store、manifest、index、validate JSON 的最小字段摘要。
- outer Agent / Skill、CLI、council prompt、manifest、validate、HTML export 的责任边界。
- 用户自选模型的权威优先级来源、超过 4 个成员的裁剪规则、少于 3 个成员的失败或追问规则。
- 输入改造判定矩阵，覆盖 raw、禁止改写、structured、fact pack、operator envelope 等场景。
- 主席贡献说明的最低可信标准、禁止表达、可选 sidecar 样例和 validate 最低校验。
- `search accounting` 与 `backfill provenance` 为什么会被本次体验升级影响。

仍可留给正式架构评估的问题：

- `AskUserQuestionTool` 在不同宿主环境的精确交互能力。
- 贡献说明最终放在正文后、证据层，还是另设摘要区。
- 是否优先实现 sidecar，还是先只改 prompt 和 HTML 展示。
- legacy run 的完整历史兼容矩阵。
