# Implementation Notes

## Phase 1: --yolo 默认化

### 决定：提取 `_build_command` 方法
provider.py 的 `query_model` 里命令构建逻辑内联在方法中。为了可测试性，提取为 `_build_command` 方法，这样测试可以直接验证命令内容而不需要跑真实子进程。

### 决定：`permission_mode` 字段值
- `use_yolo=True` → `permission_mode="bypass_permissions"`
- `use_yolo=False` → `permission_mode="default"`
这和 traecli 的实际行为对齐。

### 决定：`--no-yolo` 而非 `--yolo`
CLI 默认行为是带 yolo，所以只需要一个关闭开关 `--no-yolo`，不需要 `--yolo` 开启开关。

## Phase 2: Quorum

### 决定：`classify_stage1_status` 独立函数
从 `update_manifest_status` 中分离出 quorum 判定逻辑，使其可独立测试。

### 决定：manifest status 三态
- `"ok"` — 全部成功
- `"degraded_ok"` — 达到 quorum 但有失败
- `"failed"` — 未达 quorum

### 权衡：`update_manifest_status` 和 `update_manifest_with_stage1_status` 并存
原有的 `update_manifest_status` 仍然负责记录 failures 和设置 failed 状态。新增的 `update_manifest_with_stage1_status` 在其之前调用，先根据 quorum 判定设置 degraded_ok。两者配合：如果 quorum 说 ok/degraded_ok，但后续 update_manifest_status 发现了 failure，会覆盖为 failed。这是合理的——quorum 只管 stage1 的整体判定，但任何 failure 都应该被记录。

## Phase 3: Chairman Fallback

### 决定：stage3 返回 tuple
`stage3_synthesize_final` 改为返回 `(final_result, chairman_meta)` 元组，而不是只返回 final_result。这是一个 breaking change，但所有调用方（只有 `run_full_council`）都已更新。

### 决定：fallback 时 label 用 `final-fb-{model}`
避免和 primary chairman 的 `final` label 冲突。

## Phase 4: Timeout + Budget

### 决定：阈值存在 provider 实例上
`explore_tool_limit`, `explore_turn_limit`, `deliver_tool_limit`, `deliver_turn_limit` 存在 `TraeCliProvider` 实例上，而不是 CouncilConfig。这样产品层不需要暴露这些细碎参数。

### 权衡：tool_budget_status 的判定时机
当前在 `query_model` 返回后判定，基于整个 stream 的 tool_calls_count 和 turns_count。这是事后统计，不是实时中断。如果需要实时中断，需要在 stream 消费过程中做 checkpoint，当前版本暂不实现。

## Phase 5: Partial Output

### 决定：`raw_partial_recoverable` 的判定条件
当 `assistant_content_chars_total > 0` 且最终结果为空或出错时，标记为 `raw_partial_recoverable=True`。这意味着有内容可以救回，但不保证内容完整。

## E2E 发现的问题

### GPT-5.4 traecli result error
Q1 首次 E2E 中，GPT-5.4 和 DeepSeek-V4-Pro 都返回 `traecli result error`，只有 GLM-5.1 成功。3-member run 中只有 1 个成功，达不到 quorum（min_valid=4）。这证实了讨论稿中关于 GPT-5.4 不稳定的判断。

### 解决方案
用更稳定的模型组合（GLM-5.1, Qwen3.6-Plus, Kimi-K2.6）和降低 min-valid-members=2 重跑。
