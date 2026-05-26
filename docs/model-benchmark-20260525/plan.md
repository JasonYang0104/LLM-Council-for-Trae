# CLC 模型测试计划

## 目标

用 live COCO 数据评估 8 个候选模型在 CLC 三阶段流程里的可用性，重点看稳定性、时延、格式遵循和角色适配。测试结果用于决定默认 member roster 和 chairman 候选，不预设任何模型表现。

## 候选池

- `openrouter-2o`
- `GPT-5.4`
- `GLM-5.1`
- `DeepSeek-V4-Pro`
- `Kimi-K2.6`
- `Qwen3.6-Plus`
- `MiniMax-M2.7`
- `Gemini-3.1-Pro-Preview`

## 指标

- `status`: `ok` / `failed`
- `latency_seconds`
- `response_chars`
- `expected_model`
- `actual_model`
- `error`
- `parse_ok`
- `stage`
- `role`

## 任务分层

第一轮小样本不跑完整 8 模型 full council，先跑单模型角色模拟，降低失败定位成本。

- `short_judgment`: Stage 1 member 短中文判断。
- `structured_json`: Stage 1 member 固定 JSON 输出。
- `stage2_ranking`: Stage 2 reviewer，必须输出可解析 `FINAL RANKING`。
- `stage3_synthesis`: Stage 3 chairman，必须保留结论、关键证据和分歧。

## 判定口径

- `member` 默认候选必须没有明显高时延，且 member 相关任务 `status=ok`、`parse_ok=true`。
- `chairman` 优先稳定性；能力只按是否能完成结构化综合和保留分歧做最低可用性判断。
- `openrouter-2o` 只记录本环境实际可用性，不因模型描述中的 `Unavailable for L4 repos` 预判结果。
- `GPT-5.4` 之前出现过一次 300s timeout，只作为风险信号，不直接定性。

## 输出产物

- `README.md`: 本次 benchmark 索引和机器推荐摘要。
- `benchmark-config.json`: 测试配置。
- `runtime-models.json`: live `traecli models --json` 快照。
- `results.jsonl`: 逐次调用结果。
- `scorecard.csv`: 聚合指标。
- `recommended-rosters.json`: 机器推荐 roster。
- `recommended-rosters.md`: 人读版结论、证据和边界。
- `raw/`: 每次模型调用的原始 stream 和 stderr。
