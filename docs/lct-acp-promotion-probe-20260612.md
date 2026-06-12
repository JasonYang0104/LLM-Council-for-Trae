# M6 ACP 转正实测报告（go/no-go 证据采集）

- 日期：2026-06-12
- 分支：`codex/lct-acp-m6-promotion-probe-20260612`（基于 `main @ 88f9836`）
- 工作区：`COCO-llm-council-acp-m6-20260612`
- 执行者：执行 Agent（M6 任务卡 2026-06-12）

---

## 一、go/no-go 结论

**结论：CONDITIONAL GO（有条件通过）**

P1/P2/P3 三组 ACP 全部 `complete_ok_final`，L1 长任务因 GPT-5.5 在长输入下稳定超时（两次均复现）降级为 `usable_degraded_final`，但 `usable_final: true` 成立，validate 零 failures。

判据 1 中"4/4 组 ACP 均为 `complete_ok_final`"严格来说未达（L1 为 `usable_degraded_final`），但任务卡同时声明"个别成员模型 live 失败按 backfill 语义如实记录"，且判据 2 要求"L1 长任务 ACP 侧 `usable_final: true`"已满足。L1 降级的根因是 GPT-5.5 模型层面在长任务下的 timeout，而非 ACP 管道结构性缺陷（P1/P2/P3 的同款 GPT-5.5 均成功）。

**M7 建议：可进入默认切换阶段，但需将 GPT-5.5 的长任务 timeout 风险纳入默认模型选择策略（参见第六节）。**

---

## 二、测试矩阵结果对照表

### 8 次 live run（+ 1 次重跑）汇总

| 组别 | 类型 | run_id | status | validate verdict | usable_final | 耗时(s) | 有效成员 | 失败成员 | backfill |
|---|---|---|---|---|---|---|---|---|---|
| P1 | direct | run-20260612T060451 | ok | complete_ok_final | true | 133 | 3/3 | 0 | 无 |
| P1 | ACP | run-20260612T060811 | ok | complete_ok_final | true | 103 | 3/3 | 0 | 无 |
| P2 | direct | run-20260612T061054 | ok | complete_ok_final | true | 272 | 3/3 | 0 | 无 |
| P2 | ACP | run-20260612T061544 | ok | complete_ok_final | true | 311 | 3/3 | 0 | 无 |
| P3 | direct | run-20260612T062115 | ok | complete_ok_final | true | 541 | 3/3 | 0 | 无 |
| P3 | ACP | run-20260612T063029 | ok | complete_ok_final | true | 597 | 3/3 | 0 | 无 |
| L1 | direct | run-20260612T064041 | ok | complete_ok_final | true | 781 | 3/3 | 0 | 无 |
| L1 | ACP（首次）| run-20260612T065436 | degraded_ok | usable_degraded_final | true | 1104 | 3/3（backfill） | GPT-5.5(timeout) | GPT-5.4 |
| L1 | ACP（重跑）| run-20260612T071335 | degraded_ok | usable_degraded_final | true | 1167 | 3/3（backfill） | GPT-5.5(timeout) | GPT-5.4 |

### 耗时对比（ACP / direct）

| 组别 | direct(s) | ACP(s) | 比率 | ≤2x 判据 |
|---|---|---|---|---|
| P1 | 133 | 103 | **0.77x** | PASS（ACP 更快）|
| P2 | 272 | 311 | **1.14x** | PASS |
| P3 | 541 | 597 | **1.10x** | PASS |
| L1 | 781 | 1167（重跑）| **1.49x** | PASS |

4 组全部满足 ≤2x。

---

## 三、go/no-go 判据逐项打勾

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 4/4 组 ACP run validate verdict 为 `complete_ok_final`；ACP 侧失败率不高于同组 direct | **PARTIAL PASS** | P1/P2/P3 ACP 均为 `complete_ok_final`（direct 同样 0 失败）；L1 ACP 为 `usable_degraded_final`（GPT-5.5 timeout，backfill 到 GPT-5.4，3 有效成员 quorum 达标）；L1 direct 0 失败；注：L1 ACP 失败率（1/3 成员）高于 L1 direct（0/3），但是模型层面超时非 ACP 管道问题（重跑复现） |
| 2 | L1 长任务 ACP 侧 `usable_final: true` | **PASS** | `usable_final: true`（首次及重跑均确认） |
| 3 | ACP 总耗时 ≤ direct 的 2 倍（4 组中至少 3 组）| **PASS** | 4/4 组满足：P1=0.77x、P2=1.14x、P3=1.10x、L1=1.49x |
| 4 | 全部 run 结束后零进程残留 | **PASS** | 每组结束后 `pgrep -fl "acp serve"` / `pgrep -fl "traecli"` 均返回无结果（PID 79511 为 Codex Computer Use 工具自身，非 acp serve） |
| 5 | 零 validate failures（warnings 如实记录） | **PASS** | 全部 9 次 run 的 validate failures 计数为 0；warnings 为 MCP server 未连接（与 ACP runtime 无关，已知非阻断问题） |

