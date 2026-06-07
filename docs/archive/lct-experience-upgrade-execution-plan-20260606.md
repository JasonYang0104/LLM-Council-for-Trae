# LCT 体验升级执行文档

日期：2026-06-06
建议实现分支：`codex/lct-experience-upgrade-20260606`
适用仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`

## 1. 目标

本执行文档服务于下一条新 `/goal` 长线程。任务不是重新设计 LCT，而是按已经收敛的架构文档实现 LCT 体验升级，并把交付闭环推进到 GitHub PR、merge、post-merge isolated E2E 和 E2E 结果复盘。

本轮升级包含四个产品点：

1. HTML 顶部摘要卡片从 quorum 黑话改为「成员模型」。
2. 输入改写规则在 Skill/Agent 层更精确，默认 raw，结构化必须有明确触发。
3. 用户自选模型产品化：自选体验路径归一化到 4；原生 `--members` 仍保持给几个跑几个。
4. 主席贡献说明：默认关闭、feature flag 灰度；启用后用 sidecar/块模型做逐段来源与分歧展示。

执行标准不是“本地测试通过”。完整交付门是：

```text
实现 -> 本地完整验证 -> 只读 subagent review -> push -> PR -> CI -> merge -> v16 fresh-main E2E -> E2E 输出审查
```

## 2. 必读文档

按顺序读。不要跳过架构裁决段，因为其中有已废弃口径的 precedence 说明。

1. `AGENTS.md`
   - 项目硬边界、默认中文、runtime 与模型策略、quorum、HTML 结构、验证命令。
2. `DECISIONS.md`
   - ADR-0001 是本轮长期决策事实源。
   - 重点：`--members` 原生行为不变；自选归一化走独立 opt-in 通道。
3. `docs/lct-experience-upgrade-implementation-spec-20260606.md`
   - 主规格。重点读阶段一/二/三、A1-A7、第二轮 B1-B3 和裁决。
4. `docs/lct-experience-upgrade-architect-brief-20260606.md`
   - 架构背景、边界和方案权衡。
5. `docs/lct-experience-upgrade-mockup-20260606.html`
   - 主席贡献说明的视觉基准，只作为视觉/信息架构参考，不作为实现代码复制源。
6. `docs/design.md`
   - CLI、artifact store、HTML export、AskUserQuestion 不进 core 的既有设计。
7. `README.md`
   - 用户路径、validate、Skill、index 产物要求。
8. 相关历史设计：
   - `docs/lct-input-boundary-docs-design-20260604.md`
   - `docs/lct-input-boundary-docs-test-plan-20260604.md`
   - `docs/lct-auto-backfill-quorum-design-20260603.md`
   - `docs/lct-search-delivery-and-index-design-20260604.md`
   - `docs/lct-global-install-skill-design-20260601.md`

重点代码入口：

- `src/llm_council_for_trae/html_export.py`
- `src/llm_council_for_trae/model_selection.py`
- `src/llm_council_for_trae/cli.py`
- `src/llm_council_for_trae/council.py`
- `src/llm_council_for_trae/store.py`
- `src/llm_council_for_trae/schema_contract.py`
- `src/llm_council_for_trae/validation.py`
- `skills/llm-council-for-trae/SKILL.md`
- `tests/test_core.py`
- `tests/test_lct_model_productization.py`
- `tests/test_global_install_skill_docs.py`

## 3. 分支与长线程要求

必须在新 branch、新 `/goal` 长线程里执行。不要直接在当前文档分支上实现。

建议分支名：

```text
codex/lct-experience-upgrade-20260606
```

启动前命令：

```bash
cd "/Users/bytedance/Documents/AI Coder/COCO-llm-council"
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/lct-experience-upgrade-20260606
git status --short --branch
```

如果本地有未提交文档或用户资产，不要 `git reset --hard`，先分类：

- 与本轮执行文档/架构文档相关的，应在新分支中保留并提交。
- 与本轮无关的本地资产，不要删除，不要混入 PR。

新会话必须维护中文 `notes.md`，记录：

- 分支、起始 commit、已读文档。
- 测试方案补充结论。
- TDD 红灯、绿灯、重构证据。
- 每个阶段 commit id。
- subagent review 结论和修复记录。
- PR、CI、merge、v16 E2E 和最终复盘证据。

## 4. 实施顺序

### Phase 0：读文档、读代码、建基线

目标：确认当前 main、分支、代码入口和测试现状。

必须执行：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果基线失败：

- 记录到 `notes.md`。
- 先判断是否与本轮相关。
- 不要把基线失败包装成新实现导致。

### Phase 1：先补测试方案

目标：把架构文档转成可执行测试矩阵，不直接改实现。

新增或更新：

```text
docs/lct-experience-upgrade-test-plan-20260606.md
```

测试方案至少覆盖：

1. HTML summary card：
   - 有 `metadata.quorum.effective_stage1_members` 时展示「成员模型」。
   - 顶部不出现 `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：`。
   - `metadata.quorum` 缺失时 legacy fallback 到 `config.members`。
   - `metadata.quorum` 存在但 effective list 缺失/为空时，不把失败配置成员冒充为有效成员。
   - quorum/backfill/search 证据仍在 metadata/evidence 中可见。

2. 输入改写 Skill 契约：
   - raw-only 触发语：`不要改写`、`按原文`、`只用原始输入`、`评估 LCT 对原问题的理解`。
   - structured 触发语：`先想我真正需要什么`、`站在架构师角度评估`、`fact pack`、`最新资料`、`来源`。
   - 负向用例：`详细分析`、`深入一点`、`给完整方案` 不得单凭字面触发结构化改写。
   - operator envelope：`notes.md`、validate、Git/PR、测试职责不得进入 `_lct_question.md`。

3. 自选模型产品化：
   - `--members` 原生路径行为不变。
   - 独立 opt-in 参数路径，例如 `--selected-members` / `--selected-chairman`，触发归一化。
   - TTY 自定义选择和 agent-assisted 自选走同一个 `normalize_user_model_selection(...)`。
   - 自选 <4 按 `PREFERRED_MEMBERS` 补足到 4。
   - 自选 >4 按 `PREFERRED_MEMBERS` 裁剪到 4，未排名可用模型排后。
   - 非法模型名阻断或追问，不 silent fallback。
   - chairman 单独校验，不自动塞进 members，除非用户明确要求。
   - manifest provenance 至少区分 `cli_raw_members`、`cli_tty_custom`、`agent_assisted`、`default_models`、`profile`。

4. 主席贡献说明：
   - 默认关闭时 legacy `final.md` 渲染不变，不要求 sidecar。
   - 开启后必须写出 sidecar，例如 `stage3/contribution_map.json`。
   - HTML 从 sidecar/块序列确定性渲染，不按自然段事后猜来源。
   - validate 检查成员引用合法、共识成员数 >=2、类型合法。
   - legacy run 缺 sidecar 不失败；开启但 sidecar 缺失/非法才失败。
   - 排名只展示为同侪锚点，不等于贡献，不输出百分比。

Phase 1 commit 建议：

```text
docs: add LCT experience upgrade test plan
```

### Phase 2：TDD 红灯测试

目标：先写失败测试，证明当前实现缺口存在。

要求：

- 每个产品点至少先有一个红灯测试。
- 红灯测试要能在当前实现下失败，不能只写永远通过的文档断言。
- 把红灯输出摘录到 `notes.md`。

建议测试落点：

- `tests/test_core.py`
- `tests/test_lct_model_productization.py`
- `tests/test_global_install_skill_docs.py`
- 如 Stage 3 sidecar 需要专门 fixture，可新增 `tests/test_stage3_contribution_map.py` 或等价文件。

Phase 2 commit 建议：

```text
test: define LCT experience upgrade contracts
```

### Phase 3：阶段一实现，低风险改动

范围：

- `html_export.py` summary card。
- `skills/llm-council-for-trae/SKILL.md` 输入改写矩阵。
- 自选模型触发边界文档。
- 文档契约测试。

不要在这一阶段改 CLI 行为。

必须验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 3 commit 建议：

```text
feat: simplify LCT report summary and input policy docs
```

### Phase 4：阶段二实现，自选模型 CLI 内核

范围：

- 新增独立 opt-in 参数，默认建议：
  - `--selected-members`
  - `--selected-chairman`
- 新增 `normalize_user_model_selection(...)` 或等价专属归一化入口。
- 扩展 `CouncilConfig` 或等价持久通道，记录 `model_selection_provenance`。
- manifest / validation additive 校验。
- Skill 文档说明 Agent-assisted 路径如何调用独立参数。

硬边界：

- 原生 `--members` / `--chairman` 行为零变化。
- `--default-models`、`profile`、`subagent` 不归一化。
- TTY 自定义选择也必须走同一个归一化函数，不能另写一套。
- 不加 fuzzy/alias。
- 不把 `AskUserQuestionTool` 引入 core。

必须验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 4 commit 建议：

```text
feat: add explicit selected-model normalization
```

### Phase 5：阶段三实现，主席贡献说明灰度

范围：

- Feature flag / config / CLI 参数，默认关闭。
- `build_stage3_prompt` 演进，喂全 Stage 1、Stage 2、aggregate rankings。
- sidecar contract，例如 `stage3/contribution_map.json`。
- `schema_contract.py` / `validation.py` additive 校验。
- `html_export.py` 渲染来源条、分歧块、编者注。
- `DECISIONS.md` 补实现层决策：feature flag、sidecar 形态、启用标记。

硬边界：

- HTML export 不调用模型，不重算归因。
- 不按 Markdown 自然段猜来源。
- 开启但 sidecar 缺失/非法时 validate 失败。
- legacy run 缺 sidecar 不失败。
- 无法归因用综合整理/无法归因，不硬配单一模型。
- 不输出贡献百分比。

必须验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 5 commit 建议：

```text
feat: add gated chairman contribution map
```

### Phase 6：文档、README、brief

范围：

- README 与 Skill 对新 CLI 参数、input policy、summary card、contribution map 的口径同步。
- 如有全局 Skill 生效要求，明确运行安装同步并验证；否则只声明仓库 Skill 已更新。
- 生成 PM director 风格简报：
  - `docs/lct-experience-upgrade-implementation-brief-20260606.md`
  - `docs/lct-experience-upgrade-implementation-brief-20260606.html`

Phase 6 commit 建议：

```text
docs: summarize LCT experience upgrade implementation
```

## 5. 完整本地验证

所有阶段实现后，必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果触及 live runtime / 模型选择 / Skill path，且 live runtime 可用，再跑：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live runtime 不可用：

- 明确写 `skipped`。
- 记录阻断证据，例如 `traecli models --json` 失败、空列表或超时。
- 不得把 fixture、fake runtime 或单元测试冒充 live E2E。

## 6. 只读 subagent review 门

本地完整验证通过后，必须启动 subagent 做只读 review。review 通过前不得 push PR。

### 6.1 Review 范围

必须覆盖：

- 代码改动：
  - `html_export.py`
  - `model_selection.py`
  - `cli.py`
  - `council.py`
  - `store.py`
  - `schema_contract.py`
  - `validation.py`
- 文档与 Skill：
  - `README.md`
  - `DECISIONS.md`
  - `skills/llm-council-for-trae/SKILL.md`
  - 新增 test plan / brief / handoff。
- 测试：
  - 所有新增或修改测试文件。

禁止 subagent 改文件。只读 review 输出 findings。

### 6.2 Review 检查项

检查项：

1. 全局红线是否被破坏：
   - 非交互 `--default-models` 不变。
   - 原生 `--members` 不变。
   - runtime override 不变。
   - validate legacy 兼容。
   - HTML export 不调用模型。
   - operator envelope 不进 `_lct_question.md`。
2. HTML card：
   - 顶部无 quorum 黑话。
   - 有效成员事实源正确。
   - quorum/backfill/search 证据未丢。
3. 输入改写：
   - raw/structured/fact pack/operator envelope 边界清楚。
   - 负向用例不误触发。
4. 自选模型：
   - 独立 opt-in 通道清楚。
   - 原生 `--members` 行为未变。
   - TTY 和 agent-assisted 共用归一化函数。
   - provenance 足够复盘。
   - invalid model fail-closed。
5. 主席贡献说明：
   - 默认关闭。
   - sidecar/块模型不会错位。
   - validate 只做合法性校验，不声称验证真实贡献。
   - legacy run 不因缺 sidecar 失败。
6. 测试：
   - 有红灯证据。
   - 新增行为有单元/契约测试。
   - 没有删除或弱化旧测试。
7. 发布安全：
   - 无 raw run artifacts、secrets、大文件、无关本地输入资产混入。
   - 没有改写用户 run artifacts。

### 6.3 Review 输出格式

Subagent 必须按下面格式输出：

```text
结论：pass | fail

