# Trae CLI Subagents 研究入口

本文记录 LLM-Council-for-Trae 对 subagent 的使用边界、已实现文件和验证口径。direct provider 是日常主路径；subagent profile 是 legacy / experimental 路径，保留用于历史 artifact validation 和未来固定成员实验。live subagent run 仍取决于当前 traecli 是否可用；Trae CLI 不可用时，只能复验静态 profile、单元测试和已保存 artifacts。

## 当前设计判断

- direct `traecli` provider 是 P1 默认路径，也是全局安装后的日常主路径。
- Trae CLI subagent provider 已作为 P2 legacy / experimental 路径实现，用于固定 council 成员实验和历史产物校验。
- 每个固定成员放在 `.trae/agents/`。
- subagent 文件必须显式声明 `model`。
- run 结束后会校验 expected model 和 actual model。
- 如果 Trae CLI 对无效模型 fallback 到默认模型，run 必须失败。
- `profiles/subagents.json` 会受 live roster 模型漂移影响；如果 profile 中的模型已不在 `traecli models --json`，不要把失败解读成 direct provider 失败。

## 需要复验的命令

```bash
traecli doc subagents
traecli doc settings
traecli models --json
llm-council-for-trae subagents --json
llm-council-for-trae run --input examples/question.md --profile profiles/subagents.json --json
llm-council-for-trae validate <run_id> --json
```

## 目标文件形态

```text
.trae/agents/
  council-chairman-gpt54.md
  council-chairman-kimi26.md
  council-deepseek-v4.md
  council-gemini31.md
  council-glm51.md
  council-gpt54.md
  council-kimi26.md
  council-qwen36.md
```

示例：

```yaml
---
name: council-gpt54
description: Fixed LLM-Council-for-Trae member using GPT-5.4. Use only when a council stage prompt explicitly asks this member to answer.
model: GPT-5.4
---

You are a fixed LLM-Council-for-Trae member.

Answer only the current council stage prompt. Do not browse the workspace, do not call tools, and do not add process commentary. Preserve the requested output format exactly, especially FINAL RANKING sections.
```

## 当前已验证文件

```text
.trae/agents/council-chairman-gpt54.md
.trae/agents/council-chairman-kimi26.md
.trae/agents/council-deepseek-v4.md
.trae/agents/council-gemini31.md
.trae/agents/council-glm51.md
.trae/agents/council-gpt54.md
.trae/agents/council-kimi26.md
.trae/agents/council-qwen36.md
profiles/subagents.json
```

`profiles/subagents.json` 当前与 direct 默认阵容对齐：

```text
members: GPT-5.4, GLM-5.1, Qwen3.6-Plus, Kimi-K2.6, DeepSeek-V4-Pro, Gemini-3.1-Pro-Preview
chairman: Kimi-K2.6
```

已验证 run：

```text
run_id: subagent-hard-20260522165545
status: ok
provider_mode: subagent
expected/actual model: all matched
validate failures: 0
subagent invocation checks: 5 / 5 passed
```

旧的 prompt-only subagent smoke 不能作为通过证据；没有 Agent tool call、tool result、子 agent `parent_tool_use_id` 和 `_source_model` 的 run 应被 `validate` 判失败。
