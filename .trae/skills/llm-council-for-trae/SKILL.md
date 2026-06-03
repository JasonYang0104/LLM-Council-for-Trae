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
members: Kimi-K2.6, MiniMax-M2.7, GPT-5.2, DeepSeek-V4-Pro
chairman: Kimi-K2.6
```

`models --recommend --json` 只给本次 run 一个可审计候选来源。默认 primary members 仍来自 `--default-models`；CLI 会在同一个 run 内用 auto-backfill 和 backfill candidates 补足有效成员，不整轮重跑。显式候补优先级通过 `--backfill-members` 传入。

## Step 2: 准备问题文件

将用户问题写入 `.md` 文件。中文问题直接写，英文问题保持原文。原始问题下方追加一行 `Report topic: <中文议题>`，让 HTML 标题稳定生成为 `<中文议题>：多模型智囊团评估`。

如果外层 Agent 需要补充事实背景，fact pack 必须直接嵌入 _lct_question.md，放在用户原始输入之后并标注来源；不要要求模型读取额外 sidecar 文件。`notes.md` 只由外层 Agent 维护，用来记录执行过程、测试和风险；模型不要创建或修改 notes，也不要把 notes 当成 council 输入。

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

记录 `default_attempt_status`、`default_attempt_run_id`、`default_attempt_failure_reason`、`backfill_candidates`、`backfill_attempts`。

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
  --members "Kimi-K2.6,MiniMax-M2.7,GPT-5.2,DeepSeek-V4-Pro" \
  --chairman "Kimi-K2.6" \
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
- `metadata.quorum.backfill_attempted`: backfill_attempts
- `metadata.stage2_reviewers`: stage2_reviewers
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

```text
lct_search_allowed: true|false
lct_search_used: true|false
lct_web_tool_calls: <number>
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
backfill_attempts: <models or none>
stage2_reviewers: <models or none>
chairman_fallback_used: true|false
```
