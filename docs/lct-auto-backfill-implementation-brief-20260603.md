# LCT Auto-Backfill Implementation Director Brief

日期：2026-06-03
分支：`codex/lct-auto-backfill-plan-20260603`

## 一句话结论

LCT 已经从“默认成员失败后靠外层 Agent 整轮重跑”推进到“同一个 run 内自动补位、可降级但必须说真话”的产品形态。本轮实现的重点不是多跑几次模型，而是把自动交付、质量底线、失败清理和用户可见证据绑定成同一套 runtime contract。

## 为什么这轮值得做

旧机制的核心问题不是“失败后不能补救”，而是补救边界不清。默认模型失败时，外层 Skill 会倾向于用推荐阵容重新跑一整轮；这会带来三个产品问题：

- 已经成功的 Stage 1 输出没有被自然复用，用户等价于为同一个问题重新付一次运行成本。
- 2-member degraded result 的语义容易混淆：它可能是可用降级，也可能是 quorum 失败后的伪成功。
- failure、fallback、HTML 展示、Skill 汇报各说各话，用户看到的是“好像完成了”，但证据链不够硬。

这轮的判断是：自动交付仍然是 LCT 的核心体验，但它不能靠模糊状态偷渡。低 quorum 可以交付，但必须在 manifest、validate、HTML、索引和最终汇报里显著可见。

## 产品决策

第一，默认目标仍是至少 3 个有效 Stage 1 成员。这个底线没有被悄悄改成 2。

第二，成员失败后的主恢复路径变为同一个 run 内 auto-backfill：保留已成功回答，只追加候补成员，不整轮重跑，不覆盖 primary failure 证据。

第三，low quorum 是可用降级，不是健康成功。只要最终有效成员低于默认 quorum，就必须标记 `degraded_ok`，并展示 `low_quorum_used`、有效成员数和 backfill 尝试。

第四，主席模型失败时允许自动走备选链；不需要打断用户，但必须记录 `chairman_fallback_used`。

第五，Skill 和 README 必须跟 CLI 行为一致。外层 Agent 不再把推荐阵容整轮 rerun 当成第一补救动作；`models --recommend --json` 现在是候补池来源，而不是另起一轮的指令。

## 关键实现

### Runtime cleanup

新增 `cancel_and_drain()`，让 Stage 1 / Stage 2 在 quorum checkpoint、timeout 或 cancellation 后等待 pending tasks 收口。provider timeout / cancel / tool-budget kill 路径现在会留下 termination metadata，包括 termination reason、kill action 和 final returncode。这样 backfill 启动前不会把上一批未清理任务留给后续 run。

对应提交：`7d7fc53 fix: drain cancelled model tasks before backfill`

### Backfill candidate pool

新增确定性候补池：显式 `--backfill-members` 优先，然后同 vendor fallback，再用 `models --recommend --json` 和当前 runtime safe models 补齐。候补池会过滤 primary members、已尝试成员、主席、hard-banned、beta 和 hot queue 模型。

对应提交：`b0d09f6 feat: add deterministic backfill candidate selection`

### Stage 1 auto-backfill

Stage 1 成员失败后，CLI 会在同一个 run 内追加新 label，例如 `Response E`，而不是覆盖失败成员原 slot。manifest 写入 `metadata.quorum`，记录 primary members、backfill candidates、backfill attempted、effective Stage 1 members、normal quorum / low quorum 状态。

对应提交：`aba731c feat: backfill failed stage1 members in-run`

### Stage 2 reviewer eligibility

Stage 2 的 review subjects 和 reviewers 默认来自有效 Stage 1 成员。失败或 contaminated 的 Stage 1 成员不再默认参与 reviewer。如果 Stage 2 reviewer 失败，CLI 会先补一个新的 Stage 1 answer，再让该候补补交 review，并把 reviewer provenance 写入 `metadata.stage2_reviewers`。

