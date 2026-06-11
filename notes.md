# LCT ACP M1 实施记录：移植 direct baseline contract tests

- 日期：2026-06-11
- 分支：`codex/lct-acp-m1-direct-baseline-20260611`（从 `main @ 04a1b9b` 切出）
- 上游任务卡：`docs/lct-acp-m1-task-card-20260611.md`
- 移植源：`COCO-llm-council-acp-disabled-tool-research-20260603` 分支 `codex/lct-acp-runtime-p0-p1-20260604` 的 commit `5c88617 test: freeze direct runtime baseline`
- 本轮按项目惯例把 worktree 内 `notes.md` 重置为本轮 M1 记录（旧研究线记录保留在 git 历史 / 移植源中）。

## 目标

把研究线 P0 direct baseline contract tests 移植到当前 main，冻结 direct runtime 当前行为，为 M2（ModelRuntime port）及后续改动提供零漂移机器证据。**纯测试移植，零 `src/` 产品代码变更。**

## 移植清单（全部完成）

- `tests/contract/__init__.py`
- `tests/contract/test_tool_policy_golden.py` — 四种 member_tool_mode 的 allowed/disallowed 全列表
- `tests/contract/test_direct_command_golden.py` — `_build_command()` 完整 argv ＋ `--yolo`
- `tests/contract/test_meta_keyset_golden.py` — `ModelCallResult.to_json()` key set 冻结
- `tests/contract/test_direct_spawn_contract.py` — spawn kwargs / runtime cwd / start_new_session / env override
- `tests/contract/test_direct_status_matrix.py` — `_query_model_once()` 状态优先级
- `tests/contract/test_direct_retry_matrix.py` — `query_model()` retry / no-retry
- `tests/contract/test_cancellation_contract.py` — CancelledError 传播、kill、failed meta、不写伪成功
- `tests/contract/test_tool_state_invariants.py` — search allowed / used / forbidden 不塌缩
- `tests/support/__init__.py`、`tests/support/golden.py`、`tests/support/runtime_contract.py`、`tests/support/runtime_fakes.py`
- `tests/test_golden_direct_run.py` ＋ `tests/golden/direct_full_run/snapshot.json`（在当前 main 重新生成，非照抄）

## 红绿过程

- 红：先落 8 个 contract 文件 ＋ support ＋ golden test，无 snapshot。
- 绿：
  - `tests/contract/` 17 个 contract tests 一次全绿（无需改产品代码）。唯一适配点是 `EXPECTED_META_KEYS`（见下）。
  - golden test 首跑 `KeyError: ('stage3', 'contribution-map-repair-1')`——暴露 main 新增的 contribution_map repair 链路（见下）。修正 stage3 chairman 脚本回复后，重新在当前 main 生成 snapshot，golden 两测全绿。
- 直接吸收研究线已知坑：cancellation 在 TemporaryDirectory 生命周期内读证据；argv 精确断言 `--query-timeout` 与其值；status matrix 测 `_query_model_once()` 而非 `query_model()`（retry 由 retry matrix 单独冻结）。这些坑在移植版本里已是正确形态，未复现。

## 适配中发现的 main 行为变化（按 P0 原则：冻结事实，不修产品）

1. **ModelCallResult meta key set 从 30 → 37**。research 线 `EXPECTED_META_KEYS` 30 个；当前 main `to_json()` 多出 7 个 web tool result 追踪字段：`lct_search_conversion_errors`、`lct_web_tool_effective_calls`、`tool_output_conversion_errors`、`tool_result_calls`、`web_tool_effective_calls_count`、`web_tool_result_call_ids`、`web_tool_result_calls_count`。已按当前 main 重新生成 `tests/support/runtime_contract.py` 的 `EXPECTED_META_KEYS`（37 个，含 `lct_web_tool_effective_calls`，它是 `web_tool_effective_calls_count` 的别名键）。

