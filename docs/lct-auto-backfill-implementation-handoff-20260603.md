# LCT Auto-Backfill Implementation Handoff

日期：2026-06-03
目标分支：`codex/lct-auto-backfill-plan-20260603`
当前仓库：`/Users/bytedance/Documents/AI Coder/COCO-llm-council`

## 这份交接是干什么的

新会话要在当前分支上实现 LCT 的 auto-backfill / quorum / runtime cleanup hardening。核心目标不是多跑几次模型，而是把“自动交付”和“结果质量底线”同时做成可审计的产品能力：

- 默认仍然追求至少 3 个有效成员模型参与结果形成。
- 某些成员模型启动后不可用、超时、工具污染或结果无效时，同一个 run 内保留已成功 Stage 1 成员，只补跑候补成员。
- 如果最终不得不低于 3 个有效成员交付，不能静默伪装成健康结果，必须在 manifest、index、final、HTML 面向用户展示为 low quorum / 2-member degraded result。
- 主席模型失败时可以自动使用主席备选链，不需要停下来问用户，但必须记录清楚。
- 启动后卡住或超时的模型进程必须明确终止、等待回收并留下可验证元数据，不能给后续 run 留历史债。

主规格文档已经写好：`docs/lct-auto-backfill-quorum-design-20260603.md`。本交接文档只负责告诉新会话如何接手实现、如何分阶段提交、如何验证。

## 当前分支状态

进入新会话后的第一步：

```bash
cd "/Users/bytedance/Documents/AI Coder/COCO-llm-council"
git status --short --branch
```

预期应该在：

```text
## codex/lct-auto-backfill-plan-20260603
```

当前分支基于已合并的 title hardening PR 结果，基础提交是 `74810b96b99a9483fa330b929cf406549c4f00cb`。不要切回 `main` 开始做，除非用户明确要求。

当前已有的方案文件：

- `docs/lct-auto-backfill-quorum-design-20260603.md`
- `docs/lct-auto-backfill-implementation-handoff-20260603.md`

这两个文档可以在第一阶段一起提交，作为实现前的规格沉淀。

## 用户要求的执行契约

新会话必须按下面这段执行，不要把它降级成普通聊天式开发：

```text
长线程用"/goal"实现：和subagent("subagent lead")一起搞TDD驱动("tdd")，先沉淀好文档（设计方案、测试方案）再动手。你的职责是让测试都通过。

实现过程中：
1. 执行时每个阶段都commit
2. 维护一个运行中的 notes.md 文件（中文），记录你不得不做出的、规范中未包含的决定，你不得不更改的内容，你不得不做出的权衡，或者任何其他我应该知道的事情。

全部完成后，在假设我很聪明但是失忆不记得你在干啥为啥要干的前提下，生成面向PM director风格的简报md/html。
```

推荐用下面的启动提示开启新会话：

```text
/goal "在 /Users/bytedance/Documents/AI Coder/COCO-llm-council 的 branch codex/lct-auto-backfill-plan-20260603 上，按 docs/lct-auto-backfill-quorum-design-20260603.md 和 docs/lct-auto-backfill-implementation-handoff-20260603.md，用 subagent-lead + tdd 实现 LCT auto-backfill/quorum/runtime-cleanup hardening。每阶段 commit，维护中文 notes.md，最终生成 PM director brief md/html，并让 PYTHONPATH=src python3 -m compileall src、make test、git diff --check 通过。"
```

必须使用的技能：

- `subagent-lead`：用于拆分 runtime cleanup、quorum/backfill、HTML/validation、Skill docs 等复核任务。
- `tdd`：先写测试，红绿重构，不要先改实现再补测试。
- `verification-before-completion`：最终声称完成前必须跑验证命令并确认输出。
- 需要生成最终 HTML 简报时，可使用 `doc-kami-parchment` 或项目已有 HTML brief 风格。

## 必读顺序

1. `AGENTS.md`
   - 先读项目定位、硬边界、runtime 与模型选择、验证命令、quorum 策略、`traecli pipe hang` 约束。
   - 关键约束：不要重引入 Web UI；不要接 OpenRouter；不要把 HTML export 和 chairman synthesis 混成一步；`traecli` preflight 仍受 `os.system` 约束，MVP 不要重写这条路径。

