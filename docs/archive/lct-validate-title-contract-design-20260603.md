# LCT validate 与标题契约设计 - 2026-06-03

## 背景

2026-06-03 的 v6 live E2E 暴露出两个产品契约问题。

第一，外层 Agent 在 run 仍未完全沉淀时观察到空目录和空 JSON，提前把默认 run 写成 `failed`。事后复核证明该 run 的 terminal manifest 是 `degraded_ok`，`stage3/final.md`、`html/index.html` 都存在，`validate` 返回 `degraded_ok` 且 `failures` 为空。这说明 `degraded_ok` 已经能被 CLI 接受，但 `validate` 输出还不够明确，外层 Agent 仍容易把“成员失败”误判为“run 失败”。

第二，HTML 报告避开了 `Original input` 作为标题，但仍可能选中英文长解释句，例如 `The user is not merely asking whether local inference hardwa...`。正文里已经有更好的中文题名，报告外壳应该稳定显示中文议题。

## 目标

本轮只硬化两个契约：

- `validate` 给出更强的机器可读终局判断，让外层 Agent 能区分 `ok`、`degraded_ok`、`running`、无最终答案、坏 artifact。
- HTML export 生成稳定中文报告题名，默认形态为 `<topic>：多模型智囊团评估`。

## 非目标

- 不改 runtime 执行策略。
- 不实现自动 recommended fallback。
- 不引入模型调用来生成标题。
- 不改 Stage 3 synthesis。
- 不把 HTML export 和主席综合混成一步。
- 不修改 `.llm-council-for-trae/` live artifacts。

## validate 输出契约

`validate_run` 保留既有字段：`run_id`、`status`、`manifest_status`、`checks`、`failures`。新增字段应兼容旧调用方，且只从 artifact 静态判断：

```json
{
  "terminal": true,
  "usable_final": true,
  "stage3_final_exists": true,
  "html_exists": true,
  "failed_stage_records": [],
  "verdict": "complete_ok_final"
}
```

字段语义：

- `terminal`: manifest status 是否为 terminal。`ok`、`degraded_ok`、`failed` 为 true，`running` 为 false。
- `usable_final`: 是否有可用最终答案。只有 terminal run、`stage3/final.md` 存在且非空、无 artifact validation failure，并且 manifest status 为 `ok` 或 `degraded_ok` 时为 true。
- `stage3_final_exists`: `stage3/final.md` 是否存在且非空。
- `html_exists`: `html/index.html` 是否存在且非空。
- `failed_stage_records`: 从 manifest stage records 中提取的失败记录。它解释“哪些模型/阶段失败”，但不等价于 run failed。
- `verdict`: 给外层 Agent 的摘要判定。

`verdict` 枚举：

- `complete_ok_final`: terminal `ok`，final 与 HTML 可用，validation 无失败。
- `usable_degraded_final`: terminal `degraded_ok`，final 与 HTML 可用，validation 无失败。
- `in_progress`: manifest status 为 `running`，不检查缺失 Stage 2 / Stage 3 / HTML 噪音。
- `failed_no_final`: terminal `failed`，或无可用 final。
- `invalid_artifacts`: manifest status 声称可用，但 schema、模型一致性、tool contamination 或 HTML export 等 validation 失败。

关键边界：成员失败不自动导致 `failed_no_final`。只要 quorum 成立、terminal manifest 为 `degraded_ok`、final/HTML 存在且 validation failures 为空，verdict 必须是 `usable_degraded_final`。

## HTML 标题契约

HTML 标题应由 deterministic artifact read 得出，不调用模型。最终 `page_title` 使用中文全角冒号和固定后缀：

```text
<topic>：多模型智囊团评估
```

固定后缀只出现一次。截断只作用于 `<topic>`，不能截断 `多模型智囊团评估`。

标题来源优先级：

1. 显式 topic 行，例如 `Report topic: ...`、`报告题名：...`、`议题：...`。
2. `stage3/final.md` 中第一个非通用中文 heading。
3. `_lct_question.md` 的 `Agent interpretation` / `Suggested council focus` 等优先章节内容。
4. 原始输入中的第一个可用中文内容行。
5. 兜底 `最终答案：多模型智囊团评估`。

必须跳过：

- `Original input`、`输入提示词` 等输入标签。
- `我真正理解你的需求`、`正面信号`、`最终判断` 等通用章节名。
- 英文长解释句，尤其是 Agent interpretation 里类似 `The user is not merely asking...` 的句子。

HTML `<title>` 和 hero `<h1>` 使用同一个 `page_title`，并保留 HTML escaping。

## Skill 与 README 契约

Skill 和 README 需要把失败判定规则写硬：

- 任何 run 被写成 `failed` 前，必须先读取 terminal manifest，再执行 `validate <run_id> --json`。
- `degraded_ok` 是可用结果，不是失败。
- 成员失败、timeout、apparent hang、中途目录为空、run JSON 为空，都只能作为调查信号，不能直接写成 final status。
- 如果进程被中断或怀疑挂起，先 validate 原 run；只有 validate 表明无可用 final 或 artifact invalid，才考虑 fallback。
- `$RUN_ID-index.md` 的 run 状态必须来自 validate JSON 的 `status` / `verdict`，不能来自自然语言观察。

## 兼容性

新增字段只扩展 `validate` JSON，不改变现有 status 退出语义：`ok` 和 `degraded_ok` 仍 exit 0，`running` 和 `failed` 仍 exit 1。HTML 标题会改变报告外壳，但不改变 Stage 3 正文。

当前 `validate` 已把 HTML export 视为完整报告交付的一部分：`html/index.html` 或 `html/export.json` 缺失时会产生 validation failure。本轮延续这个报告可用性口径，因此 `--skip-html` 产物可以有 `stage3/final.md`，但不应被 `validate` 标成 `usable_final=true` 的完整可交付报告。
