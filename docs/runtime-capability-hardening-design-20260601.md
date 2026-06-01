# Runtime Capability Hardening Design

日期：2026-06-01

## 目标

这轮解决 LCT 成员模型的 runtime capability 边界。目标不是禁用所有工具，而是让成员只能使用本次 run 明确授权的工具，并把模式选择、命令参数和越权行为都落进 artifact。

默认策略：

- 保留受控搜索能力。
- 禁止 `Skill`、`Agent`、workspace 读写、shell、task/todo 类工具。
- direct provider 默认不传 `--yolo`。
- direct provider 默认在 isolated member cwd 运行，降低项目 workspace 注入。
- provider 自己解析 `stream-json`，把越权 tool call 标成结构化失败。

## 非目标

- 不重做 council protocol。
- 不把 subagent provider 升成 P0 主路径。
- 不依赖 prompt 约束替代 runtime 判定。
- 不假设 TraeCLI 有未证实的 `--no-workspace-context`、`--no-skills` 或 `--no-tools`。
- 不在运行中设计父 Agent 代替用户点击授权。

## 公共接口

新增 `member_tool_mode`：

```text
answer_only
search_enabled
workspace_enabled
```

默认值：`search_enabled`。

语义：

| 模式 | 允许工具 | 禁止工具 | 适用场景 |
|---|---|---|---|
| `answer_only` | 无 | 所有 tool call | 纯推理、写作、互评 |
| `search_enabled` | `WebSearch`, `WebFetch` | `Skill`, `Agent`, 文件、写入、shell、task/todo | 默认成员模式，适合事实核查 |
| `workspace_enabled` | `Read`, `Glob`, `Grep`, `LS`, `WebSearch`, `WebFetch` | `Skill`, `Agent`, `Write`, `Edit`, `Bash`, task/todo | 后续代码库审查模式，本轮先只读 |

CLI 增加：

```bash
llm-council-for-trae run --member-tool-mode search_enabled
llm-council-for-trae run --yolo
```

`--no-yolo` 保留为兼容入口，但默认已经是 no-yolo。需要 bypass permissions 时必须显式传 `--yolo`。

## Provider 命令生成

`TraeCliProvider` 根据 `member_tool_mode` 生成 TraeCLI 参数：

```bash
--allowed-tool WebSearch
--allowed-tool WebFetch
--disallowed-tool Skill
--disallowed-tool Agent
...
```

`--allowed-tool` 只代表预授权，不代表严格 allowlist。真正的隔离结果由 provider 解析 `stream-json` 后判定。

## Isolated Member CWD

direct provider 默认使用 run 内部空目录：

```text
<system temp>/lct-<run_id>-member-cwd-*/
```

如果用户显式传 `--runtime-cwd`，以用户提供值为准。subagent provider 仍使用项目根目录，因为真实 subagent 文件在 `.trae/agents/` 下，不能默认隔离到空目录。

artifact 要记录实际 `runtime_cwd`，并在 event 中记录 isolated cwd 是否启用。run 目录内写入：

```text
runtime/member-cwd.path
```

不能把 isolated cwd 放在 repo 内部。live smoke 已证明 repo 内 `.llm-council-for-trae/runs/.../runtime/member-cwd/` 仍会让 TraeCLI 向上发现根 `AGENTS.md`，导致模型尝试 `Read AGENTS.md` 并触发污染门禁。

## Tool Contamination

provider 必须从每条 assistant event 中提取：

- tool name
- tool id
- arguments 摘要
- turn index

判定规则：

- 工具名不在当前 mode allowlist：污染。
- 工具名在 always-forbidden：污染。
- `answer_only` 中任何 tool call：污染。

污染行为：

- `ModelCallResult.status = "failed"`
- `ModelCallResult.error` 以 `tool_contaminated:` 开头。
- `ModelCallResult.forbidden_tool_calls` 记录越权工具。
- stage record 和 meta JSON 都保留 `member_tool_mode`、`allowed_tools`、`disallowed_tools`、`forbidden_tool_calls`。
- 失败成员不计入 quorum；如果 quorum 仍满足，manifest 可以是 `degraded_ok`，但不能是 `ok`。

## Artifact 与 Validate

新增字段：

```json
{
  "member_tool_mode": "search_enabled",
  "allowed_tools": ["WebSearch", "WebFetch"],
  "disallowed_tools": ["Skill", "Agent", "..."],
  "forbidden_tool_calls": []
}
```

兼容策略：

- 新 run 写入这些字段。
- 旧 run 缺少字段时，schema validation 不直接失败。
- 如果任何 stage record 或 meta 中存在非空 `forbidden_tool_calls`，`validate` 必须拒绝 `manifest.status == "ok"`。
- 如果某条 stage record 仍是 `status == "ok"` 但带有 forbidden tool call，`validate` 必须失败。

## Subagent Provider

本轮只更新 `.trae/agents/*.md` frontmatter：

- member agents：保留 `WebSearch,WebFetch`，禁止 `Skill`、`Agent`、文件、写入、shell、task/todo。
- chairman agents：禁止 `Skill`、`Agent`、文件写入、shell；是否保留搜索按后续验证决定，本轮先与 member 一致保守处理。

subagent provider 的真实 invocation evidence 仍由现有 validate 合同负责，本轮不把它作为 P0 成功路径。

实现上，subagent provider 不复用 direct 默认的 `search_enabled` policy。原因是 subagent provider 需要顶层 `Agent` tool call 作为真实 invocation evidence，而 `search_enabled` 会禁止 `Agent`。因此 provider 内部使用 `subagent_invocation` policy：只允许 `Agent`，仍禁止 `Skill`、workspace、shell 和 web 工具；真正的成员工具边界交给 `.trae/agents/*.md` frontmatter。

## 已实现状态字段

新 run 的 stage meta 必须记录：

```json
{
  "member_tool_mode": "search_enabled",
  "allowed_tools": ["WebSearch", "WebFetch"],
  "disallowed_tools": ["Skill", "Agent"],
  "forbidden_tool_calls": []
}
```

这些字段不是展示装饰，而是 validate 和审计依据。缺少字段意味着该 stage meta 不能证明本次模型调用的 capability 边界。

## 回滚边界

如果 live smoke 发现默认 `search_enabled` 仍触发审批或不可用，可以临时把 CLI 默认切回 `answer_only`，但 provider 侧污染检测和默认 no-yolo 不回滚。
