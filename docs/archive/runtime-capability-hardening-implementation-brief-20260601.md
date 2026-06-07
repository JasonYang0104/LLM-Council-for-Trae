# Runtime Capability Hardening Implementation Brief

日期：2026-06-01

## 一句话结论

LCT 已从“成员模型可能进入完整 Agent runtime”推进到“成员模型有明确 capability policy”。默认 direct run 保留 `WebSearch` / `WebFetch`，默认不再 `--yolo`，默认隔离到系统临时 cwd，并且任何越权工具调用都会被 provider 标成 `tool_contaminated` 失败。

## 这轮解决了什么

- 默认 member runtime 从 bypass permissions 改为 no-yolo。
- 新增 `member_tool_mode`：`answer_only`、`search_enabled`、`workspace_enabled`。
- direct 默认 `search_enabled`：允许 web 搜索，禁止 `Skill`、`Agent`、workspace、shell、task/todo。
- direct 默认 runtime cwd 改为系统临时目录，并在 artifact 写入 `runtime/member-cwd.path`。
- provider 从 `stream-json` 提取 tool call 明细：tool name、id、arguments 摘要、turn index。
- provider 对越权工具调用写入 `forbidden_tool_calls`，并将该模型调用标记为 failed。
- stage records、stage meta、manifest config 都记录工具策略字段。
- `validate` 拒绝 `status=ok` 但包含 forbidden tool call 的 artifact。
- subagent provider 增加内部 `subagent_invocation` policy，避免 direct policy 禁掉真实 `Agent` invocation evidence。
- `.trae/agents/council-*.md` frontmatter 增加工具 allow/deny 字段。

## 用户可感知变化

以前成员模型可能读 workspace、调用 LCT skill、等待 nested council 或检查 run 目录，最后还被算作 `ok`。现在这类行为会变成结构化失败；如果 quorum 仍满足，run 可以 `degraded_ok` 交付，但不能伪装成全绿。

实现过程中有一个重要修正：最初把 isolated cwd 放在 repo 内 run 目录，live run `runtime-capability-smoke-20260601-1825` 失败，因为 TraeCLI 仍向上发现根 `AGENTS.md` 并诱导模型调用 `Read`。改成系统临时目录后，live run `runtime-capability-smoke-20260601-1835` 返回 `ok`，`validate` 也返回 `ok`。

默认允许搜索意味着事实核查能力没有被一刀切砍掉。真正禁止的是会污染 council member 角色边界的能力：`Skill`、`Agent`、文件系统、shell 和写操作。

## 仍未解决的风险

- TraeCLI 没有已证实的全局 `--no-workspace-context`，isolated cwd 只能降低项目级注入，不能移除所有系统上下文。
- `--allowed-tool` / `--disallowed-tool` 仍不能当成唯一隔离边界；provider 污染检测是第二道门。
- 本轮单测覆盖了命令、parser、artifact、validate 和 fake provider 路径；live smoke 仍取决于当前机器 TraeCLI 状态。
- `workspace_enabled` 目前是只读策略，不开放 shell 白名单。

## 验证状态

- `PYTHONPATH=src python3 -m compileall src`：通过。
- `make test`：112 tests 通过。
- `git diff --check`：通过。
- `doctor --json`：`ok=true`，有 TraeCLI warning。
- `models --recommend --json`：返回 23 个模型。
- live run：`runtime-capability-smoke-20260601-1835`，`status=ok`、`degraded=false`、HTML 已生成。
- live validate：`runtime-capability-smoke-20260601-1835`，`status=ok`、无 failures。

## 下一轮应该看哪里

- live smoke：验证 `search_enabled` 下 forced `WebSearch`、forced `Skill`、isolated cwd 三个真实行为。
- 质量门槛：污染之外，短而无效的“我在等待 council”类回答也应在 Stage 1 前置拦截。
- provider 合同：继续区分 direct、true subagent、prompt-agent 三种路径，避免有内容但无 invocation evidence 的结果被误读。
