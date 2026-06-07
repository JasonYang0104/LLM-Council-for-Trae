# Runtime Hardening Test Plan

日期：2026-06-01

## 测试原则

本轮采用 TDD **（注释：Test-Driven Development，测试驱动开发，先写失败测试，再写最小实现让测试通过）**。测试优先验证公共行为，不直接绑定私有实现细节。

每个切片按这个顺序推进：

1. 写一个能失败的行为测试。
2. 只写足够让该测试通过的实现。
3. 运行相关测试。
4. 再进入下一个行为。

## 必测行为

### Slice 1：Run Lease 防并发

行为：

- 当 store base 没有 active lock 时，`cmd_run` 可以获取 lease 并在结束后释放。
- 当 lock 对应 PID 仍活着时，第二个 run 快速失败，并输出可读错误。
- 当 lock 对应 PID 不存在时，新 run 可以清理 stale lock 并继续。

测试入口：

- 新增 `tests/test_runtime_hardening.py`。
- 优先测试 lease helper 的公共函数。
- 再用 `cmd_run` 的轻量 mock 路径测试失败出口。

验收：

- 不启动真实 traecli。
- 不依赖 sleep 或真实长进程。

### Slice 2：Stage 2 Timeout

行为：

- `stage2_collect_rankings` 在 `stage2_timeout` 内收集已完成 reviewer。
- 超时未完成 reviewer 会被标记为 `failed`。
- 至少一个完整 parse 的 reviewer 成功时，Stage 2 继续并写 `aggregate.json`。
- 所有 reviewer 失败或 parse 失败时，`run_full_council` 标记 manifest 为 `failed`。

测试入口：

- 使用 fake provider async side effect。
- 用短 timeout 配置，避免慢测试。

验收：

- 测试不超过数秒。
- 验证 review record、event、aggregate 三类可观察产物。

### Slice 3：Chairman Timeout 真值源

行为：

- Stage 3 调用 provider 时传入 `config.chairman_timeout`。
- provider 生成的 traecli command 使用该 timeout。
- `query_timeout` 仍控制 Stage 1 / Stage 2，不能被 chairman timeout 全局污染。

测试入口：

- fake provider 记录 `query_timeout` 参数。
- `_build_command` 验证 `--query-timeout` 文本。

验收：

- `config.json` 中的 `chairman_timeout` 与实际调用参数一致。

### Slice 4：Stage 3 Degraded Final

行为：

- chairman 和 fallback 全失败时，如果 Stage 2 aggregate 能定位最佳 Stage 1 ok response，生成降级 final。
- manifest 状态为 `degraded_ok`，CLI exit code 为 0，HTML export 可以继续。
- `stage3/final.json` 标明 `degraded_source`。
- 如果没有可用 aggregate 或映射不到 Stage 1 ok response，保持 `failed`。

测试入口：

- 单测 `stage3_synthesize_final` 的全失败降级路径。
- 集成式 fake `run_full_council` 测试 manifest 与 HTML gate。

验收：

- 不把主席失败伪装成 `ok`。
- failures 仍保留原始主席/fallback 错误。

### Slice 5：Process Group Cleanup

行为：

- provider timeout/cancel/budget kill 时调用统一 cleanup helper。
- POSIX 下尝试进程组清理。
- 不支持进程组时回退到直接 kill。

测试入口：

- 对 cleanup helper 用 fake proc 和 patched `os.killpg` 测试。
- 不创建真实长期子进程。

验收：

- 测试覆盖 timeout 和 cancellation 两条路径。

## 最终验证命令

完成前必须运行 fresh verification：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 live traecli 可用，再运行：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input examples/question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

如果 live run 未执行，最终汇报必须明确说是 skipped，并写出阻断点。
