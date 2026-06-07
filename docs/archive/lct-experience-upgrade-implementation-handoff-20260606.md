# LCT 体验升级实现交接

创建日期：2026-06-06
目标执行方式：新会话、新分支、`/goal` 长线程执行
建议分支名：`codex/lct-experience-upgrade-20260606`
当前仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`

## 1. 这份交接是干什么的

新会话要按已收敛的架构文档实现 LCT 体验升级，并完成完整发布闭环。不要把本任务降级成“本地实现 + 测试通过”。本轮真正完成的定义是：

```text
新分支实现
-> TDD 本地验证
-> 只读 subagent review
-> push GitHub
-> 创建 PR
-> CI 通过
-> merge PR
-> v16 隔离 workspace 从最新 main 执行 E2E
-> review 两个 E2E 会话输出并给出问题分级
```

本交接不重复架构推导。架构事实源在：

- `DECISIONS.md`
- `docs/lct-experience-upgrade-implementation-spec-20260606.md`
- `docs/lct-experience-upgrade-execution-plan-20260606.md`
- `docs/lct-experience-upgrade-architect-brief-20260606.md`
- `docs/lct-experience-upgrade-mockup-20260606.html`

## 2. 启动要求

必须新开 `/goal` 长线程执行，必须在新 branch 上做，不要继续当前文档分支。

推荐启动提示：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/COCO-llm-council 新建分支 codex/lct-experience-upgrade-20260606，按 docs/lct-experience-upgrade-implementation-handoff-20260606.md 和 docs/lct-experience-upgrade-execution-plan-20260606.md 实现 LCT 体验升级。必须先读 DECISIONS.md、docs/lct-experience-upgrade-implementation-spec-20260606.md、AGENTS.md、README.md 和相关代码；先补 docs/lct-experience-upgrade-test-plan-20260606.md，再用 TDD 写红灯测试，然后实现。每阶段 commit，维护中文 notes.md。完成后跑 PYTHONPATH=src python3 -m compileall src、make test、git diff --check；本地绿后启动只读 subagent review，review 无 P1/P2 后推 GitHub、开 PR、等 CI 通过并 merge。merge 后在 /Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16 分两个独立会话做 fresh-main E2E，并 review 两个会话全部输出。"
```

建议使用技能：

- `tdd`：先红灯测试，再实现。
- `subagent-lead`：本地验证后做只读 review；不要让 subagent 直接改文件。
- `verification-before-completion`：任何完成/通过声明前必须有最新验证证据。
- `handoff`：如果任务中断，更新或续写 repo 内交接，不要只留聊天摘要。

## 3. 必须先读

阅读顺序：

1. `AGENTS.md`
2. `DECISIONS.md`
3. `docs/lct-experience-upgrade-implementation-spec-20260606.md`
4. `docs/lct-experience-upgrade-execution-plan-20260606.md`
5. `docs/lct-experience-upgrade-architect-brief-20260606.md`
6. `docs/lct-experience-upgrade-mockup-20260606.html`
7. `README.md`
8. `docs/design.md`
9. `docs/lct-input-boundary-docs-design-20260604.md`
10. `docs/lct-auto-backfill-quorum-design-20260603.md`
11. `docs/lct-search-delivery-and-index-design-20260604.md`
12. `docs/lct-global-install-skill-design-20260601.md`

代码入口：

- `src/llm_council_for_trae/html_export.py`
- `src/llm_council_for_trae/model_selection.py`
- `src/llm_council_for_trae/cli.py`
- `src/llm_council_for_trae/council.py`
- `src/llm_council_for_trae/store.py`
- `src/llm_council_for_trae/schema_contract.py`
- `src/llm_council_for_trae/validation.py`
- `skills/llm-council-for-trae/SKILL.md`
- `tests/`

## 4. 当前架构裁决摘要

执行时按这些结论，不要回到旧口径：

