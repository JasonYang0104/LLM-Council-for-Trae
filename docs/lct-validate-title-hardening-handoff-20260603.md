# LCT validate and title hardening handoff - 2026-06-03

这份交接面向一个足够聪明、但没有本轮上下文的 Agent。它不要求照抄方案；它要求先理解 LCT 当前处在什么阶段，为什么最新 E2E 暴露的问题不是单点 bug，而是“CLI 输出、Skill 工作流、外层 Agent 记录”之间的产品契约还不够硬。

当前 GitHub `main` 已经合入两轮关键变更。PR #5 产品化了默认 direct roster、推荐逻辑和搜索证据字段；PR #6 修正了运行中 manifest 语义，使新 run 初始为 `running`，并让 `validate` 遇到 running run 时只报告 `run_in_progress`，不再把尚未生成的 Stage 2 / Stage 3 / HTML 当作坏 artifact。最新可用本地 main worktree 是：

```text
/Users/bytedance/Documents/AI Coder/COCO-llm-council-runtime-status-title-20260602
```

旧 worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council` 仍保留在 `codex/lct-runtime-capability-hardening-20260601`，用于 review / 善后，不应作为下一轮实现基底。下一轮必须从最新 `origin/main` 新建 worktree 和 `codex/` 前缀分支。

## 现状和证据

最新手动 E2E 在这里：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v6
```

关键文件：

- `notes.md`：运行过程、误判、review 追问和执行 Agent 的回复。
- `lct-20260603-103030-index.md`：已修正后的 run index。
- `lct-20260603-103030-fallback2-final.md`：最终选用答案。
- `.llm-council-for-trae/runs/lct-20260603-103030/`：默认 run artifacts。
- `.llm-council-for-trae/runs/lct-20260603-103030-fallback2/`：最终选用 full `ok` run artifacts。

这次 E2E 的真实状态如下。默认 run `lct-20260603-103030` 不是 hard failed；它是 `degraded_ok`。DeepSeek-V4-Pro 在 Stage 1 失败，但 quorum 成立，Stage 2、Stage 3、HTML 和 validate 都完成，`validate` 返回 `degraded_ok` 且 failures 为空。执行 E2E 的 Agent 最初把它写成 failed，是因为它在 run 尚未完全沉淀时观察到 Stage 2 / Stage 3 目录还空、run JSON 为空，于是提前下结论。后来它在 `notes.md` 的 `Agent reply to reviewer` 区块承认并纠正了这个判断；index 也已改为 `default_attempt_status: degraded_ok`。

最终选用 run 是 `lct-20260603-103030-fallback2`。它把 DeepSeek-V4-Pro 换成 DeepSeek-V4-Flash，并把 timeout 提高到 600 秒，最终 `status: ok`、`validate: ok`。它可以继续作为本次 E2E 的最终答案，但它应被描述为“为了 full ok 和更干净结果而做的可选重跑”，不是“默认 run 不可用后被迫 fallback”。

这次还暴露了 HTML 标题质量问题。PR #6 已经避免了 `Original input` 出现在 hero 标题，但当前报告 title 仍来自英文长句 `The user is not merely asking whether local inference hardwa...`。页面正文里实际有更好的中文题名，例如 `本地AI推理与Agent消费级爆发：系统性评估`。用户希望报告标题变成中文，并倾向形态：

```text
<中文议题>：多模型智囊团评估
```

其中 `多模型智囊团评估` 是固定后缀。

## 下一轮目标

下一轮目标不是继续调模型阵容，而是把 LCT 的“可用状态”和“报告题名”这两个产品契约硬化，避免外层 Agent 再次误报或生成难读标题。

第一条主线是状态判定硬化。`validate` 应提供足够明确的机器可读结论，让外层 Agent 很难把 `degraded_ok` 误写成 `failed`。可以增强现有 `validate` 输出，而不是急着新增命令。推荐字段包括 `terminal`、`usable_final`、`stage3_final_exists`、`html_exists`、`failed_stage_records` 和 `verdict`。`verdict` 可以表达为 `complete_ok_final`、`usable_degraded_final`、`in_progress`、`failed_no_final` 或 `invalid_artifacts`。如果设计过程中发现 `validate` 不适合承载这些字段，再考虑新增只读 `summarize` / `status` 命令。