2. **stage3 新增 contribution_map repair 链路**（commits efc2823 / 04a1b9b 等）。`stage3_synthesize_final` 在 `chairman_contribution_enabled`（默认 True）且 chairman 回复中无 renderable contribution_map 时，会再发起一次 `query_model(stage="stage3", label="contribution-map-repair-{n}")`，最多 `chairman_contribution_repair_attempts`（默认 2）次。research 线 golden（contribution_map 之前）没有这条路径。
   - **适配方式**：让 golden 的 chairman stage3 回复内联一个合法 contribution_map fenced JSON（`multi_member_consensus` 归因到真实 Stage 1 模型 Model-A/Model-B）。这样 happy path 端到端跑通 contribution_map 特性、产出 `stage3/contribution_map.json`，且**不触发** repair 子调用（`contribution_map_repair` 不出现、`contribution_map_error=None`）。保持单次 chairman 调用结构，与 research 线 golden 的脚本形态一致。

3. **HTML 搜索摘要卡片格式变化**。research 线 golden 的 `html_checks.contains_search_summary=True`（探测 "允许：" ＋ "实际使用：" 字符串）。当前 main `render_summary_cards` 只在 `lct_web_tool_calls > 0` 时渲染搜索卡片，且文案改为 `调用次数：N`，不再有 "允许：/实际使用："。golden run 零 web tool call，故不渲染搜索卡片，`contains_search_summary=False`。这是当前 main 真相，已按事实冻结进 snapshot。

## golden snapshot 与研究线快照的字段差异（已写入 commit message）

- 文件数 46 → 47：新增 `stage3/contribution_map.json`。
- config 多出：`chairman_contribution_enabled`、`chairman_contribution_repair_attempts`、`chairman_contribution_required`、`model_selection_provenance`。
- stage1/stage2 各成员 meta 多出 7 个 web tool result 字段（同上 §1）。
- stage3_final 多出：`chairman_copy_check`、`contribution_map_enabled`、`contribution_map_path`、`contribution_map_requested`、`contribution_map_required`、`contribution_map_stripped_from_response`、`raw_response`，外加 7 个 web tool result 字段及其别名 `lct_web_tool_result_calls`。
- manifest.stages.stage3 同步多出 contribution_map / copy_check / web tool result 字段。
- html_checks：`contains_search_summary` True → False（见 §3）；`chars` 50729 → 61883（HTML 体积增大，含 contribution_map 渲染）。
- 顶层结构、manifest 顶层 key、html_export key set 无差异。

## 验证（全部通过）

- `make test`：`Ran 314 tests ... OK`（295 基线 ＋ 19 新增 = 17 contract ＋ 2 golden）。
- `PYTHONPATH=src:tests python3 -m unittest discover -s tests/contract -v`：17 tests，OK。
- golden 连跑两次零漂移：snapshot SHA `11eb499f...` 两次一致，两测均 OK。
- `git diff main..HEAD -- src/`：空（零产品代码变更）。
- `git diff --check`：通过。

## 残余风险

- golden 中 chairman 内联 contribution_map 是 happy-path 选择；repair 链路本身仍未被 golden 覆盖（它有独立单元测试在基线 295 中）。M1 范围只冻结 direct happy path，repair 失败路径冻结留待需要时单独补测。
- `EXPECTED_META_KEYS` 现含 37 键，硬编码于 `runtime_contract.py`；M2 加 ACP 字段时必须显式扩列并更新此契约——这正是该测试的设计意图（防止隐式漂移）。
- `support/golden.py` 的正则用 raw string 修正了研究线中 `[^\\s\"']` 的双反斜杠笔误（研究线那是非预期形态）；因 snapshot 在本 normalizer 下重新生成，连跑零漂移已实测，无影响。

## M2：ModelRuntime port 与 runtime_backend 轴

- 基线：worktree 从 `main @ c6a7591`（M1 已合入）切出，`make test` 314 全绿。
- 移植源：研究线 `98890bd ref: extract model runtime port`（P1 时点），只取该 commit，研究线后续 `2668359`/`bfa7be9`/`deb9119`（M3/M4）不带入。

### 目标

