# LCT 默认 3 成员与贡献归因口径实现交接

创建日期：2026-06-08
目标执行方式：新会话、新分支、`/goal` 长线程执行
建议分支名：`codex/lct-default-3-models-attribution-20260608`
当前仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`

## 1. 这份交接是干什么的

新会话要实现一轮 LCT 体验可信度迭代：默认成员从 4 收敛到 3，成员优先级重排，自选路径同步归一化到 3，auto-backfill 继续补到 3，主席顺序变成单一事实源，并修正 contribution map 中 `synthesis.members` 的归因口径和 HTML 展示。

本轮真正完成的定义是：

```text
新分支实现
-> 先补测试方案
-> TDD 红灯测试
-> 实现
-> 本地完整验证
-> 只读 subagent review
-> push GitHub
-> 创建 PR
-> 本地验证通过后合并 PR
-> v16 隔离 workspace 从最新 main 执行两会话 E2E
-> review 两个 E2E 会话全部输出
-> E2E 通过后确认 README/docs/Skill 没有旧口径
```

不要把本任务降级成“本地测试过了”。PR merge 和 fresh-main E2E 是交付定义的一部分。

## 2. 关键文档

本交接不重复所有设计细节。事实源在：

- `docs/lct-default-three-models-attribution-architecture-20260608.md`
- `docs/lct-default-three-models-attribution-execution-20260608.md`
- `/Users/bytedance/Downloads/LCT贡献归因口径问题与改进建议.md`
- `AGENTS.md`
- `README.md`
- `DECISIONS.md`
- `docs/design.md`

历史参考：

- `docs/archive/lct-experience-upgrade-implementation-spec-20260606.md`
- `docs/archive/lct-experience-upgrade-execution-plan-20260606.md`
- `docs/archive/lct-experience-upgrade-implementation-handoff-20260606.md`
- `docs/archive/lct-auto-backfill-implementation-brief-20260603.md`

如果历史文档和本交接冲突，以 2026-06-08 的架构文档和执行文档为准。

## 3. 启动要求

必须新开 `/goal` 长线程执行，必须新建 branch。不要在当前 `main` 上直接实现。

推荐启动提示：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/COCO-llm-council 新建分支 codex/lct-default-3-models-attribution-20260608，按 docs/lct-default-three-models-attribution-transfer-20260608.md、docs/lct-default-three-models-attribution-architecture-20260608.md 和 docs/lct-default-three-models-attribution-execution-20260608.md 实现 LCT 默认 3 成员与贡献归因口径迭代。必须先读 AGENTS.md、README.md、DECISIONS.md、docs/design.md、/Users/bytedance/Downloads/LCT贡献归因口径问题与改进建议.md 和相关代码；先补测试方案，再按 TDD 写红灯测试，然后实现。默认成员改为 DeepSeek-V4-Pro、GPT-5.5、openrouter-3o；min_valid_members 保持 3；自选路径归一化到 3；允许 auto-backfill 补到 3；主席顺序从一个权威 priority 派生；HTML 必须把 synthesis.members 显示为主席综合整理的主要参考而不是多成员共识。维护中文 notes.md。完成后跑 PYTHONPATH=src python3 -m compileall src、make test、git diff --check；本地绿后启动只读 subagent review，review 无 P1/P2 后 push GitHub、创建 PR、合并 PR。merge 后在 /Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16 分两个独立会话做 fresh-main E2E，并 review 两个会话全部输出，重点看 notes.md。"
```

建议使用技能：

- `tdd`：先红灯测试，再实现。
- `subagent-lead`：本地验证后做只读 review；不要让 subagent 直接改文件。
- `verification-before-completion`：任何完成/通过声明前必须有最新验证证据。
- `handoff`：如果任务中断，更新 repo 内交接，不要只留聊天摘要。

## 4. 当前已拍板事项

按下面结论执行，不要回到旧口径：

1. 默认成员并行数改为 3。
2. `min_valid_members` 保持 3。
3. 自选模型路径也归一化到 3。
4. 原生 `--members` / `--chairman` 仍给几个跑几个，不补足、不裁剪。
5. 默认 run 允许 auto-backfill 在同一个 run 内补到 3 个有效 Stage 1 成员。
6. 成员优先级改为：

