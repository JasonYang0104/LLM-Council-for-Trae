# LCT Stage 2 Reviewer-Only Backfill Handoff

日期：2026-06-03
目标分支：`codex/lct-auto-backfill-plan-20260603`
当前仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`

## 这份交接是干什么的

新会话要继续在当前分支上做一个聚焦修正：把 Stage 2 故障补位从“先生成候补模型 D 的 Stage 1 回答，再让 D 做 reviewer”改成“如果 Stage 1 已经满足 quorum，D 只作为 Stage 2 reviewer，评审既有有效 Stage 1 answers，不新增候选答案”。

这是对 auto-backfill 语义的收紧，不是推翻上一轮实现。上一轮已经完成 Stage 1 auto-backfill、low quorum 可见性、runtime cleanup、validate / HTML / Skill 对齐；这轮只修 Stage 2 reviewer backfill 的产品语义和测试契约。

## 用户要求的执行契约

继续沿用上一份 handoff 的执行规范：

```text
长线程用"/goal"实现：和subagent("subagent lead")一起搞TDD驱动("tdd")，先沉淀好文档（设计方案、测试方案）再动手。你的职责是让测试都通过。

实现过程中：
1. 执行时每个阶段都commit
2. 维护一个运行中的 notes.md 文件（中文），记录你不得不做出的、规范中未包含的决定，你不得不更改的内容，你不得不做出的权衡，或者任何其他我应该知道的事情。

全部完成后，在假设我很聪明但是失忆不记得你在干啥为啥要干的前提下，生成面向PM director风格的简报md/html。
```

推荐新会话启动提示：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/COCO-llm-council 的 branch codex/lct-auto-backfill-plan-20260603 上，按 docs/lct-stage2-reviewer-only-backfill-handoff-20260603.md，用 subagent-lead + tdd 实现 Stage 2 reviewer-only backfill：当 Stage 1 已满足 quorum 而 Stage 2 reviewer 失败时，候补模型只评审既有有效 Stage 1 answers，不生成新的候选答案。每阶段 commit，维护中文 notes.md，最终更新 PM director brief md/html，并让 PYTHONPATH=src python3 -m compileall src、make test、git diff --check main..HEAD 通过。"
```

必须使用的技能：

- `subagent-lead`：至少让一个 subagent 复核 Stage 2 语义和测试覆盖。
- `tdd`：先改测试，让当前“D 先生成 Stage 1 回答”的行为红掉，再改实现。
- `verification-before-completion`：最终声明完成前跑完整验证。

## 当前现状

当前实现确实是“Stage 2 失败后先补 Stage 1 answer”：

- `src/llm_council_for_trae/council.py` 第 796-827 行附近：
  - 当 `0 < len(valid_stage2) < stage2_reviewer_target` 时，调用 `backfill_stage1_responses(...)`。
  - 这会把候补模型追加进 `stage1_results`，生成新的 `Response D` / `Response E`。
  - 随后把这些 `new_reviewers` 传给 `stage2_collect_rankings(...)`。
- `tests/test_auto_backfill_quorum.py` 第 320 行附近的 `test_run_full_council_stage2_reviewer_failure_backfills_new_reviewer` 锁定了旧行为：
  - M4 先跑 Stage 1。
  - M4 的 ranking 包含 `Response D`。
  - 断言 calls 里包含 `("stage1", "M4", "D")` 和 `("stage2", "M4", "D")`。

这就是这轮要改掉的地方。

上一轮 review 发现的 branch-level whitespace 问题已经由执行会话修复并提交：

- `1d4fd8a docs: fix auto-backfill branch whitespace`
- `git diff --check main..HEAD` 当前通过。

所以本轮不用再修这项，只需要在 Phase 0 复核验证口径。

## 新目标语义

区分两个概念：

- `member backfill`：补 Stage 1 成员答案。只有 Stage 1 有效成员数不足 quorum 时才做。候补模型会生成自己的 answer，进入候选答案池。
- `reviewer backfill`：补 Stage 2 评审者。只解决 reviewer 数不足，不新增候选答案。

新规则：

1. Stage 1 出问题，导致有效成员不足 `min_valid_members`：
   - 继续使用上一轮已实现的 `backfill_stage1_responses()`。
   - 候补模型生成 Stage 1 answer，并进入有效成员集合。

2. Stage 1 已经满足 quorum，但 Stage 2 reviewer 失败：
   - 不再调用 `backfill_stage1_responses()`。
   - 从 backfill candidates 里挑 D。
   - D 只运行 Stage 2 reviewer prompt，评审进入 Stage 2 时已经存在的 `valid_stage1` answers，例如 A/B/C。
   - D 不写入 `stages.stage1`。
   - D 不产生 `Response D`。
   - D 的 Stage 2 review label 应是独立 reviewer label，建议使用不和 response label 混淆的文件 label，例如 `R4` 或 `reviewer-E`。如果为了兼容沿用单字母 label，也必须在 record 中明确 `reviewer_source=stage2_reviewer_backfill`，并保证 `label_to_model` 仍只映射 review subjects。