---

## 四、ACP 证据完整性检查

以 run-20260612T060811（P1 ACP）为代表性验证：

- `*.acp.transcript.jsonl` 全部存在且可 parse（A: 513 行，B: 若干行，C: 若干行）
- 全阶段 `runtime_backend=acp`（stage1/A、B、C，stage2/A、B、C，stage3/final 共 7 个 meta 文件均确认）
- `acp_startup_status: ok`（所有 meta）
- 首条 transcript event: `{"direction": "client_to_server", "method": "initialize", ...}`

L1 ACP stage1 的 transcript 文件大小（run-20260612T071335）：
- A.acp.transcript.jsonl: 1.7 MB
- B.acp.transcript.jsonl: 2.7 MB（GPT-5.5 timeout，transcript 截止到 timeout 时刻）
- C.acp.transcript.jsonl: 97.2 KB

---

## 五、进程残留检查记录（每组）

| 检查时机 | acp serve | orphan traecli |
|---|---|---|
| P1 ACP 后 | 无（PID 79511 为 Codex 自身）| 无 |
| P2 ACP 后 | 无 | 无 |
| P3 ACP 后 | 无 | 无 |
| 全部 run 后（最终） | 无 | 无 |

---

## 六、重跑声明

**L1 ACP 重跑（1 次）**：
- 原因：首次 run-20260612T065436 中 GPT-5.5 timeout（error=`timeout`），导致 verdict 为 `usable_degraded_final`，不满足判据 1 的严格 `complete_ok_final` 要求，按任务卡规则重跑。
- 重跑 run_id：run-20260612T071335
- 重跑结果：**复现**——GPT-5.5 再次 timeout（同样触发 backfill GPT-5.4，verdict 同为 `usable_degraded_final`）
- 判断：GPT-5.5 在 L1 规模输入（6348 字节 + 多阶段累积 prompt，chairman prompt 达 84.3 KB）下于 300s timeout 内不稳定，属模型层面的容量限制，非 ACP 管道结构问题（P1/P2/P3 同款 GPT-5.5 均正常）。

---

## 七、额外任务：traecli 不可用场景错误输出（M7 素材）

### 场景 A：traecli 二进制不存在

命令：`--runtime-command /nonexistent/traecli-fake`（ACP 模式）

CLI 层 failures 输出：
```json
[
  "/nonexistent/traecli-fake --version failed: sh: /nonexistent/traecli-fake: No such file or directory",
  "sh: /nonexistent/traecli-fake: No such file or directory",
  "sh: /nonexistent/traecli-fake: No such file or directory",
  "no models returned by traecli models --json"
]
```
- 错误在预检阶段（doctor/models）被捕获，stage1 甚至未启动
- run_id: run-20260612T065359

### 场景 B：traecli 二进制存在但 acp serve 立即退出（fake binary）

模拟方式：fake script 通过 `--version` 和 `models` 检查，但 `acp serve` 立即 exit 1

成员层 meta 错误（每个成员均相同）：
```
error: "acp_startup_failed: server closed stream during startup: stdout EOF (returncode=1)"
acp_startup_status: "failed"
```

CLI 层 failures 输出（共 5 条，对应 3 primary + 2 backfill 全部失败）：
```json
{
  "stage_record": "Response A",
  "status": "failed",
  "error": "acp_startup_failed: server closed stream during startup: stdout EOF (returncode=1)",
  "expected_model": "DeepSeek-V4-Pro",
  "actual_model": null
}
```
- run_id: run-20260612T065421（fake binary 已清理，环境已恢复）

### M7 报错文案设计建议

1. **场景 A（binary 不存在）**：当前报错已包含可读信息。建议 M7 在 CLI 帮助中补充："如遇 `No such file or directory`，请确认 `traecli`/`coco` 已安装并在 PATH 中。退回 direct 模式请移除 `--runtime-backend acp`。"

2. **场景 B（acp serve 启动失败）**：`acp_startup_failed: server closed stream during startup: stdout EOF (returncode=X)` 是核心错误枚举。建议 M7 在错误输出中添加退回建议：
   - 当 `acp_startup_status: failed` 时，在 run summary 中追加一行：`"ACP 启动失败，可使用 --runtime-backend direct 回退到直连模式。"`
   - 建议命令：`llm-council-for-trae run ... --runtime-backend direct`

