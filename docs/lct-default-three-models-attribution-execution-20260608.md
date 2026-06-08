# LCT 默认 3 成员与贡献归因口径执行文档

创建日期：2026-06-08
建议实现分支：`codex/lct-default-3-models-attribution-20260608`
适用仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`
架构事实源：`docs/lct-default-three-models-attribution-architecture-20260608.md`

## 1. 目标

本执行文档服务于下一条新 `/goal` 长线程。任务不是重新设计 LCT，而是按架构文档把默认模型体验和贡献归因口径收敛到可测试、可发布、可验证的实现。

完整交付门不是“本地测试通过”，而是：

```text
新 branch
-> 读文档和代码
-> 先补测试方案
-> TDD 红灯测试
-> 实现
-> 本地完整验证
-> 只读 subagent review
-> push GitHub
-> 创建 PR
-> 本地验证通过后合并 PR
-> v16 隔离 workspace 从最新 GitHub main 做两会话 E2E
-> review 两个 E2E 会话输出
-> 发现旧口径文档时，在 E2E 通过后更新为最新已验证情况
```

## 2. 必读文档

按顺序读：

1. `AGENTS.md`
2. `README.md`
3. `DECISIONS.md`
4. `docs/design.md`
5. `docs/lct-default-three-models-attribution-architecture-20260608.md`
6. `docs/lct-default-three-models-attribution-transfer-20260608.md`
7. `/Users/bytedance/Downloads/LCT贡献归因口径问题与改进建议.md`
8. `docs/archive/lct-experience-upgrade-implementation-spec-20260606.md`
9. `docs/archive/lct-experience-upgrade-test-plan-20260606.md`
10. `docs/archive/lct-auto-backfill-implementation-brief-20260603.md`

重点代码入口：

- `src/llm_council_for_trae/council.py`
- `src/llm_council_for_trae/model_selection.py`
- `src/llm_council_for_trae/cli.py`
- `src/llm_council_for_trae/roster.py`
- `src/llm_council_for_trae/contribution_map.py`
- `src/llm_council_for_trae/html_export.py`
- `src/llm_council_for_trae/validation.py`
- `src/llm_council_for_trae/schema_contract.py`
- `skills/llm-council-for-trae/SKILL.md`
- `profiles/subagents.json`
- `tests/test_core.py`
- `tests/test_lct_model_productization.py`
- `tests/test_global_install_skill_docs.py`

## 3. 分支与运行记录

必须新 branch、新 `/goal` 长线程执行。

建议分支名：

```text
codex/lct-default-3-models-attribution-20260608
```

启动命令：

```bash
cd "/Users/bytedance/Documents/AI Coder/COCO-llm-council"
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/lct-default-3-models-attribution-20260608
git status --short --branch
```

新会话必须维护中文 `notes.md`，记录：

- branch、起始 commit、remote、worktree 状态。
- 已读文档。
- 基线验证命令和结果。
- 测试方案补充。
- 红灯测试命令、失败测试名、失败原因。
- 实现切片、commit id、验证结果。
- subagent review 输出、修复记录。
- PR URL、merge proof、v16 E2E 证据和最终复盘。

不要用 `git reset --hard` 或清理用户未跟踪资产。任何本轮无关文件都不要混入 PR。

## 4. Phase 0：读文档、读代码、建基线

先读文档和代码，不要直接改实现。

基线命令：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果基线失败：

- 写入 `notes.md`。
- 判断是否与本轮相关。
- 不要把基线失败伪装成本轮红灯测试。

## 5. Phase 1：先补测试方案

新增或更新测试方案文档。建议路径：

```text
docs/lct-default-three-models-attribution-test-plan-20260608.md
```

测试方案至少覆盖：

### 5.1 默认 3 成员

- `DEFAULT_MEMBERS == ["DeepSeek-V4-Pro", "GPT-5.5", "openrouter-3o"]`。
- `PREFERRED_MEMBERS` 等于架构文档的新 12 模型顺序。
- `recommend_model_choice()` 最多推荐 3 个 members。
- `--default-models` 走新的默认 3 成员。
- `target_valid_members` 默认改为 3，或等价配置不再保留旧 4 目标。
- `min_valid_members` 仍为 3。

### 5.2 自选路径归一化到 3

- `normalize_user_model_selection(... target_members default)` 默认归一化到 3。
- 用户选 1 或 2 个，按 `PREFERRED_MEMBERS` 补足到 3。
- 用户选超过 3 个，按 `PREFERRED_MEMBERS` 裁剪到 3。
- TTY custom 选择和 agent-assisted `--selected-members` 使用同一个归一化函数。
- 原生 `--members` 仍不补足、不裁剪。
- provenance 记录 `normalization_target_members: 3`。

### 5.3 Auto-backfill 补到 3

- 默认首发 3 个成员，1 个失败时，Stage 1 auto-backfill 按剩余优先级补位。
- 有效 Stage 1 成员达到 3 时停止补位。
- `metadata.quorum.backfill_candidates` 来自 terminal manifest，不从默认成员或推荐结果猜。
- HTML / validate / index 显示 effective members，不把失败 primary 冒充有效成员。

### 5.4 主席顺序单一来源

- `DEFAULT_CHAIRMAN == CHAIRMAN_PRIORITY[0]`。
- `CHAIRMAN_FALLBACK_CHAIN == CHAIRMAN_PRIORITY[1:]`。
- `models --recommend` 和 Stage 3 fallback 使用同一顺序。
- 删除或防止 `model_selection.py` 与 `roster.py` 双写主席链。

### 5.5 贡献归因口径

- Stage 3 prompt 解释 `multi_member_consensus`、`synthesis`、`synthesis.members`、`editor_note`、`not_attributable` 的边界。
- `synthesis.members` 表示“主要参考成员”，不是“共识成员”。
- HTML 渲染：
  - `multi_member_consensus` 显示 `多成员共识：A, B`。
  - `synthesis + members` 显示 `主席综合整理，主要参考：A, B`。
  - `synthesis` 不带 members 显示 `来源：主席综合整理`。
  - `editor_note` 独立主席评注块。
  - `not_attributable` 显示 `来源：无法可靠归因`。
- validation 继续检查 member refs、single member 数量、consensus 成员数量。
- `synthesis.members` 引用未知成员必须 fail 或按现有 contribution semantic check 失败。

### 5.6 文档与 Skill 契约

- README / docs / Skill 不再说默认 4 成员。
- README / docs / Skill 不再说自选归一化到 4。
- README / docs / Skill 展示新的成员排序。
- README / docs / Skill 说明默认 auto-backfill 补到 3。
- README / docs / Skill 说明 `synthesis.members` 是“主要参考”，不是“共识”。

Phase 1 commit 建议：

```text
docs: add default-three-model attribution test plan
```

## 6. Phase 2：TDD 红灯测试

先写会失败的测试，不要先改实现。

建议红灯切片：

1. `test_default_roster_uses_three_member_priority_suite`
2. `test_recommendation_caps_primary_members_at_three`
3. `test_selected_members_normalizes_to_three`
4. `test_target_valid_members_default_is_3`
5. `test_chairman_fallback_chain_derived_from_single_priority`
6. `test_stage3_prompt_defines_synthesis_members_as_reference_not_consensus`
7. `test_html_renders_synthesis_members_as_chairman_reference`
8. `test_docs_describe_default_three_member_roster`

每个红灯都要记录到 `notes.md`：

```text
命令：
失败测试：
失败原因：
预期绿灯实现：
```

Phase 2 commit 建议：

```text
test: define default-three model and attribution contracts
```

## 7. Phase 3：默认成员与模型选择实现

范围：

- `DEFAULT_MEMBERS` 改为 3 个。
- `PREFERRED_MEMBERS` 改为新 12 模型顺序。
- `recommend_model_choice()` 默认 cap 从 4 改 3。
- `normalize_user_model_selection()` 默认 target 从 4 改 3。
- `CouncilConfig.target_valid_members` 或等价默认目标改 3。
- CLI TTY 文案、非交互错误文案、模型推荐说明同步。
- `profiles/subagents.json` 如继续镜像 direct 默认阵容，应同步为 3 成员；同时保留其 legacy / experimental 口径。
- benchmark 默认候选如有硬编码当前优先级，也应同步。

硬边界：

- `min_valid_members` 不变，仍为 3。
- 原生 `--members` 不归一化。
- `--default-models` 使用静态默认 3。
- 不修改 runtime provider。

验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 3 commit 建议：

```text
feat: default LCT council to three prioritized members
```

## 8. Phase 4：主席顺序单一来源

范围：

- 在 `model_selection.py` 或最合适的模型策略模块定义完整 `CHAIRMAN_PRIORITY`。
- `DEFAULT_CHAIRMAN` 和 `CHAIRMAN_FALLBACK_CHAIN` 从 `CHAIRMAN_PRIORITY` 派生。
- `roster.py` 如保留 `PRIMARY_CHAIRMAN` / `CHAIRMAN_FALLBACK_CHAIN` 导出，必须从同一事实源派生，不得复制 list。
- 更新 tests，防止未来双写漂移。

验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 4 commit 建议：

```text
refactor: derive chairman fallback from one priority chain
```

## 9. Phase 5：贡献归因口径实现

范围：

- 强化 `build_stage3_prompt()` 的 attribution 规则。
- 修 `contribution_source_html()` 或等价 HTML 渲染逻辑。
- 保持 contribution map blocks contract，不按 Markdown 段落猜来源。
- validation 保持结构和成员引用校验，不声称验证真实贡献程度。
- 增加来源说明 legend 可放到 P2；如果做，文案使用架构文档第 6 节。

最小实现要求：

```text
synthesis + members:
  主席综合整理，主要参考：A（同侪#n）, B（同侪#n）

