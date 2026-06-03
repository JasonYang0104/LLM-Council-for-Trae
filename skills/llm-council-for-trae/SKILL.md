---
name: llm-council-for-trae
description: 当用户要求使用 LCT、跑 LCT、council run、用委员会回答、让多个模型讨论，或需要 LLM-Council-for-Trae 生成可复盘答案时使用。默认在干净问题 workspace 中调用全局安装的 llm-council-for-trae CLI，运行后必须 validate，并汇报最终答案与 HTML artifact。
---

# LLM-Council-for-Trae Workflow

## Trigger

当用户说“使用 LCT”“跑 LCT”“council run”“用委员会回答”“让多个模型讨论”或明确要求 `LLM-Council-for-Trae` 时触发。

## Preflight

1. 确认当前目录不是 LCT 源码 repo。出现以下任一标记时停止，除非用户明确说正在做 LCT 开发：
   - `src/llm_council_for_trae/`
   - `.trae/agents/`
   - `profiles/subagents.json`
2. 确认 `traecli --version` 可用。
3. 确认 `traecli models --json` 返回非空模型列表。
4. 确认 `command -v llm-council-for-trae` 可找到全局 CLI。
5. 尽量确认 wrapper 内容指向 `~/.LCT/src`，而不是旧开发 checkout。
6. 如果 CLI 不可用，提示用户先完成 `~/.LCT` 全局安装，并把本 Skill 安装到 `/Users/bytedance/.agents/skills/llm-council-for-trae`。

## Input Preparation

LCT CLI 只消费 `_lct_question.md`；是否做轻量意图理解和 prompt shaping 是外层 Agent 行为。

默认使用 `structured by Agent` 模式：

1. 保留用户原始输入，使用清晰标题标注为 `Original input`。
2. 可以补充 `Agent interpretation` 和 `Suggested council focus`，用于拆解约束、成功标准、需要正反论证的维度。
3. 不要伪造用户没有表达过的事实、偏好或结论。

如果用户明确说 `按原始输入`、`不要改写`、`只用原文`、`我要评估 LCT 对原始问题的理解` 或类似表达，必须使用 `raw original input` 模式：`_lct_question.md` 只写用户原文，不加结构化增强。

无论哪种模式，最终根目录 `$RUN_ID-index.md` 和对用户汇报都必须写明 `Input mode` 和证据字段；输入模式取值为：

```text
Input mode: raw original input
```

或：

```text
Input mode: structured by Agent
```

`$RUN_ID-index.md` 必须拆开记录 LCT 内部搜索证据和外层 Agent 自己补充的外部搜索证据：

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

## Run

1. 按 Input Preparation 规则将用户问题写入当前 workspace 的临时 Markdown 文件，例如 `_lct_question.md`。
2. 设置 run id：

```bash
RUN_ID="lct-$(date +%Y%m%d-%H%M%S)"
```

3. 先记录推荐阵容，作为默认阵容失败后的外层重跑依据：

```bash
llm-council-for-trae models --recommend --json
```

当前静态默认模型套是：

```text
members: Kimi-K2.6, MiniMax-M2.7, GPT-5.2, DeepSeek-V4-Pro
chairman: Kimi-K2.6
```

推荐阵容不改变默认 run。fallback 编排只属于 Skill / 外层 Agent，不属于 CLI 内部自动行为。

4. 执行非交互 default attempt：

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --default-models \
  --run-id "$RUN_ID" \
  --timeout 180 \
  --json
```

记录：

```text
default_attempt_status: ok|degraded_ok|failed|skipped
default_attempt_run_id: <RUN_ID or none>
default_attempt_failure_reason: <reason or none>
```

5. 如果 default attempt 表面返回 `failed`、默认模型缺失、apparent hang、run JSON 为空，或中途目录看起来缺 Stage 2 / Stage 3，先读取 terminal manifest 并执行：

```bash
llm-council-for-trae validate <run_id> --json
```

不要用自然语言观察判 failed。`degraded_ok 是可用结果`，成员失败不等于 run 失败。只有 validate JSON 显示无可用 final，才用第 3 步推荐阵容显式重跑：

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --members "Kimi-K2.6,MiniMax-M2.7,GPT-5.2,DeepSeek-V4-Pro" \
  --chairman "Kimi-K2.6" \
  --run-id "$RUN_ID-recommended" \
  --timeout 180 \
  --json
```

记录：

