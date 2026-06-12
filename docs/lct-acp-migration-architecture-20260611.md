# Track C-1 深化设计：ACP runtime 迁移路线

- 日期：2026-06-11
- 状态：深化设计，待用户拍板后执行
- 上游：`docs/lct-three-track-upgrade-architecture-20260611.md` §3.1、ADR-0002
- 研究线资产：worktree `COCO-llm-council-acp-disabled-tool-research-20260603`，本地分支 `codex/lct-acp-runtime-p0-p1-20260604`（9 commits，未推送，behind main 56），含 P0-P3 全部离线交付与设计文档 `docs/acp-runtime-design-20260604.md`、`docs/acp-runtime-test-plan-20260604.md`

---

## 1. 本轮新增实测证据（2026-06-11，本机）

研究线当时的最大未知是「traecli 是否真支持 ACP」。本轮已做最小 live probe，**结论：go 信号明确**：

| 检查项 | 结果 |
|---|---|
| `traecli acp serve` 子命令存在 | ✅（coco 与 traecli 为同一二进制的 alias） |
| JSON-RPC `initialize` 握手 | ✅ 返回 `protocolVersion: 1`，stderr 干净 |
| agentCapabilities | `loadSession: true`、`mcpCapabilities: {http, sse}`、`sessionCapabilities.list`、`promptCapabilities: {}`（空，未声明多模态）、扩展 `_ext/session/executing_session` |
| `session/new` | ✅ 返回 `_meta.cwd` ＋ **`models.availableModels`（modelId / name / context window）**——模型发现可经 ACP 完成 |
| 启动时工具策略注入点 | ✅ `acp serve` 接受全局 flags：`--allowed-tool`、`--disallowed-tool`、`--query-timeout`、`--yolo`、`-c k=v` config override——与研究线「启动时下发 disabled tool policy」设计吻合 |

**仍未验证（C-1b live probe 清单的核心）**：

1. 单 session 的模型选择机制——首选候选：process-per-query 下经启动参数 `-c <key>=<model>` 固定（key 名待 probe 确认）；备选：协议级 set model（`session/new` 返回了 models 对象，提示存在协议级选择）。
2. `session/prompt` 的完整 turn 流：`session/update` 事件形态、stop reason 枚举、响应文本聚合方式。
3. `session/request_permission` 实际行为：`--disallowed-tool` 下工具是被隐藏、还是产生可 deny 的 permission request（决定五态证据里 disabled vs denied 的真实语义）。
4. actual model 证据在何处出现（anti-fallback 校验依赖它，direct 路径靠 stream-json 中的 model 字段）。
5. 进程残留行为：kill 后无孤儿 `traecli` 进程。

## 2. 迁移决策（沿用研究线结论，本轮固化）

1. **不整体 merge 研究分支**（behind 56；研究线两个 subagent reviewer 一致结论）。按 P0→P3 逐阶段移植到从最新 main 切出的新分支，每阶段红绿过程独立、`make test` 全绿再进下一阶段。
2. **先推备份分支**到 origin（建议名 `backup/acp-runtime-p0-p3-20260604`）：9 commits 目前是单机单点，属资产风险，移植前必须消除。（对外动作，待用户确认后执行。）
3. **架构骨架照搬研究线已验证设计**，不重新发明：
   - `ModelRuntime` protocol（最小接口 = async `query_model(...) -> ModelCallResult`），`runtime_backend: "direct" | "acp"`，默认 `direct`，`acp` × `provider_mode=subagent` fail-fast。
   - **process-per-query**：一次 `query_model()` = 一个 `traecli acp serve` 进程 = 一段独立 transcript 证据。放弃长驻 server 多路复用（v1 不要跨 query 状态隔离与 orphan 风险）。
   - transcript（`*.acp.transcript.jsonl`，逐条 JSON-RPC direction event）是 ACP 证据真相源；`~/Library/Caches/coco/sessions` 复制只是 best-effort。
   - 五态证据 `allowed ≠ disabled ≠ requested ≠ denied ≠ used`；forbidden 工具被 allow 或实际 used → 成员不计入有效 quorum。
   - validate hard gate 防伪造：路径约束（禁绝对路径/`../`）、最小协议结构、meta/transcript/manifest 三方一致性、枚举语义校验；direct/legacy artifact 不受影响。
   - 三层兜底不变：启动策略下发 → permission broker deny → 事后 forbidden post-check（与 direct 同款，作为最后一层）。

## 3. 移植与实施阶段（M0–M5）

| 阶段 | 内容 | 完成判据 | 风险点 |
|---|---|---|---|
| M0 | push 备份分支 | origin 上可见 9 commits 原样 | 无（需用户点头） |
| M1 | 移植 P0 direct contract tests（spawn/argv/retry/status precedence/cancellation/golden full-run） | 新 main 上全部 contract tests 绿；golden 快照按当前 main 字段集重生成并在 commit message 说明字段差异 | main 56 commits 间 `ModelCallResult`/config 字段已变（contribution_map 链路、repair attempts），golden 与 meta keyset 必须重冻结，不能照抄研究线快照 |
| M2 | 移植 P1 `ModelRuntime` port ＋ `runtime_backend` 轴 | M1 的 tests 不改断言即通过（port 零行为变化的机器证据）；config JSON / profile 持久化 backend 字段 | `run_full_council()` 在 main 上有改动，runtime 构造点收敛需重做而非 cherry-pick |
| M3 | 移植 P2 offline ACP adapter（transcript parser 纯函数 ＋ `AcpTraeCliRuntime` skeleton，可注入 transcript provider） | parser/adapter 离线 tests 全绿；live transport 缺失时明确失败为 `acp_startup_failed: ACP live transport is not implemented yet` | 无 live 依赖，风险低 |
| M4 | 移植 P3 evidence 字段 ＋ validate hard gate ＋ HTML 五态 ＋ orchestration provenance follow-up（synthetic failed call 的 ACP 字段、sidecar 命名分流） | forged-evidence 负向测试全绿；direct/legacy HTML 显示 `not_applicable`（不是 0）；direct golden 仅因显式新增字段重生成 | HTML 在 main 上已大改（contribution map 渲染），五态展示区需重新落位 |
| M5 | **C-1b live transport**（唯一的新开发） | 见 §4 | §1 的 5 个未验证项 |