2. `docs/lct-auto-backfill-quorum-design-20260603.md`
   - 这是本轮主规格。
   - 重点读：
     - `背景`
     - `Zoom-Out 模块图`
     - `MVP：同 Run Auto-Backfill`
     - `Manifest / Provenance`
     - `用户面展示`
     - `Runtime Cleanup 方案`
     - `Skill 更新`
     - `Best-Practice 测试方案`
     - `Red-Green 实施顺序`

3. `README.md`
   - 当前 README 仍描述“默认失败后由外层 Skill 用推荐阵容整 run 重跑”的旧流程。
   - 本轮实现后要改成：CLI 内同 run auto-backfill 是主路径；外层 Skill 不再把完整推荐重跑当首选补救。

4. Runtime hardening 背景文档：
   - `docs/runtime-hardening-handoff-20260601.md`
   - `docs/runtime-hardening-design-20260601.md`
   - `docs/runtime-capability-hardening-design-20260601.md`
   - 这些文档解释了为什么不能随便改 `traecli` 调用方式，尤其是 pipe hang 和 cleanup 边界。

5. 最近 title/validation 相关文档：
   - `docs/lct-validate-title-hardening-handoff-20260603.md`
   - `docs/lct-validate-title-contract-design-20260603.md`
   - `docs/lct-validate-title-contract-test-plan-20260603.md`
   - 本轮改 manifest / validate / HTML 时，要避免破坏刚合并的标题 contract。

6. 代码入口：
   - `src/llm_council_for_trae/council.py`
     - `stage1_collect_responses`
     - `stage2_collect_rankings`
     - `stage3_synthesize_final`
     - `run_full_council`
     - `classify_stage1_status`
   - `src/llm_council_for_trae/provider.py`
     - `query_model`
     - `_query_model_once`
     - `terminate_process_tree`
   - `src/llm_council_for_trae/model_selection.py`
   - `src/llm_council_for_trae/roster.py`
   - `src/llm_council_for_trae/validation.py`
   - `src/llm_council_for_trae/html_export.py`
   - `src/llm_council_for_trae/cli.py`

7. Skill 文档：
   - `skills/llm-council-for-trae/SKILL.md`
   - `.trae/skills/llm-council-for-trae/SKILL.md`
   - 这两处都要同步改，避免用户级 Skill 和项目内 Trae Skill 口径分裂。

## 实现阶段

每个阶段都要 commit。每个 commit 前至少跑与该阶段相关的测试；最终阶段再跑完整验证。

### Phase 0：规格落地与基线

目标：确认当前分支、创建运行中的 `notes.md`、提交设计/测试/交接文档。

动作：

