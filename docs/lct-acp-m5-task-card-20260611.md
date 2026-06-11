# M5 任务卡：ACP live probe 与 live transport（交执行 Agent）

- 日期：2026-06-11
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §4（调用序列、失败映射、probe 清单全文照此执行）
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m5-20260611`，分支 `codex/lct-acp-m5-live-transport-20260611`（从 `main @ ef90bc7` 切出）
- 流程约束：纯本地，不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 回滚锚点：`pre-acp-m4` 已打。

## 背景与基线事实

- `main @ ef90bc7`：M1–M4 已合入，`make test` 349 个 unittest 全绿。offline adapter、transcript parser、evidence hard gate、HTML 五态全部在位。`AcpTraeCliRuntime` 默认 provider 缺失时报 `acp_startup_failed: ACP live transport is not implemented yet`。
- 2026-06-11 架构师已实测：`traecli acp serve` 存在；`initialize` 握手返回 `protocolVersion: 1`；`session/new` 返回 `_meta.cwd` 与 `models.availableModels`（modelId/name/context window）；serve 接受 `--allowed-tool` / `--disallowed-tool` / `--query-timeout` / `--yolo` / `-c k=v`。
- 本机 traecli 可用、已登录、模型列表非空。

## 阶段 A：live probe（先于任何产品代码）

产出 `docs/lct-acp-live-probe-20260611.md`（probe 报告，含实际 JSON-RPC 收发记录摘录），逐项给出证据：

1. **模型选择机制**（go/no-go 关键）：确认 per-query 固定模型的方式。候选顺序：① `traecli acp serve -c <key>=<model>` 启动参数（探明 key 名，可看 `traecli config --help` / 配置文件结构）；② 协议级方法（session/new 返回 models 对象，探测是否有 `session/set_model` 类方法或 prompt 参数）。两者都不可行 → **no-go：停止 M5，写 no-go 报告，不写产品代码**。
2. **permission 语义**：启动带 `--disallowed-tool WebSearch`，发一个诱导搜索的 prompt，记录产生的是 `session/request_permission`（可 deny）还是工具被静默隐藏（schema 不可见）——决定 `disabled` 态取证方式是 argv 证据还是 transcript 证据。
3. **actual model 证据**：在 `session/update` 流中找模型标识字段；找不到则记录降级方案（availableModels 校验 ＋ 启动参数即为证据上限）并在 validate 注释如实声明。
4. **stop reason 枚举**：prompt 正常完成 / 超时 / 取消各自的终止信号形态。
5. **进程残留**：kill server 进程后确认无孤儿 `traecli` 进程（`pgrep` 证据）。

probe 期间所有实验脚本放 worktree 内 `tmp-probe/`（gitignore 或最终删除），不进 commit；probe 报告进 commit。

## 阶段 B：live transport 实现（probe 全过才开工）

按架构文档 §4.1 调用序列实现 `AcpTraeCliRuntime` 默认 live provider：

1. spawn `traecli acp serve` ＋ 策略 argv（`--disallowed-tool` 从 `tool_policy_for_mode(member_tool_mode)` disallowed 集合派生、`--query-timeout`、模型固定参数按 probe 结论）；cwd = member runtime cwd（沿用 direct 的 isolated temp cwd 语义）。
2. initialize（protocolVersion 1，fs 能力全关）→ session/new（校验 availableModels 含目标 model，缺 → `invalid_model` 同 direct 语义）→ session/prompt → 收 update 循环；`session/request_permission` 按 policy 即时 allow/deny 并记录。
3. 全程逐事件追加写 `*.acp.transcript.jsonl`（M3 parser 可解析、M4 gate 可校验是硬约束——transcript 写出后立即用 `parse_acp_transcript_text()` 自检）。
4. 失败映射按架构文档 §4.2 表：startup（`acp_startup_timeout`）/ request timeout / model mismatch / cancellation，全部与 direct 状态枚举对齐；`terminate_process_tree()` 清理，不留孤儿。
5. 注入式 `transcript_provider` 测试通道保留（M3 offline tests 不改断言继续绿）。
6. 事后 forbidden post-check 保留（第三层兜底，backend 无关）。

## 阶段 C：live 验证

1. **单查询 live smoke**：用 `AcpTraeCliRuntime` 直接对 1 个可用模型发最小 prompt，得 `status=ok`、transcript 落盘且 parser 自检通过。
2. **禁用工具 live 验证**：`member_tool_mode=answer_only` 下诱导工具使用，验证 deny/隐藏行为与 meta 记录一致。
3. **最小 live E2E**：`llm-council-for-trae --runtime-backend acp run --input <小问题文件> --default-models --timeout 180 --json`（成员数走默认），随后 `validate <run_id> --json`——**M4 的 ACP hard gate 必须对真实 artifact 给出可用结论**（`usable_final: true` 或如实记录的降级原因）。若个别成员模型 live 失败，按现有 backfill 语义如实记录，不算 M5 失败。
4. 验证后 `pgrep -f "acp serve"` 无残留。
5. 全部 live 证据（命令、exit code、关键输出、run_id、validate verdict）记 notes.md 与 probe 报告附录。

## 边界（不得越过）

1. **默认 backend 仍是 direct**：不改默认值、不改 README 主路径文档（README/Skill 文档更新属后续批次）。
2. M1–M4 所有测试不改断言（`EXPECTED_META_KEYS` 44 键不变——live transport 不新增 meta 字段）；golden 零重生成（direct 路径无字段变化）。
3. 离线测试仍是 CI 真相源：新增单元测试一律 fake/注入驱动，live 证据只进 notes 与 probe 报告，不写依赖 live traecli 的 unittest。
4. 不实现长驻 server / 多路复用；不做默认切换评估（那是后续 go/no-go 议题）。

## 验收标准

1. probe 报告 5 项证据齐全（或 no-go 报告 + 停止）。
2. `make test` 全绿（349 ＋ 新增 fake 驱动测试数）。
3. 阶段 C 的 1/2/3/4 全部有记录在案的实测结果。
4. golden 零改动；M1–M4 测试零断言改动；`git diff --check` 通过。
5. notes.md 追加 M5 节；红绿提交粒度（probe 报告可单独 commit）。

## 汇报要求

简体中文：probe 5 项结论（特别是模型选择机制）、live transport 实现要点与偏离架构文档之处、阶段 C 各项实测结果（含 E2E run_id 与 validate verdict）、测试总数、commit SHA、遗留风险与默认切换前还缺什么。如实报告，live 失败不粉饰。