第二条主线是中文标题契约。HTML export 应生成稳定的报告题名，默认格式是 `<topic>：多模型智囊团评估`，固定后缀不能重复，也不能被截断。当前有一个设计分歧需要在设计阶段显式收敛：subagent 和上一轮 reviewer 倾向“双保险”，即外层 Agent 在 `_lct_question.md` 写显式 topic，LCT 也能从 artifacts fallback；执行 E2E 的 Agent 则认为最好由 LCT 从现有 artifacts 自动推断，避免 Skill 过于脆弱。更稳妥的设计通常是二者兼容：显式 topic 最高优先级，缺失时再从 final answer 的非通用中文标题、`Suggested council focus`、`Agent interpretation` 或原始输入中推断。必须跳过英文长解释句和通用章节名，例如“我真正理解你的需求”“正面信号”“最终判断”。

第三条主线是 Skill / README 工作流对齐。用户级 Skill 和仓库内 Skill 需要明确：任何 run 被写成 failed 前，必须先读取 terminal manifest 并执行 `validate <run_id> --json`。成员失败不等于 run 失败；`degraded_ok` 是可用结果。apparent hang、interruption 或中途目录为空之后，必须先 validate 原 run，再决定是否 fallback。index 中每个 run 的状态应来自 validate JSON，而不是自然语言观察。

## 执行方式

这件事应作为新的长线程目标执行，用 `/goal` 启动。请和 `subagent-lead` 一起推进，并按 TDD **（Test-Driven Development，测试驱动开发）** 工作：先把设计方案和测试方案写清楚，再动代码。你的职责不是“写出看起来合理的代码”，而是让测试真实通过，并让 live / fixture / manual E2E 的边界可复验。

实现必须在新的 worktree / branch 上进行。建议分支名类似：

```text
codex/lct-validate-title-contract-20260603
```

建议阶段如下。

第一阶段是设计和测试计划。先读 `README.md`、`skills/llm-council-for-trae/SKILL.md`、`.trae/skills/llm-council-for-trae/SKILL.md`、`src/llm_council_for_trae/validation.py`、`src/llm_council_for_trae/html_export.py`、`src/llm_council_for_trae/cli.py`，再读 v6 E2E 的 `notes.md` 和 index。产出设计文档和测试计划，说明状态字段、verdict 语义、标题来源优先级、Skill 变更边界和兼容性风险。这个阶段完成后 commit。

第二阶段是 TDD 的红灯阶段。先添加失败测试。状态相关测试应覆盖 `ok`、`degraded_ok`、`running`、缺 Stage 3、缺 HTML、成员失败但 quorum 成立等场景。标题相关测试应覆盖显式 topic、固定后缀不重复、英文长 Agent interpretation 不入选、final answer 中文题名 fallback、通用章节名跳过、topic 过长时只截断 topic 不截断固定后缀、HTML `<title>` 与 hero `<h1>` 一致、HTML escape 正确。这个阶段完成后 commit。

第三阶段是实现。最小化改动，优先增强 `validate` 输出和 `html_export` 标题抽取，不重写 runtime，不引入模型调用，不把 HTML export 和 Stage 3 synthesis 混在一起。这个阶段完成后 commit。

第四阶段是 Skill / docs 对齐。更新 canonical Skill、`.trae` Skill、README 里关于 fallback、validate、index 和 report topic 的约定。不要写成冗长提示词；写成硬规则和可执行证据要求。这个阶段完成后 commit。

第五阶段是验证和 review。必须运行：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 `traecli` 可用，再做 live smoke，并把 fake / fixture / live 分开记录。实现过程中必须启动 subagent review；review 的发现必须处理完再给用户最终结论。这个阶段完成后 commit。

第六阶段是 PM director brief。全部完成后，假设用户很聪明但已经忘了这件事为什么要做，生成一份面向 PM director 的简报，保留 Markdown 和 HTML 两种形态。简报应说明当前 LCT 已经解决了什么、这轮为什么做、风险被如何收敛、还剩哪些不是本轮目标的问题。这个阶段完成后 commit。

整个过程中维护运行中的 `notes.md`。它不是流水账；它只记录规范中没有覆盖、但你不得不做出的决定、权衡、修改和异常。每个阶段都要 commit，commit 范围应窄而可解释。不要把 `.llm-council-for-trae/` live artifacts 放进 Git。

## 成功标准

下一轮结束时，一个接手者应能看到这些事实：

- `validate` 对 terminal run 的输出足以防止外层 Agent 把 `degraded_ok` 误判为 failed。
- Skill 明确要求任何 failed 判定必须来自 terminal manifest + validate JSON。
- HTML 报告标题稳定为中文 `<topic>：多模型智囊团评估`，不会再显示英文长解释句或 `Original input`。
- 测试覆盖状态契约和标题契约。
- live smoke 如果可用，能证明新契约在真实 run 中可观察。
- PM director brief 能让失忆读者在几分钟内重新理解这轮改动的必要性和结果。
