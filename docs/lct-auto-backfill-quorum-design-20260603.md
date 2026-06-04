# LCT Auto-Backfill Quorum Design

日期：2026-06-03

## 背景

本轮人工 E2E 暴露的关键问题不是单个模型失败，而是 LCT 的恢复语义还不够成熟：

- 默认期望是至少 3 个有效成员参与 council。
- 实际运行中，部分成员会因为超时、`traecli result error`、工具污染或模型漂移失败。
- 当前外层 Skill 容易用推荐阵容重新开完整 run，导致已成功的 Stage 1 成员回答被丢弃。
- 执行 Agent 为了交付可能把 `min_valid_members` 从 3 降到 2；这可以作为 fallback，但必须清楚记录并在用户面展示，不能伪装成标准 3-member quorum。

用户对齐后的目标是：自动交付仍然是刚需，但交付过程必须保存有效产物、补齐 quorum、记录降级事实，并可靠收口失败进程和 stale run。

## Zoom-Out 模块图

```text
Skill / README workflow
  - 决定外层 Agent 如何准备输入、选择默认/推荐模型、是否重跑、如何汇报
  - 当前问题：默认失败后鼓励整轮 recommended rerun

cli.py
  - 解析 run 参数，构造 CouncilConfig
  - 当前问题：没有 auto-backfill 参数；低 quorum 没有显式开关或用户面强标记

model_selection.py / roster.py
  - 给出默认 roster、推荐 roster、主席 fallback chain
  - 当前问题：推荐阵容只能作为整轮替换，不能作为候补池补齐 quorum

council.py
  - Stage 1 成员回答、Stage 2 互评、Stage 3 主席综合
  - 当前问题：只有同模型 retry，没有候补 backfill；Stage 2 reviewer 仍按 config.members 全量启动；主席 fallback 自动可用但 provenance 不够显眼

provider.py
  - 单次 traecli 模型调用、stream 解析、工具污染检测、超时/预算 kill
  - 当前能力：direct call 超时、取消、工具预算爆掉时已有进程组 kill 逻辑
  - 当前缺口：Stage 1 orchestrator 取消 pending task 后没有显式 await cleanup 完成；preflight 的 os.system 路径不具备同等 kill 保证

validation.py
  - 检查 manifest、stage 文件、schema、模型一致性、工具污染
  - 当前问题：不理解 backfilled/composite provenance；running manifest 永久 in_progress

html_export.py
  - 从 artifacts 确定性导出 HTML
  - 当前问题：没有对 low quorum、backfill、有效成员数、主席 fallback 做足够显眼的用户面展示
```

## 设计原则

1. **保留成功，不整批作废**：已经 `status: ok` 且无工具污染的 Stage 1 回答是有效资产，后续只补失败缺口。
2. **默认守住 3-member quorum**：正常路径至少 3 个有效 Stage 1 成员；低于 3 仍可自动交付，但必须显式记录和展示。
3. **自动交付优先**：主席 fallback 可自动使用；成员 backfill 可自动使用；不要把每次模型失败都推回用户。
4. **降级必须可见**：低 quorum、backfill、主席 fallback、工具污染、超时都进入 manifest / index / HTML。
5. **进程先收口，再补跑**：启动候补模型前，必须确保上一批被取消或超时的模型进程已完成终止流程。
6. **第一版不做跨 run 拼接**：先做同一个 run 内的 auto-backfill；跨 run composite provenance 后续再做。

## Subagent 复核结论

本方案经两个只读 subagent 静态审视后收敛：

- Runtime cleanup 复核：direct model call 已有进程组 kill 路径，但 Stage 1 阶段级取消缺少 cancel 后 drain，不能证明被取消成员进程已收口。MVP 应先补 `cancel_and_drain`、`try/finally` 和最小 termination metadata，不做全局扫杀。
- Quorum/backfill 复核：MVP 应是 CLI 内部单次 run 自动补位，而不是外层 Agent 整轮重跑；失败槽位不要覆盖，新增 label；候补池必须来自当次 `traecli models --json` 和现有安全排除逻辑；HTML 首屏不能只展示 config members，必须展示实际有效成员和低 quorum。

