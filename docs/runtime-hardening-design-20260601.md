# Runtime Hardening Design

日期：2026-06-01

## 目标

这轮不重做 LCT，也不扩展 Web UI、OpenRouter 或旧 TR。目标是把现有 CLI runtime 从“能跑”推进到“可靠、可解释、可恢复”。

本轮实现范围按优先级收敛为：

1. P0 防自爆：run 级互斥，避免多个 live run 同时抢同一批模型资源。
2. P0 防卡死：Stage 2 增加超时与可收敛结果，避免任一 reviewer hang 住拖死整个 run。
3. P1 说真话：`chairman_timeout` 接入 Stage 3 控制流，config 中展示的 timeout 必须真实生效。
4. P2 可收场：Stage 3 主席与 fallback 全失败时，基于 Stage 2 聚合排序输出降级 final，允许 HTML 继续生成。
5. P2 可恢复：provider 超时、取消或预算杀进程时尽量清理进程组，减少 orphan traecli 风险。

## 非目标

- 不重新设计 council protocol。
- 不修改 HTML export 的职责边界；HTML 仍只渲染 artifacts。
- 不把 fake runtime 或单元测试结果说成 live traecli 结果。
- 不尝试绕开已知 `traecli` pipe hang 约束；`utils.run_command` 继续保留 `os.system + 临时文件重定向`。
- 不做 P3 数据化优化，例如 retry backoff、长期 telemetry、性能 dashboard。

## 当前代码事实

当前代码已经有一部分 runtime hardening：

- Stage 1 有 `member_soft_checkpoint`、`member_quorum_checkpoint`、`member_hard_timeout`。
- Stage 1 quorum 已经支持 `ok` / `degraded_ok` / `failed`。
- provider 有 per-model query timeout、部分 retry、tool budget 统计和 budget kill。
- Stage 3 已有 chairman fallback 链，但 `chairman_timeout` 尚未接入实际控制流。
- Stage 2 仍是 `asyncio.gather`，任一任务长期不返回会拖住整个阶段。
- run 启动没有互斥 lease，同一 store 下可并发创建多个 live run。
- Stage 3 全失败会把 manifest 标成 `failed`，导致 HTML export 被跳过。

## 设计方案

### 1. Run Lease

新增轻量 run lease，文件位于 store base：

```text
.llm-council-for-trae/runs/.runtime/run.lock
```

lease 内容：

```json
{
  "run_id": "run-...",
  "pid": 12345,
  "created_at": "...",
  "command": "llm-council-for-trae run"
}
```

行为：

- `cmd_run` 在创建 run 目录和调用模型前获取 lease。
- 若 lock 存在且 PID 仍活着，则快速失败，返回结构化错误，避免资源争抢。
- 若 lock 存在但 PID 已不存在，则视为 stale lock，覆盖并记录 warning。
- run 结束后释放 lease。
- 这轮先做 run 级互斥，不实现 global slot lease / model lease。原因是当前故障首先来自多 run 并发，单 run 内保留 Stage 1 并行度仍是产品价值。

### 2. Stage 2 Timeout

新增 `stage2_timeout` 到 `CouncilConfig` 和 `config.json`，默认取 `query_timeout + 30` 与 240 秒中的较大值。

Stage 2 改为和 Stage 1 类似的任务收集循环：

- 对每个 reviewer 创建 task。
- 在 `stage2_timeout` 内收集完成的 review。
- 超时后取消剩余 task，并为未完成 reviewer 生成 `status=failed`、`error=cancelled_by_stage_timeout` 的 review record。
- 只要存在至少一个 `status=ok` 且 `parse_status=ok` 的 review，就继续聚合和 Stage 3。
- 若没有有效 review，则 manifest 为 `failed`。

### 3. Chairman Timeout

`chairman_timeout` 必须控制 Stage 3 每一次 chairman/fallback 调用的等待窗口。

实现方式：

- `TraeCliProvider.query_model` 增加可选 `query_timeout` 参数，覆盖 provider 默认 timeout。
- `_build_command` 使用本次调用 timeout 生成 `--query-timeout`。
- `_query_model_once` 使用本次调用 timeout 做 `asyncio.wait_for(..., timeout=query_timeout + 30)`。
- Stage 3 调用 primary chairman 和每个 fallback 时传入 `config.chairman_timeout`。

这保持 provider 默认 query timeout 仍用于 Stage 1 / Stage 2，不扩大普通成员调用窗口。

### 4. Stage 3 Degraded Final

当 primary chairman 和全部 fallback 均失败时，系统应尽量交付一个可解释的降级 final。

降级策略：

1. 读取 Stage 2 aggregate rankings。
2. 选择 `average_rank` 最低的 model。
3. 找到对应 Stage 1 ok response。
4. 写入 `stage3/final.md` 和 `stage3/final.json`。
5. `final.json.status = "degraded_ok"`，并记录 `degraded_source = "stage2_best_stage1_response"`。
6. manifest status 至少保持或降级为 `degraded_ok`，不因 Stage 3 主席失败直接变成 `failed`。
7. warnings 记录主席路径失败，failures 仍记录原主席/fallback 错误。

如果 aggregate 缺失或无法映射到 Stage 1 ok response，则不能伪造成功，保持 `failed`。

### 5. Process Group Cleanup

provider 创建 traecli 子进程时设置新进程组；超时、取消、budget kill 时优先终止整个进程组。

行为：

- POSIX 环境使用 `start_new_session=True` 创建子进程。
- cleanup 先尝试 `SIGTERM`，短暂等待后仍未退出再 `SIGKILL`。
- Windows 或不支持进程组的环境回退到 `proc.kill()`。

## 状态语义

- `ok`：所有关键阶段正常完成。
- `degraded_ok`：有失败或降级，但已生成可用最终答案和 HTML。
- `failed`：没有足够证据生成最终答案，或 runtime 前置检查失败。

Stage 3 降级不是“主席成功”，必须在 `stage3/final.json`、manifest warnings 和 PM brief 中明确说明。

## Subagent 合同

这轮 subagent 只做并行审查，不直接改共享 runtime 文件。

范围：

- 阅读本设计、测试方案、`council.py`、`provider.py`、`cli.py`、`validation.py`、`tests/test_core.py`。
- 输出可能遗漏的测试点、实现风险、状态语义冲突。

边界：

- 不编辑文件。
- 不重写方案。
- 不验证 live traecli。

输出契约：

- `must_fix`：会导致行为错误或测试遗漏的问题。
- `nice_to_have`：本轮可不做的后续建议。
- `scope_risk`：是否发现超出本轮边界的风险。

验收：

- 主线程会抽检 subagent 结论；只有和设计目标一致的项进入实现。
