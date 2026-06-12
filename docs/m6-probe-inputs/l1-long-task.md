# L1 长任务：LCT（LLM-Council-for-Trae）ACP 迁移架构综合评估

## 背景材料

以下为 LCT 项目的核心架构文档节选，请基于这些材料进行综合分析。

---

### 材料一：ACP Runtime 迁移路线（节选自 lct-acp-migration-architecture）

LCT 项目正在从 direct runtime（直接调用 traecli）迁移到 ACP runtime（通过 JSON-RPC 协议的 ACP 模式）。

**迁移决策要点：**
1. **不整体 merge 研究分支**（behind 56 commits）：按 P0→P3 逐阶段移植到从最新 main 切出的新分支。
2. **process-per-query 架构**：一次 `query_model()` = 一个 `traecli acp serve` 进程 = 一段独立 transcript 证据。放弃长驻 server 多路复用（v1 不要跨 query 状态隔离与 orphan 风险）。
3. **transcript 作为证据真相源**：`*.acp.transcript.jsonl`，逐条 JSON-RPC direction event。
4. **五态证据设计**：`allowed ≠ disabled ≠ requested ≠ denied ≠ used`。
5. **三层兜底不变**：启动策略下发 → permission broker deny → 事后 forbidden post-check。

**调用序列（v1）：**
```
AcpTraeCliRuntime.query_model(model, prompt, stage, label, output_dir, query_timeout)
  1. spawn: traecli acp serve --disallowed-tool <policy> --query-timeout <t> [-c model.name=<model>]
  2. initialize（protocolVersion 1，fs 能力全关）
  3. session/new（cwd、mcpServers=[]）→ 校验 availableModels
  4. session/prompt（prompt 全文）
  5. 循环收 session/update；session/request_permission 按 policy 即时 allow/deny 并记录
  6. stop → 聚合响应文本；全程逐事件追加写 transcript JSONL
  7. 映射 ModelCallResult（含五态证据字段）；terminate_process_tree()
```

**失败映射分层表：**
| 层 | 触发 | 映射 |
|---|---|---|
| startup | spawn 失败 / initialize 超时 | status=failed, error=acp_startup_failed:* |
| request | query_timeout 超时 | status=failed, error=timeout |
| model | availableModels 不含目标 | invalid_model 语义 |
| cancellation | 外部 cancel | CancelledError 上传、kill 进程树 |

**推翻条件：**
- probe 发现模型选择不可行 → M5 冻结，记 no-go 证据
- process-per-query 在 live 下启动开销显著（如每次 serve 冷启 >5s × 4 成员 × 3 阶段）→ 再评估单进程多 session 复用
- traecli ACP 接口跨版本不稳定 → ACP 保持 experimental

---

### 材料二：LCT 系统设计概要（节选自 design.md）

LLM Council for Trae（LCT）是一个基于 traecli 的多模型协议系统，核心设计哲学：

**三阶段协议：**
- Stage 1：独立成员回答（3 个 LLM 并发，answer_only 工具模式）
- Stage 2.5（质询轮）：成员相互阅读并质询彼此答案
- Stage 3：主席综合各成员答案，生成最终报告

**核心不变量：**
- 成员彼此不可见（Stage 1 期间）
- 主席只能看到经 Stage 2 完成的成员答案
- 工具策略严格隔离：成员 answer_only 时不能使用任何工具

**验证体系（validation）：**
- validate hard gate 防伪造：路径约束（禁绝对路径/`../`）、最小协议结构、meta/transcript/manifest 三方一致性、枚举语义校验
- direct/legacy artifact 不受影响
- verdict 状态枚举：complete_ok_final / complete_ok_degraded / failed_*

**关键指标：**
- `usable_final`：布尔，表示报告是否可用
- `member_valid_count`：有效成员数
- `backfill_attempts`：回填次数（因模型失败补位）
- `validate.failures` / `validate.warnings`：验证失败/警告

---

### 材料三：M1-M5 实施历史

| 阶段 | 内容 | 状态 |
|---|---|---|
| M1 | 移植 P0 direct contract tests | 完成，368 unittest 全绿 |
| M2 | 移植 P1 ModelRuntime port + runtime_backend 轴 | 完成 |
| M3 | 移植 P2 offline ACP adapter + transcript parser | 完成 |
| M4 | 移植 P3 evidence 字段 + validate hard gate + HTML 五态 | 完成 |
| M5 | C-1b live transport（新开发） | 完成，E2E 验证通过 |

**M5 live probe 结论（2026-06-11）：**
- traecli acp serve 子命令存在，JSON-RPC initialize 握手成功（protocolVersion: 1）
- 模型选择机制：`-c model.name=<model>` 有效
- session/new 返回 availableModels（模型发现可经 ACP 完成）
- process-per-query 架构：每次调用约 3-8s 启动开销

---

### 材料四：M6 go/no-go 判据（本阶段目标）

M6 的核心目标是采集足够的实测证据，支撑 ACP 从 experimental 转为 default backend。

**GO 需全部满足：**
1. 4/4 组 ACP run 的 validate verdict 为 `complete_ok_final`
2. L1 长任务 ACP 侧 `usable_final: true`
3. ACP 总耗时 ≤ 同组 direct 的 2 倍（4 组中至少 3 组满足）
4. 全部 run 结束后零进程残留
5. 零 validate failures（warnings 如实记录并逐条评估）

---

## 综合分析任务

基于以上材料，请对以下问题进行深度分析：

### 问题一：架构风险评估
评估 LCT 从 direct 迁移到 ACP 的核心风险。从以下角度分析：
- process-per-query 架构在高并发场景下的性能风险（假设 4 成员 × 3 阶段 = 12 次启动）
- transcript 作为证据真相源的可靠性：如果进程崩溃导致 JSONL 不完整，如何处理？
- ACP 版本兼容性风险：traecli 0.120.38 是否足够稳定？

### 问题二：go/no-go 决策框架评价
评估当前 M6 的 go/no-go 判据设计是否合理：
- 4/4 组 ACP 全通过的判据是否过于严格或过于宽松？
- 耗时限制"≤ direct 的 2 倍"是否是合理的性能阈值？
- 还有哪些应该纳入但未纳入的判据？

### 问题三：M7 实施建议
如果 M6 判定为 GO，M7 需要将 ACP 从 `--runtime-backend acp` 升级为默认值。
- 建议 M7 的切换策略（开关设计、灰度方案、回滚机制）
- 关键风险点和必须完成的验证
- 向用户暴露 ACP 启动失败时的报错文案设计思路

### 问题四：长期演进建议
从软件架构角度，process-per-query vs. 长驻 server 的权衡：
- 什么时候应该考虑从 process-per-query 迁移到 session 复用？
- 迁移的前提条件和技术风险
- 如何在不破坏现有 direct 路径的情况下逐步演进

请给出结构清晰、有深度的分析，每个问题分别作答，并在最后给出总体架构健康度评估（1-10 分）和简要理由。
