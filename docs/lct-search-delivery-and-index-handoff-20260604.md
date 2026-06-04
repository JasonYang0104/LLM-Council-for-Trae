# LCT 搜索生效计数与索引补位候选修正交接

创建日期：2026-06-04
目标执行方式：新会话、新分支、`/goal` 长线程执行
建议分支名：`codex/lct-search-delivery-index-20260604`

## 1. 这次要解决什么

本次只处理两个从 v10 live E2E 复盘中发现的可审计性问题：

1. **P1：WebSearch 调用与调用生效没有拆开。**
   当前 HTML 和索引能展示 LCT 是否允许搜索、是否观察到 WebSearch / WebFetch tool call、工具调用次数，但不能判断搜索结果是否成功进入模型上下文。v10 运行里 D 成员有 9 次 WebSearch tool call，同时 session log 出现 `unsupported tool output conversion` 和 `failed to convert ADK output to model format`。这说明“调用发生”不能等价为“调用结果生效”。

2. **P2：根目录 `<run_id>-index.md` 的 `backfill_candidates` 来源可能写错。**
   v10 根目录索引写成了默认成员阵容，但 terminal manifest 里的真实候补池来自 `metadata.quorum.backfill_candidates`。本次没触发 backfill，所以 final 未受影响；但失败复盘时会误导模型补位策略判断。

不要扩大范围。不要重做 LCT protocol，不要改模型阵容，不要把这轮变成 live benchmark。

## 2. 背景证据

### 2.1 v10 live run 观察

问题 workspace：

```text
/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae-v10
```

关键 run：

```text
lct-20260604-114802
```

已复验事实：

- `llm-council-for-trae validate lct-20260604-114802 --json` 结果为 `complete_ok_final`，`usable_final=true`。
- D 成员 `stage1/D.meta.json` 里 `error: null`、`status: ok`，并记录 9 次 WebSearch tool call。
- D 成员 `stage1/D.traecli.session.log` 同时出现：
  - `unsupported tool output conversion`
  - `failed to convert ADK output to model format`
- chairman final 没明显依赖 D 的低可信搜索源，因此本次最终答案可用；问题在审计记录不够精确。
- v10 根目录 `lct-20260604-114802-index.md` 的 `backfill_candidates` 写成默认成员，但 run manifest 的 `metadata.quorum.backfill_candidates` 是实际候补池。

### 2.2 已有项目约束

必须先读：

- `README.md`：项目入口、运行方式、validate contract、search 和 backfill 汇报要求。
- `docs/design.md`：整体 protocol 和 artifact 边界。
- `docs/lct-ux-evidence-hardening-design-20260602.md`：已明确 `search_enabled` 只表示允许搜索，不表示实际搜索；已有 HTML/search summary 基础。
- `docs/lct-auto-backfill-quorum-design-20260603.md`：auto-backfill、quorum、HTML 可见性的既有设计约束。
- `docs/lct-input-boundary-docs-design-20260604.md` 和 `docs/lct-input-boundary-docs-test-plan-20260604.md`：根目录索引、外层 Agent 搜索、LCT 内部搜索分离的文档契约。

关键代码入口：

- `src/llm_council_for_trae/provider.py`
  - `ModelCallResult` 当前持久化 `tool_calls`、`tool_calls_count`、`copied_session_files`。
  - `parse_stream_json()` 当前只解析 assistant tool calls，不统计 tool result 是否成功交付。
  - `copy_traecli_session_files()` 会复制 `session.log`，这是当前发现 conversion error 的证据来源。
- `src/llm_council_for_trae/council.py`
  - Stage 1 / Stage 2 / Stage 3 stage records 从 `ModelCallResult` 生成。
  - `tool_policy_record(call)` 是把工具策略和调用数据放进 manifest stage record 的关键点。
- `src/llm_council_for_trae/html_export.py`
  - `render_summary_cards()` 当前显示“允许 / 实际使用 / Web 工具调用 / 总工具调用”。
  - `summarize_search_usage()` 当前只根据 `allowed_tools` 和 `tool_calls` 计算搜索是否被调用。
- `src/llm_council_for_trae/validation.py`
  - `validate_run()` 当前检查 schema、必需文件、model match、tool contamination、quorum semantic checks，但不检查 WebSearch output conversion warning。
- `skills/llm-council-for-trae/SKILL.md`
  - 根目录 `<run_id>-index.md` 字段要求在这里约束。P2 主要改这里和对应测试。

## 3. 目标行为

### 3.1 HTML 展示层简化口径

按用户最新要求，HTML 搜索工具卡片只需要简化成：

```text
搜索工具：
- 调用次数：XX
- 调用生效次数：XX
```

推荐中文文案：

```text
搜索工具
调用次数：9
调用生效次数：0
```

不要在首屏塞长解释。详细 warning 可放在 metadata / warning banner / manifest JSON 里，但卡片只展示这两个数。

### 3.2 字段定义

