# LCT validate 与标题契约测试计划 - 2026-06-03

## 测试原则

优先通过公共接口验证行为：

- `validate_run(store)` 用真实临时 artifact store。
- `render_html(root, manifest)` / `export_html(store)` 用真实文件。
- Skill / README 用文档测试验证硬规则文本存在。

不 mock `validate_run` 内部 helper，不调用 live 模型。

## TDD 切片

### Slice 1: validate terminal verdict

新增测试覆盖：

- `ok` run: `terminal=true`、`usable_final=true`、`stage3_final_exists=true`、`html_exists=true`、`verdict=complete_ok_final`。
- `degraded_ok` run with one failed member: `status=degraded_ok`、`usable_final=true`、`failed_stage_records` 包含失败成员、`verdict=usable_degraded_final`。
- `running` run: `terminal=false`、`usable_final=false`、`verdict=in_progress`，且不产生 Stage 2 / Stage 3 / HTML 缺失噪音。
- missing Stage 3 final: `usable_final=false`、`stage3_final_exists=false`、`verdict=failed_no_final` 或 `invalid_artifacts`，取决于 manifest 声称状态。
- missing HTML: `html_exists=false`，manifest 声称 `ok` / `degraded_ok` 时 `verdict=invalid_artifacts`。
- terminal failed run: `terminal=true`、`usable_final=false`、`verdict=failed_no_final`。

### Slice 2: title topic extraction

新增测试覆盖：

- 显式 topic 行优先，输出 `<topic>：多模型智囊团评估`。
- 固定后缀不重复：输入已经含 `多模型智囊团评估` 时不追加第二次。
- 英文长 Agent interpretation 不入选，转而使用 final answer 中文 H1。
- final answer 中文 H1 可作为 fallback。
- 通用章节名跳过，例如 `我真正理解你的需求`、`正面信号`、`最终判断`。
- topic 过长时只截断 topic，不截断固定后缀。
- `<title>` 与 hero `<h1>` 一致。
- HTML escape 正确。

### Slice 3: Skill / README hard rules

新增或扩展文档测试覆盖：

- canonical Skill 要求 failed 判定前读取 terminal manifest 并执行 `validate <run_id> --json`。
- `.trae` Skill 同步该要求。
- README Quickstart 要求 index 状态来自 validate JSON。
- 文档明确 `degraded_ok` 是可用结果，成员失败不等于 run 失败。
- apparent hang / interruption / 中途目录为空后必须先 validate 原 run，再决定 fallback。

## 验收命令

每个实现阶段至少跑相关单测；最终必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 `traecli` 可用，再做 live smoke：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input <clean-workspace>/_lct_question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

live smoke 汇报必须拆分 fake / fixture / live，不把 fixture 说成 live。

