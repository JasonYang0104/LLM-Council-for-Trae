# Runtime Hardening Implementation Brief

日期：2026-06-01
对象：产品负责人 / PM director

## 一句话结论

这轮把 LCT runtime 从“能跑但容易在真实使用中误判或卡住”，推进到“有互斥、有超时、有降级、有清理、有可验证状态”的阶段。它仍不是最终成熟 runtime，但已经解决了 2026-06-01 外部复盘里最容易造成用户误操作和假失败的主链路问题。

## 为什么要做

外部测试证明，LCT 的入口和基本 council 流程已经成立；失败点不再是“不会启动”，而是运行期治理不足：

- 多个 run 被重复启动，争抢同一批模型资源。
- Stage 2 reviewer 可能挂住整个 run。
- `chairman_timeout` 写进 config，却没有真实控制主席阶段。
- Stage 3 全失败时，明明已有 Stage 1/2 证据，却不能生成可交付降级结果。
- 超时或取消时，traecli 子进程清理不够稳。

这类问题会让 Agent 在错误时间做错误操作：重复启动、过早 kill、把 degraded 误报成 failed、或者把环境噪音当产品失败。

## 这轮解决了什么

### P0 防自爆

新增 run lease：

- 同一 store 下只允许一个 live run 持有 `.runtime/run.lock`。
- active lock 会让第二个 run 快速失败。
- stale lock 和 malformed lock 会被识别并替换。
- lock 创建改为原子 `O_EXCL`，避免 `exists -> write` 的竞争窗口。

### P0 防卡死

Stage 2 增加 `stage2_timeout`：

- reviewer 在超时内返回就被纳入排序。
- 超时 reviewer 被标记为 `failed`，并写入 review/meta/stream sidecar。
- 至少一个有效 review 存在时继续 Stage 3。
- partial Stage 2 failure 会把 run 标为 `degraded_ok`，不再伪装成 `ok`。

### P1 说真话

`chairman_timeout` 已经接入 Stage 3：

- primary chairman 和 fallback chairman 都使用该 timeout。
- CLI 新增 `--chairman-timeout`。
- CLI 新增 `--stage2-timeout`，让 Stage 2 控制也可显式设置。

### P2 可收场

Stage 3 全失败时新增 degraded final：

- 如果 Stage 2 能定位最佳 Stage 1 回答，系统会把该回答作为降级 final。
- `stage3/final.json` 标记 `status=degraded_ok` 和 `degraded_source=stage2_best_stage1_response`。
- primary/fallback 失败证据保留在 manifest failures。
- HTML export gate 接受 `degraded_ok`，用户仍能拿到报告。

### P2 可恢复

provider 超时、取消、tool budget kill 时统一走进程树清理：

- POSIX 下优先清理 process group。
- 不支持 process group 时回退到直接 kill。

## 验证证据

本轮非 live 验证全部通过：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

结果：

- `compileall`：pass
- `make test`：pass，94 tests
- `git diff --check`：pass

live smoke 也跑过：

```bash
PYTHONPATH=src python3 -m llm_council_for_trae.cli --json run \
  --input examples/question.md \
  --default-models \
  --run-id runtime-hardening-smoke-20260601 \
  --timeout 60 \
  --stage2-timeout 90 \
  --chairman-timeout 180 \
  --json
```

结果：

- `run_id`：`runtime-hardening-smoke-20260601`
- run status：`degraded_ok`
- validate status：`degraded_ok`
- validate failure count：`0`
- HTML：`.llm-council-for-trae/runs/runtime-hardening-smoke-20260601/html/index.html`

这不是“所有模型完美成功”的证据；它更重要地证明了 degraded 路径现在能真实交付并通过 validate。

## 没有解决什么

本轮没有做 P3：

- 没有实现 global slot lease / model lease。
- 没有做长期 telemetry 或模型稳定性画像。
- 没有合并 provider retry 和 council retry。
- 没有重新设计默认模型 roster。

这些不是遗漏，而是刻意不扩 scope。当前最需要的是先让 runtime 不自爆、能说真话、失败后可交付。

## 交付文件索引

- 设计方案：`docs/runtime-hardening-design-20260601.md`
- 测试方案：`docs/runtime-hardening-test-plan-20260601.md`
- 运行记录：`notes.md`
- 简报 Markdown：`docs/runtime-hardening-implementation-brief-20260601.md`
- 简报 HTML：`docs/runtime-hardening-implementation-brief-20260601.html`
- 核心代码：`src/llm_council_for_trae/runtime.py`、`src/llm_council_for_trae/council.py`、`src/llm_council_for_trae/provider.py`、`src/llm_council_for_trae/cli.py`、`src/llm_council_for_trae/validation.py`
- 新增测试：`tests/test_runtime_hardening.py`

## 下一步建议

下一轮应该进入 P3，但不要混在本轮提交里：

1. 引入 model lease，限制同一模型被多个 run 或多个阶段同时争抢。
2. 用真实 run artifacts 建立模型稳定性和时延画像。
3. 清理双重 retry，避免资源拥塞时重试放大问题。
4. 基于 live 数据重新校准默认 roster 和 timeout。