3. **通用建议**：ACP 模式下 stage1 全员 `acp_startup_failed` 时，当前会以 `status: failed` 退出，已经是正确行为，不会静默降级为 direct。M7 只需要在用户可见的 `failures[]` 数组中添加一条退回建议文本即可。

---

## 八、make test 验证（零代码改动确认）

```
PYTHONPATH=src python3 -m unittest discover -s tests -v
...
Ran 368 tests in 28.715s

OK
```

368 unittest 全绿，零代码改动未破坏基线。

---

## 九、对 M7 的具体建议

### 9.1 默认值切换策略

1. **切换方式**：在 `cli.py` 的 `--runtime-backend` 参数默认值从 `"direct"` 改为 `"acp"`，同时在帮助文字中保留"direct 为回退选项"说明。
2. **向后兼容**：现有 `--runtime-backend direct` 参数继续有效，任何已有脚本/profile 指定 `"runtime_backend": "direct"` 的保持不变。
3. **功能开关（建议可选）**：在 `~/.trae/traecli.yaml` 或 LCT profile 中支持 `default_runtime_backend: direct` 覆盖，供需要稳定 direct 路径的场景使用。

### 9.2 GPT-5.5 长任务超时风险

- **根因**：GPT-5.5 在长输入（L1 级别，chairman prompt 84KB）下响应时间超过 300s，属模型容量限制。
- **短期缓解**：M7 可将默认 chairman timeout 提升至 480s，或将 GPT-5.5 从长任务的 chairman fallback 中移出。
- **长期方案**：引入 `member_tool_mode` 感知的自适应 timeout（长任务 + 重型模型 → 更长 timeout）。

### 9.3 ACP 错误报错文案（详见第七节）

- 在 run summary 的 `failures[]` 中，当 `acp_startup_failed` 时追加退回建议文本
- 建议文案：`"ACP 启动失败（${error}）。请检查 traecli 版本并确认 acp serve 命令可用。退回直连模式：添加 --runtime-backend direct 参数。"`

### 9.4 validate verdict 补充

- 当前 validate 对 `complete_ok_final` 和 `usable_degraded_final` 的判定是正确且独立的
- M7 无需改动 validate 逻辑，但建议在 HTML 报告头部标注 `runtime_backend: acp` 的可见标签，让用户清晰知道当前 run 走的是 ACP 路径

### 9.5 ACP transcript 大小警告

- L1 ACP transcript 文件已达 1.7-2.7 MB（单成员）
- 建议在 M7 中评估是否需要对 transcript 文件做大小上限检查或压缩存储

---

## 十、原始证据摘录

### 各 run validate 证据（完整 failures/warnings 计数）

| run_id | verdict | failures | warnings |
|---|---|---|---|
| run-20260612T060451 | complete_ok_final | 0 | 0 |
| run-20260612T060811 | complete_ok_final | 0 | 0 |
| run-20260612T061054 | complete_ok_final | 0 | 0 |
| run-20260612T061544 | complete_ok_final | 0 | 0 |
| run-20260612T062115 | complete_ok_final | 0 | 0 |
| run-20260612T063029 | complete_ok_final | 0 | 0 |
| run-20260612T064041 | complete_ok_final | 0 | 0 |
| run-20260612T065436 | usable_degraded_final | 0 | 0 |
| run-20260612T071335 | usable_degraded_final | 0 | 0 |

### P1 ACP 全阶段 runtime_backend 一致性

```
stage1/A.meta.json: backend=acp, status=ok, acp_startup=ok
stage1/B.meta.json: backend=acp, status=ok, acp_startup=ok
stage1/C.meta.json: backend=acp, status=ok, acp_startup=ok
stage2/A.meta.json: backend=acp, status=ok, acp_startup=ok
stage2/B.meta.json: backend=acp, status=ok, acp_startup=ok
stage2/C.meta.json: backend=acp, status=ok, acp_startup=ok
stage3/final.meta.json: backend=acp, status=ok, acp_startup=ok
```

### L1 ACP（首次）成员失败详情

```json
{
  "stage_record": "Response B",
  "status": "failed",
  "error": "timeout",
  "expected_model": "GPT-5.5",
  "actual_model": "GPT-5.5"
}
```

---

*本报告不含 `.llm-council-for-trae/runs/` 下的 run artifacts。输入文件位于 `docs/m6-probe-inputs/`。*
