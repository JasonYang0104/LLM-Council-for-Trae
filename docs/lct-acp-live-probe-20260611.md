# ACP live probe 报告（M5 阶段 A）

- 日期：2026-06-11
- 环境：本机 macOS，`traecli`（coco 0.120.38，build 7a806e910d，2026-06-05），已登录，模型列表非空
- 方法：自研 JSON-RPC stdio 探针（worktree 内 `tmp-probe/probe.py`，不进 commit），对 `traecli acp serve` 逐项实测；以下 JSON-RPC 摘录均来自实际收发记录（`tmp-probe/logs/*.jsonl`）
- 上游清单：`docs/lct-acp-migration-architecture-20260611.md` §4.3、任务卡阶段 A 5 项

## 总结论：GO

5 项 probe 全部有证据；模型选择机制（go/no-go 关键项）有两条可行通道，首选启动参数 `-c model.name=<modelId>` 已实测生效。

---

## 1. 模型选择机制（go/no-go 关键）：GO，key 名为 `model.name`

**机制 ①（首选，已实测生效）**：`traecli acp serve -c model.name=<modelId>`。

- key 名来源：`~/.trae/traecli.yaml` 配置文件结构为 `model.name: GPT-5.5`，与 direct 路径 `traecli -c model.name=<model>` 同一个 key。
- 证据：不带 override 启动时 `session/new` 返回 `currentModelId: "GPT-5.5"`（与配置文件一致）；带 `-c model.name=Qwen3.6-Plus` 启动后：

```json
// session/new result（p1-model-Qwen3.6-Plus.jsonl，节选）
{"id": 2, "result": {"models": {"availableModels": [
  {"modelId": "Qwen3.6-Plus", "name": "Qwen3.6-Plus", "description": "Context window: 184k"}, ...],
  "currentModelId": "Qwen3.6-Plus"}}}
```

- 该 session 的 prompt 正常完成（`stopReason: "end_turn"`，响应 `PROBE_MODEL_OK`）。
- `availableModels` 共 20 个 modelId（Seed-Dogfooding-2.0、Doubao-Seed-2.0-Code、…、GPT-5.5、Qwen3.6-Plus、Qwen3.5-Plus 等），与 IDE 模型列表一致，可作 pre-flight 校验。

**机制 ②（协议级，存在但本轮不用）**：`session/set_model` 方法存在：

```json
// p1-protocol.jsonl
[client] {"id": 3, "method": "session/set_model", "params": {"sessionId": "...", "modelId": "GPT-5.5"}}
[server] {"id": 3, "result": {}}
```

`session/setModel`、`session/select_model`、`_ext/session/set_model` 均返回 `-32601 Method not found`；`session/set_mode` 存在但语义是 permission mode。本轮 process-per-query 架构下用机制 ①（argv 即证据），机制 ② 留作备选。

## 2. permission 语义：disallowed = schema 静默隐藏（argv 证据）；非白名单工具 = 可 deny 的 permission request

实验 ①（p2-permission-deny.jsonl）：`acp serve --disallowed-tool WebSearch --disallowed-tool WebFetch`，prompt 强诱导 WebSearch：

- **transcript 全程没有出现任何针对 WebSearch 的 `session/request_permission`，也没有 WebSearch 的 `tool_call` 事件**——被 `--disallowed-tool` 的工具是静默不可用（schema 隐藏/前置拒绝），不产生协议级痕迹。
- 因此**五态中 `disabled` 态的取证方式只能是 argv 证据**（meta 的 `disabled_tools` 与启动参数 `--disallowed-tool` 一一对应），不是 transcript 证据。validate 对 disabled 的校验维持「meta 字段在位 + 与策略一致」口径。
- 模型随即绕道：调了 `Skill`(tavily-search) 与 `Bash`(which tvly)——本实验未禁这两个工具，它们属于产品策略 `ALWAYS_FORBIDDEN_TOOLS`/`WORKSPACE_WRITE_TOOLS`，真实 runtime 会逐项下发 `--disallowed-tool`。
- `Bash`(tvly search …) 触发了真实 permission request（含 options 数组）：