## MVP：同 Run Auto-Backfill

### 新配置

建议在 `CouncilConfig` 增加：

```python
backfill_members: list[str] = []
stage1_auto_backfill: bool = True
stage2_auto_backfill: bool = True
allow_low_quorum: bool = True
low_quorum_floor: int = 2
```

CLI 参数建议：

```bash
--backfill-members "Qwen3.6-Plus,Gemini-3.1-Pro-Preview,MiniMax-M2.5"
--no-auto-backfill
--low-quorum-floor 2
```

不建议要求 `--allow-low-quorum` 才能降到 2，因为用户已明确“自动交付”是刚需，低 quorum 不应被封死。更合理的是：允许自动低 quorum fallback，但必须在输出里强标记。

`backfill_members` 的默认候选池必须来自已批准的成员整体优先级。当前生成顺序：

1. 读取当次 `traecli models --json`，只作为可用性和安全过滤依据。
2. 遍历 `model_selection.py` 的成员整体优先级。
3. 过滤 hard-banned / beta / queue heat 过高模型，复用 `model_selection.py` 的安全排除逻辑。
4. 排除已经作为 primary member、已尝试失败、或主席专用且不适合做 member 的模型。
5. 不追加未批准的 runtime safe models，不再默认插入同 vendor fallback。

### Stage 1 流程

当前流程：

```text
跑 config.members
失败成员同模型 retry 一次
quorum 不够则 run failed 或外层整轮重跑
```

建议流程：

```text
1. 跑 primary members。
2. 记录每个成员 outcome。
3. 如果 ok_count >= min_valid_members：
   - 进入 Stage 2。
4. 如果 ok_count < min_valid_members：
   - 先确保失败/超时/取消的 pending 进程完成 cleanup。
   - 从 backfill_members 中取未尝试候补。
   - 按需逐批或逐个补跑。
   - 每成功一个就加入 effective_stage1_members。
   - 达到 min_valid_members 后停止补跑。
5. 如果候补耗尽仍不足 3，但 ok_count >= low_quorum_floor：
   - 允许进入 low-quorum degraded path。
   - manifest.status 最终可为 degraded_ok。
   - HTML/index/final 明确显示“仅 2 个有效成员”。
6. 如果 ok_count < low_quorum_floor：
   - terminal failed。
```

补位记录必须追加新 label，例如 `Response E`，不要覆盖原失败的 `Response C`。覆盖会破坏审计，也会让 Stage 2 label 映射变脏。

### Stage 2 流程

Stage 2 有两个集合，必须分开：

- `review_subjects`：被评审的 Stage 1 有效回答。
- `reviewers`：参与互评的模型。

MVP 规则：

```text
review_subjects = effective Stage 1 ok members
reviewers = effective Stage 1 ok members
reviewer_target = min(len(review_subjects), min_valid_members)
```

如果某个 reviewer 在 Stage 2 超时或污染：

```text
1. 标记该 reviewer failed。
2. 从 backfill_members 中找一个尚未使用过、且已在 Stage 1 产出 ok 回答的模型。
3. 如果没有这样的模型，但还有未尝试候补：
   - 先让候补跑 Stage 1，生成有效 answer。
   - 将该 answer 加入 review_subjects。
   - 再让该模型参与 Stage 2。
4. 如果补齐后 Stage 2 有至少 reviewer_target 个有效 review：
   - 继续 Stage 3，视为标准 Stage 2。
5. 如果有效 review 少于 reviewer_target 但至少 2 个：
   - 继续 Stage 3，标记 stage2_degraded。
6. 如果 Stage 2 review 少于 2 个：
   - 可降级到 Stage 1 best-response fallback，但必须显眼标记。
```

这比“失败 reviewer 直接算 degraded”更强，因为它让评估阶段也具备恢复能力。