1. HTML 顶部卡片显示「成员模型」，取 `metadata.quorum.effective_stage1_members`；只有 `metadata.quorum` 整体缺失时才 legacy fallback 到 `config.members`。
2. 输入改写仍在 Skill/Agent 层，不下沉 CLI。默认 raw；结构化必须有明确触发；operator envelope 不进 `_lct_question.md`。
3. `AskUserQuestionTool` 只属于 outer Agent/Skill，可选且必须有文本 fallback；core 不依赖它。
4. 原生 `--members` 永远不归一化，给几个跑几个。
5. 自选体验路径使用独立 opt-in 通道，建议参数名 `--selected-members` / `--selected-chairman`；该通道归一化到 4 并写 provenance。
6. TTY 自定义选择和 agent-assisted 自选必须走同一个 `normalize_user_model_selection(...)`。
7. 主席贡献说明默认关闭；开启后必须使用 sidecar/块模型，不按 Markdown 自然段事后猜来源。
8. validate 新增校验必须 additive + legacy 兼容。

## 5. 执行顺序

必须按下面顺序推进。

### 5.1 新分支与基线

```bash
cd "/Users/bytedance/Documents/AI Coder/COCO-llm-council"
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/lct-experience-upgrade-20260606
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

创建 `notes.md`，中文记录。

### 5.2 先补测试方案

先写：

```text
docs/lct-experience-upgrade-test-plan-20260606.md
```

测试方案必须覆盖执行文档第 4 节和第 5 节列出的 HTML、Skill、自选模型、主席贡献说明、legacy 兼容与 provenance。

### 5.3 TDD 红灯测试

先写会失败的测试。不要直接改实现。

红灯测试必须覆盖：

- HTML summary card 的新文案和 fallback 收紧。
- Skill 输入改写触发矩阵和负向用例。
- `--members` 原生路径不变。
- `--selected-members` / `--selected-chairman` 或等价自选通道归一化。
- selected model provenance。
- Stage 3 feature flag 默认关闭和 enabled sidecar 校验。

将红灯命令、失败测试名、失败原因写入 `notes.md`。

### 5.4 实现

按执行文档 `Phase 3` 到 `Phase 6` 实现。每阶段 commit。

不要把三个阶段混成一个巨型无边界 diff。如果确实必须同一 PR，至少拆清晰 commits：

1. `docs/test plan`
2. `test contracts`
3. `html/input docs`
4. `selected model normalization`
5. `stage3 contribution map`
6. `brief/docs`

### 5.5 本地完整验证

必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如触及 live runtime / 模型选择 / Skill path，且 live runtime 可用，补：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

live runtime 不可用时必须记录 skipped 证据，不得用 fixture 冒充 live。

## 6. 只读 subagent review

本地完整验证通过后，必须启动 subagent 做只读 review。review 通过前不得 push。

Review prompt 建议：

```text
请只读 review 当前分支相对 origin/main 的改动，不要改文件。范围：LCT 体验升级实现，重点检查 html_export/model_selection/cli/council/store/schema_contract/validation、README、DECISIONS、skills/llm-council-for-trae/SKILL.md、测试和新增文档。请按 P1/P2/P3 输出 findings，必须给文件/行号、影响和建议修复。重点看：--default-models 和原生 --members 是否兼容；selected-members 自选通道是否独立且 provenance 可复盘；HTML 顶部是否移除 quorum 黑话但未删除证据；输入改写规则是否默认 raw 且 operator envelope 不进 council input；Stage 3 contribution map 是否默认关闭、legacy 兼容、HTML 不调模型、不事后猜来源；测试是否覆盖红灯缺口；PR 是否会混入 run artifacts/secrets/无关本地资产。结论必须是 pass 或 fail；有 P1/P2 即 fail。
```

输出格式必须是：

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

P1/P2 阻断条件见 `docs/lct-experience-upgrade-execution-plan-20260606.md` 第 6 节。P1/P2 未清零不得 push/merge，除非用户明确重新裁决。

## 7. PR、CI、merge

Subagent review 通过后继续走 GitHub，不要停在本地。

流程：

```bash
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
git push -u origin codex/lct-experience-upgrade-20260606
gh pr create --base main --head codex/lct-experience-upgrade-20260606 --title "Improve LCT experience transparency" --body-file <prepared-pr-body.md>
gh pr checks --watch
```

PR body 至少包含：

- 变更目标。
- 分阶段实现摘要。
- 兼容性边界。
- 测试命令与结果。
- Subagent review 结论。
- live runtime 是否执行。
- 风险和后续观察。

合并条件：

- 本地完整验证通过。
- Subagent review 无 P1/P2。
- CI 通过。
- PR diff 无无关资产。

如果没有 CI，不能写 CI 通过。记录 `CI not configured`，请用户确认是否按本地验证 + review 合并。

合并后本地确认：

```bash
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD
git log -1 --oneline
git status --short --branch
```

## 8. PR 合并后的 v16 E2E

必须在隔离 workspace 执行：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16
```

