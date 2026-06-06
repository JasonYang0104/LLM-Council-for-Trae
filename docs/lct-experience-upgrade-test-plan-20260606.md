# LCT 体验升级测试方案

日期：2026-06-06

## 1. 测试目标

本方案把 `DECISIONS.md` ADR-0001、`docs/lct-experience-upgrade-implementation-spec-20260606.md` 和 `docs/lct-experience-upgrade-execution-plan-20260606.md` 转成可执行测试矩阵。目标不是扩大测试数量，而是锁住本轮四个产品点的兼容边界：

1. HTML 顶部摘要卡片说人话，但不删除 quorum / backfill / search 证据。
2. Skill 输入改写规则默认 raw，结构化必须有明确触发，operator envelope 不进入 `_lct_question.md`。
3. 自选模型走独立 opt-in 通道归一化到 4，原生 `--members` 行为不变，并持久记录 provenance。
4. 主席贡献说明默认关闭；开启后使用 `stage3/contribution_map.json` blocks contract，HTML 确定性渲染，validate 做 additive + legacy-compatible 校验。

## 2. 基线验证

Phase 0 已跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

基线结果：三条命令均 exit 0；`make test` 当前 222 个 unittest 通过。

## 3. HTML Summary Card

测试落点：`tests/test_core.py`。

新增或更新测试：

- `test_html_summary_card_shows_effective_member_models_without_quorum_jargon`
  - fixture：manifest 有 `metadata.quorum.effective_stage1_members`、`effective_valid_members=4`、`min_valid_members=3`。
  - 断言：顶部卡片标题为「成员模型」，列出有效 Stage 1 成员。
  - 断言：HTML 不含 `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：`。
- `test_html_summary_card_legacy_falls_back_to_config_members_when_quorum_missing`
  - fixture：manifest 缺整个 `metadata.quorum`。
  - 断言：legacy run 仍显示 `config.members`，不破旧 artifact。
- `test_html_summary_card_does_not_show_config_members_when_quorum_present_but_effective_missing`
  - fixture：`metadata.quorum` 存在，但 `effective_stage1_members` 缺失或为空；`config.members` 含失败成员。
  - 断言：顶部不把 `config.members` 冒充为有效成员，应显示空态 / 降级文案。
- `test_html_summary_preserves_quorum_backfill_metadata_evidence`
  - fixture：`metadata.quorum.backfill_candidates`、`backfill_attempted`、`low_quorum_used` 存在。
  - 断言：metadata / evidence 区仍可找到这些字段；summary card 改文案不等于删除证据。

红灯预期：当前 `render_summary_cards()` 仍输出 `Quorum 状态`、`4 / 3`、`normal quorum`、`有效成员：...`，第一条和第三条应失败。

## 4. Skill 输入边界与自选触发

测试落点：`tests/test_global_install_skill_docs.py`。

新增或更新测试：

- `test_skill_documents_raw_input_trigger_matrix`
  - 必含 raw triggers：`不要改写`、`按原文`、`只用原始输入`、`评估 LCT 对原问题的理解`。
  - 必含结论：这些表达只能追加 `Report topic`，不得加 `Agent interpretation` / fact pack。
- `test_skill_documents_structured_input_trigger_matrix`
  - 必含 structured triggers：`先想我真正需要什么`、`站在架构师角度评估`、`fact pack`、`最新资料`、`来源`。
  - 必含约束：必须保留 `Original input`，fact pack 直接内嵌并标来源。
- `test_skill_documents_negative_triggers_do_not_imply_rewrite`
  - 必含负向用例：`详细分析`、`深入一点`、`给完整方案`。
  - 断言：Skill 不得写成这些词单独触发结构化改写。
- `test_skill_documents_operator_envelope_never_enters_lct_question`
  - 必含 operator envelope：`notes.md`、`validate`、`Git/PR`、测试职责、开 branch、提交代码。
  - 断言：这些职责不得进入 `_lct_question.md`。
- `test_skill_documents_selected_model_agent_assisted_path`
  - 断言：用户明确要挑成员 / 指定主席时才触发模型选择体验。
  - 断言：`AskUserQuestionTool` 是 outer Agent 可选体验，必须有文本 fallback，不进入 LCT core。
  - 断言：Agent-assisted 自选应调用独立自选参数，而不是复用原生 `--members`。

红灯预期：当前 Skill 已有基础 input boundary，但缺完整 raw / structured / negative trigger matrix 和 selected model 独立入口说明。

## 5. 自选模型归一化与 Provenance

测试落点：`tests/test_core.py`、`tests/test_lct_model_productization.py`。

新增或更新测试：

- `test_normalize_user_model_selection_fills_to_four_by_preferred_members`
  - 输入：2 个可用且已解析的用户自选 members。
  - 断言：按 `PREFERRED_MEMBERS` 补足到 4；不重复用户已选模型。
- `test_normalize_user_model_selection_trims_to_four_by_preferred_members`
  - 输入：超过 4 个自选 members，其中包含优先级外但可用模型。
  - 断言：按 `PREFERRED_MEMBERS` 裁剪到 4；优先级外模型排后并进入 `trimmed_members`。
- `test_normalize_user_model_selection_keeps_exact_four_user_order`
  - 输入：正好 4 个合法自选 members。
  - 断言：members 原样使用，不按优先级重排。
- `test_normalize_user_model_selection_fails_closed_for_unknown_model`
  - 输入：不存在或拼错模型名。
  - 断言：非交互路径抛出清晰错误，不 silent fallback。