### Stage 3 流程

主席 fallback 保持自动：

```text
primary chairman failed
  -> try chairman_fallback chain
  -> record attempted / used / fallback_from
```

不需要询问用户。需要增强的是展示和 provenance，而不是停止。

如果所有主席都失败：

```text
如果 Stage 2 aggregate 可用：
  degraded to best-ranked Stage 1 response
否则：
  failed
```

## Manifest / Provenance

建议新增或扩展 `manifest.metadata.quorum`：

```json
{
  "min_valid_members": 3,
  "target_valid_members": 4,
  "low_quorum_floor": 2,
  "effective_valid_members": 3,
  "normal_quorum_met": true,
  "low_quorum_used": false,
  "backfill_used": true,
  "primary_members": ["DeepSeek-V4-Pro", "openrouter-1o", "GPT-5.4", "Gemini-3.1-Pro-Preview"],
  "candidate_source": "member_priority.filtered",
  "backfill_candidates": ["GPT-5.2", "openrouter-1", "Kimi-K2.6", "DeepSeek-V4-Flash", "MiniMax-M2.7", "Qwen3.6-Plus"],
  "backfill_attempted": ["Qwen3.6-Plus"],
  "effective_stage1_members": ["DeepSeek-V4-Pro", "openrouter-1o", "Qwen3.6-Plus"]
}
```

每个 Stage 1 record 建议增加：

```json
{
  "attempt_role": "primary|retry|backfill",
  "attempt_index": 1,
  "source_run_id": "same-run-id",
  "provenance": {
    "input_path": "input.md",
    "prompt_path": "stage1/member.prompt.md",
    "member_tool_mode": "answer_only",
    "runtime_cwd_mode": "isolated_temp"
  },
  "termination": {
    "pid": 12345,
    "pgid": 12345,
    "terminated": true,
    "termination_reason": "timeout|stage_cancel|tool_budget|none",
    "termination_signal": "SIGTERM|SIGKILL|none"
  }
}
```

Stage 2 record 建议增加：

```json
{
  "reviewer_eligible": true,
  "reviewer_source": "stage1_ok|stage1_backfill",
  "review_subject_count": 3,
  "attempt_role": "primary|backfill"
}
```

主席 metadata 保留现有字段并增强：

```json
{
  "attempted": ["Kimi-K2.6", "DeepSeek-V4-Pro"],
  "used": "DeepSeek-V4-Pro",
  "fallback_from": "Kimi-K2.6",
  "fallback_used": true
}
```

## 用户面展示

HTML / index / final copy 必须包含：

- 有效成员数：`effective_valid_members / min_valid_members`
- 是否 normal quorum：`normal_quorum_met`
- 是否 low quorum：`low_quorum_used`
- 实际参与 Stage 1 的有效成员模型
- 实际参与 Stage 2 的 reviewer 模型
- 是否使用 backfill
- 是否使用主席 fallback
- 失败模型和原因

低 quorum 的展示文案建议：

```text
本报告为 degraded fallback：仅 2 个有效成员参与最终综合，低于默认 3-member quorum。
```

backfill 的展示文案建议：

```text
本报告使用 auto-backfill：保留已成功成员回答，并补跑候补模型达到 quorum。
```

主席 fallback 的展示文案建议：

```text
主席模型使用备选：Kimi-K2.6 失败后，DeepSeek-V4-Pro 完成 Stage 3 综合。
```

## Runtime Cleanup 方案

当前 direct model call 已具备基本进程终止能力：

- `provider.py` 用 `asyncio.create_subprocess_exec` 启动模型调用。
- POSIX 下使用 `start_new_session=True` 创建独立 process group。
- timeout、tool budget kill、task cancel 会调用 `terminate_process_tree`。
- `terminate_process_tree` 先 `SIGTERM`，超时后 `SIGKILL`。

MVP 需要补的不是重写 runtime，而是把 Stage 1 的“取消后清理完成”变成强保证：