E2E 拆成两个独立会话。

### 会话 1：同步最新 main

只做 workspace 准备和状态记录，不跑 E2E。

必须记录：

- remote URL。
- branch。
- local HEAD。
- origin/main HEAD。
- `git status --short --branch`。
- 是否确认 local HEAD 等于最新 GitHub main。

产物建议：

```text
v16-session1-main-sync.md
```

如果 workspace 脏，停止，不要 reset。

### 会话 2：执行 E2E

基于会话 1 workspace 执行真实 E2E。

必须：

- 先读 `v16-session1-main-sync.md`。
- 维护中文 `notes.md`。
- 在干净问题子目录执行，不在源码 repo 根目录直接跑问题。
- 证明 `llm-council-for-trae` wrapper 指向最新 main 代码。
- 记录 runtime 状态。
- 执行 live run，除非 runtime 明确不可用。
- 执行 validate。
- 产出 final/index/html/validate 证据。

最小 live E2E 命令见 `docs/lct-experience-upgrade-execution-plan-20260606.md` 第 8.2 节。

如果自选模型功能已落地且当前模型列表允许，必须追加 selected-members live smoke；如果未执行，必须写清 skipped 原因。

## 9. E2E 输出 review

E2E 完成后，还要 review 两个会话的全部输出，重点看 `notes.md`。不要只看 validate JSON。

必须从零说明：

1. E2E 是否真的基于最新 GitHub main。
2. live run 是否真的执行。
3. validate 是否通过，verdict 是什么。
4. HTML 是否存在且来自同一 run。
5. 发现了哪些：
   - 产品问题。
   - 文档/Skill 问题。
   - 执行 Agent 问题。
   - runtime 环境问题。
6. 哪些问题必须修，哪些只是后续观察。

建议输出：

```text
docs/lct-experience-upgrade-v16-e2e-review-20260606.md
docs/lct-experience-upgrade-v16-e2e-review-20260606.html
```

如果 E2E review 发现 P1/P2，回到实现分支修复，重新 PR/merge/E2E。不要用总结淡化。

## 10. 非目标与禁区

- 不重写 runtime provider。
- 不引入 OpenRouter API。
- 不恢复旧 Web UI。
- 不把 HTML export 和 chairman synthesis 混成一步。
- 不把 `AskUserQuestionTool` 做成 core 依赖。
- 不删除或改写用户已有 run artifacts。
- 不把 fake runtime / fixture 说成 live E2E。

## 11. 最终交付格式

最终回答用户时，必须列出：

- PR URL、merge commit。
- 本地验证命令与结果。
- Subagent review 结论。
- CI 结果。
- v16 会话 1 main-sync 证据。
- v16 会话 2 E2E run_id、validate verdict、HTML 路径。
- E2E 输出 review 的问题分级和必须修/观察结论。

不要只说“完成”。
