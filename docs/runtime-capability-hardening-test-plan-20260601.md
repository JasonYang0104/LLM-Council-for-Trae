# Runtime Capability Hardening Test Plan

日期：2026-06-01

## 测试原则

本轮按 TDD 垂直切片推进：一次只写一个行为测试，让它先失败，再做最小实现。测试优先覆盖用户可观察行为：CLI 参数、provider 命令、artifact 字段、manifest 状态和 validate 结果。

## Slice 1：默认不再 Yolo

行为：

- `CouncilConfig.use_yolo` 默认是 `False`。
- `TraeCliProvider` 默认不生成 `--yolo`。
- CLI 只有显式 `--yolo` 时才启用 bypass permissions。
- 旧 `--no-yolo` 参数保留兼容，但不改变默认。

验收：

- 不启动真实 TraeCLI。
- 更新旧测试中“默认包含 --yolo”的断言。

## Slice 2：Member Tool Mode 命令生成

行为：

- `search_enabled` 命令包含 `--allowed-tool WebSearch` 和 `--allowed-tool WebFetch`。
- `search_enabled` 命令包含 `--disallowed-tool Skill` 和 `--disallowed-tool Agent`。
- `answer_only` 不包含 allowed web tools，且会禁止 Web 与 workspace 工具。
- `workspace_enabled` 允许只读 workspace 工具，但仍禁止 `Skill`、`Agent`、写入和 shell。

验收：

- 测试 `_build_command` 的公共命令输出。
- 不把 `--allowed-tool` 断言成 strict allowlist，只断言 LCT 生成了预期预授权/禁用参数。

## Slice 3：Stream JSON Tool Call Extraction

行为：

- `parse_stream_json` 提取每个 assistant tool call 的 name、id、arguments 摘要和 turn index。
- 现有 subagent `Agent` evidence 解析保持不变。
- 工具调用计数仍正确。

验收：

- 用 JSONL fixture 覆盖 `WebSearch`、`Skill`、`Bash`。

## Slice 4：Provider Tool Contamination

行为：

- `answer_only` 中任何 tool call 都产生 `tool_contaminated`。
- `search_enabled` 中 `WebSearch` / `WebFetch` 不污染。
- `search_enabled` 中 `Skill` 或 `Read` 污染。
- 污染结果写入 `ModelCallResult.forbidden_tool_calls`、`status=failed`、`error=tool_contaminated:*`。

验收：

- 优先单测纯函数判定。
- 再用 fake parsed stream 或 patched subprocess 路径覆盖 `query_model` 可观察结果。

## Slice 5：Artifact 与 Manifest

行为：

- `config.json` / manifest config 记录 `member_tool_mode` 和 `member_runtime_cwd_mode`。
- stage1 / stage2 / stage3 record 记录工具策略字段。
- meta JSON 记录工具策略字段。
- 被污染成员进入 failures，不计入 ok quorum。
- 如果 quorum 仍满足，manifest 是 `degraded_ok`，不是 `ok`。

验收：

- 使用 fake provider，不调用真实模型。

## Slice 6：Validate 污染门禁

行为：

- 旧 run 缺少新字段时不因 schema 失败。
- `manifest.status == "ok"` 且任一 stage/meta 有 forbidden tool call 时，validate 失败。
- 任一 stage record `status == "ok"` 但带 forbidden tool call 时，validate 失败。
- `manifest.status == "degraded_ok"` 且污染成员已是 failed 时，validate 可以通过其他完整性检查。

验收：

- 基于最小 valid run fixture 修改 manifest/meta。

## Slice 7：Isolated Member CWD

行为：

- direct provider 且未显式 `--runtime-cwd` 时，运行目录为 `runtime/member-cwd`。
- 显式 `--runtime-cwd` 时尊重用户输入。
- subagent provider 仍默认项目根目录。

验收：

- fake provider 记录初始化参数。
- 不依赖真实 TraeCLI。

## Slice 8：Subagent Frontmatter

行为：

- `.trae/agents/council-*.md` frontmatter 包含工具 allow/deny 字段。
- `profiles/subagents.json` 无需变化。

验收：

- 静态文本测试或 `inspect_subagents` 结果检查。

## 最终验证命令

完成前必须运行：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 live TraeCLI 可用，再运行：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

live smoke 需要额外覆盖：

- trivial prompt 不应调用 `Skill`。
- forced `WebSearch` 应能成功或给出明确环境阻断。
- forced `Skill` 应被拒绝或被 provider 标记污染。
- isolated cwd 不应暴露 LCT repo URL / GitStatus。