```json
[server] {"id": 1, "method": "session/request_permission", "params": {
  "options": [
    {"kind": "allow_once", "optionId": "allow", "name": "Allow once"},
    {"kind": "allow_once", "optionId": "session_level_allow", "name": "Allow all tools during this session"},
    {"kind": "allow_always", "optionId": "always_allow_for_Bash(tvly search:*)", ...},
    {"kind": "reject_once", "optionId": "reject", "name": "Reject, and tell TraeCli what to do differently"}],
  "toolCall": {"title": "bash", "toolCallId": "call_1a6ca0f796fb497c8501d17f",
               "rawInput": {"command": "tvly search \"AI news today\" ...", ...}}}}
[client] {"id": 1, "result": {"outcome": {"outcome": "selected", "optionId": "reject"}}}
[server] session/update {"update": {"sessionUpdate": "tool_call_update", "status": "failed",
  "content": [{"content": {"text": "Tool call rejected by user", "type": "text"}, ...}],
  "toolCallId": "call_1a6ca0f796fb497c8501d17f"}}
```

deny 后回合正常收束（`stopReason: "end_turn"`），即 **denied ≠ 整轮失败**，与五态语义一致。

实验 ②（p2b-search-allowed.jsonl）：真实 search_enabled 策略（`--allowed-tool WebSearch --allowed-tool WebFetch` + 16 项 `--disallowed-tool`），prompt 要求 WebSearch：

- WebSearch 正常执行且**不产生 permission request**（`--allowed-tool` 自动放行），事件形态：

```json
[server] session/update {"update": {"sessionUpdate": "tool_call", "status": "in_progress",
  "title": "WebSearch", "toolCallId": "call_7c39a11b0c974ddbbad025c4",
  "rawInput": {"query": "Eiffel Tower completion year"}}}
[server] session/update {"update": {"sessionUpdate": "tool_call_update", "status": "completed",
  "rawOutput": {...}, "toolCallId": "call_7c39a11b0c974ddbbad025c4"}}
```

- 注意工具名载体是 `toolCall.title` / `update.title`：builtin 名称大小写不一（`WebSearch` 规范名 vs `bash`/`skill` 小写）。live parser 需做大小写无关的规范名映射。

## 3. actual model 证据：update 流无模型字段，降级方案生效

- 完整 turn 的 `session/update` 流（thought chunk、message chunk、tool_call、tool_call_update）的 `_meta` 只有 `createdAt`/`id`/`lastChunk`/`type`（及 `messageId`），**无任何模型标识字段**；`session/prompt` 响应只有 `{"stopReason": ...}`。
- **降级方案（证据上限）**：`session/new` result 的 `currentModelId`（受启动参数 `-c model.name=` 控制，实测跟随变化）＋ `availableModels` pre-flight 校验 ＋ 启动 argv 本身。transcript parser 从 transcript 里的 session/new 响应提取 `currentModelId` 作为 actual_model。
- 该降级已在 validate 代码注释与本报告如实声明：ACP 路径的 anti-fallback 证据强度低于 direct（direct 有 stream-json 逐消息 model 字段），是「服务端声明的会话模型」而非「逐响应模型标注」。

## 4. stop reason 枚举：三种终止形态

| 场景 | 信号形态 | 证据 |
|---|---|---|
| 正常完成 | `session/prompt` 响应 `{"result": {"stopReason": "end_turn"}}` | p1-model-Qwen3.6-Plus.jsonl |
| 超时（`--query-timeout 3s`） | `session/prompt` 响应为 JSON-RPC error：`{"error": {"code": -32603, "message": "Internal error", "data": {"error": "failed to call agent: model 'Qwen3.6-Plus': context deadline exceeded; context deadline exceeded"}}}` | p4-timeout.jsonl |
| 取消（`session/cancel` 通知） | `session/prompt` 响应 `{"result": {"stopReason": "cancelled"}}` | p4-cancel.jsonl |

附：模型过载排队期间（GPT-5.5 queue position 300+）server 持续等待并最终走 `--query-timeout` 的 -32603 路径；排队状态只出现在 session 缓存 events.jsonl（`request_wait_in_queue`），不在 ACP 流中。

## 5. 进程残留：无孤儿

- 每次 probe 结束以 SIGTERM（进程组）终止 server，全部正常退出 `rc=0`，SIGKILL 从未触发。
- 全部 probe 跑完后 `pgrep -fl "acp serve"` / `pgrep -fl traecli`：无本轮残留。仅有的 3 个 `traecli -y` 进程（pid 17658/48726/70939）启动时间为 2026-06-10（本轮 probe 之前），属其它会话，已用 `ps -o lstart` 证实与本轮无关。

---

## 对阶段 B 实现的直接约束（probe 衍生结论）