P1 阻断：
- None
或
- [P1] 文件:行 - 问题、影响、建议修复

P2 阻断：
- None
或
- [P2] 文件:行 - 问题、影响、建议修复

P3 非阻断：
- None
或
- [P3] 文件:行 - 问题、影响、建议修复

测试与验证观察：
- 已检查的测试证据
- 仍需主 Agent 复核的地方

开放问题：
- None
或列出需要用户/架构师裁决的问题
```

### 6.4 P1/P2 阻断条件

P1 必须修复并重跑 review：

- 破坏 `--default-models`、原生 `--members`、profile/subagent、runtime override 任一兼容路径。
- 新增 validate 让 legacy run 错误失败。
- HTML export 调模型或重算归因。
- 贡献 sidecar 可引用不存在成员、共识少于 2 仍通过。
- 用户输入 operator envelope 进入 council input 的文档或实现口径。
- 测试失败、编译失败、`git diff --check` 失败。
- PR 会包含 run artifacts、secrets、大文件或无关本地资产。

P2 默认也阻断 merge，除非用户明确接受：

- provenance 不足以复盘用户选择、裁剪、最终 config。
- 阶段三 feature flag / enabled marker 不清晰。
- Skill/README/DECISIONS 口径互相矛盾。
- 新功能缺少对应回归测试。
- v16 E2E 计划无法证明来自最新 main。

P3 可记录为后续观察，不阻断 merge。

## 7. GitHub PR 与 merge

Subagent review 通过后继续发布，不要停在本地完成。

建议流程：

```bash
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
git push -u origin codex/lct-experience-upgrade-20260606
gh pr create --base main --head codex/lct-experience-upgrade-20260606 --title "Improve LCT experience transparency" --body-file <prepared-pr-body.md>
gh pr checks --watch
```

PR body 必须包含：

- 目标与范围。
- 关键行为变化。
- 兼容性边界。
- 测试命令与结果。
- Subagent review 结论。
- live runtime 是否执行、如未执行则原因。

合并条件：

- 本地完整验证通过。
- Subagent review 无 P1/P2。
- PR CI 通过。
- PR diff 不包含无关资产。

如果 `gh pr checks` 显示没有配置 CI，不要写“CI 通过”。记录为 `CI: not configured / no checks reported`，并向用户确认是否允许按本地验证 + review 合并。

合并后记录：

```bash
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD
git log -1 --oneline
```

## 8. 合并后 v16 隔离 E2E

PR 合并后，必须在隔离 workspace 做 fresh-main E2E：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16
```