引入 runtime 抽象与显式 `runtime_backend` 选择轴。direct 行为零变化（以 M1 contract tests 不改断言通过为机器证据）；为 M3 offline ACP adapter 留工厂挂载点；acp backend 本阶段 fail-fast，不实现 adapter。

### 红绿过程

- 红：先移植 `tests/contract/test_runtime_backend_contract.py`（98890bd 时点版本，6 个 test）。单跑即报 `ImportError: cannot import name 'build_model_runtime'`——缺口正是 `CouncilConfig` 两字段、CLI 两参数、`config_to_json` 持久化、`ModelRuntime` protocol、`DirectTraeCliRuntime` 别名、`build_model_runtime` 工厂与 fail-fast。提交为 commit 1（`test:`，bc37f1a）。
- 绿：补齐产品代码（`provider.py`/`council.py`/`cli.py`），新 6 个 contract test 一次全绿；唯一连带失败是 direct golden（预期内的 config 字段新增）。重生成 golden 后两测全绿。提交为 commit 2（`ref:`）。

### 产品代码变更（限 4 文件，不新建 src 模块）

- `council.py`：`CouncilConfig` 新增 `runtime_backend: str = "direct"`、`acp_startup_timeout: int = 30`；`config_to_json()` 持久化两字段；新增 `build_model_runtime(config, provider_runtime_cwd, provider_member_tool_mode)` 工厂（direct→现有 `TraeCliProvider`；acp→`ValueError("runtime_backend=acp is not implemented yet")`；未知→`ValueError(f"unknown runtime_backend: ...")`）；`run_full_council()` 的 provider 构造点收敛到该工厂；stage1_collect / backfill_stage1 / stage2_collect / backfill_stage2 / stage3_synthesize 五个编排函数的 `provider` 类型标注从 `TraeCliProvider` 收窄为 `ModelRuntime`。
- `provider.py`：新增 `ModelRuntime` Protocol（最小接口 async `query_model(...) -> ModelCallResult`）＋ `DirectTraeCliRuntime = TraeCliProvider` 显式别名。
- `cli.py`：`run` 新增 `--runtime-backend`（choices `direct`/`acp`，默认 `direct`）、`--acp-startup-timeout`（默认 30）；`provider_mode=subagent` × `runtime_backend=acp` 在 `build_config` 中 fail-fast；两字段经 `getattr(..., default)` 流入 `CouncilConfig`（旧 profile / 旧 args 缺该字段时按 `direct`/`30` 兜底，不失败）。

### golden 重生成 — 逐字段差异（仅这 5 处，无其他漂移）

- `config.acp_startup_timeout`：新增 → `30`
- `config.runtime_backend`：新增 → `"direct"`
- `manifest.config.acp_startup_timeout`：新增 → `30`
- `manifest.config.runtime_backend`：新增 → `"direct"`
- `html_checks.chars`：`61883` → `62049`（+166，由两字段进入 HTML config 区块所致）

`EXPECTED_META_KEYS`（37 键）不变；M2 不加任何 meta 字段。顶层结构、文件数、html_export key set、stage meta key set 全部不变。

### 与研究线 P1 的适配差异

- 研究线 98890bd 的 golden 基于 contribution_map 之前的形态（`chars 50729→50895`，+166）。本 worktree 基于 main（M1 已含 contribution_map），基线 `chars=61883`，重生成后 `62049`，同为 +166。两字段的 config 落点与 HTML 增量形态一致，仅绝对基数因 main 漂移不同——故 golden 在本 worktree 实测重生成，未照抄研究线 snapshot。
- 测试文件、CLI 参数、工厂语义、错误文案与研究线 98890bd 时点逐字一致；研究线后续对该测试文件的 P2/P3 修订未带入。
- `repair_contribution_map()`（main 新增、研究线 98890bd 无）的 `provider` 标注保持 `TraeCliProvider` 未收窄——它不在任务卡列出的 5 个编排函数范围内，按规格保留。

### 验证（全部通过）

