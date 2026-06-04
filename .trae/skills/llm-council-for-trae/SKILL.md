---
name: llm-council-for-trae
description: |
  LLM-Council-for-Trae (LCT) 工作流技能。当用户需要多个 LLM 模型组成委员会回答问题时使用。
  触发场景：(1) 用户说"用委员会回答"、"让多个模型讨论"、"LLM council"、"council run"；
  (2) 用户要求对复杂问题获得多模型综合答案；(3) 用户需要生成 council HTML 报告；
  (4) 用户提到 "LCT"、"llm-council-for-trae" 并要求执行。
  此技能定义完整的 council 工作流：环境检查 → 问题准备 → 三阶段运行 → 验证 → 输出交付。
---

# LLM-Council-for-Trae 工作流

## 前置条件

确认当前目录不是 LCT 源码 repo。出现以下任一标记时停止，除非用户明确说正在做 LCT 开发：

- `src/llm_council_for_trae/`
- `.trae/agents/`
- `profiles/subagents.json`

日常使用应在干净问题 workspace 中调用全局 CLI，不要在 LCT 源码 repo 中跑用户问题。

确认以下条件满足后再开始：

```bash
which traecli && traecli --version
```

如果 traecli 不可用，参考项目 `docs/traecli-installation-and-paths.md` 安装。

## 工作流概览

```
Step 0: 定位或自举 LCT CLI
  ↓
Step 1: 环境检查 (doctor)
  ↓
Step 2: 准备问题文件
  ↓
Step 3: 运行 council (Stage 1 → 2 → 3)
  ↓
Step 4: 验证结果 (validate)
  ↓
Step 5: 交付 HTML 报告
```

## Step 0: 定位或自举 LCT CLI

在干净问题 workspace 中执行。新环境可能还没有安装 `llm-council-for-trae` wrapper，先选择可用命令：

```bash
if command -v llm-council-for-trae >/dev/null 2>&1; then
  LCT="llm-council-for-trae"
else
  make install-local
  if command -v llm-council-for-trae >/dev/null 2>&1; then
    LCT="llm-council-for-trae"
  else
    LCT="env PYTHONPATH=src python3 -m llm_council_for_trae.cli"
  fi
fi
```

后续命令优先使用 `$LCT`。如果当前 shell 不保留变量，就把 `$LCT` 替换成上面选中的实际命令。

## Step 1: 环境检查

```bash
$LCT doctor --json
```

检查输出中 `ok: true`、`models.count > 0`。如果 doctor 失败：
- MCP-only 错误：忽略，继续运行
- 其他错误：停止，按错误信息排障

确认可用模型：

```bash
$LCT models --recommend --json
```

记录 `recommendation.members` 和 `recommendation.chairman`。当前静态默认模型套是：

```text
members: DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Gemini-3.1-Pro-Preview
chairman: DeepSeek-V4-Pro
```

`models --recommend --json` 只给本次 run 一个可审计候选来源。默认 primary members 仍来自 `--default-models`；CLI 会在同一个 run 内用 auto-backfill 和 backfill candidates 补足有效成员，不整轮重跑。显式候补优先级通过 `--backfill-members` 传入。最终 `$RUN_ID-index.md` 的 `backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`；如果 terminal manifest 没有记录该字段，写 `backfill_candidates: not recorded`。不得从默认成员阵容、不得从 models --recommend --json 的 primary roster、不得从实际有效 Stage 1 成员猜测候补池。

补位语义必须拆开：Stage 1 是 member backfill，只有 Stage 1 quorum 不足时才新增候选答案；Stage 2 是 reviewer-only backfill，当 Stage 1 quorum 已经满足但 reviewer 失败或不足时，候补模型只评审既有有效 Stage 1 answers，不新增候选答案。

## Step 2: 准备问题文件

将用户问题写入 `.md` 文件。先区分两层输入：

- `council input`：用户真正要委员会回答的问题、必要事实背景、输出要求，以及 `Report topic: <中文议题>`。`Report topic` 是报告元数据，不是成员任务指令。
- `operator envelope`：使用 LCT、运行 validate、写 final/index、生成 HTML、维护 notes.md、Git/PR/测试职责、开 branch、提交代码等外层执行职责。外层执行指令不得写入 _lct_question.md。

