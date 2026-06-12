# M3 任务卡：offline ACP adapter 与 transcript parser（交执行 Agent）

- 日期：2026-06-11
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §3
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m3-20260611`，分支 `codex/lct-acp-m3-offline-adapter-20260611`（从 `main @ a12eac3` 切出）
- 流程约束：纯本地，不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 回滚锚点：tag `pre-acp-m2` 已打；本阶段合并前打 `pre-acp-m3`。

## 背景与基线事实

- `main @ a12eac3`：M1+M2 已合入，`make test` 320 个 unittest 全绿；`build_model_runtime()` 的 acp 分支当前 fail-fast。
- 移植源（只读，共享 object store）：commit `2668359 feat: add offline ACP runtime adapter`（P2 状态）＋ 研究线 notes.md Phase 4 节（红绿过程与三个已知坑）。
- 研究线后续 commits（`bfa7be9` evidence validation、`deb9119` provenance）属 M4，不带入。

## 目标

ACP transcript 纯函数 parser ＋ `AcpTraeCliRuntime` offline skeleton（可注入 transcript provider），离线证明 `query_model()` 映射正确；live transport 明确未实现且失败语义诚实。

## 移植内容

1. 新模块 `src/llm_council_for_trae/acp_transcript.py`：`parse_acp_transcript_text()`（纯函数）、`AcpTranscriptParseResult`、`resolve_acp_transcript_path()`（拒绝绝对路径与逃出 run root 的 `../`）。
2. 新模块 `src/llm_council_for_trae/acp_runtime.py`：`AcpStartupError`、`AcpQueryRequest`、`AcpTraeCliRuntime`（只经可注入 `transcript_provider` 做 offline 映射；默认 provider 缺失 → `acp_startup_failed: ACP live transport is not implemented yet`，不伪装 live）。command 记录为 `["traecli", "acp", "serve"]` 形态，不复用 direct 的 prompt 脱敏假设。
3. `build_model_runtime()` acp 分支：fail-fast → 返回 `AcpTraeCliRuntime`；同步更新 `test_runtime_backend_contract.py` 的对应断言（研究线同款修订，这是 M2 测试唯一允许的改动，commit message 说明）。
4. 移植测试：`tests/contract/test_acp_transcript_parser.py`、`tests/contract/test_acp_model_runtime_contract.py`（覆盖：clean transcript → ok ＋ 三 sidecar 落盘；forbidden permission 被 deny 且未 used → ok；forbidden 被 allow → fail；forbidden used → fail；protocol error / startup error / cancellation 各自映射；坏 JSONL → `protocol_errors` 不静默；无最小 ACP 结构 → missing required method errors；路径约束）。

## 上轮 review 发现（本阶段必须解决）

1. **`repair_contribution_map` 类型收窄**：provider 参数标注从 `TraeCliProvider` 收窄为 `ModelRuntime`（类型层面改动，不改行为）。
2. **签名门卫测试**：新增契约断言——用 `inspect.signature` 对比 `AcpTraeCliRuntime.query_model` 与 `TraeCliProvider.query_model`（或 `ModelRuntime` protocol 定义）的参数名集合与顺序一致，防 structural Protocol 下的签名漂移在运行期才暴露。

## 研究线已知坑（直接吸收，勿重踩）

- Python 3.9：类型别名禁用 `str | Any` 运行时求值形态，回退 `Callable[..., Any]`。
- macOS 临时目录 `/var/...` 规范化为 `/private/var/...`：路径约束测试用 `root.resolve()` 比较。
- P1 的 acp fail-fast 测试在本阶段更新为 factory 返回 `AcpTraeCliRuntime` 契约。

## 边界（不得越过）

1. 不新增 validation hard gate、不改 HTML、不扩 `EXPECTED_META_KEYS`（37 键不变，evidence 字段属 M4）。
2. 不实现 live transport（默认失败语义如上）。
3. M1 contract tests 与 golden 零改动（本阶段无 config 字段新增，golden 不得重生成）。
4. `src/` 改动限于：两个新模块 ＋ `council.py`（factory ＋ repair 标注）。

## 验收标准

1. `make test` 全绿，总数 = 320 ＋ 新增（研究线 P2 为 13 个，加签名门卫测试，以实测为准）。
2. `git diff main..HEAD -- tests/golden/` 为空（golden 零改动机器证明）。
3. M1 测试文件零改动（M1 任务卡同款 diff 命令为空）。
4. 红态确认记录：两个新测试文件在产品模块缺失时 import 失败（红）→ 实现后绿。
5. `git diff --check` 通过；notes.md 追加 M3 节。
6. 提交粒度：红绿两 commit，停在分支。

## 汇报要求

最终测试总数与新增数、M2 测试文件改动的精确范围与理由、两个 review 发现的解决证明、所有验收命令 pass/fail、commit SHA、遗留风险。如实报告。