synthesis + no members:
  来源：主席综合整理
```

不要把 `synthesis.members` 渲染成“多成员共识”。

验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Phase 5 commit 建议：

```text
feat: clarify contribution attribution semantics
```

## 10. Phase 6：文档、Skill、当前入口同步

范围：

- `README.md`
- `docs/design.md`
- `docs/traecli-subagents.md`
- `docs/lct-deployment-guide-20260601.md` 如涉及默认模型或 E2E 口径
- `skills/llm-council-for-trae/SKILL.md`
- tests 中的文档契约断言

必须同步：

- 默认 direct 阵容是 3 成员。
- 默认成员是 `DeepSeek-V4-Pro, GPT-5.5, openrouter-3o`。
- 成员优先级为新 12 模型顺序。
- 自选路径归一化到 3。
- 原生 `--members` 仍给几个跑几个。
- auto-backfill 默认补到 3。
- `synthesis.members` 是主要参考，不是共识。

注意：如果实现阶段发现 live E2E 不能通过，不要把 README 写成“已验证”。README 只能描述已经落地且验证过的行为；未验证事项要标明边界或留到后续修复。

Phase 6 commit 建议：

```text
docs: sync default roster and attribution guidance
```

## 11. 本地完整验证

所有实现完成后必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 live runtime 可用，PR 前建议补本地 smoke：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live runtime 不可用，记录 skipped 原因。不要用 fake runtime 或 fixture 说成 live run。

## 12. 只读 subagent review

本地完整验证通过后，必须启动 subagent 做只读 review。review 通过前不得 push。

Review 范围：

- `src/llm_council_for_trae/council.py`
- `src/llm_council_for_trae/model_selection.py`
- `src/llm_council_for_trae/cli.py`
- `src/llm_council_for_trae/roster.py`
- `src/llm_council_for_trae/contribution_map.py`
- `src/llm_council_for_trae/html_export.py`
- `src/llm_council_for_trae/validation.py`
- `README.md`
- `docs/`
- `skills/llm-council-for-trae/SKILL.md`
- `profiles/subagents.json`
- `tests/`

Review prompt：

```text
请只读 review 当前分支相对 origin/main 的改动，不要改文件。范围：LCT 默认 3 成员、成员优先级重排、主席顺序单一来源、auto-backfill 补到 3、贡献归因口径修正、README/docs/Skill/tests 同步。