M1–M4 是移植不是新设计；执行 Agent 的自由度在「适配新 main」，不在「改协议语义」。每阶段独立 commit，研究线 notes.md 的红绿记录模式沿用。

## 4. M5：live transport 设计契约

### 4.1 调用序列（v1）

```
AcpTraeCliRuntime.query_model(model, prompt, stage, label, output_dir, query_timeout)
  1. spawn: traecli acp serve
       --disallowed-tool <由 tool_policy_for_mode(member_tool_mode) 派生，逐项>
       --query-timeout <query_timeout>
       [-c <model-key>=<model>]        # 机制以 probe 结论为准
       cwd = member runtime cwd（沿用 direct 的 isolated temp cwd 语义）
  2. initialize（protocolVersion 1，fs 能力全关——成员不需要客户端文件系统）
  3. session/new（cwd、mcpServers=[]）
       └─ 校验 availableModels 含目标 model（失败 → invalid_model，与 direct 语义对齐）
  4. session/prompt（prompt 全文）
  5. 循环收 session/update；session/request_permission 按 policy 即时 allow/deny 并记录
  6. stop → 聚合响应文本；全程逐事件追加写 transcript JSONL
  7. 映射 ModelCallResult（含 §2 五态证据字段）；terminate_process_tree()
```

### 4.2 失败映射（沿用研究线分层表）

| 层 | 触发 | 映射 |
|---|---|---|
| startup | spawn 失败 / initialize 超时（`acp_startup_timeout`，默认 30s） | `status=failed`, `error=acp_startup_failed:*`, `acp_startup_status=failed` |
| request | `query_timeout` 超时 | `status=failed`, `error=timeout`（与 direct 同枚举，retry matrix 不把 timeout 当可重试） |
| model | availableModels 不含目标 / actual model 不匹配 | 与 direct 的 invalid_model / model mismatch 同语义 |
| cancellation | 外部 cancel | `CancelledError` 上传、kill 进程树、写 failed meta、不写伪成功 |

### 4.3 C-1b probe 前置清单（写产品代码前完成，产出 probe 报告入 docs/）

§1 的 5 个未验证项逐项给出证据（实际 JSON-RPC 收发记录），特别是：

- **模型选择机制**：确认 `-c` 的 key 名或协议级方法；两者都不可行 → live transport 冻结（no-go），M1–M4 资产仍保留（contract tests 永久保护主干，offline adapter 备用）。
- **permission 语义**：用 `--disallowed-tool WebSearch` 跑一次带搜索倾向的 prompt，确认产生的是 deny 事件还是 schema 隐藏，据此定五态中 `disabled` 的取证方式（这决定 validate 的 disabled 校验是「argv 证据」还是「transcript 证据」）。
- **actual model 证据**：在 update 流中找到模型标识字段；找不到 → anti-fallback 只能依赖 session/new 的 availableModels 校验 ＋ 启动参数，证据强度降级要在 validate 注释中如实声明。

### 4.4 默认切换门槛（远期，本轮非目标）

维持研究线口径，缺一不可，否则 `direct` 永远默认：

1. M1–M4 全绿且 direct baseline 未削弱；
2. live paired probe ≥ 3 次稳定（direct 与 ACP 同 prompt 配对跑）；
3. 代表性长 E2E `validate` 给出 `usable_final=true`；
4. 无残留 ACP server / traecli 孤儿进程；
5. `model_benchmark.py` 口径下 ACP 时延/失败率不劣于 direct。

## 5. 与 Track B 的交互

- 质询轮（stage2_5）只依赖 `ModelRuntime.query_model()` 抽象，**对 backend 无感知**；M2 完成后 debate 自动同时支持 direct/ACP。建议执行顺序上 M1–M2 先于 B-1a 落地，B-1a 直接面向 `ModelRuntime` 类型标注开发。
- stats 是 manifest-only 只读，与 runtime 迁移零耦合；ACP run 的 stats 维度（如 permission denied 计数）留待 ACP 灰度有真实数据后再议，首版不做。

## 6. 推翻条件

- probe 发现模型选择不可行（无 config key、无协议方法）→ M5 冻结，记 no-go 证据，等 traecli 上游演进。
- process-per-query 在 live 下启动开销显著（如每次 serve 冷启 >5s × 4 成员 × 3 阶段）→ 再评估单进程多 session 复用，前提是先解决跨 query 状态隔离与 transcript 归属切分。
- traecli ACP 接口跨版本不稳定（probe 通过但 E2E 行为漂移）→ ACP 保持 experimental，在 README runtime 矩阵中如实标注。