对应提交：`ce0c1ad feat: backfill stage2 reviewers from effective members`

### Manifest / validate / HTML 可见性

HTML summary 现在展示 quorum 状态、有效成员、auto-backfill 尝试和主席备选。low quorum 会在 final answer 前显示 warning banner。validate 增加 quorum semantic checks：low quorum 不能标成 `ok`，backfill record 必须有 `attempt_role=backfill`，eligible reviewer 必须有有效 Stage 1 answer。

对应提交：`bbf7ca1 feat: surface backfill and low-quorum provenance`

### Skill / README 对齐

README、canonical Skill 和 `.trae` Skill 已删除整轮 recommended rerun 旧口径，改为同一个 run 内 auto-backfill。索引和汇报要求新增：`valid_stage1_models`、`quorum_default`、`quorum_effective`、`low_quorum_used`、`backfill_attempts`、`stage2_reviewers`、`chairman_fallback_used`。fact pack 必须直接嵌入 `_lct_question.md`；`notes.md` 只由外层 Agent 维护，模型不要创建或修改 notes。

对应提交：`90ae5b7 docs: align skill workflow with auto-backfill`

## 测试证据

本轮按测试先行推进。关键新增覆盖包括：

- Stage 1 / Stage 2 cancellation drain 和 provider termination metadata。
- backfill candidates 的过滤、排序和 CLI config。
- Stage 1 backfill append、不覆盖 primary failure、low quorum degraded。
- Stage 2 reviewer eligibility 和 reviewer backfill。
- validate 对 low quorum / backfill semantic 的拒绝与接受。
- HTML 对 quorum、chairman fallback、low quorum banner 的展示。
- README / Skill 文档契约，防止旧 recommended rerun 流程回流。

本轮阶段验证已通过：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

当前全量测试结果：`make test` 通过 179 个 unittest。

补充 live smoke 也已通过：

- `doctor --json`：`ok: true`；仅有 MCP connecting 和 upgrade server timeout warning，无 doctor error。
- `models --recommend --json`：runtime models 21 个；推荐成员为 Kimi-K2.6、MiniMax-M2.7、GPT-5.2、DeepSeek-V4-Pro；主席为 Kimi-K2.6。
- live run：`live-auto-backfill-20260603-final`，`status: ok`，`degraded: false`，`failures: []`。
- validate：`status: ok`，`terminal: true`，`usable_final: true`，`verdict: complete_ok_final`，`failed_stage_records: []`。

## 剩余风险

Phase 7 没有纳入本轮实现，作为后续 PR 保留：

- Stale run terminalization：当前 validate 仍偏 read-only；对 interrupted run 主动 terminalize 的命令或写回策略尚未实现。
- Forbidden tool fail-fast：当前 provider 能检测 forbidden tool call 并把 attempt 标记 failed，但“发现后立即终止模型进程”的更激进 fail-fast 还没落地。
- Stage 1 旧 retry 语义仍保留；当 `stage1_max_retries>0` 时，同模型 retry 仍可能复用原 slot。auto-backfill 已保证追加、不覆盖，但 retry append 化需要单独处理。
- Stage 2 backfill reviewer 的 prompt sidecar 仍是共享 prompt 文件；manifest/stage records 可审计，但 batch-specific prompt path 还不是第一版范围。

这些不是隐藏故障，而是本轮刻意保留的边界。主路径已经完成：同 run auto-backfill、low quorum 可见性、runtime cleanup、validate/HTML/Skill 对齐均有测试覆盖。

## 交付索引

- 设计：`docs/lct-auto-backfill-quorum-design-20260603.md`
- 实施交接：`docs/lct-auto-backfill-implementation-handoff-20260603.md`
- 运行记录：`notes.md`
- Markdown 简报：`docs/lct-auto-backfill-implementation-brief-20260603.md`
- HTML 简报：`docs/lct-auto-backfill-implementation-brief-20260603.html`