3. Stage 2 出问题，同时 Stage 1 本来就没有达到 quorum：
   - 先回到 Stage 1 member backfill，把候选答案补够。
   - 再进入 Stage 2。
   - 不要把 reviewer-only backfill 用来掩盖 Stage 1 quorum 不足。

## 为什么要这样改

旧 MVP 能交付，但语义不够干净：

- D 是因为 Stage 2 reviewer 不足才被拉上来，却被迫生成了一个新的候选答案。
- A/C 这些旧 reviewer 已经评完 A/B/C，不会重新评 D。
- D 可能评 A/B/C/D，于是评审集合不对称。
- 这会让用户误以为形成了完整 peer-review matrix，但实际上不是。

新方案更准确：

- Stage 2 的问题是 reviewer 不够，不是候选答案不够。
- D 只评 A/B/C，所有成功 reviewer 的 review subjects 一致。
- 少跑一次 Stage 1，降低耗时和 token。
- provenance 更清楚：D 是 `stage2_reviewer_backfill`，不是 `stage1_backfill`。

## 必读文档

先读：

- `docs/lct-auto-backfill-quorum-design-20260603.md`
- `docs/lct-auto-backfill-implementation-handoff-20260603.md`
- `docs/lct-auto-backfill-implementation-brief-20260603.md`
- `notes.md`

重点代码：

- `src/llm_council_for_trae/council.py`
  - `stage2_collect_rankings`
  - `backfill_stage1_responses`
  - `run_full_council`
  - `stage1_quorum_metadata`
- `src/llm_council_for_trae/model_selection.py`
  - `build_backfill_candidates`
- `src/llm_council_for_trae/validation.py`
  - `quorum_semantic_checks`
- `src/llm_council_for_trae/html_export.py`
  - summary card / warning display

重点测试：

- `tests/test_auto_backfill_quorum.py`
- `tests/test_core.py`
- `tests/test_runtime_hardening.py`
- `tests/test_global_install_skill_docs.py`

## 实施阶段

### Phase 0：复核验证口径和当前分支

上一轮 review 发现一个非功能问题：执行摘要说 `git diff --check` 通过，但 clean worktree 下这条命令检查的是空 diff。真实应该跑：

```bash
git diff --check main..HEAD
```

这项已经由 `1d4fd8a docs: fix auto-backfill branch whitespace` 修掉。新会话只需要确认：

- 当前 HEAD 包含 `1d4fd8a`。
- `git diff --check main..HEAD` 通过。
- `notes.md` 继续记录本轮 reviewer-only backfill 的新决策，不要把已完成的 whitespace 修复当作新实现阶段。

如果复核发现 whitespace 又失败，再单独修复并提交；否则不要为这项再创建提交。

### Phase 1：TDD 红测，锁定 reviewer-only 语义

先改或新增测试，让当前实现失败。

必须覆盖：

1. Stage 1 已有 A/B/C 三个有效 answers，Stage 2 中 B reviewer 失败。
2. 候补 D 被拉起来只做 Stage 2 reviewer。
3. calls 中不应出现 `("stage1", "D", ...)`。
4. calls 中应出现 D 的 Stage 2 reviewer call。
5. `manifest["stages"]["stage1"]` 仍只有 A/B/C，不出现 D。
6. `stage2/label_to_model.json` 仍只映射 `Response A/B/C`。
7. D 的 ranking 只包含 `Response A/B/C`，不包含 `Response D`。
8. `metadata.stage2_reviewers.backfill_reviewers` 记录 D。
9. D 的 Stage 2 record 标记 `reviewer_source=stage2_reviewer_backfill` 或等价字段。
10. `metadata.quorum.effective_stage1_members` 不因为 reviewer-only D 增加。

测试命名建议：

- 把旧的 `test_run_full_council_stage2_reviewer_failure_backfills_new_reviewer` 改成：
  - `test_run_full_council_stage2_reviewer_failure_backfills_reviewer_only_when_stage1_quorum_met`

提交建议：`test: define stage2 reviewer-only backfill contract`

### Phase 2：实现 reviewer-only backfill

建议新增 helper，不要继续复用 `backfill_stage1_responses()`：

```python
async def backfill_stage2_reviewers(
    user_query: str,
    review_subjects: list[dict[str, Any]],
    existing_stage1_results: list[dict[str, Any]],
    failed_stage2_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: TraeCliProvider,
    store: ArtifactStore,
    runtime_models: list[dict[str, Any]],
    needed_reviewers: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    ...
```

