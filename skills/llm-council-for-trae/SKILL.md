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

## Run

1. 将用户问题写入当前 workspace 的临时 Markdown 文件，例如 `_lct_question.md`。
2. 设置 run id：

```bash
RUN_ID="lct-$(date +%Y%m%d-%H%M%S)"
```

3. 执行非交互 council run：

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --default-models \
  --run-id "$RUN_ID" \
  --timeout 180 \
  --json
```

4. 如果 run 返回 `ok` 或 `degraded_ok`，执行 validate：

```bash
llm-council-for-trae validate "$RUN_ID" --json
```

5. 从 artifacts 读取最终答案：

```bash
cat ".llm-council-for-trae/runs/$RUN_ID/stage3/final.md"
```

6. 在当前 workspace 根目录写出：
   - `$RUN_ID-final.md`：主席最终答案。
   - `$RUN_ID-index.md`：run id、run status、validate status、HTML 路径、失败模型或 timeout。

## Report

向用户分开汇报：

- run id
- run status
- validate status
- final answer path
- HTML report path
- failed models / timeout
- live `traecli` 是否可用

如果 `traecli` 不可用、模型列表为空、run 未产生有效 artifacts，必须说清楚是 skipped / failed。不要把 fake runtime 结果说成 live traecli 结果。

## Hard Constraints

- 必须使用 `--default-models`：Agent 非 TTY 场景不能交互选择模型。
- 必须使用 `--json`：外层 Agent 需要结构化输出。
- 必须运行 `validate`：run 完成不等于 artifact 可信。
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
