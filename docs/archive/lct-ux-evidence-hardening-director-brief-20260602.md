# LCT 使用体验与证据口径迭代简报

日期：2026-06-02
分支：`codex/lct-ux-evidence-hardening-20260602`
状态：实现完成，测试与轻量 live runtime 检查通过
置信度：高

## 结论

本轮不是模型稳定性大评测，而是把 LCT 的默认使用路径说得更诚实、更可复盘。

已经落地五件事：

- HTML 报告开头的输入提示词改为默认折叠，最终答案重新成为第一阅读面。
- `search_enabled` 被拆成 `search_allowed` 和 `search_used` 两个证据信号，不再暗示“允许搜索 = 实际搜索”。
- provider 已把真实 `tool_calls` 明细持久化进 meta 和 manifest stage records，HTML 不再依赖测试里虚构的字段形态。
- Skill 增加 raw / structured 输入模式：默认可由 Agent 轻量结构化，但用户说“按原始输入 / 不要改写 / 只用原文 / 评估 LCT 对原始问题的理解”时必须只写原文。
- subagent profile 从主路径降级为 legacy / experimental；`profiles/subagents.json` 和 `.trae/agents/` 保留，但不再作为日常 global install 主链路。

另一个现实也必须直说：静态 `--default-models` 仍包含 `GLM-5.1`，而当前 live `traecli models --json` 没有它。本轮没有假装完成模型阵容重定标；只把 `models --recommend` 的自动推荐修到默认排除 Seed/Doubao，并保留“无安全候选时才回落”的口径。下一阶段仍应单独处理 default roster。

## 为什么这轮有价值

此前 LCT 的问题不是“完全不能跑”，而是证据容易被误读：

| 旧风险 | 真实含义 | 本轮处理 |
|---|---|---|
| 输入 prompt 占据 HTML 顶部 | 长问题会压住最终答案 | 默认折叠输入，仍保留源码和复制 payload |
| `search_enabled` | 只代表 WebSearch / WebFetch 被允许 | 新增 `search_allowed` / `search_used` |
| tool call 明细只在 stream 解析中存在 | HTML 无法可靠判断是否搜索 | 持久化 `tool_calls` 到 run metadata |
| subagent profile 还像主路径 | 容易受模型漂移影响 | README / docs 降级为 legacy / experimental |
| Agent 是否改写输入不透明 | 用户无法判断 LCT 是跑原文还是结构化版 | Skill 和 index contract 标明 Input mode |

## 关键实现

代码层：

- `src/llm_council_for_trae/html_export.py`：输入提示词改为 `<details id="input-prompt">`，新增 search usage summary。
- `src/llm_council_for_trae/provider.py`：`ModelCallResult` 新增 `tool_calls`，写入 `to_json()`。
- `src/llm_council_for_trae/council.py`：stage records 保留 `tool_calls`，让 HTML 和 validate 后续都有真实证据源。
- `src/llm_council_for_trae/model_selection.py`：自动推荐优先排除 Seed/Doubao；只有没有更安全候选时才回落。

文档层：

- `skills/llm-council-for-trae/SKILL.md`：新增 Input Preparation、Input mode、search_allowed / search_used 汇报要求。
- `README.md`：Quickstart 的 root index contract 明确包含 `Input mode`、`search_allowed`、`search_used`。
- `docs/traecli-subagents.md`：subagent provider 降级为 legacy / experimental。
- `docs/lct-ux-evidence-hardening-design-20260602.md` 与 `docs/lct-ux-evidence-hardening-test-plan-20260602.md`：保留设计和测试口径。

## Subagent Review 结果

三个只读 reviewer 都跑完，发现的问题都已关闭：

| Reviewer | 发现 | 处理 |
|---|---|---|
| HTML / metadata | HTML search summary 依赖未持久化的 `tool_calls` 明细 | provider 和 stage records 持久化 `tool_calls` |
| Skill / docs | README Quickstart 没锁住 root index 的 `Input mode` / search 字段 | README 和 tests 补 index contract |
| Evidence / recommendation | `[Seed, openrouter]` 边界会推荐 Seed；菜单文案说主席优先 GPT 但实际不是 | 候选池三层 fallback；菜单文案改成真实优先级 |

## 验证证据

本地验证：

```text
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

结果：

- `compileall`：pass。
- `make test`：pass，132 tests。
- `git diff --check`：pass。

轻量 live runtime 检查：

```text
PYTHONPATH=src python3 -m llm_council_for_trae.cli doctor --json
PYTHONPATH=src python3 -m llm_council_for_trae.cli models --recommend --json
```

结果：

- `doctor`：`ok=true`；`traecli` 版本 `coco version 0.120.32`；warnings 仅来自 MCP still connecting 和 update server timeout；errors 为空。
- live model count：21。
- recommendation：members `GPT-5.4, DeepSeek-V4-Pro, Kimi-K2.6, MiniMax-M2.7`；chairman `Kimi-K2.6`。
- 推荐结果没有 Seed / Doubao。

没有执行 live council run。原因不是 runtime 不可用，而是本轮验收目标不是再做一次模型稳定性评测；默认 roster 漂移应作为下一阶段独立处理。

## 剩余风险

- 静态 `--default-models` 仍可能因为 `GLM-5.1` 缺席而失败。
- `search_used=false` 只能说明当前 artifacts 没观察到 WebSearch / WebFetch tool call，不等于回答中的事实一定未经外部校验。
- subagent historical artifacts 仍可 validate，但新的 profile live run 不应被当成日常 smoke。

## 下一步

建议下一阶段只处理一个问题：默认 roster 重定标。不要把它和 HTML、Skill、subagent 文档继续混在一个 PR 里。

候选动作：

- 基于当前 live roster 设计新的 static default 或把非交互 Skill 从“必须 `--default-models`”改为“default 失败后自动推荐显式 roster”。
- 对候选阵容做小型稳定性 smoke，不做泛化 benchmark。
- 明确 GPT-5.5、Seed/Doubao、OpenRouter 的默认排除规则和显式 opt-in 规则。