核心要求：

- 使用 `build_backfill_candidates(...)` 生成候补池，但 `attempted_models` 要包含：
  - primary members
  - 已经作为 Stage 1 backfill 尝试过的模型
  - 已经参与 Stage 2 的 reviewer
  - 已失败的 Stage 2 reviewer
- reviewer-only 候补不写 `stage1/*.response.md`。
- reviewer-only 候补可以写 `stage2/<reviewer_label>.review.md/json/meta.json`。
- `stage2_collect_rankings(...)` 需要支持 reviewer record 不是 Stage 1 record 的情况：
  - `reviewer_records` 可以来自 Stage 1，也可以来自 reviewer-only candidates。
  - `review_subjects` 始终是固定的有效 Stage 1 answers。
  - reviewer-only record 没有 `response`，不能被当成 review subject。

提交建议：`feat: backfill stage2 reviewers without adding stage1 answers`

### Phase 3：validate / manifest / HTML 语义跟上

当前 validate 有一条语义检查：eligible Stage 2 reviewer 必须有有效 Stage 1 answer。这个规则要改，否则 reviewer-only backfill 会被误杀。

新的 validate 规则：

- 如果 `reviewer_source` 是 `stage1_ok` 或 `stage1_backfill`：
  - reviewer model 必须在有效 Stage 1 models 中。
- 如果 `reviewer_source` 是 `stage2_reviewer_backfill`：
  - reviewer model 不需要在 Stage 1 models 中。
  - 但必须不出现在 `label_to_model` 的 subject 映射中。
  - 它的 parsed ranking 必须只包含当前 review subjects。

manifest / metadata 建议：

```json
"stage2_reviewers": {
  "reviewer_target": 3,
  "review_subject_count": 3,
  "review_subject_models": ["A", "B", "C"],
  "valid_reviewers": ["A", "C", "D"],
  "failed_reviewers": ["B"],
  "reviewer_backfill_attempted": ["D"],
  "member_backfill_attempted": [],
  "reviewer_only_backfill": true
}
```

HTML / final / index 展示建议：

- 区分 `Stage 1 backfill members` 和 `Stage 2 reviewer backfill`。
- 如果只发生 reviewer-only backfill，不要让用户误以为 D 也是候选答案之一。

提交建议：`feat: validate and display reviewer-only backfill provenance`

### Phase 4：文档和 Skill 口径更新

需要更新：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`
- `docs/lct-auto-backfill-implementation-brief-20260603.md`
- `notes.md`

文档口径：

- Stage 1 auto-backfill 是 member backfill。
- Stage 2 auto-backfill 优先是 reviewer-only backfill。
- 只有 Stage 1 quorum 不足时，才补 Stage 1 answer。
- 汇报字段要区分：
  - `stage1_backfill_members`
  - `stage2_reviewer_backfill`
  - `review_subject_count`
  - `reviewer_count`

提交建议：`docs: clarify member and reviewer backfill semantics`

### Phase 5：最终验证和 brief 更新

必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check main..HEAD
```

如果 `traecli` 当前可用，可选再跑 live smoke；但如果 live smoke 没触发 Stage 2 reviewer-only backfill，不要把它当成该异常路径证据。异常路径证据应来自 fake provider / deterministic tests。

最终更新或新增 brief：

- 可更新 `docs/lct-auto-backfill-implementation-brief-20260603.md/html`。
- 如果不想改旧 brief，也可以新增：
  - `docs/lct-stage2-reviewer-only-backfill-brief-20260603.md`
  - `docs/lct-stage2-reviewer-only-backfill-brief-20260603.html`

brief 必须用 PM director 口径解释：

- 为什么旧 MVP 不够准。
- 新语义如何区分 member backfill 和 reviewer backfill。
- 哪些测试证明 reviewer-only 不会新增候选答案。
- 剩余边界：Phase 7 stale terminalization 和 forbidden tool fail-fast 如果仍没做，要继续写清楚。

提交建议：`docs: record reviewer-only backfill verification`

## 完成定义

这轮完成必须同时满足：

- 当前 Stage 2 reviewer failure 场景不再生成 D 的 Stage 1 answer。
- D 只评审进入 Stage 2 时的有效 Stage 1 answers。
- Stage 1 quorum metadata 不把 reviewer-only D 算成 effective Stage 1 member。
- validate 接受 reviewer-only backfill，但拒绝 reviewer-only D 混入 `label_to_model` subject 映射。
- HTML / index / brief 能区分 member backfill 和 reviewer backfill。
- `notes.md` 记录这次语义修正、测试红绿过程和权衡。
- 每个阶段都有 commit。
- 最终三条验证命令通过：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check main..HEAD
```
