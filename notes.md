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
