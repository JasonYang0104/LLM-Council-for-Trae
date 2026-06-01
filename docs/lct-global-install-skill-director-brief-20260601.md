# LCT 全局安装与用户级 Skill 迭代简报

日期：2026-06-01
分支：`codex/lct-global-install-skill-docs-20260601`
状态：完成实现与验证，live smoke 为 `degraded_ok`，不是 full `ok`
置信度：高

## 结论

本轮把 LCT 的默认使用方式从“把仓库 clone 到问题 workspace 后让 Agent 用根目录能力”改成了“全局安装到 `~/.LCT`，安装用户级 Skill，然后在干净问题 workspace 运行”。

核心改动已经落地：

- README 默认入口改为 `~/.LCT` 全局安装、`~/.local/bin/llm-council-for-trae` wrapper、`/Users/bytedance/.agents/skills/llm-council-for-trae` Skill、干净问题 workspace。
- 新增 canonical Skill：`skills/llm-council-for-trae/SKILL.md`。
- 新增部署指南：`docs/lct-deployment-guide-20260601.md`。
- 新增设计与测试方案：`docs/lct-global-install-skill-design-20260601.md`、`docs/lct-global-install-skill-test-plan-20260601.md`。
- Makefile 新增 `install-global` 和 `install-skill`；`install-local` 保持开发者路径。
- 新增 repository contract tests，锁住 README / deployment guide / Skill / Makefile 的安装与隔离口径。

这不是 runtime 改造。没有改 council protocol、模型阵容、`validate` 语义、HTML 报告结构，也没有把 fake runtime 当 live 证据。

## 为什么要做

旧 README 的默认用法会诱导用户把 LCT repo clone 到问题 workspace。这个路径有污染风险：`traecli` 可能看到 LCT 源码、设计文档、`.trae/agents/`、`profiles/subagents.json`、历史 artifacts 和本地 dirty state。模型回答用户问题时不应吸收 LCT 自己的实现上下文。

新边界是三目录分离：

| 目录 | 职责 | 是否运行用户问题 |
|---|---|---|
| 开发仓库 | 写代码、文档、测试、review | 否 |
| `~/.LCT` | 全局安装根目录 | 否 |
| 干净问题 workspace | 用户问题、run artifacts、最终答案索引 | 是 |

## 关键设计

`install-global` 做两件事：

1. 写入 `~/.local/bin/llm-council-for-trae`，wrapper 的 `PYTHONPATH` 指向 `~/.LCT/src`。
2. 把 `~/.LCT/skills/llm-council-for-trae` 链接到 `/Users/bytedance/.agents/skills/llm-council-for-trae`。

`install-local` 明确保留为开发者路径。它继续指向当前 checkout 的 `src/`，适合本地调试，不是默认用户安装方式。

Skill 的硬约束：

- 当前目录出现 `src/llm_council_for_trae/`、`.trae/agents/`、`profiles/subagents.json` 时停止。
- 必须使用 `--default-models`。
- 必须使用 `--json`。
- 必须运行 `validate`。
- 必须把 live `traecli`、fixture、fake runtime 分开汇报。

## Subagent Review 结果

使用了三个只读 reviewer：

| Reviewer | 初始结论 | 关键发现 | 收口 |
|---|---:|---|---|
| Fresh Install Reviewer | fail | deployment guide 的 live smoke 示例还用 `examples/question.md`，违背干净 workspace 口径 | 已修复 |
| Workspace Isolation Reviewer | pass | README guard marker 和根目录 final/index 输出不够显式 | 已修复 |
| Operational Consistency Reviewer | fail | README / deployment guide clean workspace 示例混入 source-repo 输入；`install-global` 有半安装 wrapper 风险 | 已修复 |

Targeted re-check 已通过：之前的 P1/P2 均关闭，无新增问题。

## 验证证据

本地验证：

```text
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

结果：

- `compileall`：pass。
- `make test`：pass，120 tests。
- `git diff --check`：pass。

全局安装验证：

- `~/.LCT` 已存在，当前为本分支 `codex/lct-global-install-skill-docs-20260601`。这是 branch install，不伪装成已经合入 main。
- `~/.local/bin/llm-council-for-trae` 指向 `/Users/bytedance/.LCT/src`。
- `/Users/bytedance/.agents/skills/llm-council-for-trae` 指向 `/Users/bytedance/.LCT/skills/llm-council-for-trae`。
- `llm-council-for-trae --help`：pass。
- `llm-council-for-trae doctor --json`：ok，只有 warnings，无 errors。
- `llm-council-for-trae models --recommend --json`：pass，返回 24 个模型。

live smoke：

```text
workspace: /tmp/lct-live-smoke
run_id: lct-global-smoke-20260601-201808
run status: degraded_ok
validate status: degraded_ok
HTML: /tmp/lct-live-smoke/.llm-council-for-trae/runs/lct-global-smoke-20260601-201808/html/index.html
final: /tmp/lct-live-smoke/.llm-council-for-trae/runs/lct-global-smoke-20260601-201808/stage3/final.md
```

这个 smoke 是真实 `traecli`。它不是 fake runtime，也不是 fixture。

## 需要直说的坏消息

live run 不是 full `ok`。它是 `degraded_ok`。

失败点：

```text
stage_record: B
expected_model: GLM-5.1
actual_model: Seed-Dogfooding-2.0
error: traecli result error
```

影响：

- Stage 1 六个成员都完成。
- Stage 2 的 GLM-5.1 reviewer 失败。
- 其余 reviewer 和 Stage 3 主席 Kimi-K2.6 成功。
- `validate` 对这个降级 run 通过，说明 artifacts 符合当前 degraded contract。

这证明“全局安装路径可运行真实模型并产出可校验 artifacts”，不证明“当前模型阵容每次都 full ok”。后者仍属于 runtime / provider 稳定性问题，不在本轮安装文档范围内。

## 剩余风险

1. 本分支尚未合入 `main`。`~/.LCT` 当前为了验证而 checkout 到本分支；合并后应切回 `main` 并 `git pull --ff-only origin main`。
2. live smoke 暴露了 GLM-5.1 Stage 2 / actual model mismatch 问题。它不是安装失败，但值得后续 runtime 线继续跟。
3. 当前 Skill 是用户级模板；外层 Agent 是否稳定触发还取决于 Agent runtime 是否加载 `/Users/bytedance/.agents/skills`。

## 下一步

- 创建 PR，把本分支合入 main。
- 合并后在 `~/.LCT` 执行：

```bash
git -C ~/.LCT checkout main
git -C ~/.LCT pull --ff-only origin main
make -C ~/.LCT install-global
```

- 如需追求 full live `ok`，另开 runtime/provider 稳定性任务，不要把它塞回本轮安装文档 PR。

