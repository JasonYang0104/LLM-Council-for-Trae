# 执行方案：retrospective-20260527 评论修复

## 变更清单

### C1: ModelCallResult 新增字段 + 数据透传（P2 + 首评）

**问题链**：`ModelCallResult` 缺 `tool_calls_count`/`turns_count` → 结果字典缺 4 字段 → manifest 缺字段 → HTML 模型表现摘要全空白

**改动文件**：

1. `provider.py` - `ModelCallResult` dataclass
   - 新增 `tool_calls_count: int = 0`
   - 新增 `turns_count: int = 0`
   - 新增 `retried: bool = False`（C2 复用）
   - 新增 `retry_error: str | None = None`（C2 复用）
   - `to_json()` 包含新字段

2. `provider.py` - `query_model` 函数
   - 从 `parsed.get("tool_calls_count", 0)` 赋值给 `ModelCallResult.tool_calls_count`
   - 从 `parsed.get("turns_count", 0)` 赋值给 `ModelCallResult.turns_count`

3. `council.py` - `stage1_collect_responses`
   - 结果字典新增：`tool_calls_count`, `turns_count`, `tool_budget_status`, `raw_partial_recoverable`

4. `council.py` - `stage2_collect_rankings`
   - 同上

5. `council.py` - `stage3_synthesize_final`
   - 同上

### C2: traecli result error 自动重试 1 次（P0）

**改动文件**：

1. `provider.py` - `query_model` 函数
   - 检测 runtime 错误：`parsed.get("error")` 包含 "result error" 或 proc.returncode != 0 且错误匹配 runtime 模式
   - 等待 10s（`asyncio.sleep(10)`）
   - 重试 1 次：重新调用 `query_model` 内部逻辑
   - 设置 `retried=True`，`retry_error` 记录首次错误
   - 重试仅针对 runtime 错误，不针对模型层面错误（空回复、格式错误等）

**实现方式**：将 `query_model` 的核心逻辑提取为 `_query_model_once`，`query_model` 调用 `_query_model_once`，失败时重试。

### C3: HTML 模型表现摘要位置修复（首评）

**改动文件**：

1. `html_export.py` - `render_summary_cards`
   - 移除 "Quorum 状态" card
   - 移除 "主席降级" card（fallback_trace）
   - 保留 "最高排序成员"、"成员模型"、"主席模型" 三个 card
   - grid 从 4 列改为 3 列

2. `html_export.py` - `render_html`
   - 将 `render_model_performance_summary(manifest)` 从 decision-summary 和 evidence 之间移入 decision-summary section 内部
   - 位置：summary-strip 之后、`</section>` 之前
   - 移除独立 `<section id='model-performance'>` 包裹，改为 `<div class='model-performance'>` 嵌入 decision-summary

3. `html_export.py` - `render_alerts`
   - 移除 Quorum 降级横幅（已在模型表现摘要中可推断）

### C4: degraded_ok 退出码改为 0（P3）

**改动文件**：

1. `cli.py` - `run` 命令
   - `status in ("ok", "degraded_ok")` 时退出码 0
   - JSON 输出中 `degraded_ok` 时标注 `degraded: true`

### C5: chairman 兼任 member quorum 逻辑优化（P4）

**改动文件**：

1. `council.py` - `classify_stage1_status`
   - 检测 chairman 是否在 members 列表中（`chairman_model in [r.get("model") for r in results]`）
   - 如果 chairman 兼任 member：
     - chairman ok → 计入 ok_count，total 包含 chairman
     - chairman failed → 从 ok_count 和 total 中同时排除（"失败免费"）
   - 如果 chairman 独立（不在 members 列表）：
     - 保持当前行为：完全排除

**验证矩阵**（8 成员，chairman=GPT-5.4，min_valid=6）：

| 场景 | chairman ok? | 其他 ok | 旧逻辑 | 新逻辑 |
|---|---|---|---|---|
| 全部 ok | ✅ | 7/7 | ok | ok |
| 仅 chairman 失败 | ❌ | 7/7 | degraded_ok (7/7≥6) | **ok** (7/7, chairman 失败免费) |
| chairman ok + 1 其他失败 | ✅ | 6/7 | degraded_ok (6/7≥6) | degraded_ok (7/8≥6) |
| chairman 失败 + 1 其他失败 | ❌ | 6/7 | degraded_ok (6/7≥6) | degraded_ok (6/7≥6) |
| chairman 失败 + 2 其他失败 | ❌ | 5/7 | failed (5/7<6) | failed (5/7<6) |

## 测试计划

### 新增单元测试

1. `test_model_call_result_new_fields`：验证 ModelCallResult 新字段默认值和 to_json 输出
2. `test_query_model_assigns_tool_counts`：验证 query_model 将 tool_calls_count/turns_count 赋给 ModelCallResult
3. `test_stage1_result_dict_has_metrics`：验证 stage1 结果字典包含 4 个指标字段
4. `test_stage2_result_dict_has_metrics`：同上
5. `test_stage3_result_dict_has_metrics`：同上
6. `test_retry_on_result_error`：验证 result error 触发重试
7. `test_no_retry_on_model_error`：验证模型层错误不触发重试
8. `test_retry_metadata`：验证 retried/retry_error 字段
9. `test_html_summary_cards_no_quorum`：验证 render_summary_cards 不包含 Quorum 状态 card
10. `test_html_model_performance_inside_decision_summary`：验证模型表现摘要在 decision-summary 内
11. `test_degraded_ok_exit_code_zero`：验证 degraded_ok 退出码为 0
12. `test_degraded_ok_json_flag`：验证 degraded_ok JSON 输出包含 degraded: true
13. `test_chairman_as_member_ok_counts`：验证 chairman 兼任 member 时 ok 计入 quorum
14. `test_chairman_as_member_failed_free`：验证 chairman 兼任 member 时失败免费
15. `test_chairman_independent_excluded`：验证独立 chairman 仍被排除

## 执行顺序

1. C1 (数据透传) → 最基础，其他改动依赖
2. C2 (重试) → 依赖 C1 的 ModelCallResult 新字段
3. C3 (HTML 位置) → 依赖 C1 的数据
4. C4 (退出码) → 独立改动
5. C5 (quorum 逻辑) → 独立改动
6. 全量测试
7. E2E 验证