1. 抽 helper：`cancel_and_drain(tasks)`，内部先 `cancel()`，再 `await asyncio.gather(*tasks, return_exceptions=True)`。
2. Stage 1 hard timeout 和 quorum checkpoint 取消 pending task 后，必须调用 `cancel_and_drain`，等待 provider 的 cleanup 分支完成。
3. Stage 1 / Stage 2 collector 外层加 `try/finally`，主 run 被用户中断或外部取消时也能 drain pending tasks。
4. provider meta 记录最小 termination 证据：`pid`、`pgid`、`termination_reason`、`signals_sent`、`final_returncode`。
5. auto-backfill 启动候补前，先完成上一批 pending task cleanup。
6. 测试用 fake provider 在 `CancelledError` cleanup 后设置 flag，断言 Stage 1 返回前 flag 已完成。

下一层再考虑 `runtime/process-ledger.json` 和 validate 检查。它有价值，但不应阻塞 auto-backfill MVP。

preflight 的 `doctor/models` 仍使用 `os.system`，这条路径不建议在本轮重写，因为它不是成员/主席模型调用，且历史上是为了规避 `traecli` pipe hang。但文档要明确：进程 cleanup 保障优先覆盖 direct model call；preflight stale 另做后续治理。

## Stale Run 收口

建议同时做一个轻量 `terminalize` 能力：

```bash
llm-council-for-trae terminalize <run_id> --reason interrupted
```

行为：

```text
1. 读取 manifest。
2. 如果 status != running，拒绝或 no-op。
3. 汇总已有 stage records。
4. 如果已有可用 final + HTML，可标记 degraded_ok/ok 并写 terminalized_by。
5. 否则标记 failed。
6. 写 manifest.metadata.terminalized。
```

validate 也可以增加 stale hint：

```text
manifest status is running; if the process is gone, run terminalize <run_id>.
```

第一版不建议让 validate 自动改 manifest；validate 保持只读更安全。

## 工具污染治理

短期建议：

- 保留现有 provider 事后 contamination 检测。
- 对 stream 中一旦观察到 forbidden tool call，立即 kill 当前模型调用，减少无效等待。
- 记录 `termination_reason: forbidden_tool_call`。

长期探索：

- 原始模型 completion provider。
- ACP `--disabled-tool` provider。

这两个不进 auto-backfill MVP。MVP 的目标是恢复和交付稳定性，不是彻底解决 `traecli` 工具 schema 注入。

## Timeout UX

当前 `--timeout` 已在 CLI help 中写成 `Per-model query timeout seconds`，但用户仍容易误解为 full-run timeout。

建议本轮只做文档和报告口径：

- index 里写 `per_model_timeout_seconds`。
- 如果新增 `--run-timeout`，放到后续实现，避免和 auto-backfill 同轮耦合过大。

## Skill 更新

Skill 必须从“失败后整轮 recommended rerun”改为：

```text
1. 先跑 default attempt。
2. validate / show manifest。
3. 如果已有 usable final，直接交付。
4. 如果 Stage 1 quorum 不足：
   - 不整轮重跑。
   - 使用 recommended roster 中尚未尝试的模型作为 backfill candidates。
   - 通过 --backfill-members 或后续 quorum/backfill 命令补齐。
5. 如果最终只有 low quorum：
   - 可以交付。
   - 必须在 notes/index/HTML/final summary 中写明有效成员数。
6. prompt shaping 阶段：
   - 不写“请读取 _lct_fact_pack.md”。
   - 如需 fact pack，把事实内容直接嵌入 `_lct_question.md`。
   - 明确 notes.md 只由外层 Agent 维护，模型不要创建或修改 notes。
```

Skill 汇报字段新增：

```text
valid_stage1_models: <models>
quorum_default: 3
quorum_effective: <count>
low_quorum_used: true|false
backfill_attempts: <models and status>
stage2_reviewers: <models and status>
chairman_fallback_used: true|false
```

## 不进 MVP 的事项

