# COCO Subagents 研究入口

本文记录 COCO-llm-council 对 subagent 的使用边界、已实现文件和验证口径。live subagent run 仍取决于当前 COCO / `traecli` 是否可用；COCO 不可用时，只能复验静态 profile、单元测试和已保存 artifacts。

## 当前设计判断

- direct `traecli` provider 是 P1 默认路径。
- COCO subagent provider 已作为 P2 路径实现，用于固定 council 成员。
- 每个固定成员放在 `.trae/agents/`。
- subagent 文件必须显式声明 `model`。
- run 结束后会校验 expected model 和 actual model。
- 如果 COCO 对无效模型 fallback 到默认模型，run 必须失败。

## 需要复验的命令

```bash
traecli doc subagents
traecli doc settings
traecli models --json
coco-llm-council subagents --json
coco-llm-council run --input examples/question.md --profile profiles/subagents.json --json
coco-llm-council validate <run_id> --json
```

## 目标文件形态

```text
.trae/agents/
  council-gpt54.md
  council-glm51.md
  council-gemini31.md
  council-chairman-gpt54.md
```

示例：

```yaml
---
name: council-gpt54
description: COCO-llm-council member using GPT-5.4
model: GPT-5.4
tools: []
---
你是 COCO-llm-council 的 council member。只回答当前阶段 prompt，不读取 workspace 外内容。
```

## 当前已验证文件

```text
.trae/agents/council-gpt54.md
.trae/agents/council-glm51.md
.trae/agents/council-chairman-gpt54.md
profiles/subagents.json
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