默认保留用户原始实质问题。中文问题直接写，英文问题保持原文。只有当用户明确要求思考真实意图、拆解问题、重构输入、加入事实包或结构化输出时，才使用 `structured by Agent` 模式，并保留 `Original input`，把额外内容标注为 `Agent interpretation`。原始问题下方追加一行 `Report topic: <中文议题>`，让 HTML 标题稳定生成为 `<中文议题>：多模型智囊团评估`。如果用户要求“直接 LCT”“不要改写提示词”，禁止的是 prompt shaping；`Report topic` 仍可追加，因为它是报告元数据，不是成员任务指令。

如果外层 Agent 需要补充事实背景，fact pack 必须直接嵌入 _lct_question.md，放在用户原始输入之后并标注来源。fact pack 只包含事实背景和来源，不能包含执行指令；不要要求成员读取 sidecar 文件，也不要要求模型读取额外 sidecar 文件。`notes.md` 只由外层 Agent 维护，用来记录执行过程、测试和风险；如果用户要求维护 notes.md，调用 Agent 应执行这个要求，但不得把它写入 council input。不要要求 council 成员创建、读取、修改或维护 notes.md，模型不要创建或修改 notes，也不要把 notes 当成 council 输入。

```bash
cat > /tmp/council-question.md << 'EOF'
<用户的问题内容>
EOF
```

如果用户已经提供了 `.md` 文件路径，直接使用该路径。

## Step 3: 运行 Council

### 3a. 非交互终端（Agent 场景）— 默认路径

必须先使用 `--default-models`。这是最常用的 default attempt。需要显式候补优先级时，在命令中追加 `--backfill-members "<comma-separated candidates>"`：

```bash
$LCT run \
  --input /tmp/council-question.md \
  --default-models \
  --timeout 180 \
  --json
```

记录 `default_attempt_status`、`default_attempt_run_id`、`default_attempt_failure_reason`、`backfill_candidates`、`backfill_attempts`。`backfill_candidates` 写入根目录索引时只能抄 terminal manifest 的 `metadata.quorum.backfill_candidates`，缺失时写 `not recorded`。

工具模式由外层 Agent 基于任务判断。answer_only 是可选工具模式，不强制 answer_only；外层 Agent 可以自行判断让 LCT 成员在 `search_enabled` 下内部搜索、先由外层 Agent 补 fact pack、使用 answer_only，或在只读代码/文件问题中使用 workspace_enabled。search_enabled 只表示搜索被允许，不表示模型实际搜索了；索引必须继续拆开记录 `lct_search_used` 和 `agent_external_search_used`。

如果 default attempt 表面失败、默认模型缺失、apparent hang、run JSON 为空，或中途目录看起来缺 Stage 2 / Stage 3，先读取 terminal manifest 并执行 `validate <run_id> --json`。不要用自然语言观察判 failed。`degraded_ok 是可用结果`，成员失败不等于 run 失败。如果 validate JSON 显示 `usable_final: true`，交付同一个 run；如果没有可用 final，报告阻断点和已尝试的 auto-backfill，不要另起整轮推荐阵容 run。

### 3b. 交互终端 — 可省略模型参数

如果在真实终端中，省略 `--default-models` 会弹出模型选择菜单：

```bash
$LCT run \
  --input /tmp/council-question.md \
  --timeout 180 \
  --json
```

### 3c. 自定义模型

```bash
$LCT run \
  --input /tmp/council-question.md \
  --members "DeepSeek-V4-Pro,openrouter-1o,GPT-5.4,Gemini-3.1-Pro-Preview" \
  --chairman "DeepSeek-V4-Pro" \
  --timeout 180 \
  --json
```

### 运行过程说明

命令执行后会依次运行三个阶段：

1. **Stage 1** — 默认 4 个成员模型独立回答同一问题（并发）
2. **Stage 2** — 每个成员对 Stage 1 的所有回答进行匿名排序和评价
3. **Stage 3** — 主席模型综合 Stage 1 回答和 Stage 2 排序，给出最终答案

运行时间取决于模型响应速度，通常在 2-5 分钟。

### 结果解读

命令输出 JSON，关键字段：