- 跨 run `merge-runs` / composite manifest。
- 完整 raw model provider。
- ACP provider。
- 全局 process sweeping 或杀未知 `traecli`/`coco` 进程。
- 自动让 validate 修改 manifest。
- 强制禁止低 quorum。
- 追求补到超过当前默认 direct roster 的目标人数。
- 复杂质量加权、模型信誉分或 Bayesian 排名。

## Best-Practice 测试方案

这轮最重要的不是“补几个测试”，而是把 auto-backfill 写成可执行 spec。测试层要先锁住协议语义，再允许实现改动；否则很容易重新滑回“整轮重跑”“低 quorum 被包装成成功”“Stage 1 失败者继续做 reviewer”这些问题。

### 测试原则

1. **默认不依赖 live `traecli`**：核心测试全部使用 deterministic fake provider，避免队列、模型漂移、网络和权限污染影响 spec。
2. **先测 artifact contract，再测自然语言输出**：manifest / meta / validate / HTML 里必须有机器可查字段；文案只作为用户面可见性补充。
3. **失败槽位不覆盖**：测试必须证明 backfill 追加新 label，不会把失败的 `Response C` 改写成成功。
4. **低 quorum 可交付但不可伪装**：低 quorum 的 run 可以 `degraded_ok`，但不能是 `ok`，且 HTML/index/validate 必须显式可见。
5. **进程收口是独立规格**：`cancelled_by_stage_timeout` 不等于 cleanup 完成；测试要断言 cancel 后 drain 已发生。
6. **Skill 文档也算 spec**：外层 Agent 会照 Skill 做事，所以 Skill / README 的 fallback 规则必须有文档契约测试。

### 测试基建

建议新增 `tests/test_auto_backfill_quorum.py`，并放以下 helper：

```python
def ok_call(model: str, response: str = "answer") -> ModelCallResult: ...
def failed_call(model: str, error: str = "timeout") -> ModelCallResult: ...
class ScriptedProvider:
    """按 (stage, model) 返回预设 ModelCallResult，记录调用顺序。"""
class CleanupAwareProvider:
    """在 CancelledError cleanup 完成后设置 flag，用来证明 drain 已完成。"""
```

测试仍使用 `ArtifactStore.create(tempfile.mkdtemp(), run_id)`，并 patch：

```python
runtime_doctor -> 返回固定 models
TraeCliProvider -> ScriptedProvider
export_html -> 对需要 HTML 检查的测试使用真实 export，其余可 patch 掉
```

不要在这些测试里真实调用 `traecli`。

### Spec Invariants

所有 auto-backfill 实现必须满足这些不变量：

1. `primary_members` 保留原始配置顺序。
2. `effective_stage1_members` 只包含 `status: ok` 且无工具污染的 Stage 1 记录。
3. backfill 只追加新 Stage 1 record，`file_label` 单调递增：A/B/C/D/E/F。
4. 原失败记录仍存在于 manifest failures 或 stage records 中。
5. `normal_quorum_met == (effective_valid_members >= min_valid_members)`。
6. `effective_valid_members < 3` 时，最终 status 不能是 `ok`。
7. Stage 2 的 `review_subjects` 和 `reviewers` 默认都来自有效 Stage 1 成员。
8. Stage 1 failed 成员不能默认参与 Stage 2 reviewer。
9. 主席 fallback 可自动使用，但 `metadata.chairman.fallback_used == true`。
10. 任何低 quorum / backfill / chairman fallback 都必须进入 HTML 首屏或 summary cards。

### Unit Tests

候补池选择：

1. `test_backfill_candidates_use_defined_member_roster_only`：候补只来自已批准的成员整体优先级，并且仍受当次 runtime 可用性过滤。
2. `test_backfill_candidates_filter_hard_banned_beta_hot_queue`：复用 hard-ban / beta / queue heat 过滤。
3. `test_backfill_candidates_exclude_unapproved_runtime_safe_models`：即使 `openrouter-3o`、`Kimi-K2.5` 等模型安全可用，也不得进入默认候补池。
4. `test_backfill_candidates_exclude_primary_and_attempted_models`：不重复尝试同一模型。
5. `test_backfill_candidates_are_deterministic`：相同 models 输入得到相同候补顺序。