```text
DeepSeek-V4-Pro
GPT-5.5
openrouter-3o
GPT-5.4
openrouter-2o
Kimi-K2.6
MiniMax-M2.7
GPT-5.2
openrouter-1o
DeepSeek-V4-Flash
Gemini-3.1-Pro-Preview
Qwen3.6-Plus
```

7. 主席顺序不变，但只保留一个权威顺序：

```text
DeepSeek-V4-Pro
Kimi-K2.6
DeepSeek-V4-Flash
GPT-5.2
openrouter-1
```

8. `DEFAULT_CHAIRMAN` 和 `CHAIRMAN_FALLBACK_CHAIN` 应从该顺序派生。
9. `synthesis.members` 是“主要参考成员”，不是“共识成员”。
10. HTML 不得把 `synthesis.members` 渲染成多成员共识。

## 5. 必须修改的代码和测试区域

优先检查：

- `src/llm_council_for_trae/council.py`
- `src/llm_council_for_trae/model_selection.py`
- `src/llm_council_for_trae/cli.py`
- `src/llm_council_for_trae/roster.py`
- `src/llm_council_for_trae/contribution_map.py`
- `src/llm_council_for_trae/html_export.py`
- `src/llm_council_for_trae/validation.py`
- `tests/test_core.py`
- `tests/test_lct_model_productization.py`
- `tests/test_global_install_skill_docs.py`
- `skills/llm-council-for-trae/SKILL.md`
- `profiles/subagents.json`
- `README.md`
- `docs/design.md`
- `docs/traecli-subagents.md`

## 6. 执行顺序

必须按下面顺序推进。

### 6.1 新分支与基线

```bash
cd "/Users/bytedance/Documents/AI Coder/COCO-llm-council"
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/lct-default-3-models-attribution-20260608
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

创建或更新中文 `notes.md`。如果当前 worktree 出现未跟踪文件，先分类，不要删除。

### 6.2 先补测试方案

新增：

```text
docs/lct-default-three-models-attribution-test-plan-20260608.md
```

测试方案必须覆盖执行文档第 5 节列出的六组测试矩阵。

### 6.3 TDD 红灯测试

先写会失败的测试。红灯必须覆盖：

- 默认成员从 4 改 3。
- 新成员优先级。
- recommendation cap 改 3。
- selected-members 归一化到 3。
- `target_valid_members` 或等价默认目标改 3。
- `min_valid_members` 保持 3。
- auto-backfill 补到 3。
- 主席 fallback 从同一 priority 派生。
- Stage 3 prompt 明确 `synthesis.members` 是主要参考，不是共识。
- HTML 对 `synthesis.members` 的新文案。
- README / docs / Skill 不再遗留默认 4 或旧归因口径。

将红灯命令、失败测试名、失败原因写入 `notes.md`。

### 6.4 实现

按执行文档 Phase 3 到 Phase 6 做小步实现。建议 commit：

1. `docs: add default-three model attribution test plan`
2. `test: define default-three model and attribution contracts`
3. `feat: default LCT council to three prioritized members`
4. `refactor: derive chairman fallback from one priority chain`
5. `feat: clarify contribution attribution semantics`
6. `docs: sync default roster and attribution guidance`

不要把 run artifacts、HTML 报告、临时 E2E workspace 内容混入 PR。

### 6.5 本地完整验证

必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 live runtime 可用，PR 前建议补：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live runtime 不可用，记录 skipped 证据，不得用 fake runtime 冒充 live。

## 7. 只读 subagent review

本地完整验证通过后，必须启动 subagent 做只读 review。review 通过前不得 push。

Review prompt 使用执行文档第 12 节。不要缩短到“看看有没有问题”。必须要求：

- 只读。
- 对比当前分支相对 `origin/main`。
- 输出 P1/P2/P3。
- 有 P1/P2 即 fail。
- 明确检查默认 3、归一化到 3、auto-backfill 补到 3、主席单一顺序、贡献归因 HTML、README/docs/Skill 同步、测试覆盖、无 artifacts。

输出格式：

```text
结论：pass | fail

P1 阻断：
- None 或 findings

P2 阻断：
- None 或 findings

P3 非阻断：
- None 或 findings

测试与验证观察：
- ...

