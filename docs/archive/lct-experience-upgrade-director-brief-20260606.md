# LCT Experience Upgrade Director Brief

日期：2026-06-06

## 结论

本轮没有进入实现，也没有改 LCT 产品代码。它把一次“已经可用，但用户体验还不够清楚”的升级诉求，整理成了可交给架构师评估的任务文档，并用一个白纸 subagent 做了只读审查。

最终产物：

- 架构师任务文档：`docs/lct-experience-upgrade-architect-brief-20260606.md`
- PM director 简报 Markdown：`docs/lct-experience-upgrade-director-brief-20260606.md`
- PM director 简报 HTML：`docs/lct-experience-upgrade-director-brief-20260606.html`

当前主张：这次升级应被视为 LCT 的体验增强，不是 runtime 重写。必须保护现有的 default run、validate、HTML deterministic export、runtime override、input boundary、search accounting 和 backfill provenance。

## 背景

LCT 已经能跑三阶段 council：

1. Stage 1：成员模型独立回答。
2. Stage 2：成员模型互评匿名答案。
3. Stage 3：主席模型综合最终答案。
4. HTML export：从 artifacts 确定性渲染报告。

现在暴露出的主要问题不是“系统不可用”，而是用户难以读懂或控制几个关键体验点：

- HTML 顶部 `Quorum 状态 4 / 3 · normal quorum` 对用户不友好。
- 主席综述难以看出各模型对最终答案的贡献。
- `_lct_question.md` 何时可以被 Agent 改造，何时必须保留原文，还需要更硬的判定矩阵。
- 用户想自选成员或主席模型时，需要一个受当前 `traecli models --json` 约束的清晰流程。

## 过程

第一步，先还原当前系统事实：

- HTML summary card 的 `4 / 3` 实际是 `effective_valid_members / min_valid_members`。
- 当前 Skill 规定默认保留用户原始实质问题，只有用户明确要求意图理解、结构化、fact pack 时，才允许 `structured by Agent`。
- CLI 已支持 `--members`、`--chairman`、`--profile` 和 TTY 交互选择，但外层 Agent 的 `AskUserQuestionTool` 体验尚未产品化。
- 默认成员最多 4 个，最低 3 个有效 Stage 1 成员即可继续，这个约束本轮不变。

第二步，写出架构师任务文档第一版。文档把升级拆成四个体验需求：

- HTML summary card 从 `Quorum 状态` 改成 `成员模型`，只展示有效 Stage 1 member models。
- 主席综述增加可审计的贡献说明，但不伪造精确贡献百分比。
- 输入改造从关键词扩展为场景判定。
- 用户自选模型只在用户表达选择意图时触发，并受当前模型清单校验。

第三步，让一个白纸 subagent 扮演架构师，只审文档清晰度，不写实现方案。它指出第一版“基本足够但需补充”，主要缺口是：

- artifact / manifest / index / validate 的结构样例不足。
- outer Agent、Skill、CLI、HTML、validate 的责任边界不够清楚。
- 主席贡献说明的可信边界不够精确。
- 用户自选模型的优先级来源、裁剪规则和失败行为不够明确。
- 输入改造缺少判定矩阵。

第四步，补强文档。最终版新增：

- 当前 artifact store、manifest、index、validate JSON 的最小字段摘要。
- 各层责任边界表。
- 成员优先级完整列表。
- 用户自选模型的裁剪、确认、失败和 provenance 规则。
- 输入改造判定矩阵。
- 主席贡献说明的最低可信标准、禁止表达和可选 sidecar 样例。
- 更可执行的测试面。

## 最终文档的关键判断

### HTML summary card

用户红框处应简化为：

```text
成员模型
DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Gemini-3.1-Pro-Preview
```

`Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：` 不应放在 summary card 中。底层 quorum 证据仍保留在 manifest、index、validate 或 evidence 区。

### 主席贡献说明

不建议输出精确贡献比例。更稳妥的是结构化表达：

- 共识观点。
- 主要采纳。
- 分歧处理。
- 主席新增。
- 未明显采用。

如果新增 `stage3/contribution_map.json`，validate 只做结构和引用合法性校验，不把缺少 sidecar 的 legacy run 判坏。

### 输入改造

默认 raw。只有用户明确要求意图理解、架构评估、结构化、fact pack 时，才允许 structured。即使 structured，也必须保留 `Original input`，并把 operator envelope 排除在 council input 之外。

### 用户自选模型

默认不问。只有用户表达模型选择意图时，才触发自选流程。

核心规则：

- 最终 members/chairman 必须来自当前 `traecli models --json`。
- members 最多 4 个。
- 产品路径要求至少 3 个 member candidates。
- 超过 4 个时，按 LCT 成员优先级裁剪。
- AskUserQuestionTool 是可选体验，不是 LCT core 依赖。
- 无交互环境必须 fail closed，不 silent fallback。

## 风险

最大风险不是某个 UI 文案改错，而是把体验升级做成协议漂移：

- 把贡献说明做成主席自编解释，会制造假透明。
- 把 AskUserQuestionTool 做成 core 依赖，会破坏非交互 CLI 和其他宿主环境。
- 把用户自选模型绕过当前模型清单，会导致 expected/actual model 校验失效。
- 把输入改造规则写得太宽，会重现“Agent 悄悄改写用户问题”的旧问题。
- 改 HTML summary 时误删 quorum/backfill/search 证据，会削弱可复盘性。

## 下一步建议

不建议一次性把所有体验改动塞进一个实现 PR。

建议分三阶段：

1. 低风险展示与 Skill 规则：简化 HTML summary card，补输入改造判定矩阵，补用户自选模型触发边界。
2. 模型选择交互产品化：把 AskUserQuestionTool 做成可选前置体验，并补文本 fallback 与 provenance。
3. 主席贡献说明：先定 schema 和可信边界，再改 prompt、validate 和 HTML。

每阶段都应有独立测试，并保持：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果触及 live runtime 或 model selection，再补 live run 与 validate。live 不可用时必须标 skipped，不得用 fake runtime 冒充。

## 状态

本轮完成的是评估输入和文档化，不是实现。当前可以把 `docs/lct-experience-upgrade-architect-brief-20260606.md` 交给架构师继续做正式架构建议。