- 阅读本交接和主规格文档。
- 创建 repo 根目录 `notes.md`，中文维护。
- 运行基线：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```
- 如已有测试失败，先记录到 `notes.md`，不要把失败归因成新实现导致。
- 提交：`docs: add auto-backfill implementation plan`

### Phase 1：Runtime cleanup 测试与最小实现

目标：保证“模型启动后卡住/超时/被取消”会明确终止进程并等待回收，尤其是在 Stage 1 / Stage 2 进入 backfill 前。

先写测试：

- provider timeout 后调用 `terminate_process_tree`。
- stage-level cancellation 后会 `cancel_and_drain`，不会留下 pending task。
- backfill 启动前，上一轮失败/取消任务已完成 cleanup。
- fake provider 能记录 `termination_reason`、`final_returncode` 或等价元数据。

实现建议：

- 在 `council.py` 增加小而明确的 `cancel_and_drain(tasks)` helper。
- `stage1_collect_responses` 和 `stage2_collect_rankings` 的任务收集逻辑用 `try/finally` 做收口。
- `provider.py` 里已有 `terminate_process_tree`，优先补元数据和测试，不要大改调用方式。
- 不要在 MVP 做全局扫进程，也不要 kill 非本 run 拥有的进程。

提交：`fix: drain cancelled model tasks before backfill`

### Phase 2：Backfill candidate pool

目标：候补成员模型选择可预测、可审计、不会把已尝试/禁用/主席专用模型重复拿来用。

先写测试：

- 显式 `--backfill-members` 优先。
- 无显式候补时，从当前 `models --recommend --json` 或可用模型清单生成候选。
- 排除 primary members、已尝试失败成员、主席专用模型、禁用模型。
- 同 vendor fallback 优先；然后按推荐顺序补齐。
- 候补列表写入 manifest provenance。

实现建议：

- 复用 `model_selection.py` / `roster.py` 已有过滤逻辑。
- 新增配置字段：

```python
backfill_members: list[str] = []
stage1_auto_backfill: bool = True
stage2_auto_backfill: bool = True
allow_low_quorum: bool = True
low_quorum_floor: int = 2
```

- CLI 增加：
  - `--backfill-members`
  - `--no-auto-backfill`
  - `--low-quorum-floor`

提交：`feat: add deterministic backfill candidate selection`

### Phase 3：Stage 1 auto-backfill

目标：同一个 run 内保留已成功 Stage 1 输出，只补跑候补成员，直到达到 `min_valid_members` 或耗尽候补。

先写测试：

- 3 个默认成员里 2 个成功、1 个失败时，只补跑 1 个候补，最终达到 3。
- 已成功成员的 response label、artifact、meta 不被覆盖。
- 新候补使用追加 label，例如 `Response E`，不复用失败成员 label。
- 如果最终只有 2 个有效成员，结果可以继续但必须标记 low quorum。
- 如果低于 `low_quorum_floor`，run 必须失败，不要导出伪可用结果。
- tool contaminated / timeout / malformed output 都算无效成员，不计 quorum。

实现建议：

- `stage1_collect_responses` 不要一次性只接受固定 `config.members`。
- 建立 `Stage1Attempt` 或等价结构，区分：
  - original roster
  - backfill candidate
  - retry attempt
  - validity
  - label
  - provenance
- `classify_stage1_status` 需要从“原始成员数”转向“有效成员数 + floor + chairman exception”的判断。

提交：`feat: backfill failed stage1 members in-run`

### Phase 4：Stage 2 reviewer eligibility 与 backfill

目标：评估阶段默认只让有输出的模型参与评估；如果评估阶段成员故障，优先沿用 Stage 1 backfill 补上。

先写测试：

- `review_subjects` 只包含有效 Stage 1 成员。
- `reviewers` 默认也是有效 Stage 1 成员。
- Stage 2 reviewer 故障时，候补模型必须先补齐 Stage 1 answer，再作为 reviewer。
- Stage 2 低于目标但 >= 2 时，继续 degraded，并显著标注。
- Stage 2 低于 2 时，按现有 fallback/fail 语义处理，不能伪装健康。

实现建议：

- 拆开 `review_subjects` 和 `reviewers`。
- reviewer target 默认是 `min(len(review_subjects), min_valid_members)`。
- 如果 backfill reviewer 需要新 Stage 1 输出，统一复用 Phase 3 的 Stage 1 backfill helper，不要复制逻辑。

提交：`feat: backfill stage2 reviewers from effective members`

### Phase 5：Manifest / validation / HTML / final 可见性

目标：把所有降级和替换从“内部细节”变成可复盘证据。

先写测试：

- manifest 包含：
  - original roster
  - backfill candidates
  - backfill attempted
  - effective Stage 1 members
  - low quorum used
  - normal quorum met
  - Stage 2 reviewer count
  - chairman fallback attempted / used
  - termination metadata
- `validate <run_id> --json` 能区分：
  - normal usable final
  - degraded usable final
  - low quorum usable final
  - failed / terminal failed
- HTML first viewport 或 summary strip 明确展示：
  - 有效成员数，例如 `2 / 3`
  - low quorum warning
  - effective member models
  - backfill used
  - chairman fallback used
- final/index 中同样展示 low quorum，不要只埋在 manifest。

实现建议：

- 优先添加字段，不要为了“清爽”删除旧字段，避免破坏兼容。
- HTML export 仍只渲染 artifacts，不要把 chairman synthesis 混进 HTML export。

提交：`feat: surface backfill and low-quorum provenance`

### Phase 6：Skill / README / prompt contract 更新

目标：外层 Agent 的执行方式要和 CLI 新能力一致，避免继续鼓励整 run 重跑。

先写测试或文档 contract 检查：

- Skill 文档不再说“默认失败后首选推荐阵容完整重跑”。
- Skill 要求记录：
  - effective members
  - low quorum
  - backfill used
  - chairman fallback
  - failed models / timeout
- Prompt 层要求把 fact pack 内容直接嵌入 `_lct_question.md`，不要让模型自己“读取某文件”。
- Prompt 层明确禁止成员模型自己创建 notes 文件；`notes.md` 是外层 Agent 的运行记录。

需要同步更新：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`

提交：`docs: align skill workflow with auto-backfill`

### Phase 7：Stale run 与 forbidden tool fail-fast