- `make test`：`Ran 320 tests ... OK`（314 基线 ＋ 6 新增 runtime backend contract）。
- M1 测试零改动：`git diff main..HEAD -- tests/contract/test_direct_*.py tests/contract/test_tool_*.py tests/contract/test_meta_keyset_golden.py tests/contract/test_cancellation_contract.py tests/support/runtime_contract.py` 为空。
- golden 连跑两次零漂移（`test_direct_full_run_snapshot_matches_golden` ＋ `test_direct_full_run_snapshot_is_deterministic` 均 OK）。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m compileall -q src`：通过。

### 残余风险

- acp backend 仅 fail-fast，无 adapter / transcript parser / live transport——M3 范围，符合任务卡边界。
- `ModelRuntime` Protocol 当前仅 `TraeCliProvider` 实现（structural 鸭子类型，未运行期 `@runtime_checkable` 校验）；M3 接入 ACP adapter 时需保证其 `query_model` 签名与该 Protocol 一致。

## M3：offline ACP adapter 与 transcript parser

### 阶段目标

- 新增 ACP transcript 纯函数 parser（不依赖 live `traecli`）。
- 新增 `AcpTraeCliRuntime` offline skeleton：经可注入 `transcript_provider` 离线证明 `query_model()` mapping；默认 provider 缺失时失败语义诚实，不伪装 live。
- 让 `runtime_backend=acp` 进入 runtime factory，返回 `AcpTraeCliRuntime`；live transport 仍明确未实现。
- 解决上轮 review 两处发现：`repair_contribution_map` 类型收窄、签名门卫契约测试。

### 产品代码变更（src 仅 3 文件）

- 新增 `src/llm_council_for_trae/acp_transcript.py`：`parse_acp_transcript_text()`、`AcpTranscriptParseResult`、`resolve_acp_transcript_path()`（拒绝绝对路径与逃出 run root 的 `../`）。
- 新增 `src/llm_council_for_trae/acp_runtime.py`：`AcpStartupError`、`AcpQueryRequest`、`AcpTraeCliRuntime`。command 记录为 `["<traecli>", "acp", "serve"]`；默认 provider 缺失 → `acp_startup_failed: ACP live transport is not implemented yet`。
- `council.py`：
  - `build_model_runtime()` 的 acp 分支从 fail-fast 改为返回 `AcpTraeCliRuntime`（透传 `runtime_command/query_timeout/runtime_cwd/use_yolo/member_tool_mode/acp_startup_timeout`）。
  - **review 发现 1（类型收窄）**：`repair_contribution_map()` 的 `provider` 标注由 `TraeCliProvider` 收窄为 `ModelRuntime`（纯类型层面，行为不变）。这与 M2 notes 中“暂保留 `TraeCliProvider`”形成对照——M3 已按本轮 review 收窄。

### 测试变更

- 新增 `tests/contract/test_acp_transcript_parser.py`（5 个）：response/actual_model/tool_calls 提取、permission request 与 decision、坏 JSONL 不静默、无最小 ACP 结构报 missing required method、路径约束（绝对路径与 `../` 逃逸均拒，比较用 `root.resolve()`）。
- 新增 `tests/contract/test_acp_model_runtime_contract.py`（10 个）：factory 返回 `AcpTraeCliRuntime`；clean transcript → ok ＋ 三 sidecar 落盘；forbidden permission deny 且未 used → ok；forbidden permission allow → fail；forbidden tool used → fail；protocol error / startup error / cancellation 各自映射；默认 provider 缺失 → live transport not implemented；**review 发现 2（签名门卫）**：`test_acp_query_model_signature_matches_model_runtime_port` 用 `inspect.signature` 对比 `AcpTraeCliRuntime.query_model` 与 `TraeCliProvider.query_model` 及 `ModelRuntime.query_model` 的参数名集合、顺序、kind 一致。
- 改动 `tests/contract/test_runtime_backend_contract.py`（M2 测试唯一允许的改动）：新增 `AcpTraeCliRuntime` import；`test_acp_runtime_backend_fails_fast_until_adapter_exists` → `test_acp_runtime_backend_builds_experimental_acp_runtime`，断言 factory 返回 `AcpTraeCliRuntime` 且透传 `member_tool_mode/acp_startup_timeout`。理由：acp 分支语义已从 fail-fast 翻转为返回 adapter，旧断言会必然失败，必须同步。

### 红绿过程与已知坑

- 红态确认：仅提交三个测试文件后，`PYTHONPATH=src:tests python3 -m unittest tests.contract.test_acp_transcript_parser tests.contract.test_acp_model_runtime_contract tests.contract.test_runtime_backend_contract` → `ModuleNotFoundError: No module named 'llm_council_for_trae.acp_runtime'`（红，3 模块 import 失败）。红态 commit：`bd8f35d`。
- 已知坑（直接吸收，未重踩）：
  - Python 3.9 类型别名禁 `str | Any` 运行期求值 → `TranscriptProvider = Callable[..., Any]`（本机 Python 3.14，但保留 3.9-safe 形态）。
  - macOS 临时目录 `/var/...` → `/private/var/...`：路径约束测试用 `root.resolve()` 比较。
  - P1 的 acp fail-fast 测试已更新为 factory 返回 `AcpTraeCliRuntime` 契约。

### 边界恪守

- 未新增 validation hard gate、未改 HTML、`EXPECTED_META_KEYS`（37 键）不变（evidence 字段属 M4）。
- 未实现 live transport。
- M1 contract tests 与 golden 零改动；本阶段无 config 字段新增，golden 未重生成。
- `src/` 改动限于两个新模块 ＋ `council.py`。

### 验证（全部通过）

- `make test`：`Ran 335 tests ... OK`（320 基线 ＋ 15 新增：5 transcript parser ＋ 10 runtime contract）。
- `git diff main..HEAD -- tests/golden/`：空（golden 零改动）。
- M1 测试零改动：`git diff main..HEAD -- tests/contract/test_direct_*.py tests/contract/test_tool_*.py tests/contract/test_meta_keyset_golden.py tests/contract/test_cancellation_contract.py tests/support/runtime_contract.py` 为空。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m compileall -q src`：通过。