- `test_native_members_build_config_is_not_normalized`
  - 输入：原生 `--members A,B,C`。
  - 断言：`build_config()` 得到 3 个 members，不补足到 4；provenance 标记为 `cli_raw_members` 或保持兼容空态。
- `test_selected_members_cli_path_is_normalized_and_records_provenance`
  - 输入：`--selected-members A,B` / `--selected-chairman C`。
  - 断言：members 补足到 4；chairman 单独校验，不自动塞进 members；`CouncilConfig.model_selection_provenance` 记录 `selection_surface=agent_assisted`、requested/resolved/trimmed/final。
- `test_interactive_custom_selection_uses_same_normalization`
  - 输入：TTY custom 选择少于 4 个 members。
  - 断言：结果走同一个 `normalize_user_model_selection(...)`，provenance 标记 `selection_surface=cli_tty_custom`。
- `test_manifest_persists_model_selection_provenance`
  - 使用 fake provider 跑最小 council。
  - 断言：manifest `metadata.model_selection` 或等价字段包含 requested members、resolved members、trimmed members、final config、selection surface。
- `test_validate_accepts_legacy_manifest_without_model_selection_provenance`
  - 断言：新增 provenance 校验 additive，旧 run 不因缺字段失败。

红灯预期：当前没有 `--selected-members` / `--selected-chairman`，没有 `normalize_user_model_selection(...)`，`CouncilConfig` 也没有持久 provenance 通道。

## 6. 主席贡献说明 Blocks Contract

实现层 contract 选型：`stage3/contribution_map.json`，schema version 1。建议最小结构：

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "b1",
      "type": "paragraph",
      "text": "...",
      "attribution": {
        "kind": "single_member",
        "members": ["DeepSeek-V4-Pro"]
      }
    },
    {
      "id": "b2",
      "type": "editor_note",
      "text": "...",
      "attribution": {
        "kind": "editor_note",
        "members": []
      }
    }
  ]
}
```

允许的 `block.type`：`heading`、`paragraph`、`editor_note`、`disagreement`。

允许的 `attribution.kind`：`single_member`、`multi_member_consensus`、`editor_note`、`synthesis`、`not_attributable`。

测试落点：`tests/test_stage3_contribution_map.py` 或 `tests/test_core.py`。

新增测试：

- `test_contribution_map_disabled_by_default_preserves_markdown_rendering`
  - 默认 run 不要求 sidecar，HTML 使用 `stage3/final.md` 现有 Markdown 渲染。
- `test_stage3_prompt_requests_contribution_blocks_only_when_enabled`
  - 默认 prompt 不要求 blocks；启用 flag 后主席 prompt 明确要求输出 blocks / contribution map，不丢 Stage 1、Stage 2、aggregate rankings。
- `test_store_writes_contribution_map_when_enabled`
  - 启用 flag 且 chairman 返回合法结构时，写出 `stage3/contribution_map.json`，manifest / final.json 标记 enabled。
- `test_validate_accepts_legacy_run_without_contribution_map`
  - legacy run 缺 sidecar 不失败。
- `test_validate_fails_enabled_run_missing_contribution_map`
  - enabled 标记为 true 但 sidecar 缺失，validate verdict 为 `invalid_artifacts`。
- `test_validate_rejects_contribution_map_unknown_member_reference`
  - sidecar 引用不在有效 Stage 1 成员内的模型，validate 失败。
- `test_validate_rejects_consensus_with_fewer_than_two_members`
  - `multi_member_consensus` 少于 2 个成员，validate 失败。
- `test_validate_rejects_invalid_attribution_kind`
  - 非法 attribution kind 失败。
- `test_html_renders_contribution_blocks_deterministically`
  - HTML 从 sidecar blocks 渲染来源条、编者注和分歧块，不按自然段猜来源。
- `test_html_contribution_view_does_not_emit_percentages_or_model_ranking_language`
  - 断言 HTML 不含贡献百分比，不把同侪排名表达成模型强弱排行。

红灯预期：当前 Stage 3 只写 `final.md` / `final.json`，没有 feature flag、sidecar、validation 或 HTML blocks 渲染。

## 7. 文档、README 与 Brief

测试落点：`tests/test_global_install_skill_docs.py`。

新增或更新测试：

- README 说明 `--selected-members` / `--selected-chairman` 或最终等价参数。
- README / Skill 明确原生 `--members` 不补不裁。
- README / Skill 明确仓库 Skill 更新不等于全局 Skill 已生效，除非实际运行安装同步。
- `DECISIONS.md` 追加实现层决策：自选参数名、provenance 字段、contribution map feature flag 和 sidecar contract。
- implementation brief Markdown / HTML 存在，并总结本轮实现、兼容边界、验证结果与 live runtime 状态。

## 8. 执行节奏

TDD 顺序按垂直切片推进：

1. HTML summary card：先写红灯测试，再改 `html_export.py`。
2. Skill input policy：先写文档契约红灯，再改 Skill / README。
3. 自选模型：先写 normalization 单元测试，再接 CLI 参数、config provenance、manifest persistence。
4. Stage 3 contribution map：先写 schema / validation 红灯，再接 prompt、store、HTML。
5. 最后补 README、Skill、DECISIONS、implementation brief。

每个阶段收尾至少跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如触及 live runtime / 模型选择 / Skill path，且 live runtime 可用，最终本地验证追加：

```bash
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

live runtime 不可用时必须记录 skipped 证据，不得用 fixture 冒充 live。