E2E 必须拆成两个独立会话。

### 8.1 会话 1：同步最新 GitHub main

职责：只准备 workspace，不执行 E2E。

目标：

- workspace 基于最新 GitHub `main`。
- 记录 branch、commit、remote、worktree 状态。
- 确认没有本地未提交改动污染。

建议启动提示：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16 执行 LCT 体验升级 post-merge E2E 会话 1：从 GitHub 最新 main 准备隔离 workspace，只做 clone/pull/status 记录，不运行 E2E。必须记录 branch、commit、remote、worktree 状态，并说明是否等于最新 origin/main。"
```

建议命令：

```bash
mkdir -p "/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16"
cd "/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16"
# 如果目录不是 git repo，clone GitHub repo 到这里；如果已经是 repo，先检查脏状态。
git remote -v
git fetch origin
git switch main
git pull --ff-only
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git log -1 --oneline
git status --short --branch
```

会话 1 产物：

- `v16-session1-main-sync.md`，至少写：
  - workspace path。
  - remote URL。
  - branch。
  - local HEAD。
  - origin/main HEAD。
  - `git status --short --branch` 输出。
  - 是否确认基于最新 main。

如果 workspace 脏，停止并报告，不要 reset。

### 8.2 会话 2：基于会话 1 workspace 执行 E2E

职责：执行真实 E2E，维护中文 `notes.md`，产出 final/index/html/validate 证据。

建议启动提示：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16 基于会话 1 已同步的最新 main 执行 LCT 体验升级 post-merge E2E。维护中文 notes.md，必须运行真实 live LCT run（除非 runtime 明确不可用并记录证据），执行 validate，产出 final/index/html/validate 证据。不要把 fixture 或 fake runtime 冒充 live。"
```