### 残余风险

- live ACP transport 仍未实现；当前 ACP runtime 的可验证范围是 offline transcript parsing 与 result mapping，不能把 offline fixture 当 live 证据。
- ACP evidence 扩字段、validate 反伪造、HTML 五态展示均留到 M4，避免在 parser/runtime skeleton 稳定前污染 direct meta key golden。
- `ModelRuntime` Protocol 仍为 structural（非 `@runtime_checkable`）；签名门卫测试现在以 `inspect.signature` 在测试期捕获 `AcpTraeCliRuntime` 与 direct/port 的签名漂移，但运行期仍无强约束。

---

# LCT ACP M4 实施记录：evidence 字段、validate 防伪、HTML 五态

- 日期：2026-06-11
- 分支：`codex/lct-acp-m4-evidence-gate-20260611`（从 `main @ c9b4536` 切出）
- 上游任务卡：`docs/lct-acp-m4-task-card-20260611.md`
- 移植源（只读，共享 object store）：`bfa7be9 feat: validate ACP runtime evidence`（P3 主体）＋ `deb9119 fix: keep ACP orchestration evidence provenance`（orchestration provenance follow-up）

## 红绿两 commit

- red：移植 11 个 ACP evidence validation 用例（`tests/contract/test_acp_evidence_validation.py`）＋ deb9119 的 3 个 runtime_backend 用例（sidecar 分流、synthetic ACP defaults）。实现未到位时 12 failures + 2 errors。
- green：实现 evidence 字段、validate hard gate、HTML 五态、orchestration provenance；`make test` 349 全绿。

## 与研究线适配差异（base 不同）

