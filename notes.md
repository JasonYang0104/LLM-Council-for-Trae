# LCT ACP M1 实施记录：移植 direct baseline contract tests

- 日期：2026-06-11
- 分支：`codex/lct-acp-m1-direct-baseline-20260611`（从 `main @ 04a1b9b` 切出）
- 上游任务卡：`docs/lct-acp-m1-task-card-20260611.md`
- 移植源：`COCO-llm-council-acp-disabled-tool-research-20260603` 分支 `codex/lct-acp-runtime-p0-p1-20260604` 的 commit `5c88617 test: freeze direct runtime baseline`
- 本轮按项目惯例把 worktree 内 `notes.md` 重置为本轮 M1 记录（旧研究线记录保留在 git 历史 / 移植源中）。

## 目标

把研究线 P0 direct baseline contract tests 移植到当前 main，冻结 direct runtime 当前行为，为 M2（ModelRuntime port）及后续改动提供零漂移机器证据。**纯测试移植，零 `src/` 产品代码变更。**

## 移植清单（全部完成）

- `tests/contract/__init__.py`
- `tests/contract/test_tool_policy_golden.py` — 四种 member_tool_mode 的 allowed/disallowed 全列表
- `tests/contract/test_direct_command_golden.py` — `_build_command()` 完整 argv ＋ `--yolo`
- `tests/contract/test_meta_keyset_golden.py` — `ModelCallResult.to_json()` key set 冻结
- `tests/contract/test_direct_spawn_contract.py` — spawn kwargs / runtime cwd / start_new_session / env override
- `tests/contract/test_direct_status_matrix.py` — `_query_model_once()` 状态优先级
- `tests/contract/test_direct_retry_matrix.py` — `query_model()` retry / no-retry
- `tests/contract/test_cancellation_contract.py` — CancelledError 传播、kill、failed meta、不写伪成功
- `tests/contract/test_tool_state_invariants.py` — search allowed / used / forbidden 不塌缩
- `tests/support/__init__.py`、`tests/support/golden.py`、`tests/support/runtime_contract.py`、`tests/support/runtime_fakes.py`
- `tests/test_golden_direct_run.py` ＋ `tests/golden/direct_full_run/snapshot.json`（在当前 main 重新生成，非照抄）

## 红绿过程

- 红：先落 8 个 contract 文件 ＋ support ＋ golden test，无 snapshot。
- 绿：
  - `tests/contract/` 17 个 contract tests 一次全绿（无需改产品代码）。唯一适配点是 `EXPECTED_META_KEYS`（见下）。
  - golden test 首跑 `KeyError: ('stage3', 'contribution-map-repair-1')`——暴露 main 新增的 contribution_map repair 链路（见下）。修正 stage3 chairman 脚本回复后，重新在当前 main 生成 snapshot，golden 两测全绿。
- 直接吸收研究线已知坑：cancellation 在 TemporaryDirectory 生命周期内读证据；argv 精确断言 `--query-timeout` 与其值；status matrix 测 `_query_model_once()` 而非 `query_model()`（retry 由 retry matrix 单独冻结）。这些坑在移植版本里已是正确形态，未复现。

## 适配中发现的 main 行为变化（按 P0 原则：冻结事实，不修产品）

1. **ModelCallResult meta key set 从 30 → 37**。research 线 `EXPECTED_META_KEYS` 30 个；当前 main `to_json()` 多出 7 个 web tool result 追踪字段：`lct_search_conversion_errors`、`lct_web_tool_effective_calls`、`tool_output_conversion_errors`、`tool_result_calls`、`web_tool_effective_calls_count`、`web_tool_result_call_ids`、`web_tool_result_calls_count`。已按当前 main 重新生成 `tests/support/runtime_contract.py` 的 `EXPECTED_META_KEYS`（37 个，含 `lct_web_tool_effective_calls`，它是 `web_tool_effective_calls_count` 的别名键）。

2. **stage3 新增 contribution_map repair 链路**（commits efc2823 / 04a1b9b 等）。`stage3_synthesize_final` 在 `chairman_contribution_enabled`（默认 True）且 chairman 回复中无 renderable contribution_map 时，会再发起一次 `query_model(stage="stage3", label="contribution-map-repair-{n}")`，最多 `chairman_contribution_repair_attempts`（默认 2）次。research 线 golden（contribution_map 之前）没有这条路径。
   - **适配方式**：让 golden 的 chairman stage3 回复内联一个合法 contribution_map fenced JSON（`multi_member_consensus` 归因到真实 Stage 1 模型 Model-A/Model-B）。这样 happy path 端到端跑通 contribution_map 特性、产出 `stage3/contribution_map.json`，且**不触发** repair 子调用（`contribution_map_repair` 不出现、`contribution_map_error=None`）。保持单次 chairman 调用结构，与 research 线 golden 的脚本形态一致。

3. **HTML 搜索摘要卡片格式变化**。research 线 golden 的 `html_checks.contains_search_summary=True`（探测 "允许：" ＋ "实际使用：" 字符串）。当前 main `render_summary_cards` 只在 `lct_web_tool_calls > 0` 时渲染搜索卡片，且文案改为 `调用次数：N`，不再有 "允许：/实际使用："。golden run 零 web tool call，故不渲染搜索卡片，`contains_search_summary=False`。这是当前 main 真相，已按事实冻结进 snapshot。

## golden snapshot 与研究线快照的字段差异（已写入 commit message）

- 文件数 46 → 47：新增 `stage3/contribution_map.json`。
- config 多出：`chairman_contribution_enabled`、`chairman_contribution_repair_attempts`、`chairman_contribution_required`、`model_selection_provenance`。
- stage1/stage2 各成员 meta 多出 7 个 web tool result 字段（同上 §1）。
- stage3_final 多出：`chairman_copy_check`、`contribution_map_enabled`、`contribution_map_path`、`contribution_map_requested`、`contribution_map_required`、`contribution_map_stripped_from_response`、`raw_response`，外加 7 个 web tool result 字段及其别名 `lct_web_tool_result_calls`。
- manifest.stages.stage3 同步多出 contribution_map / copy_check / web tool result 字段。
- html_checks：`contains_search_summary` True → False（见 §3）；`chars` 50729 → 61883（HTML 体积增大，含 contribution_map 渲染）。
- 顶层结构、manifest 顶层 key、html_export key set 无差异。

## 验证（全部通过）

- `make test`：`Ran 314 tests ... OK`（295 基线 ＋ 19 新增 = 17 contract ＋ 2 golden）。
- `PYTHONPATH=src:tests python3 -m unittest discover -s tests/contract -v`：17 tests，OK。
- golden 连跑两次零漂移：snapshot SHA `11eb499f...` 两次一致，两测均 OK。
- `git diff main..HEAD -- src/`：空（零产品代码变更）。
- `git diff --check`：通过。

## 残余风险

- golden 中 chairman 内联 contribution_map 是 happy-path 选择；repair 链路本身仍未被 golden 覆盖（它有独立单元测试在基线 295 中）。M1 范围只冻结 direct happy path，repair 失败路径冻结留待需要时单独补测。
- `EXPECTED_META_KEYS` 现含 37 键，硬编码于 `runtime_contract.py`；M2 加 ACP 字段时必须显式扩列并更新此契约——这正是该测试的设计意图（防止隐式漂移）。
- `support/golden.py` 的正则用 raw string 修正了研究线中 `[^\\s\"']` 的双反斜杠笔误（研究线那是非预期形态）；因 snapshot 在本 normalizer 下重新生成，连跑零漂移已实测，无影响。
