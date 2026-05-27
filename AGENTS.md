# COCO-llm-council Agent Notes

## 项目定位

`COCO-llm-council` 是一个本地 CLI：它调用 COCO / `traecli` 跑 `references/llm-council` 的核心 protocol，即 Stage 1 独立回答、Stage 2 匿名互评、Stage 3 主席综合，然后从已保存 artifacts 确定性导出 HTML。

面向用户的默认语言是简体中文。代码、命令、路径、模型名、字段名和既有技术标识保持原文。

## 阅读顺序

把 `README.md` 当唯一入口。它会索引后续文档：

- `docs/design.md`：架构、protocol 和产品边界。
- `docs/COCO_INSTALLATION_AND_PATHS.md`：COCO 安装、登录、路径和排障事实。
- `docs/coco-subagents.md`：固定 council subagent 的行为和验证方式。
- `docs/llm-council-parity.md`：与 `references/llm-council` 的对齐关系。
- `docs/director-brief-20260522.md`：阶段状态和验证证据。

## 硬边界

- 不重新引入原 Web UI。
- 不接 OpenRouter API。
- 不依赖旧 TR。
- 不把 HTML export 和 chairman synthesis 混成一步。Stage 3 只写 `stage3/final.md`；HTML 只渲染 artifacts。
- 不把 prompt-only `@agent` 输出当成真实 subagent 执行。验证必须看到 Agent tool evidence。

## Runtime 与模型选择

真实 council run 需要当前 COCO / `traecli` 可用。如果 COCO 不可用，只验证非 live 部分：单元测试、fixture schema validation、模型推荐逻辑、非交互 CLI 失败路径，以及明确可用的 fake runtime E2E。不要把 fake runtime 结果说成 live COCO 结果。

CLC 的 direct model execution 不依赖外部 MCP server。`traecli doctor` 如果只报告 MCP 初始化失败，但 `traecli --version` 和 `traecli models --json` 正常，run 不应被硬阻断；这类 MCP-only error 应记录到 `runtime/doctor.json` 的 `ignored_errors` 和 `manifest.warnings`，后续排查时作为环境噪音处理。非 MCP 的 doctor error、模型列表为空或模型缺失仍然必须失败。

模型选择已经在 CLI 内主动发生：

- `coco-llm-council run --input <file> --json` 在 TTY 中会列出当前 `traecli models --json` 结果，并询问是否使用推荐模型套。
- `--default-models` 跳过询问，使用静态默认模型套。
- `--members/--chairman` 或 `--profile` 会绕过交互选择。
- 非交互调用方必须传 `--default-models`、显式模型或 profile；CLC 应快速失败，不应挂起。

## 验证命令

声称完成前必须跑 fresh verification：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

COCO 可用时再加：

```bash
coco-llm-council doctor --json
coco-llm-council models --recommend --json
coco-llm-council run --input examples/question.md --json
coco-llm-council validate <run_id> --json
```

## E2E 汇报格式

做 E2E 测试时，最终汇报只保留可复验事实：

- 执行过的命令。
- 每条命令的结果：pass / fail / skipped。
- live COCO 是否可用。
- 如果产生 run：`run_id`、`validate` 状态、HTML 路径。
- 如果没有 live run：明确是 non-live / fake-runtime / skipped，并说明阻断点。
- 需要下一阶段处理的问题。

## 当前模型阵容（2026-05-27 收敛）

- **成员（6人）**：GPT-5.4、GLM-5.1、Qwen3.6-Plus、Kimi-K2.6、DeepSeek-V4-Pro、Gemini-3.1-Pro-Preview
- **主席**：Kimi-K2.6
- **主席备选链**：DeepSeek-V4-Pro → GPT-5.4
- **严禁使用**：Doubao 系、GPT-5.5
- 主席和成员物理隔离：不同 session_id、不同输出目录、不同 prompt

## Quorum 策略

- `min_valid_members` 默认值 **3**（底线：至少 3 个成员有有效结果才继续）
- Chairman 兼任 member 时：chairman ok 计入 quorum；chairman failed 免费（排除出 ok_count 和 total）
- `degraded_ok` 退出码为 0，JSON 标注 `degraded: true`
- Stage 1 quorum 不够时需对失败成员发起重试（P2 待实现）

## HTML 报告结构

```
archive-hero → summary-strip → article#final-answer → section#evidence
```

- failures 不管有无都不展示
- 模型表现摘要表格已取消
- final-answer 输出综述答案，不是评价模型排名

## 已知 Runtime 问题

- traecli 在 stdout 是 pipe（非 tty）时可能挂起（MCP 初始化），`run_command` 已有 fallback 到 `os.system`
- macOS 下 `os.system` 返回值需 `rc >> 8` 获取真实退出码
- traecli 8 模型并发极不稳定，已收敛到 6 成员阵容

## Git 边界

项目现在是 git repo。`.coco-llm-council/` 是本地 run artifacts，已被 ignore。不要改写或删除用户产物，除非用户明确要求。