关键要求：

- 先读 `v16-session1-main-sync.md`，确认 HEAD 与 origin/main 一致。
- 不要在 LCT 源码 repo 根目录直接作为问题 workspace 跑 LCT；在 v16 下创建干净问题子目录，例如：

```text
e2e-workspace-20260606/
```

- 如果使用全局 `llm-council-for-trae` wrapper，必须证明 wrapper 对应最新 main 代码。可接受路径：
  - 同步 `~/.LCT` 到同一 main commit 后 `make -C ~/.LCT install-global`；
  - 或从 v16 checkout 运行 `make install-global LCT_DIR="/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16"` 并记录该选择。
- 运行前记录：
  - `command -v llm-council-for-trae`
  - `llm-council-for-trae --version`
  - `traecli --version`
  - `traecli models --json`
  - `llm-council-for-trae models --recommend --json`

最小 live E2E：

```bash
cd "/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16/e2e-workspace-20260606"
printf '%s\n' '请用两段话解释：LCT 体验升级后，用户为什么更容易信任多模型结果？' '' 'Report topic: LCT 体验升级可信度验证' > _lct_question.md
llm-council-for-trae run --input _lct_question.md --default-models --json
llm-council-for-trae validate <run_id> --json | tee <run_id>-validate.json
```

如果自选模型功能已合并，且当前 runtime 模型列表至少有 4 个可用模型，再追加一个 selected-members live smoke。命令参数按最终实现为准，示例：