label / quorum 计算：

1. `test_next_stage_label_appends_after_primary_members`：4 个 primary 后第一个 backfill 是 `E`。
2. `test_effective_stage1_members_excludes_failed_and_contaminated`。
3. `test_low_quorum_sets_degraded_not_ok`。
4. `test_normal_quorum_met_requires_configured_min_valid_members`。

cleanup：

1. `test_cancel_and_drain_awaits_cancelled_tasks`。
2. `test_stage1_hard_timeout_drains_pending_before_return`。
3. `test_stage1_quorum_checkpoint_drains_cancelled_slow_members`。
4. `test_provider_termination_meta_records_timeout_signal_path`。

### Component Tests

Stage 1:

1. `test_stage1_backfill_preserves_successful_primary_outputs`：A/B 成功、C/D 失败、E 成功，A/B 不重跑。
2. `test_stage1_backfill_appends_records_without_overwriting_failures`：C/D 失败记录仍可见，E 是新记录。
3. `test_stage1_backfill_stops_when_min_quorum_met`：达到 3 后不继续补 F/G。
4. `test_stage1_backfill_exhausted_low_quorum_degraded`：只有 2 个有效成员时允许继续，但标 low quorum。
5. `test_stage1_backfill_exhausted_below_floor_fails`：只有 1 个有效成员时 terminal failed。

Stage 2:

1. `test_stage2_reviewers_default_to_valid_stage1_models`：Stage 1 failed 的 C 不参与 review。
2. `test_stage2_reviewer_failure_backfills_new_reviewer`：B reviewer 失败后补 E reviewer。
3. `test_stage2_reviewer_backfill_runs_stage1_first_when_needed`：候补 E 尚无 Stage 1 answer 时，先跑 Stage 1，再跑 Stage 2。
4. `test_stage2_degraded_when_reviewers_below_target_but_usable`。
5. `test_stage2_fails_or_stage1_best_fallback_when_reviewers_below_floor`。

Stage 3:

1. `test_chairman_fallback_success_records_fallback_used`。
2. `test_chairman_fallback_success_sets_degraded_when_primary_failed`。
3. `test_all_chairmen_failed_degrades_to_best_ranked_stage1_when_possible`。

### Integration Tests

建议用 `run_full_council` + fake provider 做端到端 artifact 测试：

1. `test_run_full_council_auto_backfills_to_normal_quorum`：
   - primary: A/B ok, C/D failed
   - backfill: E ok
   - 断言最终 `degraded_ok` 或 `ok` 的规则按是否有其他降级决定，但 `normal_quorum_met=true`。
   - 断言 Stage 2 只评审 A/B/E。

2. `test_run_full_council_low_quorum_visible_and_usable`：
   - primary 2 ok，其余失败，backfill 全失败
   - 断言 status=`degraded_ok`
   - 断言 `low_quorum_used=true`
   - 断言 HTML 包含“仅 2 个有效成员”或等价文案。

3. `test_run_full_council_stage2_backfills_reviewer`：
   - Stage 1 A/B/C ok
   - Stage 2 B failed
   - E backfill 成功参与 reviewer
   - 断言 `metadata.stage2_reviewers.backfill_reviewers=["E"]`。

4. `test_run_full_council_records_chairman_fallback_in_manifest_and_html`。

5. `test_run_full_council_does_not_start_backfill_until_cancel_cleanup_done`：
   - slow primary 被 quorum checkpoint cancel
   - fake provider cleanup flag 完成后才允许 backfill call
   - 断言调用顺序。

### Validate / Schema Contract Tests

`validation.py` 要新增语义检查，不只检查文件存在：