重点检查：
1. 默认 direct 成员是否确实为 3 个：DeepSeek-V4-Pro、GPT-5.5、openrouter-3o。
2. min_valid_members 是否保持 3，target/default recommendation/selected-members 是否统一为 3。
3. 原生 --members / --chairman 是否仍保持给几个跑几个，不被归一化。
4. auto-backfill 是否只在同一个 run 内补足到 3 个有效 Stage 1 成员，不整轮重跑，不覆盖成功输出。
5. PREFERRED_MEMBERS 是否为新 12 模型顺序，Seed/Doubao/GLM hard-ban 是否未被破坏。
6. 主席顺序是否只有一个权威来源，DEFAULT_CHAIRMAN 和 fallback 是否由同一 priority 派生。
7. contribution prompt 是否清楚区分 multi_member_consensus、synthesis、synthesis.members、editor_note、not_attributable。
8. HTML 是否把 synthesis.members 渲染为“主席综合整理，主要参考”，而不是多成员共识。
9. validate 是否没有夸大能力：只校验结构和成员引用，不声称能验证真实贡献。
10. README/docs/Skill 是否没有遗留默认 4、归一化到 4、旧排序或旧综合整理口径。
11. 测试是否覆盖关键红灯路径，不只是改快照。
12. PR diff 是否混入 run artifacts、secrets、临时 E2E workspace 或无关本地资产。

输出必须按下面格式：

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

