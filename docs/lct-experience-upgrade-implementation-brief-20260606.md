# LCT Experience Upgrade Implementation Brief

日期：2026-06-06
分支：`codex/lct-experience-upgrade-20260606`

## 一句话结论

LCT 本轮体验升级已经把三个容易误解的用户界面问题收进可测试合同：HTML 顶部不再把 quorum 黑话当作主信息，输入改写边界写进 Skill/README，自选模型路径和主席贡献说明都有独立 opt-in surface 与 provenance。默认运行路径保持兼容；新增能力只在明确触发时生效。

## 这轮解决了什么

第一，报告顶部从「Quorum 状态」改成「成员模型」。新 run 读取 `metadata.quorum.effective_stage1_members`，只展示最终真正贡献 Stage 1 有效答案的模型；只有 legacy run 整体缺少 `metadata.quorum` 时才 fallback 到 `config.members`。这避免用户看到 `4 / 3`、`normal quorum` 这类内部状态后误以为报告在评价模型表现。

第二，Skill 输入边界被重新钉死。默认是 `raw original input`；只有用户明确要求「先想真正需要什么」「站在架构师角度评估」「补 fact pack / 最新资料 / 来源」时，外层 Agent 才能进入 `structured by Agent`。`notes.md`、validate、Git、PR、测试、branch 和 commit 都属于 operator envelope，不得写入 `_lct_question.md`。

第三，自选模型体验从原生 `--members` 中剥离。原生 `--members` 仍是 power-user 精确路径，给几个跑几个，不补足、不裁剪。agent-assisted 自选使用 `--selected-members` / `--selected-chairman`，会归一化到 4 个成员，并把用户请求、解析结果、补足成员、裁剪成员和最终 config 写入 `manifest.metadata.model_selection`。

第四，主席贡献说明采用默认关闭的 sidecar contract。只有追加 `--chairman-contribution-map` 时，Stage 3 才要求主席输出 `stage3/contribution_map.json`；HTML 从 blocks 确定性渲染段落来源，validate 只在 enabled 时校验 sidecar。系统不输出贡献百分比，也不把 Stage 2 同侪排序解释成模型能力排行。

## 关键实现

### HTML summary card

`src/llm_council_for_trae/html_export.py` 的 summary card 改为「成员模型」卡片。新逻辑优先使用 `metadata.quorum.effective_stage1_members`，并保留 legacy fallback：只有 `metadata.quorum` 缺失时才读取 `config.members`。如果 quorum metadata 存在但有效成员为空，HTML 明确写 `暂无有效成员记录`，不把配置成员伪装成有效成员。

对应提交：`9f1a097 feat: simplify LCT report summary and input policy docs`

### Input policy docs

`README.md`、`skills/llm-council-for-trae/SKILL.md` 和 `.trae/skills/llm-council-for-trae/SKILL.md` 增加 raw / structured / negative trigger matrix，明确 `Report topic` 是报告元数据，不是 prompt shaping。fact pack 必须直接嵌入 `_lct_question.md` 并标来源；执行职责留在外层 Agent。

对应提交：`9f1a097 feat: simplify LCT report summary and input policy docs`

### Selected model normalization

`src/llm_council_for_trae/model_selection.py` 新增 `normalize_user_model_selection(...)`。它复用既有模型 token 解析能力，处理 exact、case-insensitive 和编号输入；少于 4 个按成员优先级补足，超过 4 个按成员优先级裁剪，正好 4 个保留用户顺序。`src/llm_council_for_trae/cli.py` 新增 `--selected-members` / `--selected-chairman`，并拒绝与原生 `--members`、`--chairman`、`--default-models` 混用。

`CouncilConfig.model_selection_provenance` 和 `manifest.metadata.model_selection` 负责把归一化证据持久化，避免它变成 silent fallback。

对应提交：`57d411a feat: add explicit selected-model normalization`

### Chairman contribution map

`src/llm_council_for_trae/cli.py` 新增 `--chairman-contribution-map`。启用后，Stage 3 prompt 要求主席输出 `contribution_map` JSON；`src/llm_council_for_trae/council.py` 解析 fenced JSON 或整段 JSON，写入 `stage3/contribution_map.json`，并在 manifest 记录 `metadata.chairman_contribution`。

`src/llm_council_for_trae/schema_contract.py` 定义 `CONTRIBUTION_MAP_SCHEMA`；`src/llm_council_for_trae/validation.py` 只在 enabled 时校验 sidecar 存在、block type 合法、attribution kind 合法、成员引用来自有效 Stage 1 成员、`multi_member_consensus` 至少引用 2 个成员、`single_member` 只引用 1 个成员。

`src/llm_council_for_trae/html_export.py` 在 sidecar 可读时渲染 blocks，否则回到 `stage3/final.md`。HTML 阶段不调模型，也不按自然段猜来源。

对应提交：`5fa99e2 feat: add gated chairman contribution map`

## 测试证据

本轮按 TDD 推进，先写红灯测试，再分阶段实现。红灯覆盖：

- HTML summary card 新文案、legacy fallback 和 evidence 保留。
- Skill raw / structured / negative trigger matrix。
- 原生 `--members` 精确语义不变。
- `--selected-members` / `--selected-chairman` 归一化与 provenance。
- chairman contribution map 默认关闭、enabled sidecar 校验和 HTML blocks 渲染。

阶段验证已经通过：

```bash
PYTHONPATH=src python3 -m compileall src
git diff --check
make test
```

截至 `5fa99e2` 后的全量结果：`make test` 通过 243 个 unittest，输出末尾包含既有 fixture 预期的 `degraded_ok`。

最终 PR 前仍会重新执行完整门禁，并在 live runtime 可用时补 `models --recommend --json`、live run 和 validate。

## 兼容性边界

- `--default-models` 不变。
- 原生 `--members` / `--chairman` 不变，不补足、不裁剪。
- `profile` 和 subagent 路径不走 selected normalization。
- `--chairman-contribution-map` 默认关闭；legacy run 缺 `stage3/contribution_map.json` 不失败。
- contribution map validate 只验证结构和引用合法性，不声称验证真实贡献程度。
- HTML 不删除 quorum/backfill evidence；只是把用户首屏主信息从内部状态改为有效成员。

## 剩余风险

- contribution map 依赖主席按要求输出结构化 JSON。validate 能拦结构错误，但不能证明主席归因绝对正确。
- enabled 时如果主席同时输出正文和 fenced JSON，`stage3/final.md` 仍保存完整原始响应；HTML 会优先使用 sidecar blocks 渲染用户可见正文。
- 本轮没有把 outer Agent 的 `AskUserQuestionTool` 做成 core dependency；它仍是 Skill/Agent 层可选体验。
- live runtime 的最终证据仍取决于当前 `traecli` 状态；PR 前和 merge 后 v16 会重新验证。

## 交付索引

- 架构规格：`docs/lct-experience-upgrade-implementation-spec-20260606.md`
- 执行计划：`docs/lct-experience-upgrade-execution-plan-20260606.md`
- 测试方案：`docs/lct-experience-upgrade-test-plan-20260606.md`
- 运行记录：`notes.md`
- Markdown 简报：`docs/lct-experience-upgrade-implementation-brief-20260606.md`
- HTML 简报：`docs/lct-experience-upgrade-implementation-brief-20260606.html`