目标：补足 P1 防线，但不要拖垮核心 auto-backfill。

建议拆成两个小提交：

1. Stale run 收口：
   - 新增 `llm-council-for-trae terminalize <run_id> --reason interrupted`，或先做 validate 的 read-only stale hint。
   - 不建议让 validate 默认修改 manifest，除非测试非常明确。

2. Forbidden tool fail-fast：
   - 一旦发现 forbidden tool call，尽快终止该 attempt，标记 `tool_contaminated`。
   - 短期仍承认这是 LCT 层检测，不假装已经解决 `traecli --disallowed-tool` 不生效的问题。

提交：

- `feat: add stale run terminalization support`
- `fix: fail fast on forbidden model tool calls`

如果时间不够，Phase 7 可以作为后续 PR，但必须在 `notes.md` 和最终 brief 里明确保留风险。

### Phase 8：最终验证与 PM Director Brief

必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 `traecli` 当前可用，再做可选 live smoke，但不要用 live smoke 替代单元/集成测试：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

最终要生成：

- `docs/lct-auto-backfill-implementation-brief-20260603.md`
- `docs/lct-auto-backfill-implementation-brief-20260603.html`

brief 的口径：假设用户很聪明，但已经忘记这件事为什么要做、改了什么、怎么证明可用。内容应包括：

- 背景问题：为什么旧机制会导致 2-member degraded result 语义不清。
- 产品决策：auto delivery 仍是刚需，低 quorum 不封死但必须显著展示。
- 关键实现：Stage 1 / Stage 2 auto-backfill、runtime cleanup、manifest provenance、HTML 可见性、Skill 更新。
- 测试证据：列出通过的测试命令和关键新增测试类别。
- 剩余风险：如果 Phase 7 没做，必须明确写出。

提交：`docs: add auto-backfill implementation brief`

## notes.md 维护规则

`notes.md` 放在 repo 根目录，中文即可。它不是流水日志，而是给用户看的运行中决策记录。每个阶段至少记录：

- 阶段目标。
- 新增/修改的测试。
- 规范没有覆盖、但你不得不做出的决定。
- 你不得不改动的内容。
- 权衡与风险。
- 阶段验证命令。
- 阶段 commit hash。

不要把 `notes.md` 写成模型输出草稿，也不要让 LCT 成员模型参与创建它。它只属于执行 Agent。

## Subagent 使用方式

主会话先读主规格和代码入口，再分配 subagent。建议分工：

- Runtime cleanup subagent：只看 `provider.py`、`council.py` 任务取消/超时/进程回收，给测试建议和最小改法。
- Quorum/backfill subagent：只看 Stage 1 / Stage 2 orchestration、candidate pool、label/provenance contract。
- Validation/HTML subagent：只看 `validation.py`、`html_export.py`、manifest schema、用户面展示。
- Skill/docs subagent：只看 README 和两个 Skill 文档，确保外层执行流程不会继续鼓励整 run 重跑。

主会话负责最终整合、冲突处理和完整测试。不要让多个 subagent 同时改同一个文件，除非已经明确文件所有权。

## 不要做的事

- 不要把跨 run merge-runs / composite provenance 作为第一版实现。
- 不要为了追求自动交付而静默把 `min_valid_members` 从 3 改成 2。
- 不要要求用户批准 chairman fallback；主席备选链可以自动用。
- 不要在 MVP 里全局 kill 不属于当前 run 的未知进程。
- 不要重写 `traecli` preflight 的 `os.system` 路径。
- 不要把 fake runtime 或 fixture 结果说成 live `traecli` 结果。
- 不要动用户本地 run artifacts，例如 `.llm-council-for-trae/` 下的历史运行结果。
- 不要把 HTML export 和 Stage 3 synthesis 混成一步。

## 完成定义

这轮实现只有在以下条件都满足时才算完成：

- 设计方案、测试方案、交接文档都在 repo 中。
- 每个实现阶段都有 commit。
- `notes.md` 记录了执行过程中的关键决定和权衡。
- auto-backfill 在 Stage 1 和 Stage 2 都有测试覆盖。
- low quorum 在 manifest、validate、index/final、HTML 中都显著可见。
- stuck / timeout / cancellation 的模型进程有明确 cleanup 测试。
- Skill / README 与新 CLI 行为一致。
- 最终 brief 的 md/html 都已生成。
- 下面三条命令全部通过：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```