- `status`: `ok` / `degraded_ok` / `failed`
- `degraded`: `true` 表示部分成员失败但 quorum 满足（≥3 个成员成功）
- `html`: HTML 报告路径
- `failures`: 失败成员列表及原因
- `recommendations`: 针对失败的改进建议
- `metadata.quorum.effective_stage1_members`: valid_stage1_models
- `metadata.quorum.min_valid_members`: quorum_default
- `metadata.quorum.effective_valid_members`: quorum_effective
- `metadata.quorum.low_quorum_used`: low_quorum_used
- `metadata.quorum.backfill_candidates`: backfill_candidates
- `metadata.quorum.backfill_attempted`: backfill_attempts
- `metadata.stage2_reviewers`: stage2_reviewers
- `metadata.stage2_reviewers.stage1_backfill_members`: stage1_backfill_members
- `metadata.stage2_reviewers.stage2_reviewer_backfill`: stage2_reviewer_backfill
- `metadata.stage2_reviewers.review_subject_count`: review_subject_count
- `metadata.stage2_reviewers.reviewer_count`: reviewer_count
- `metadata.chairman.fallback_used`: chairman_fallback_used

## Step 4: 验证结果

```bash
$LCT validate <run_id> --json
```

确认 validate JSON：`terminal`、`usable_final`、`stage3_final_exists`、`html_exists`、`failed_stage_records`、`verdict`。`verdict` 取值为 `complete_ok_final`、`usable_degraded_final`、`in_progress`、`failed_no_final`、`invalid_artifacts`。只有 `usable_final: true` 才能交付最终答案；`$RUN_ID-index.md` 的 run status / validate status / verdict 必须来自 validate JSON。`degraded_ok 是可用结果`，成员失败不等于 run 失败。

## Step 5: 交付 HTML 报告

报告路径在 Step 3 输出的 `html` 字段中。用浏览器打开：

```bash
open <html_path>
```

## 常见问题处理

### 模型超时

如果某些模型超时（常见于 GPT-5.4），但 ≥3 个成员成功，系统返回 `degraded_ok`。这是正常降级，不影响最终答案质量。如需提高成功率：

```bash
$LCT run \
  --input /tmp/council-question.md \
  --default-models \
  --timeout 300 \
  --json
```

### 模型不可用

如果 `traecli models --json` 中缺少某些默认模型，优先使用 `--backfill-members` 指定可用 backfill candidates；只有用户明确要自定义 primary roster 时才使用 `--members`。

### 产物存储

所有运行产物存储在 `.llm-council-for-trae/runs/<run_id>/` 下，包括：
- `input.md` — 原始问题
- `stage1/*.response.md` — 各成员回答
- `stage2/*.review.md` — 互评结果
- `stage3/final.md` — 主席最终答案
- `html/index.html` — HTML 报告

交付给用户的根目录索引还必须拆开记录：

- `$RUN_ID-index.md`：run id、run status、validate status、HTML 路径、Input mode、lct_search_allowed、lct_search_used、lct_web_tool_calls、lct_web_tool_effective_calls、lct_search_conversion_errors、agent_external_search_allowed、agent_external_search_used、agent_sources、agent_fact_pack_path、agent_added_context、final_answer_source、valid_stage1_models、quorum_default、quorum_effective、low_quorum_used、backfill_candidates、backfill_attempts、stage2_reviewers、stage1_backfill_members、stage2_reviewer_backfill、review_subject_count、reviewer_count、chairman_fallback_used、default attempt 状态、失败模型或 timeout。

```text
lct_search_allowed: true|false
lct_search_used: true|false
lct_web_tool_calls: <number>
lct_web_tool_effective_calls: <number>
lct_search_conversion_errors: <number>
agent_external_search_allowed: true|false
agent_external_search_used: true|false
agent_sources: <URLs or none>
agent_fact_pack_path: <path or none>
agent_added_context: true|false
final_answer_source: stage3/final.md
valid_stage1_models: <comma-separated models or none>
quorum_default: <number>
quorum_effective: <number>
low_quorum_used: true|false
backfill_candidates: <models or not recorded>
backfill_attempts: <models or none>
stage2_reviewers: <models or none>
stage1_backfill_members: <models or none>
stage2_reviewer_backfill: <models or none>
review_subject_count: <number>
reviewer_count: <number>
chairman_fallback_used: true|false
```