- 研究线 `bfa7be9` 从更早的 base 切出，缺 M1–M3 演进字段（`tool_result_calls`/`web_tool_*`/`parse_session_log_search_delivery` 等）。因此本轮按 **delta 移植**，不整文件覆盖：只叠加 M4 的 7 个 evidence 字段、validate ACP gate、HTML 五态、deb9119 provenance。
- `validation.py`：当前 worktree 用 `stage_stream_file_check(...)` 处理 stream（M3 cancelled-stream 兼容）。移植时保留该 helper，仅在 `runtime_backend != "acp"` 时才调用它，ACP run 不再要求 `.traecli.stream.jsonl`。
- `council.py` stage2 sidecar：当前条件是 `not exists or size==0`（M3 演进），deb9119 是 `not exists`。保留 M3 条件，仅外加 `if call.runtime_backend == "direct":` 守卫。
- `tool_policy_record()` 显式补写 7 个 evidence 字段，使 manifest stage records 携带 ACP 证据（cross-gate 经 manifest stage record 这一层生效）。

## EXPECTED_META_KEYS 扩列（37 → 44，显式过门）

新增 7 键（字母序插入）：`acp_startup_status`、`acp_transcript_path`、`disabled_tools`、`enforcement_method`、`enforcement_proof`、`runtime_backend`、`tool_permission_requests`。

## ModelCallResult / schema 扩字段（direct 默认值）

- `runtime_backend="direct"`、`enforcement_method="direct_disallowed_tool_post_check"`、`enforcement_proof="post_run_contamination_check"`、`disabled_tools=[]`、`tool_permission_requests=[]`、`acp_transcript_path=None`、`acp_startup_status="not_applicable"`。
- `STAGE_META_SCHEMA` 同步扩 7 键；`STAGE_META_COMPAT_OPTIONAL_FIELDS` 扩 7 键（legacy run 缺字段不失败）。

## validate ACP hard gate（研究线 Validation Contract 全单照搬）

- cross-gate：`record_requires_acp_gate()` —— config / stage record / meta 的 `runtime_backend` 或 `enforcement_method` 任一声明 ACP 即进 gate，防 `enforcement_method` 单点绕过。
- 拒绝清单：transcript 路径安全（绝对路径 / `../` 经 `resolve_acp_transcript_path` 抛 ValueError）、transcript 缺失/空、解析失败、无最小协议结构、meta↔transcript permission request 不一致、forbidden permission 被 allow、forbidden tool used、`status=ok` 含 forbidden 证据、record 声明 ACP 而 config=direct（config_consistency）、config=acp 但 record 缺 evidence、枚举语义校验（`enforcement_method`/`enforcement_proof`/`acp_startup_status`）。
- direct/legacy artifact 不受影响；ACP run 不再强制 `.traecli.stream.jsonl`。

## HTML 五态展示位置（file:line）

- `src/llm_council_for_trae/html_export.py`：
  - `summarize_acp_tool_state()`（约 1174 行起）：聚合 allowed/disabled/requested/denied/used 计数；无 ACP record 返回 `not_applicable`。
  - `render_summary_cards()` 内 ACP 卡片（约 1058 行后）：direct/legacy 显示 `not_applicable`，ACP 显示 Allowed/Disabled + Requested/Denied/Used 计数。
  - `render_metadata()` 运行时 cell 增 `Backend：`（约 1278 行）。
  - `render_acp_tool_state()` + `format_tool_names()`（`render_trace` 后，约 1305 行起）：每个 stage cell 展示五态工具名；非 ACP 显示 `ACP 工具证据：not_applicable`。
  - direct/legacy 对 ACP 专属项一律 `not_applicable`，不显示 0。

## orchestration provenance（deb9119）

- `ensure_stage1_stream_sidecar()`：`call.runtime_backend != "direct"` 时早退，不向 ACP call 补 direct sidecar。
- `runtime_stdout_path()` / `runtime_stderr_path()` / `runtime_acp_transcript_path()`：direct 用 `.traecli.stream.jsonl`/`.traecli.stderr.log`，ACP 用 `.acp.transcript.jsonl`/`.acp.stderr.log`。
- stage1/stage2 的 `synthetic_failed_call(...)` 全部传 backend-aware 路径。
- stage2 stream sidecar 仅在 `call.runtime_backend == "direct"` 时补写。
- `synthetic_failed_call()` 在 `runtime_backend=="acp"` 时写 ACP defaults（含 `permission_mode="acp_permission_broker"`、`acp_startup_status` 由 error 前缀派生）。

