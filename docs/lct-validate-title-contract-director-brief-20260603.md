# LCT validate 与报告标题契约：PM Director Brief

日期：2026-06-03  
分支：`codex/lct-validate-title-contract-20260603`  
范围：`validate` 状态契约、HTML 报告题名、Skill / README 工作流硬规则

## 一句话结论

这轮把 LCT 从“能跑出结果”推进到“外层 Agent 更难误报结果状态、HTML 报告标题更像可交付报告”。核心变化是：`validate` 现在输出明确的 terminal / usable / verdict 字段，HTML 标题稳定为中文 `<topic>：多模型智囊团评估`，Skill 明确要求任何 failed 判定必须来自 terminal manifest 加 `validate <run_id> --json`。

## 为什么要做

v6 live E2E 的默认 run 实际是 `degraded_ok`：DeepSeek-V4-Pro 在 Stage 1 失败，但 quorum 成立，Stage 2、Stage 3、HTML 和 validate 都完成。执行 Agent 最初把它写成 failed，是因为它在 run 尚未沉淀完成时看到空目录和空 JSON，提前下结论。

这不是一个单点 bug，而是产品契约不够硬：

- CLI 输出没有把“可用最终答案”和“成员失败”拆得足够清楚。
- Skill 允许外层 Agent 用过程观察替代 terminal validation。
- HTML 标题仍可能选中英文长解释句，削弱报告可读性。

## 本轮解决了什么

`validate` 增加机器可读字段：

- `terminal`
- `usable_final`
- `stage3_final_exists`
- `html_exists`
- `failed_stage_records`
- `verdict`

`verdict` 的枚举为：

- `complete_ok_final`
- `usable_degraded_final`
- `in_progress`
- `failed_no_final`
- `invalid_artifacts`

这保留了旧的 `status` 语义：`ok` 和 `degraded_ok` 仍是可成功退出的状态；`running` 和 `failed` 不被伪装成成功。新增字段只负责让外层 Agent 更明确地知道“有没有可交付最终答案”。

HTML 报告标题现在按确定性优先级生成：

1. 显式 topic，例如 `Report topic: ...` 或 `报告题名：...`。
2. `stage3/final.md` 的第一个非通用中文 heading。
3. `Agent interpretation` / `Suggested council focus` 的可用中文议题。
4. 原始输入中的可用中文内容。
5. 兜底 `最终答案：多模型智囊团评估`。

固定后缀 `多模型智囊团评估` 不重复，过长时只截断 topic，不截断后缀。英文长解释句和通用章节名不会再进入 HTML `<title>` 或 hero `<h1>`。

Skill / README 对齐了失败判定规则：

- failed 判定前必须先读取 terminal manifest，并执行 `validate <run_id> --json`。
- `degraded_ok` 是可用结果，成员失败不等于 run 失败。
- apparent hang、interruption、中途目录为空、run JSON 为空，只能作为调查信号，不能直接写成 final status。
- index 状态必须来自 validate JSON 的 `status` / `verdict`。
- `.trae` Skill 也补上源码 repo guard，不再引导在 LCT 源码仓库里跑用户问题。

## 风险如何收敛

本轮按 TDD 执行：先提交设计和测试计划，再提交 RED 测试，再实现，再修复 reviewer 发现的问题。

review 发现并修复了三个实质风险：

- `failed_stage_records` 可能把同一个真实失败记录重复输出。
- `.trae` Skill 仍有“在仓库根目录执行”的旧路径表述。
- 无标点英文长解释句仍可能进入标题。

这些都已加回归测试。

最终验证：

- `PYTHONPATH=src python3 -m compileall src`：pass。
- `make test`：pass，161 tests。
- `git diff --check`：pass。
- `git diff --check origin/main..HEAD`：pass。

live smoke：

- 使用真实 `traecli`，版本 `coco version 0.120.32`。
- `doctor --json`：`ok: true`，仅 warnings。
- `models --recommend --json`：21 个 live models，推荐阵容存在。
- run id：`lct-validate-title-smoke-20260603`。
- run status：`ok`。
- validate：`terminal: true`、`usable_final: true`、`stage3_final_exists: true`、`html_exists: true`、`verdict: complete_ok_final`。
- HTML `<title>` 与 hero `<h1>`：`LCT validate 状态契约 smoke：多模型智囊团评估`。

## 不是本轮目标

- 没有调整模型阵容。
- 没有实现自动 fallback。
- 没有改变 runtime 并发、timeout 或 retry 策略。
- 没有把 HTML export 和 Stage 3 synthesis 混成一步。
- 没有把 fake runtime 或 fixture 结果当成 live smoke。

## 剩余问题

`validate` 已经把 terminal 状态讲清楚，但外层 Agent 是否持续遵守规则，还取决于安装到用户环境里的 Skill 是否更新到本分支之后的版本。合并后需要刷新 `~/.LCT` 和用户级 Skill symlink。

`--skip-html` 仍会产生没有 HTML 的 run。本轮延续当前口径：完整报告交付必须有 HTML，因此 `usable_final` 只对具备 Stage 3 final 和 HTML 的报告为 true。若未来要支持“纯 Markdown final 也算可交付”，需要另设 verdict，而不是挤进当前报告交付语义。

