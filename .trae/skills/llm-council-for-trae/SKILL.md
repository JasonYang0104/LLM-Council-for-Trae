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

在仓库根目录执行。新 clone 的 workspace 可能还没有安装 `llm-council-for-trae` wrapper，先选择可用命令：

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

`models --recommend --json` 只给外层 Agent 一个可审计候选。fallback 编排只属于 Skill / 外层 Agent，不属于 CLI 内部自动行为。

## Step 2: 准备问题文件

将用户问题写入 `.md` 文件。中文问题直接写，英文问题保持原文。

```bash
cat > /tmp/council-question.md << 'EOF'
<用户的问题内容>
EOF
```

如果用户已经提供了 `.md` 文件路径，直接使用该路径。

## Step 3: 运行 Council

### 3a. 非交互终端（Agent 场景）— 默认路径

必须先使用 `--default-models`。这是最常用的 default attempt：

```bash
$LCT run \
  --input /tmp/council-question.md \
  --default-models \
  --timeout 180 \
  --json
```

记录 `default_attempt_status`、`default_attempt_run_id`、`default_attempt_failure_reason`。

如果 default attempt 失败、默认模型缺失，或没有产生可 validate artifacts，再用 Step 1 的推荐阵容显式重跑：

```bash
$LCT run \
  --input /tmp/council-question.md \
  --members "Kimi-K2.6,MiniMax-M2.7,GPT-5.2,DeepSeek-V4-Pro" \
  --chairman "Kimi-K2.6" \
  --timeout 180 \
  --json
```

记录 `recommended_rerun_status`、`recommended_rerun_run_id`、`recommended_members`、`recommended_chairman`。

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

## Step 4: 验证结果

```bash
$LCT validate <run_id> --json
```

确认 `status: "ok"` 或 `status: "degraded_ok"`。

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

如果 `traecli models --json` 中缺少某些默认模型，使用 `--members` 显式指定可用模型。

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
```