建议新增或派生以下字段。命名可在实现时微调，但必须满足语义：

```json
{
  "lct_web_tool_calls": 9,
  "lct_web_tool_effective_calls": 0,
  "lct_search_conversion_errors": 2
}
```

定义：

- `lct_web_tool_calls`：观察到的 WebSearch / WebFetch 调用次数。继续沿用当前去重逻辑。
- `lct_web_tool_effective_calls`：有证据证明搜索工具结果成功进入模型上下文的次数。
- `lct_search_conversion_errors`：与 WebSearch / WebFetch 输出转换失败相关的错误计数。

如果当前 stream JSON 没有可靠 tool result event，但 session log 明确出现 conversion failure，则不能把所有 WebSearch 调用都当成有效。最保守行为：

```text
调用次数 = observed web tool calls
调用生效次数 = max(0, observed web tool calls - conversion_error_count) 或 0
```

更推荐的行为：

```text
调用生效次数 = 已观察到的、和 WebSearch/WebFetch tool_use_id 对得上的成功 tool_result 数
```

如果无法从 stream/session 证明成功交付，则宁可显示 `0` 或 `未知`，不要显示等同调用次数。用户要求卡片是数字，所以实现上建议用 `0`，并在 metadata/warnings 里解释“无法证明生效”。

### 3.3 validate 行为

validate 不应因为 conversion error 直接把一个已有 final 判成不可用。更合适的是新增 warning / check：

```text
name: search_tool_output_conversion
ok: true
message: "WebSearch tool calls observed, but conversion errors mean effective delivery is lower than calls"
severity: warning
```

如果现有 `checks` 没有 severity 体系，可以先把 warning 写入 manifest `warnings` 或 validate payload 的新增 `warnings` 字段；不要把 `complete_ok_final` 改成 `invalid_artifacts`。本次问题是审计风险，不是最终答案必然不可用。

### 3.4 P2 根目录 index 规则

Skill 和 README 的 index contract 要明确：

```text
backfill_candidates 必须来自 terminal manifest 的 metadata.quorum.backfill_candidates。
```

不得从以下来源替代：

- 默认成员阵容。
- `models --recommend --json` 的 primary roster。
- 当前实际参与 Stage 1 的有效成员。

如果 manifest 没有 `metadata.quorum.backfill_candidates`，索引应写：

```text
backfill_candidates: not recorded
```

而不是猜。

## 4. 推荐实现节奏

执行时必须每个阶段 commit。不要用 `git add .`；只 stage 本阶段相关文件。

### 阶段 0：启动与基线确认

目标：确认新分支、干净基线、读完文档。

要求：

1. 从最新 `origin/main` 创建新分支。
2. 创建或清空本轮 `notes.md`，中文记录运行中决策。
3. 读取本 handoff 和第 2 节列出的关键文档。
4. 跑基线验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

阶段 commit：

```text
docs: start search delivery handoff notes
```

如果只创建 `notes.md` 不想单独 commit，也可以把阶段 0 和阶段 1 文档 commit 合并，但后续实现阶段必须分 commit。

### 阶段 1：设计方案与测试方案

目标：先沉淀正式设计，不直接改代码。

新增文档建议：

- `docs/lct-search-delivery-and-index-design-20260604.md`
- `docs/lct-search-delivery-and-index-test-plan-20260604.md`

设计文档至少说明：

- “调用次数”和“调用生效次数”的定义。
- 为什么 conversion error 不等于 run failed。
- HTML 卡片为什么只展示两个数字。
- manifest / meta / validate / HTML / Skill index contract 的数据流。
- legacy artifact 兼容策略。

测试方案至少覆盖：

- provider / stream parser 如何识别成功 tool result。
- session log conversion error 如何进入 meta / manifest。
- HTML 简化展示。
- validate warning。
- Skill / README 对 `backfill_candidates` 来源的文档契约。

阶段 commit：

```text
docs: design search delivery and index provenance
```

### 阶段 2：TDD 红灯测试

目标：先写会失败的测试，证明当前缺口存在。

建议测试点：

1. `tests/test_lct_model_productization.py`
   - `test_search_summary_distinguishes_calls_from_effective_calls`
   - 构造 manifest：`tool_calls` 有 2 个 WebSearch，但 `search_tool_output_conversion_errors` 有 1 或 2 个。
   - 断言 HTML summary 出现“调用次数：2”“调用生效次数：0/1”。

2. `tests/test_core.py` 或新增更合适的 provider 测试文件
   - 构造 stream JSON：assistant 发起 WebSearch tool call，但没有匹配成功 tool result。
   - 断言 parser 不把它算成 effective。

3. `tests/test_core.py` / `tests/test_validation.py`
   - 构造 meta 或 manifest 有 WebSearch tool call 和 conversion error。
   - 断言 validate 有 warning，不把 usable final 打成 invalid。

