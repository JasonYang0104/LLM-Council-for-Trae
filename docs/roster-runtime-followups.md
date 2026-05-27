# CLC 后续推进讨论稿

## 文档用途

这份文档不是结论文档，而是接下来我们持续沟通的工作底稿。

建议用法：

- 你直接在对应章节下面追加问题、批注、反例或新要求。
- 我后续基于这个文件继续更新判断、方案和代码改动建议。
- 如果某项从"讨论"进入"确定执行"，我会把状态从 `待讨论` 改成 `已确认` 或 `已落地`。

当前聚焦 5 个推进点：

1. `traecli -y` 默认化 → **已落地** ✅
2. candidate pool + quorum + chairman fallback → **代码已落地，quorum 覆盖 bug 待修复** ⚠️
3. timeout / cutoff 策略放宽并结构化 → **config 已加，未接线** ⚠️
4. 工具预算与长工具链失控治理 → **事后统计已实现，实时中断待做** ⚠️
5. partial output 救回与报告展示 → **已落地** ✅

***

## 推进点 1：`traecli -y` 默认化

**状态：已落地** ✅

- `TraeCliProvider(use_yolo=True)` 默认拼接 `--yolo`
- `--no-yolo` CLI 关闭开关
- `permission_mode` 字段记录在 meta.json
- E2E 验证通过

***

## 推进点 2：candidate pool + quorum + chairman fallback

**状态：代码已落地，有 bug 待修复** ⚠️

已实现：
- 供应商梯队表（roster.py）：8 组 primary → fallback
- `classify_stage1_status`：ok / degraded_ok / failed 三态
- chairman fallback：primary 失败后按 chain 降级
- manifest `metadata.chairman` 轨迹记录

待修复：
- **quorum 覆盖 bug**：`update_manifest_status` 中 failure 记录覆盖了 quorum 的 degraded_ok 判定。修复方向：quorum 优先，failure 只记录细节不覆盖总状态
- **min_valid_members 调整**：从 4/5 改为 6/8（用户 2026-05-26 确认）
- **主席不计入 quorum**：chairman 成功不算在 min_valid_members 内

***

## 推进点 3：timeout / cutoff 策略

**状态：config 已加，未接线** ⚠️

已实现：
- CouncilConfig 新增 `member_soft_checkpoint=300`、`member_quorum_checkpoint=480`、`member_hard_timeout=660`、`chairman_timeout=720`
- CLI 新增 `--member-mode normal|deep_research`

待实现：
- `query_model` 中实际使用分层超时（当前只用单一 query_timeout）
- 阈值需从 E2E 数据校准（当前全是拍脑袋）

***

## 推进点 4：工具预算与长工具链失控治理

**状态：事后统计已实现，实时中断待做** ⚠️

已实现：
- `parse_stream_json` 提取 `tool_calls_count` 和 `turns_count`
- `tool_budget_status` 三态：ok / near_limit / dropped_tool_budget
- 阈值存在 provider 实例上

待实现：
- **实时中断**：在子进程运行过程中流式读取 JSONL，实时计数，超限 kill
- 阈值校准：从 E2E stream.jsonl 提取实际分布

***

## 推进点 5：partial output 救回与报告展示

**状态：已落地** ✅

- `parse_stream_json` 提取 `assistant_content_chars_total`、`last_assistant_content_chars`、`raw_partial_recoverable`
- HTML 区分展示成功 / dropped / failed-with-partial
- E2E 验证通过

***

## 下一步优先级（2026-05-26 确认）

| 优先级 | 任务 | 依赖 |
|--------|------|------|
| P0 | quorum 覆盖 bug 修复（quorum 优先于 failure） | 无 |
| P0 | min_valid → 6, target → 8 + 主席不计入 quorum | 建议与 quorum bug 一起 |
| P0 | tool budget 实时中断（流式读取 + kill） | 无硬依赖 |
| P1 | 全量阈值数据驱动校准 | E2E stream.jsonl |
| P1 | HTML "模型表现摘要前置"（替换"存在警告"） | 无 |
| P1 | stage3 返回类型 TDD 处理 | 无 |
| P2 | 模型选择多维分析 | P1 数据提取 |
| P2 | 分层 timeout 实际接线 | P0 实时中断 + P1 校准 |
| P2 | degraded_ok + chairman fallback E2E 真实验证 | P0 quorum 修复 |
