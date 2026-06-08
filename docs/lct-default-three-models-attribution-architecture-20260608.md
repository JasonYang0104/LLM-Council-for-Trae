# LCT 默认 3 成员与贡献归因口径架构决策

创建日期：2026-06-08
适用仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`
目标实现分支建议：`codex/lct-default-3-models-attribution-20260608`

## 1. 这份文档的作用

本文件是下一轮实现的架构事实源。执行 Agent 不需要重新争论本轮产品方向；如果发现当前代码和本文冲突，按本文写测试方案并让红灯测试暴露差异，再实现收敛。

本轮不是 runtime 重写，不改 Stage 1 / Stage 2 / Stage 3 protocol，不改 `validate` 的终局语义，不改原生 `--members` 的 power-user 精确路径。目标是做一轮体验可信度迭代：

1. 默认成员并行数从 4 改成 3。
2. Stage 1 最低有效结果保持 `min_valid_members=3`。
3. 默认 run 允许 auto-backfill 在同一个 run 内补到 3 个有效 Stage 1 成员。
4. 成员优先级改成新的 12 模型顺序。
5. 主席模型顺序收敛为一个权威来源。
6. 贡献归因口径收窄并讲清楚，修复 `synthesis.members` 被 HTML 吞掉和语义混淆的问题。

## 2. 必须先读

执行前按顺序读：

1. `AGENTS.md`
2. `README.md`
3. `DECISIONS.md`
4. `docs/design.md`
5. `docs/lct-default-three-models-attribution-execution-20260608.md`
6. `docs/lct-default-three-models-attribution-transfer-20260608.md`
7. `/Users/bytedance/Downloads/LCT贡献归因口径问题与改进建议.md`

相关历史文档只作决策溯源，不作为本轮当前口径：

- `docs/archive/lct-experience-upgrade-implementation-spec-20260606.md`
- `docs/archive/lct-experience-upgrade-execution-plan-20260606.md`
- `docs/archive/lct-experience-upgrade-implementation-handoff-20260606.md`
- `docs/archive/lct-v19-chairman-note-and-kimi-default-design-20260606.md`

## 3. 成员模型决策

### 3.1 默认成员数

默认 direct run 的成员模型并行数改为 3。

新的默认成员是成员优先级前 3 个：

```text
DeepSeek-V4-Pro
GPT-5.5
openrouter-3o
```

`min_valid_members` 保持 3。默认 run 要么首发 3 个成员全有效，要么通过同一个 run 内的 auto-backfill 补足到 3 个有效成员；否则按现有 quorum / degraded / failed 语义处理。

### 3.2 自选路径目标数

`--selected-members` / `--selected-chairman` 这类 agent-assisted 自选路径也统一归一化到 3 个成员。不要保留旧的“默认 3、自选补到 4”的割裂口径。

原生 `--members` / `--chairman` 仍是 power-user 精确路径：给几个跑几个，不自动补足、不自动裁剪。

`--profile`、subagent provider、测试 fixture 也不应该被无差别归一化逻辑误伤。

### 3.3 成员优先级

新的成员优先级唯一事实源应在 `src/llm_council_for_trae/model_selection.py`。

顺序为：

```text
DeepSeek-V4-Pro
GPT-5.5
openrouter-3o
GPT-5.4
openrouter-2o
Kimi-K2.6
MiniMax-M2.7
GPT-5.2
openrouter-1o
DeepSeek-V4-Flash
Gemini-3.1-Pro-Preview
Qwen3.6-Plus
```

`models --recommend --json` 只能从当前 runtime 返回的模型中，按这份优先级选择安全可用模型。Seed/Doubao/GLM 的 hard-ban 继续保留。不要引入“runtime safe models 里随便补一个”的第二套候补池。

### 3.4 GPT-5.5 风险

`GPT-5.5` 被提升到默认第 2 位。当前代码不硬排除它，但历史 notes 中出现过 GPT-5.5 在高并发 benchmark 下稳定性较差的记录。这个历史记录不阻止本轮变更，因为本轮默认并发数从 4 降到 3，风险条件已经改变。

执行要求：

- 本地单元测试必须覆盖默认推荐和默认成员。
- 如果 live runtime 可用，merge 后隔离 E2E 必须实际跑一次默认 3 成员 live run。
- E2E 复盘必须明确记录 `GPT-5.5` 是否真的执行、是否成功、失败时是否通过 auto-backfill 补到 3。

## 4. Auto-backfill 决策

默认 run 允许 auto-backfill 补到 3 个有效 Stage 1 成员。

语义如下：

```text
默认首发成员：优先级前 3 个
有效 Stage 1 结果 < 3：按成员优先级剩余可用模型继续补位
补位目标：effective_stage1_count >= min_valid_members == 3
不整轮重跑
不覆盖已经成功的 Stage 1 输出
不把 failed primary 冒充成有效成员
```

manifest / validate / HTML / index 仍必须保留：

- `valid_stage1_models`
- `quorum_default`
- `quorum_effective`
- `low_quorum_used`
- `backfill_candidates`
- `backfill_attempts`
- `stage1_backfill_members`
- `stage2_reviewer_backfill`
- `review_subject_count`
- `reviewer_count`
- `chairman_fallback_used`

## 5. 主席模型顺序决策

主席模型顺序不变，但必须收敛成一个文件、一个权威顺序。

完整主席优先级：

```text
DeepSeek-V4-Pro
Kimi-K2.6
DeepSeek-V4-Flash
GPT-5.2
openrouter-1
```

推荐实现口径：

```python
CHAIRMAN_PRIORITY = [
    "DeepSeek-V4-Pro",
    "Kimi-K2.6",
    "DeepSeek-V4-Flash",
    "GPT-5.2",
    "openrouter-1",
]