4. `tests/test_global_install_skill_docs.py` 或 `tests/test_lct_model_productization.py`
   - 断言 canonical Skill / README 明确 `backfill_candidates` 来源必须是 `manifest.metadata.quorum.backfill_candidates`。
   - 断言文档不允许把 default members 当 backfill candidates。

阶段 commit：

```text
test: cover search delivery and index provenance gaps
```

### 阶段 3：provider / manifest 实现

目标：让工具调用生效证据进入 meta 和 manifest。

建议切入：

1. 扩展 `ModelCallResult`：
   - `tool_result_calls` 或 `effective_tool_calls`
   - `web_tool_effective_calls_count`
   - `tool_output_conversion_errors`

2. 扩展 `parse_stream_json()`：
   - 继续记录 assistant tool calls。
   - 尝试识别非 Agent 的 `tool_result` event。
   - 如果 stream JSON 无法识别具体 WebSearch result，但 session log 有 conversion failure，要记录 conversion error。

3. 在 `_query_model_once()` 调用 `copy_traecli_session_files()` 后读取复制出来的 `*.traecli.session.log`，解析关键错误：

```text
unsupported tool output conversion
failed to convert ADK output to model format
```

4. 在 `tool_policy_record(call)` 或 stage record 生成处，把新字段带入 manifest。

阶段 commit：

```text
feat: record effective web tool delivery evidence
```

### 阶段 4：HTML / validate 实现

目标：用户面和校验面同步。

HTML：

- 修改 `render_summary_cards()` 的搜索卡片。
- 搜索卡片只展示：

```text
调用次数：XX
调用生效次数：XX
```

- 不再展示“允许：是 / 实际使用：是”这种容易误读的卡片口径。

validate：

- 对有 WebSearch/WebFetch 调用但有效次数小于调用次数的 run，输出 warning 或 manifest warning。
- 不因为这个 warning 直接让可用 final 失败。

阶段 commit：

```text
feat: display effective search calls in html and validate
```

### 阶段 5：Skill / README index contract 修正

目标：解决 P2。

改动范围：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`
- 相关 docs contract tests

必须写清：

```text
backfill_candidates 来源：terminal manifest metadata.quorum.backfill_candidates
```

并明确：

```text
如果 manifest 未记录，写 not recorded，不猜。
```

阶段 commit：

```text
docs: require manifest-sourced backfill candidates
```

### 阶段 6：全量验证、live fixture 复核、最终简报

必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 `traecli` 当前可用，再追加：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
```

可选但推荐：用 v10 run artifact 或最小 fixture 验证 HTML 字符串。不要把旧 v10 run 直接改写成新 run；它是复盘证据。

最终产物：

- 所有测试通过。
- `notes.md` 有中文运行记录。
- PM director 风格简报：
  - `docs/lct-search-delivery-and-index-brief-20260604.md`
  - `docs/lct-search-delivery-and-index-brief-20260604.html`

阶段 commit：

```text
docs: add search delivery implementation brief
```

## 5. subagent 分工建议

使用 `subagent-lead`，至少拉一个独立 reviewer。

推荐分工：

1. 主 Agent：负责设计、TDD、实现和最终汇总。
2. Subagent A：审查 P1 数据流，重点看 `provider.py`、`council.py`、`html_export.py`、`validation.py` 是否一致。
3. Subagent B 可选：审查 P2 文档契约，重点看 README、canonical Skill、`.trae` Skill 和 tests 是否一致。

Subagent 输出不要直接改文件，先返回 findings；主 Agent 决定是否纳入。

## 6. notes.md 要求

`notes.md` 必须中文维护，至少记录：

- 本轮分支名和开始时间。
- 哪些文档已读。
- 每个阶段做了什么、commit id。
- 任何规范没有明确但实现时不得不做的决定。
- 对 `调用生效次数` 的最终定义。
- 如果没跑 live run，明确说明只做了 unit / fixture 验证。
- 如果跑了 live run，记录 run_id、validate verdict、HTML 路径。

不要把 `notes.md` 当流水账。只记录对复盘有价值的取舍和证据。

## 7. 最小启动提示词

新会话可以直接使用：

```text
/goal 执行：/Users/bytedance/Documents/AI Coder/COCO-llm-council/docs/lct-search-delivery-and-index-handoff-20260604.md
```

并追加：

```text
新分支执行。和 subagent-lead 一起搞，TDD 驱动，先沉淀设计方案和测试方案再动手。每个阶段 commit。维护中文 notes.md。完成后生成 PM director 风格 brief md/html。你的职责是让测试都通过。
```

## 8. 非目标

- 不重新跑完整 benchmark。
- 不修改默认模型阵容。
- 不把 conversion error 升级为硬失败，除非后续发现它直接导致 final 缺失或 artifact 不完整。
- 不改写 v10 已有 run artifact。
- 不删除 `.llm-council-for-trae/` 里的用户运行产物。
- 不把 HTML export 和 chairman synthesis 混成一步。