开放问题：
- None 或问题
```

P1/P2 未清零不得 push/merge，除非用户明确重新裁决。

## 8. PR、合并和本地确认

Subagent review 通过后继续走 GitHub。

PR 前再跑：

```bash
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

推送和开 PR：

```bash
git push -u origin codex/lct-default-3-models-attribution-20260608
gh pr create --base main --head codex/lct-default-3-models-attribution-20260608 --title "Default LCT to three members and clarify attribution" --body-file <prepared-pr-body.md>
gh pr checks --watch
```

如果 GitHub 没有 CI，不要写 CI 通过；记录 `CI not configured`，并按本地验证 + subagent review 证据推进。

合并后本地确认：

```bash
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD
git log -1 --oneline
git status --short --branch
```

## 9. PR 合并后的 v16 E2E

必须在隔离 workspace 执行：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16
```

E2E 拆成两个独立会话。

### 会话 1：拉取最新 main

只做 workspace 准备和状态记录，不跑 E2E。

必须记录：

- remote URL。
- branch。
- local HEAD。
- GitHub `origin/main` HEAD。
- `git status --short --branch`。
- local HEAD 是否等于最新 GitHub main。
- wrapper / global install 是否需要刷新。

建议产物：

```text
v16-session1-main-sync-20260608.md
```

如果 workspace 脏，停止，不要 reset。

### 会话 2：执行 E2E

基于会话 1 workspace 执行真实 E2E。

必须：

- 先读 `v16-session1-main-sync-20260608.md`。
- 维护中文 `notes.md`。
- 确认 `llm-council-for-trae` 入口来自最新 main 或记录 install refresh。
- 记录 `models --recommend --json`。
- 执行 `run --input _lct_question.md --default-models --json`。
- 执行 `validate <run_id> --json`。
- 产出 final / index / html / validate 证据。
- 记录默认成员是否为 3。
- 记录 `GPT-5.5` 是否真实执行、是否成功。
- 记录 auto-backfill 是否触发、是否补到 3。
- 检查 HTML 贡献归因新口径；如果没有出现 `synthesis.members`，记录 sidecar 实际 attribution kinds。

`_lct_question.md` 只写 council-facing 问题，不写 notes.md、Git、PR、validate 等外层执行要求。

## 10. E2E 输出 review

E2E 完成后，还要 review 两个会话的全部输出，重点看 `notes.md`。假设用户已经忘了上下文，从零说明：

1. E2E 是否真的基于最新 GitHub main。
2. live run 是否真的执行。
3. validate 是否通过，verdict 是什么。
4. final / index / html 是否来自同一个 run。
5. 默认成员是否为 3。
6. `GPT-5.5` 是否实际参与，结果如何。
7. auto-backfill 是否触发，是否补到 3。
8. 贡献归因 HTML 是否体现新口径。
9. 发现了哪些产品问题。
10. 发现了哪些文档/Skill 问题。
11. 发现了哪些执行 Agent 问题。
12. 发现了哪些 runtime 环境问题。
13. 哪些问题必须修，哪些只是后续观察。

建议产物：

```text
docs/lct-default-three-models-attribution-v16-e2e-review-20260608.md
docs/lct-default-three-models-attribution-v16-e2e-review-20260608.html
```

## 11. README / GitHub 文档更新门槛

如果 GitHub 中的说明文档写了更新前的情况，例如默认 4 成员、归一化到 4、旧成员排序、旧 `synthesis` 口径，必须更新为最新情况。

但前提是：

```text
本地完整验证通过
-> subagent review 通过
-> PR 已合并
-> v16 fresh-main E2E 完成
-> E2E 输出 review 通过
```

如果 E2E 发现产品问题、文档/Skill 问题、执行 Agent 问题或 runtime 环境问题，先如实分级。必须修的问题不能靠 README 文案遮住。

## 12. 最终汇报格式

最终汇报必须结论先行，并列出实际执行过的命令和结果：

- branch、commit、PR URL、merge commit。
- 本地验证命令与 pass/fail。
- subagent review 结论。
- v16 会话 1 证据。
- v16 会话 2 run_id、validate status、verdict、HTML path。
- E2E review 结论。
- 必修问题和后续观察。

不要只说“已经完成”。没有证据的成功声明无效。