```text
recommended_rerun_status: ok|degraded_ok|failed|skipped
recommended_rerun_run_id: <RUN_ID or none>
recommended_members: <comma-separated models or none>
recommended_chairman: <model or none>
```

6. 如果最终 run 返回 `ok` 或 `degraded_ok`，把成功 run 记为 `FINAL_RUN_ID`，再执行 validate：

```bash
llm-council-for-trae validate "$FINAL_RUN_ID" --json
```

validate JSON 必须记录 `terminal`、`usable_final`、`stage3_final_exists`、`html_exists`、`failed_stage_records` 和 `verdict`。`verdict` 取值为 `complete_ok_final`、`usable_degraded_final`、`in_progress`、`failed_no_final`、`invalid_artifacts`。只有 `usable_final: true` 才能交付最终答案；`$RUN_ID-index.md` 的 run status / validate status / verdict 必须来自 validate JSON。

7. 从 artifacts 读取最终答案：

```bash
cat ".llm-council-for-trae/runs/$FINAL_RUN_ID/stage3/final.md"
```

8. 在当前 workspace 根目录写出：
   - `$RUN_ID-final.md`：主席最终答案。
   - `$RUN_ID-index.md`：run id、run status、validate status、HTML 路径、Input mode、lct_search_allowed、lct_search_used、lct_web_tool_calls、agent_external_search_allowed、agent_external_search_used、agent_sources、agent_fact_pack_path、agent_added_context、final_answer_source、default/recommended attempt 状态、失败模型或 timeout。

## Report

向用户分开汇报：

- run id
- run status
- validate status
- validate verdict
- final answer path
- HTML report path
- Input mode: `raw original input` 或 `structured by Agent`
- lct_search_allowed：LCT member 是否允许 `WebSearch` / `WebFetch`
- lct_search_used：LCT artifacts 中是否实际观察到 `WebSearch` / `WebFetch` tool call
- lct_web_tool_calls：LCT artifacts 中的 Web 工具调用数量
- agent_external_search_allowed：外层 Agent 是否被允许在 LCT 之外自行检索
- agent_external_search_used：外层 Agent 是否实际在 LCT 之外自行检索
- agent_sources / agent_fact_pack_path：外层 Agent 补充给问题文件的来源或 fact pack
- final_answer_source：通常为 `stage3/final.md`
- failed models / timeout
- live `traecli` 是否可用

`--member-tool-mode search_enabled` 只代表搜索工具被允许，不代表模型实际搜索了。必须把 `lct_search_allowed` 和 `lct_search_used` 分开说；如果 manifest 中 tool call count 为 0，就明确说搜索被允许但未发生。外层 Agent 自己做的网页检索必须进入 `agent_external_search_*` 字段，不要混进 LCT 的 `lct_search_*` 字段。

如果 `traecli` 不可用、模型列表为空、run 未产生有效 artifacts，必须说清楚是 skipped / failed。不要把 fake runtime 结果说成 live traecli 结果。

## Hard Constraints

- 必须使用 `--default-models`：Agent 非 TTY 场景不能交互选择模型。
- 必须使用 `--json`：外层 Agent 需要结构化输出。
- 必须运行 `validate`：run 完成不等于 artifact 可信。
- 不要在 CLI 内部实现默认失败后的隐式 recommended fallback；默认失败后的重跑只能由本 Skill / 外层 Agent 显式编排。
- 不要在问题 workspace 中 clone LCT 仓库。
- 不要在 LCT 源码 repo 中跑用户问题；切换到干净问题 workspace。
- 不要修改 `.llm-council-for-trae/` 中的 artifacts；只读，必要时复制最终答案到 workspace 根目录。
- 不要把 fake runtime、fixture、单元测试或非 live 路径说成 live `traecli` smoke。

## Failure Handling

- `traecli` 不可用：报告阻断点，不继续 run。
- `llm-council-for-trae` 不可用：提示完成 `~/.LCT` 全局安装。
- 当前目录疑似 LCT 源码 repo：要求切换到干净问题 workspace。
- run 超时：报告 timeout，建议调大 `--timeout` 后重试。
- quorum 不够：报告哪些模型失败以及失败原因。
- validate 失败：报告具体 schema、模型一致性或 contamination 检查失败项。
- apparent hang / interruption：先读取 terminal manifest 并执行 `validate <run_id> --json`；如果 `verdict` 是 `complete_ok_final` 或 `usable_degraded_final`，不要 fallback。