## golden 逐字段差异（`tests/golden/direct_full_run/snapshot.json`）

- 18 条记录（stage1/2/3 的 meta、manifest stage records、stage2 reviews、stage3 final）各 +7 字段：`runtime_backend="direct"`、`enforcement_method="direct_disallowed_tool_post_check"`、`enforcement_proof="post_run_contamination_check"`、`disabled_tools=[]`、`tool_permission_requests=[]`、`acp_transcript_path=null`、`acp_startup_status="not_applicable"`。
- `html_checks.chars`：62049 → 67866（新增 not_applicable 五态卡片与 trace 行）。
- 差异仅含上述两类；连跑两次 byte-identical 零漂移。golden 用 `sort_keys=True, indent=2, ensure_ascii=False` 重生，与仓库原约定一致。

## 验证（全部通过）

- `make test`：`Ran 349 tests ... OK`（335 基线 ＋ 14 新增：11 evidence validation ＋ 3 runtime_backend）。
- forged-evidence 负向测试全绿（伪造 transcript / 路径逃逸 / 声明不一致全被拒）。
- golden 连跑两次零漂移；diff 仅 7 新字段 ＋ chars。
- M1 测试零改动：`git diff c9b4536..HEAD -- tests/contract/test_direct_*.py tests/contract/test_tool_*.py tests/contract/test_meta_keyset_golden.py tests/contract/test_cancellation_contract.py tests/contract/test_acp_model_runtime_contract.py tests/contract/test_acp_transcript_parser.py` 为空；唯一动过的 support 文件是 `tests/support/runtime_contract.py`（EXPECTED_META_KEYS 显式扩列）。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m compileall -q src`：通过。

## 残余风险

- live ACP transport 仍未实现；validate 校验范围是「结构与证据一致性」，不声称验证「ACP 已隐藏 schema」这类未观察状态（与研究线 HTML / Index Contract 一致）。
- `tool_policy_record()` 现在无条件写 7 个 evidence 字段；direct run 写的是 direct 默认值，对 manifest 体积有极小增量，已纳入 golden。
- HTML 五态计数为跨 stage 累加（summary 卡片），trace 行为单 record 维度；二者口径不同已在实现区分，阅读时注意 summary 是聚合视图。

---

# M5：ACP live probe 与 live transport（2026-06-11 ~ 2026-06-12）

## 阶段 A：live probe（commit 6b67c99）

5 项全过，GO。报告：`docs/lct-acp-live-probe-20260611.md`（含 JSON-RPC 摘录与阶段 C 附录）。

1. **模型选择**：`traecli acp serve -c model.name=<modelId>`（与 direct 同 key，来源 `~/.trae/traecli.yaml`）；`session/new` 返回 `currentModelId` 跟随 override 变化，availableModels 20 项可 pre-flight。协议级 `session/set_model` 存在（备选未用）。
2. **permission 语义**：`--disallowed-tool` = schema 静默隐藏（transcript 零痕迹）→ disabled 态取证 = argv/meta；非白名单工具触发 `session/request_permission`（options 数组，allow_once/reject_once），deny 后 `tool_call_update status=failed`、回合正常 `end_turn`。
3. **actual model 证据**：update 流无模型字段 → 降级为 session/new `currentModelId` + availableModels 校验 + argv，已在代码注释（`_AcpLiveSession` docstring）与 probe 报告声明。
4. **stop reason**：正常 `end_turn`；`--query-timeout` 超时 = JSON-RPC error `-32603` data 含 `context deadline exceeded`；`session/cancel` → `stopReason: "cancelled"`。
5. **进程残留**：SIGTERM 全部干净退出 rc=0，无孤儿。

## 阶段 B：红绿（3e609ad 红 → ee6aa0e 绿）

- 红：`test_acp_live_transcript_parser.py`（8，live 事件形态）+ `test_acp_live_transport.py`（11，fake ACP server 子进程驱动，零 live 依赖）。
- 绿（parser，纯增量分支，旧 fake 形态分支零改动）：`agent_message_chunk` 逐 chunk 拼接成块、thought 不计入；`sessionUpdate: tool_call` 提取（`title` 大小写无关规范化 `canonical_tool_name`）；live permission（`toolCall.title/rawInput`、决策从 `outcome.optionId` 解析）；被 deny 的 toolCallId 不计入 used；session/new 响应 `currentModelId` 兜底 actual_model；permission 决策记录后 pop pending（防 id 复用串写）。
- 绿（runtime `_AcpLiveSession`，process-per-query）：spawn argv = base + `-c model.name` + `--query-timeout Ns` + 策略 `--allowed-tool/--disallowed-tool`（+`--yolo` 与 direct 对齐）；initialize（fs 全关）→ session/new（availableModels 缺目标 → `invalid_model:*`；currentModelId 不符 → direct 同款 mismatch 文案）→ session/prompt；permission broker 按策略选 `allow_once`/`reject_once` option，无匹配 option → cancelled outcome；deadline 护栏：startup=acp_startup_timeout、prompt=query_timeout+acp_prompt_grace（新构造参数，默认 30）；失败映射：client deadline 或 `-32603 context deadline exceeded` → `error="timeout"`、`stopReason != end_turn` → `acp_stop_reason: *`、spawn/握手失败 → `acp_startup_failed:*`；全程逐事件追加写 transcript（cancel/startup 失败保留 partial 证据，不再覆盖为空）；`terminate_process_tree()` 所有路径收尾；server stderr tail 追加进 `*.acp.stderr.log`；session 缓存 best-effort 复制（复用 `copy_traecli_session_files`，key 为 ACP server sessionId）。
- **唯一 M3 断言取代**（已在 commit message 与汇报声明）：`test_default_provider_missing_reports_live_transport_not_implemented`（断言占位文案 "ACP live transport is not implemented yet"）被 `test_default_provider_with_missing_binary_reports_startup_failure`（缺二进制 → `acp_startup_failed: spawn failed:*`）取代——该断言钉住的正是 M5 要替换的行为，实现后必然失效。其余 M1–M4 断言零改动；EXPECTED_META_KEYS 44 键不变；golden 零改动。
- `make test`：368（349 + 19）全绿；`git diff --check` 通过。

## 阶段 C：live 验证（证据全文见 probe 报告附录）

1. 单查询 smoke：Qwen3.6-Plus，`status=ok`，transcript parser 自检 `protocol_errors=[]`。
2. answer_only 禁用验证：18 项 disallowed 下发，transcript 零工具痕迹（隐藏语义），meta 一致。
3. 最小 live E2E：`run-20260611T230225`（默认 3 成员 DeepSeek-V4-Pro/GPT-5.5/openrouter-3o + 主席 DeepSeek-V4-Pro），9 次 ACP 调用全 ok、零 backfill；validate verdict `complete_ok_final`，`usable_final: true`，497 checks（175 ACP）0 failures。
4. 无孤儿进程（pgrep 证据在报告附录）。

## 残余风险 / 默认切换缺口（§4.4 口径）

- actual model 证据是会话级（currentModelId）非逐响应级，弱于 direct；上游若提供 update 流模型字段应立即升级。
- 工具名 canonical 映射基于已观察 title 集合（`bash`/`skill`/`WebSearch`）；MCP/未知工具按「非白名单即 deny + 记录原始 title」兜底，未知 title 被 allow 会触发 forbidden 判定（保守安全侧）。
- ACP 无 direct 的 tool/turn budget 流式监控与单次重试 wrapper（v1 不做，timeout 护栏覆盖挂死）。
- 默认切换还缺：≥3 次 paired probe（direct vs ACP 同 prompt）、代表性长 E2E、model_benchmark 时延/失败率对比——本轮单次 E2E 不构成切换依据，默认仍 direct。