```bash
llm-council-for-trae run --input _lct_question.md --selected-members "<model1>,<model2>" --json
llm-council-for-trae validate <selected_run_id> --json | tee <selected_run_id>-validate.json
```

如果 selected-members live smoke 未执行，必须在 `notes.md` 写清原因，例如当前 runtime 不可用、可用模型不足、或该功能未在本 PR 范围内落地。

会话 2 必须产出：

- 中文 `notes.md`。
- `<run_id>-final.md`：从 `stage3/final.md` 提取/整理。
- `<run_id>-index.md`：包含 run status、validate status、validate verdict、HTML path、Input mode、runtime 状态、成员模型、quorum、search、backfill、chairman fallback、selected model provenance。
- `<run_id>-validate.json`。
- HTML 路径：`.llm-council-for-trae/runs/<run_id>/html/index.html`。

validate 交付门：

- 首选：`verdict=complete_ok_final` 且 `usable_final=true`。
- 如果是 `usable_degraded_final`，必须明确标注 degraded，不得包装成普通成功。
- `invalid_artifacts`、`failed_no_final`、`in_progress` 都不能算 E2E 通过。

### 8.3 E2E 输出 review

E2E 完成后，必须 review 会话 1 和会话 2 的全部输出，重点看 `notes.md`。

Review 输入：

- `v16-session1-main-sync.md`
- 会话 2 的 `notes.md`
- `_lct_question.md`
- `<run_id>-final.md`
- `<run_id>-index.md`
- `<run_id>-validate.json`
- HTML artifact
- run manifest：`.llm-council-for-trae/runs/<run_id>/manifest.json`
- 如有 selected-members run，也一起审。

Review 输出必须从零说明：

1. E2E 是否真的基于最新 GitHub main。
2. live run 是否真的执行。
3. validate 是否通过，verdict 是什么。
4. HTML 是否存在且来自同一 run。
5. 新功能是否在证据中体现：
   - summary card 是否是成员模型。
   - selected model provenance 是否可见（如执行了自选 E2E）。
   - legacy 兼容是否未被破坏。
6. 发现的问题分类：
   - 产品问题。
   - 文档/Skill 问题。
   - 执行 Agent 问题。
   - runtime 环境问题。
7. 每个问题判断：
   - 必须修。
   - 可后续观察。
   - 非问题/符合预期。

建议产出：

```text
docs/lct-experience-upgrade-v16-e2e-review-20260606.md
docs/lct-experience-upgrade-v16-e2e-review-20260606.html
```

如果 E2E review 发现 P1/P2，必须回到实现分支修复并重新走 PR/merge/E2E，不得只在最终汇报里淡化。

## 9. 非目标

- 不重写 runtime provider。
- 不引入 OpenRouter API。
- 不恢复旧 Web UI。
- 不把 HTML export 和 chairman synthesis 混成一步。
- 不把 `AskUserQuestionTool` 做成 core 依赖。
- 不清理用户已有 `.llm-council-for-trae/` run artifacts。
- 不把 fake runtime 或 fixture 测试说成 live E2E。