1. `test_validate_accepts_backfilled_normal_quorum_manifest`。
2. `test_validate_accepts_low_quorum_only_when_marked_degraded`。
3. `test_validate_rejects_low_quorum_with_status_ok`。
4. `test_validate_rejects_backfill_record_missing_attempt_role`。
5. `test_validate_rejects_stage2_reviewer_without_stage1_ok_source`。
6. `test_validate_reports_running_manifest_terminalize_hint`。

如果 schema 仍保持宽松兼容旧 artifact，则这些新检查可以是 semantic checks，不必强制老 manifest 全量失败；但新 run 生成的 manifest 必须满足。

### HTML / User-Facing Golden Tests

HTML 不需要 brittle full snapshot，但要有关键字符串 / DOM 结构断言：

1. `test_html_summary_shows_effective_not_only_config_members`。
2. `test_html_low_quorum_banner_visible_above_final_answer`。
3. `test_html_backfill_banner_visible`。
4. `test_html_chairman_fallback_visible`。
5. `test_html_trace_marks_backfill_attempts`。

这些测试要防止回到当前问题：HTML 只展示 `config.members`，用户看不出实际只有 2 个成员生效。

### CLI / Docs / Skill Contract Tests

CLI:

1. `test_build_config_accepts_backfill_members_and_low_quorum_floor`。
2. `test_default_auto_backfill_enabled`。
3. `test_no_auto_backfill_disables_backfill`。

Skill / README:

1. `test_skills_no_longer_instruct_full_recommended_rerun_as_primary_recovery`。
2. `test_skills_require_auto_backfill_and_effective_member_reporting`。
3. `test_skills_require_fact_pack_inline_not_read_file_instruction`。
4. `test_readme_documents_low_quorum_as_visible_degraded_fallback`。

### Regression Fixtures

建议新增 fixture 目录：

```text
tests/fixtures/auto_backfill/
  normal_quorum_backfilled/
  low_quorum_degraded/
  stage2_reviewer_backfilled/
  chairman_fallback_used/
  stale_running_terminalize/
```

每个 fixture 至少包含：

```text
manifest.json
config.json
stage1/*.meta.json
stage2/*.review.json
stage3/final.json
html/index.html, if HTML semantics are under test
```

fixture 的作用不是替代 unit test，而是防止 schema/reporting contract 漂移。

### Optional Live Smoke

live `traecli` smoke 只作为发布前补充，不作为 PR 必须通过条件：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live run 失败，只能说明当前 runtime 环境或模型队列不稳定；不能推翻 fake-provider spec 测试。汇报时必须拆开 unit/spec pass 与 live smoke fail。

### Red-Green 实施顺序

1. 先写 cleanup spec：Stage 1 cancel-and-drain 失败测试。
2. 再写候补池 unit tests：保证候补来源、过滤和顺序。
3. 写 Stage 1 backfill component tests：保留成功、追加 label、低 quorum。
4. 写 Stage 2 reviewer eligibility/backfill tests。
5. 写 manifest/quorum metadata schema tests。
6. 写 HTML banner / effective members tests。
7. 写 Skill / README contract tests。
8. 最后补 terminalize 和 forbidden tool fail-fast tests。

每一步都应先看到失败测试，再实现；不要先改大段实现后补“看起来覆盖”的测试。

## 推荐实施顺序

1. 修 Stage 1 cancellation cleanup：取消后 await pending，补测试。
2. 增加 Stage 1 auto-backfill 数据结构和流程，补测试。
3. 修 Stage 2 reviewer eligibility，再加 Stage 2 reviewer backfill。
4. 增加 quorum metadata、低 quorum/backfill/主席 fallback 用户面展示。
5. 改 Skill / README fallback 规程，去掉整轮 recommended rerun 默认路径。
6. 增加 terminalize 命令。
7. 增加 forbidden tool call fail-fast kill。

## 一句话结论

LCT 下一轮不应主要追求“更多重跑”，而应把每次成功模型输出变成可复用资产：先自动补齐 quorum，补不齐再低 quorum 交付，并把所有降级、候补、主席 fallback 和进程收口写成可验证 artifact。