有 P1/P2 即 fail。不要因为实现看起来接近就放过文档/Skill 口径漂移。
```

P1 阻断条件：

- 默认成员数、min/target、自选归一化、auto-backfill 语义不一致。
- 原生 `--members` 兼容边界被破坏。
- 主席顺序仍双写且可能漂移。
- contribution HTML 把 `synthesis.members` 误呈现为共识。
- validate / README / Skill 声称了未验证或静态校验做不到的能力。
- 测试缺关键红灯或失败。
- PR 混入用户 artifacts / secrets / E2E 输出。

P2 阻断条件：

- 文档和代码口径不一致。
- provenance 字段不足以复盘默认/自选/backfill。
- live runtime 可用但没有合理 smoke，且没有解释。
- `GPT-5.5` 默认提升后缺少 E2E 观察计划。

P3 非阻断：

- 文案可读性优化。
- legend 是否放本轮还是后续。
- 测试命名和小型重构建议。

## 13. PR、merge、本地确认

Subagent review pass 后继续走 GitHub，不要停在本地完成。

PR 前再跑：

```bash
git status --short --branch
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

推送与 PR：

```bash
git push -u origin codex/lct-default-3-models-attribution-20260608
gh pr create --base main --head codex/lct-default-3-models-attribution-20260608 --title "Default LCT to three members and clarify attribution" --body-file <prepared-pr-body.md>
gh pr checks --watch
```

PR body 至少包含：

- 目标和背景。
- 默认 3 成员和新成员优先级。
- auto-backfill 补到 3 的语义。
- 主席顺序单一来源。
- 贡献归因口径变化。
- README/docs/Skill 同步范围。
- 测试命令与结果。
- subagent review 结论。
- live runtime smoke 是否执行。
- 风险：`GPT-5.5` 默认第 2 位需要 post-merge E2E 观察。

合并条件：

- 本地完整验证通过。
- subagent review 无 P1/P2。
- CI 通过；如果无 CI，明确记录 `CI not configured`，并按本地验证 + review 证据推进。
- PR diff 无无关资产。

合并后本地确认：

```bash
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD
git log -1 --oneline
git status --short --branch
```

## 14. v16 隔离 workspace E2E

PR merge 后必须在隔离 workspace 执行：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v16
```

E2E 必须拆成两个独立会话。

### 会话 1：同步最新 main

只做 workspace 准备和状态记录，不跑 E2E。

必须记录：

- remote URL。
- branch。
- local HEAD。
- GitHub `origin/main` HEAD。
- `git status --short --branch`。
- 是否确认 local HEAD 等于最新 GitHub main。
- wrapper / global install 是否需要刷新；如刷新，记录命令和结果。

建议产物：

```text
v16-session1-main-sync-20260608.md
```

如果 workspace 脏，停止，不要 reset，先向用户说明。

### 会话 2：执行 live E2E

基于会话 1 workspace 执行真实 E2E。

必须：

- 先读 `v16-session1-main-sync-20260608.md`。
- 维护中文 `notes.md`。
- 不在源码 repo 根目录直接把 LCT 源码当问题上下文跑。
- 确认 `llm-council-for-trae` 入口来自最新 main 或明确记录 install refresh。
- 记录 `llm-council-for-trae models --recommend --json`。
- 执行 `--default-models` live run。
- 执行 `validate <run_id> --json`。
- 产出 final / index / html / validate 证据。
- 记录 `GPT-5.5` 是否作为默认成员实际执行、是否成功、是否触发 auto-backfill。
- 检查 HTML 中 contribution source 是否出现“主席综合整理，主要参考”或等价新口径；若本次模型未产出 `synthesis.members`，至少记录 sidecar 中实际 attribution kinds。

最小命令：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input _lct_question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

`_lct_question.md` 必须是 council-facing 问题，不要写入 notes.md、PR、Git、validate 等外层执行要求。

## 15. E2E 输出 review

E2E 完成后，还要 review 两个会话的全部输出，重点看 `notes.md`。假设用户已经忘了上下文，从零说明：

1. E2E 是否真的基于最新 GitHub main。
2. live run 是否真的执行。
3. validate 是否通过，verdict 是什么。
4. final / index / html 是否来自同一个 run。
5. 默认成员是否为 3。
6. `GPT-5.5` 是否实际参与，结果如何。
7. auto-backfill 是否触发，是否补到 3。
8. 贡献归因 HTML 是否体现新口径。
9. 发现了哪些：
   - 产品问题。
   - 文档/Skill 问题。
   - 执行 Agent 问题。
   - runtime 环境问题。
10. 哪些问题必须修，哪些只是后续观察。

建议输出：

```text
docs/lct-default-three-models-attribution-v16-e2e-review-20260608.md
docs/lct-default-three-models-attribution-v16-e2e-review-20260608.html
```

如果 GitHub 中的 README / docs / Skill 仍写旧情况，且以上本地验证、subagent review、PR merge、v16 E2E 和 E2E review 都通过，必须补文档更新 PR 或在同一 release 后续提交中修正。前提未满足时，不要把文档写成已经验证。