DEFAULT_CHAIRMAN = CHAIRMAN_PRIORITY[0]
CHAIRMAN_FALLBACK_CHAIN = CHAIRMAN_PRIORITY[1:]
```

建议落点：

- `model_selection.py` 定义完整主席优先级。
- `roster.py` 不再维护第二份主席顺序；如因兼容需要保留导出名，应从 `model_selection.py` 派生或反向导入，不得复制常量。
- `models --recommend` 和 Stage 3 fallback 使用同一条主席优先级。

## 6. 贡献归因口径决策

### 6.1 问题

当前 contribution map 的类型方向是对的，但口径有混淆：

- `multi_member_consensus` 表示多个成员独立表达了同一核心观点。
- `synthesis` 表示主席对成员素材进行编辑、合并、桥接或结构化整理。
- 当前 HTML 对 `synthesis.members` 一律显示 `来源：综合整理`，用户看不到主要参考成员。
- 如果直接显示成 `综合整理：A, B`，又容易被理解成 `多成员共识：A, B`。

### 6.2 新口径

四类来源必须清楚分工：

```text
多成员共识：多个成员独立表达了相同或高度一致的核心观点。
综合整理：主席参考成员材料后进行编辑、合并或转述，不等同于成员逐字共识。
主席评注：主席基于成员素材额外给出的判断、提醒或取舍建议。
无法可靠归因：无法可靠对应到具体成员，系统不强行署名。
```

`synthesis.members` 的语义是“主要参考成员”，不是“共识成员”。

### 6.3 实现边界

Stage 3 prompt 必须明确：

- `multi_member_consensus.members` 表示这些成员都表达过同一核心观点。
- `synthesis.members` 表示主席主要参考了这些成员素材。
- `synthesis` 不等于成员共识。
- 完全无法可靠归因时优先使用 `not_attributable`，不要让 `synthesis` 成为兜底大筐。
- `editor_note` 必须作为主席评注隔离展示。

HTML 必须区分：

```text
multi_member_consensus + members:
  多成员共识：A（同侪#n）, B（同侪#n）

synthesis + members:
  主席综合整理，主要参考：A（同侪#n）, B（同侪#n）

synthesis + no members:
  来源：主席综合整理

not_attributable:
  来源：无法可靠归因
```

Validation 可以保持轻量：

- `multi_member_consensus` 少于 2 个成员继续 hard fail。
- `single_member` 不等于 1 个成员继续 hard fail。
- `synthesis.members` 如果存在，必须都是有效 Stage 1 成员。
- 不要声称 validate 能验证“成员是否真的表达了同一观点”。这是 prompt + review + live artifact 审查问题，不是静态校验能完全解决的问题。

## 7. 文档同步决策

当前 GitHub 文档中仍有默认 4 成员、归一化到 4、旧成员排序、旧贡献归因口径的内容。执行 Agent 必须更新这些当前入口文档，但触发顺序要严格：

1. 先改代码、测试、Skill 和本轮相关文档。
2. 本地验证通过。
3. subagent review 通过。
4. PR 合并。
5. v16 隔离 workspace 从最新 GitHub main 完成 E2E。
6. E2E 输出 review 通过后，再确认 README / docs / Skill 没有遗留旧口径。

如果 E2E 暴露产品或 runtime 问题，不能为了“文档看起来新”而粉饰真实状态。README 应反映最新已验证行为，而不是预期行为。

## 8. 不做的事

本轮不做：

- 不重写 runtime provider。
- 不引入 OpenRouter API。
- 不恢复旧 Web UI。
- 不改变原生 `--members` 的精确语义。
- 不把 HTML export 和主席 synthesis 混成一步。
- 不让 HTML export 调模型或重新推理归因。
- 不用 fixture / fake runtime 冒充 live E2E。
- 不把 subagent profile 当 direct 默认阵容来源。
