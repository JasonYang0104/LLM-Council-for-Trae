# CLC 模型基准测试

生成时间：`2026-05-25T07:28:44Z`

## 产物

- `benchmark-config.json`：测试配置和任务定义。
- `runtime-models.json`：本次 `traecli models --json` 快照。
- `results.jsonl`：逐次调用结果。
- `scorecard.csv`：按模型聚合的稳定性、格式和时延指标。
- `recommended-rosters.json`：机器生成的候选 roster。
- `recommended-rosters.md`：结合 full council 验证后的人读版推荐。
- `raw/`：每次 `traecli` 调用的 stream 和 stderr 证据。

## 机器推荐

- fast_default_members: `MiniMax-M2.7, openrouter-2o`
- analysis_default_members: `MiniMax-M2.7, openrouter-2o, GPT-5.4`
- research_stress_members: `MiniMax-M2.7, openrouter-2o, GPT-5.4, Kimi-K2.6`
- chairman: `GLM-5.1`

注意：机器推荐只基于单模型 benchmark。最终默认建议以 `recommended-rosters.md` 为准；本轮唯一通过复杂 full council + validate 的组合是 `DeepSeek-V4-Pro,Qwen3.6-Plus / GLM-5.1`。

## Scorecard

| model | samples | success | parse | p95 latency | failed |
| --- | ---: | ---: | ---: | ---: | ---: |
| `DeepSeek-V4-Pro` | 8 | 1.00 | 0.88 | 36.53 | 0 |
| `GLM-5.1` | 8 | 1.00 | 0.88 | 33.58 | 0 |
| `GPT-5.4` | 8 | 1.00 | 1.00 | 76.98 | 0 |
| `Gemini-3.1-Pro-Preview` | 8 | 0.88 | 1.00 | 73.30 | 1 |
| `Kimi-K2.6` | 8 | 1.00 | 1.00 | 120.93 | 0 |
| `MiniMax-M2.7` | 8 | 1.00 | 1.00 | 35.37 | 0 |
| `Qwen3.6-Plus` | 8 | 1.00 | 0.88 | 45.22 | 0 |
| `openrouter-2o` | 8 | 1.00 | 1.00 | 44.89 | 0 |