1. live 事件形态与 M3 offline parser 的假设字段不同，parser 需**增量扩展**（不改旧分支、不改 M3/M4 断言）：
   - 响应文本：`sessionUpdate == "agent_message_chunk"` 的 `update.content.text` 逐 chunk 拼接；`agent_thought_chunk` 不计入响应。
   - 工具调用：`sessionUpdate == "tool_call"`（`title`/`toolCallId`/`rawInput`）+ `tool_call_update`（终态 status）；被 deny 的 toolCallId 不计入 used。
   - permission：params 形如 `{options, toolCall:{title, toolCallId, rawInput}}`，决策从客户端响应 `outcome.optionId`（含 `allow`→allow，`reject`→deny）解析；工具名从 `toolCall.title` 做大小写无关规范化（`bash`→`Bash`）。
   - actual_model：从 transcript 中 session/new 响应的 `models.currentModelId` 提取（update 流证据缺失的降级）。
2. permission broker 决策规则：canonical 工具名 ∈ allowed_tools → 选 `allow_once` option；否则选 `reject_once` option（默认拒绝）。
3. 失败映射落点：prompt 响应 error 且 data 含 `context deadline exceeded` → `error="timeout"`；`stopReason != "end_turn"` → 失败并如实记录 stop reason；initialize/session/new 超时 → `acp_startup_failed`。
4. 模型校验顺序：session/new 后先验 `availableModels` 含目标 model（缺 → invalid_model 语义失败），再验 `currentModelId == model`（不符 → 与 direct mismatch 同语义失败），都过才发 prompt。

---

## 附录：阶段 C live 验证记录（2026-06-12，实现完成后）

实现 commits：`3e609ad`（红）→ `ee6aa0e`（绿，live transport + parser live 分支）。

### C-1 单查询 live smoke

- 命令：`AcpTraeCliRuntime(query_timeout=120, member_tool_mode="search_enabled").query_model(model="Qwen3.6-Plus", ...)`（tmp-probe/smoke.py），exit 0
- 结果：`status=ok`，`actual_model=Qwen3.6-Plus`，response `LIVE_SMOKE_OK`；transcript 19 行，`parse_acp_transcript_text()` 自检 `protocol_errors=[]`，parser response 与 meta response 一致；meta 45 键（44 + captured_at）
- 实际 argv：`traecli acp serve -c model.name=Qwen3.6-Plus --query-timeout 120s --allowed-tool WebSearch --allowed-tool WebFetch --disallowed-tool ×16`

### C-2 禁用工具 live 验证（answer_only）

- 强诱导 prompt（要求用 WebSearch/Bash/Skill 查今日新闻），18 项 `--disallowed-tool` 全量下发（WebSearch/WebFetch 也在内），exit 0
- 结果：`status=ok`，transcript 85 行内**零** `tool_call` 事件、**零** `session/request_permission`；模型自述工具不可用后凭文本作答——与 probe 第 2 项「disabled = schema 静默隐藏，argv 取证」结论一致；meta `disabled_tools` 18 项与 argv 一一对应

### C-3 最小 live E2E + validate hard gate

- 命令：`llm-council-for-trae run --input tmp-probe/e2e-question.md --default-models --runtime-backend acp --timeout 180 --json`，exit 0
- run_id：`run-20260611T230225`；成员 DeepSeek-V4-Pro / GPT-5.5 / openrouter-3o，主席 DeepSeek-V4-Pro
- 9 次 live ACP 调用（stage1×3 + stage2×3 + stage3）全部 `status=ok`，`expected_model == actual_model`，零 backfill、零 permission 请求；manifest `status=ok`（1 条 warning：`traecli doctor reported warnings`，与 ACP 无关）
- `validate run-20260611T230225 --json`，exit 0，verdict 原文：

```json
{"run_id": "run-20260611T230225", "status": "ok", "manifest_status": "ok", "terminal": true,
 "usable_final": true, "stage3_final_exists": true, "html_exists": true, "verdict": "complete_ok_final"}
```

- checks 共 497 项（其中 ACP hard gate 175 项），failures 0、warnings 0——M4 gate 对真实 live artifact 给出 `usable_final: true`

### C-4 进程残留

- E2E 与全部 smoke 结束后：`pgrep -fl "acp serve"` 仅命中一个 argv 文本含该字符串的无关 GUI 进程（SkyComputerUseClient）；`pgrep -x traecli`、`pgrep -fl "traecli acp"` 均无匹配。无孤儿进程，无需清理。
