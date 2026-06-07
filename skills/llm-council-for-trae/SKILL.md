---
name: llm-council-for-trae
description: 当用户要求安装/更新 LCT、从 GitHub main 全局安装最新版 LCT、使用 LCT、跑 LCT、council run、用委员会回答、让多个模型讨论，或需要 LLM-Council-for-Trae 生成可复盘答案时使用。默认在干净问题 workspace 中调用全局安装的 llm-council-for-trae CLI，运行后必须 validate，并汇报最终答案与 HTML artifact。
---

# LLM-Council-for-Trae Workflow

## Trigger

当用户说“安装 LCT”“更新 LCT”“从 GitHub main 全局安装最新版 LCT”“使用 LCT”“跑 LCT”“council run”“用委员会回答”“让多个模型讨论”或明确要求 `LLM-Council-for-Trae` 时触发。

## Global Install / Update From GitHub Main

当用户只要求安装或更新 LCT，而不是立即运行 council，先完成安装并写 `notes.md`，不要把安装成功包装成 E2E 成功。执行顺序：

自然语言安装入口：用户说 `请从 GitHub 仓库 https://github.com/JasonYang0104/LLM-Council-for-Trae 的最新版 LCT` 时，等同于从 GitHub main 安装或更新。必须使用 `~/.LCT + make install-global`：clone/fetch/pull `~/.LCT` 后运行 `make -C "$HOME/.LCT" install-global`；不得使用 `uv tool install`。安装成功必须同时证明：`~/.LCT HEAD == GitHub refs/heads/main`、`command -v llm-council-for-trae` 的 wrapper 包含 `.LCT/src`、Skill symlink 指向 `~/.LCT/skills/llm-council-for-trae`。

```bash
if [ ! -d "$HOME/.LCT/.git" ]; then
  git clone https://github.com/JasonYang0104/LLM-Council-for-Trae.git "$HOME/.LCT"
fi
git -C "$HOME/.LCT" fetch origin --prune
git -C "$HOME/.LCT" checkout main
git -C "$HOME/.LCT" pull --ff-only origin main
make -C "$HOME/.LCT" install-global
```

安装最新版不能只看 `llm-council-for-trae --version`。必须在 `notes.md` 记录每条 actual command、exit code、key stdout/stderr 和 pass/fail 结论：

```bash
git -C "$HOME/.LCT" remote get-url origin
git -C "$HOME/.LCT" rev-parse HEAD
git -C "$HOME/.LCT" rev-parse origin/main
git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main
LOCAL_HEAD="$(git -C "$HOME/.LCT" rev-parse HEAD)"
GITHUB_MAIN="$(git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main | awk '{print $1}')"
test "$LOCAL_HEAD" = "$GITHUB_MAIN"
command -v llm-council-for-trae
head -5 "$(command -v llm-council-for-trae)"
grep -F '.LCT/src' "$(command -v llm-council-for-trae)"
PYTHONPATH="$HOME/.LCT/src${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from pathlib import Path
import llm_council_for_trae.contribution_map as cm

source = Path(cm.__file__).resolve()
expected = (Path.home() / ".LCT" / "src").resolve()
print(source)
assert str(source).startswith(str(expected)), source
assert hasattr(cm, "extract_contribution_map")
assert hasattr(cm, "strip_contribution_map_fence")
PY
```

`~/.LCT HEAD == GitHub refs/heads/main` 是硬门槛。如果 `origin` 不是 `https://github.com/JasonYang0104/LLM-Council-for-Trae.git`、本地 `HEAD` 与 GitHub main SHA 不一致、`command -v` 指向 uv tool、`site-packages`、旧开发 checkout，或 wrapper 不包含 `.LCT/src`，重新执行 `make -C "$HOME/.LCT" install-global` 后再验证。只有以上 freshness checks 通过，才可以说“已从 GitHub main 全局安装最新版 LCT”。

## Preflight

1. 确认当前目录不是 LCT 源码 repo。出现以下任一标记时停止，除非用户明确说正在做 LCT 开发：
   - `src/llm_council_for_trae/`
   - `.trae/agents/`
   - `profiles/subagents.json`
2. 确认 `traecli --version` 可用，并记录输出。
3. 确认 `traecli models --json` 返回非空模型列表。默认 runtime 仍是 traecli；正常路径继续使用 `llm-council-for-trae run` 和 `llm-council-for-trae validate`。
4. 如果 `traecli models --json` 返回空列表、非 0 退出、明显超时或无结构化输出，不要立刻启动 run，也不要把问题包装成普通 live `traecli` 可用。先记录默认入口阻断证据，再 probe explicit runtime override。runtime override 是外层 Agent 有证据时显式传 `--runtime-command coco`；coco 只在显式 override 中使用；这不是 CLI silent fallback，也不是把默认入口改写为 `coco`。
5. override probe 必须记录：

```bash
traecli --version
traecli models --json
coco --version
coco models --json
llm-council-for-trae --runtime-command coco doctor --json
llm-council-for-trae --runtime-command coco models --recommend --json
```

只有 `coco models --json` 返回非空、`llm-council-for-trae --runtime-command coco doctor --json` 没有非 MCP 阻断错误，并且 `llm-council-for-trae --runtime-command coco models --recommend --json` 的 `recommendation.members` 和 `recommendation.chairman` 都可用时，才允许本次显式 override。
6. 确认 `command -v llm-council-for-trae` 可找到全局 CLI。
7. 尽量确认 wrapper 内容指向 `~/.LCT/src`，而不是旧开发 checkout。
8. 如果 CLI 不可用，提示用户先完成 `~/.LCT` 全局安装，并把本 Skill 安装到 `~/.agents/skills/llm-council-for-trae`。

## Input Preparation

LCT CLI 只消费 `_lct_question.md`；是否做轻量意图理解和 prompt shaping 是外层 Agent 行为。先区分两层输入：

- `council input`：用户真正要委员会回答的问题、必要事实背景、输出要求，以及 `Report topic: <中文议题>`。`Report topic` 是报告元数据，不是成员任务指令。
- `operator envelope`：使用 LCT、运行 validate、写 final/index、生成 HTML、维护 notes.md、Git/PR/测试职责、开 branch、提交代码等外层执行职责。外层执行指令不得写入 _lct_question.md。

短例：

- 反例：不要写入 `_lct_question.md`：`使用LCT回答："""`
- 正确：`_lct_question.md` 只写真实问题：`分析解读这个 JD。先意图理解我为何有这个需求，而不是直接动手。`
- 外层 Agent 自己执行安装、validate、notes.md、HTML、Git/PR；这些不交给 council 成员。

默认保留用户原始实质问题。输入模式按以下矩阵判断：

- raw original input：用户说 `使用 LCT 回答`、`不要改写`、`按原文`、`只用原始输入`、`评估 LCT 对原问题的理解` 时使用。该模式只追加 `Report topic`，不得加 `Agent interpretation`，不得拆解、重写或补 fact pack。
- structured by Agent：用户明确说 `先想我真正需要什么`、`站在架构师角度评估`、要求 `fact pack`、`最新资料` 或 `来源` 时使用。必须保留 `Original input`，fact pack 直接内嵌并标来源。
- negative triggers：`详细分析`、`深入一点`、`给完整方案` 不得单凭字面触发结构化改写；只有上下文另有明确意图时才进入 `structured by Agent`。
- operator envelope：`notes.md`、`validate`、生成 HTML、写 final/index、Git/PR、测试职责、开 branch、提交代码等外层执行职责，绝不进 `_lct_question.md`。

只有当用户明确要求思考真实意图、拆解问题、重构输入、加入事实包或结构化输出时，才使用 `structured by Agent` 模式：

1. 保留用户原始输入，使用清晰标题标注为 `Original input`。
2. 可以补充 `Agent interpretation` 和 `Suggested council focus`，用于拆解约束、成功标准、需要正反论证的维度。
3. 不要伪造用户没有表达过的事实、偏好或结论。

如果用户明确说 `按原始输入`、`不要改写`、`只用原文`、`我要评估 LCT 对原始问题的理解` 或类似表达，必须使用 `raw original input` 模式：不加 `Agent interpretation`、不拆解、不补 fact pack、不重写问题。仍应在原文下方追加 `Report topic: <中文议题>`；它是报告元数据，不是 prompt shaping。

如果外层 Agent 需要补充事实背景，fact pack 必须直接嵌入 _lct_question.md，放在用户原始输入之后并清楚标注来源。fact pack 只包含事实背景和来源，不能包含执行指令；不要要求成员读取 sidecar 文件，也不要让模型去读取另一个 sidecar 文件。`notes.md` 只由外层 Agent 维护，用来记录执行过程、测试和风险；如果用户要求维护 notes.md，调用 Agent 应执行这个要求，但不得把它写入 council input。不要要求 council 成员创建、读取、修改或维护 notes.md，模型不要创建或修改 notes，也不要把 notes 当成 council 输入。

## Model Selection

默认不打扰用户选择模型。只有用户明确要挑成员、指定主席、比较模型阵容，或要求“我想自己选模型”时，外层 Agent 才进入自选模型体验。

- 用户只问“有什么模型”时，只展示 `models --recommend --json` / 当前模型清单和推荐套装，不擅自启动 run。
- 用户说“我想指定模型”“我想自己选模型”“想挑成员/指定主席/比较模型阵容”，但想指定模型但没有给具体模型时，先读取当前模型清单和推荐阵容，再追问用户或给文本 fallback。
- 非 TTY run 必须显式指定模型路径：允许 `--default-models`、`--selected-members/--selected-chairman`、原生 `--members/--chairman` 或 `--profile`，具体取决于用户意图；外层 Agent 可先追问用户后再运行。
- 可用时可以用 `AskUserQuestionTool` 展示当前模型清单；不可用时必须提供文本 fallback。
- Agent-assisted 自选路径必须调用独立 CLI surface：`--selected-members` / `--selected-chairman`。
- 不要复用原生 `--members` 表达 agent-assisted 自选；原生 `--members` 是 power-user 精确路径，给几个跑几个，不补足、不裁剪。
- 自选路径的运行索引和 manifest provenance 必须记录 `selection_surface=agent_assisted`、用户请求的 members、解析后的 members、补足成员、裁剪成员和最终 config。
- `--selected-chairman` 当前不能单独出现；如果用户只想指定主席、成员保持默认，必须明确改用原生 `--members/--chairman` 并说明该路径是 power-user 精确语义。

## Chairman Contribution Map

主席贡献说明默认开启。日常 `run` 不需要追加 `--chairman-contribution-map`；该兼容 flag 仍可传入，但默认路径已经会请求主席输出 contribution map。

如明确不想请求主席贡献说明，运行时追加 `--no-chairman-contribution-map`。如本次是 release / E2E strict gate，运行时追加 `--require-chairman-contribution-map`，让缺失或非法 sidecar 成为 validate failure。

索引和最终汇报必须记录：

- `chairman_contribution_requested: true|false`
- `chairman_contribution_required: true|false`
- `chairman_contribution_present: true|false`
- `contribution_map_path: stage3/contribution_map.json|none`
- `contribution_map_validate_status: ok|warning|failed|missing|disabled`

该功能只使用 Stage 3 写出的 `stage3/contribution_map.json` blocks 渲染 HTML 来源说明；不要在外层 Agent 或 HTML 阶段按 Markdown 自然段猜来源。HTML 会根据 `metadata.aggregate_rankings` 给单一成员和多成员共识来源追加 `同侪#n`，作为主席无法改写的可验证锚点。默认 requested 但不 required 时，缺 sidecar 或结构非法只记录 warning，并 fallback 到 `stage3/final.md`；Stage 3 会对 contribution map JSON 字符串里的常见未转义英文双引号做有限修复；无论 sidecar 是否可用，`stage3/final.md`、HTML 正文和复制 Markdown 都不会展示尾部 contribution JSON 块。只有 `required=true` 才把缺失或非法 sidecar 判为 validate failure。legacy run 缺少 `metadata.chairman_contribution` 或显式 disabled 不要求 contribution map。不要输出贡献百分比，不要把 Stage 2 同侪排序解释成模型能力排行。

无论哪种模式，最终根目录 `$RUN_ID-index.md` 和对用户汇报都必须写明 `Input mode` 和证据字段；输入模式取值为：

```text
Input mode: raw original input
```

或：

```text
Input mode: structured by Agent
```

`$RUN_ID-index.md` 必须拆开记录 LCT 内部搜索证据和外层 Agent 自己补充的外部搜索证据：

```text
runtime_default_command: traecli
runtime_default_version: <value or error>
runtime_default_models_status: ok|empty|failed|timeout|not_checked
runtime_default_models_count: <number or none>
runtime_override_used: true|false
runtime_override_command: coco|none
runtime_override_reason: <short reason or none>
runtime_override_version: <value or none>
runtime_override_doctor_ok: true|false|not_checked
runtime_override_models_count: <number or none>
runtime_override_recommendation_members: <models or none>
runtime_used_by_lct: traecli|coco|other
lct_search_allowed: true|false
lct_search_used: true|false
lct_web_tool_calls: <number>
lct_web_tool_effective_calls: <number>
lct_search_conversion_errors: <number>
agent_external_search_allowed: true|false
agent_external_search_used: true|false
agent_sources: <URLs or none>
agent_fact_pack_path: <path or none>
agent_added_context: true|false
final_answer_source: stage3/final.md
valid_stage1_models: <comma-separated models or none>
quorum_default: <number>
quorum_effective: <number>
low_quorum_used: true|false
backfill_attempts: <models or none>
stage2_reviewers: <models or none>
stage1_backfill_members: <models or none>
stage2_reviewer_backfill: <models or none>
review_subject_count: <number>
reviewer_count: <number>
chairman_fallback_used: true|false
backfill_candidates: <models or not recorded>
```

## Run

1. 按 Input Preparation 规则将用户问题写入当前 workspace 的临时 Markdown 文件，例如 `_lct_question.md`。默认保留用户原文；在原始问题下方追加一行 `Report topic: <中文议题>`，让 HTML 标题稳定生成为 `<中文议题>：多模型智囊团评估`。
2. 设置 run id：

```bash
RUN_ID="lct-$(date +%Y%m%d-%H%M%S)"
```

3. 先记录推荐阵容，作为当前模型可用性和推荐安全过滤参考：

```bash
llm-council-for-trae models --recommend --json
```

当前静态默认模型套是：

```text
members: DeepSeek-V4-Pro, GPT-5.4, openrouter-3o, Kimi-K2.6
chairman: DeepSeek-V4-Pro
```

推荐阵容不改变 primary default members；它只是当前模型可用性和推荐安全过滤参考，不是根目录 index 的 backfill candidates 来源。CLI 默认会在同一个 run 内 auto-backfill，不整轮重跑。最终 `$RUN_ID-index.md` 的 `backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`；如果 terminal manifest 没有记录该字段，写 `backfill_candidates: not recorded`。不得从默认成员阵容、不得从 models --recommend --json 的 primary roster、不得从实际有效 Stage 1 成员猜测候补池。

补位语义必须拆开：Stage 1 是 member backfill，只有 Stage 1 quorum 不足时才新增候选答案；Stage 2 是 reviewer-only backfill，当 Stage 1 quorum 已经满足但 reviewer 失败或不足时，候补模型只评审既有有效 Stage 1 answers，不新增候选答案。

工具模式由外层 Agent 基于任务判断。answer_only 是可选工具模式，不强制 answer_only；外层 Agent 可以自行判断让 LCT 成员在 `search_enabled` 下内部搜索、先由外层 Agent 补 fact pack、使用 answer_only，或在只读代码/文件问题中使用 workspace_enabled。search_enabled 只表示搜索被允许，不表示模型实际搜索了；索引必须继续拆开记录 `lct_search_used` 和 `agent_external_search_used`。

4. 执行非交互 run。默认启用 auto-backfill；如第 3 步的推荐结果里有适合作为候补的模型，可在命令中追加 `--backfill-members "<comma-separated candidates>"` 显式给出优先级：

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --default-models \
  --run-id "$RUN_ID" \
  --timeout 180 \
  --json
```

如果 Preflight 触发 runtime override，run 和 validate 必须都显式使用同一个 runtime command：

```bash
llm-council-for-trae --runtime-command coco run \
  --input _lct_question.md \
  --default-models \
  --run-id "$RUN_ID" \
  --timeout 180 \
  --json
```

记录：

```text
default_attempt_status: ok|degraded_ok|failed|skipped
default_attempt_run_id: <RUN_ID or none>
default_attempt_failure_reason: <reason or none>
backfill_candidates: <models or not recorded>
backfill_attempts: <models or none>
stage1_backfill_members: <models or none>
stage2_reviewer_backfill: <models or none>
review_subject_count: <number>
reviewer_count: <number>
```

5. 如果 run 表面返回 `failed`、默认模型缺失、apparent hang、run JSON 为空，或中途目录看起来缺 Stage 2 / Stage 3，先读取 terminal manifest 并执行：

```bash
llm-council-for-trae validate <run_id> --json
```

不要用自然语言观察判 failed。`degraded_ok 是可用结果`，成员失败不等于 run 失败。如果 validate JSON 显示 `usable_final: true`，直接交付该 run；如果没有可用 final，报告阻断点和已尝试的 backfill，不要另起整轮推荐阵容 run。

6. 如果 run 返回 `ok` 或 `degraded_ok`，把该 run 记为 `FINAL_RUN_ID`，再执行 validate：

```bash
llm-council-for-trae validate "$FINAL_RUN_ID" --json
```

override 路径必须使用：

```bash
llm-council-for-trae --runtime-command coco validate "$FINAL_RUN_ID" --json
```

validate JSON 必须记录 `terminal`、`usable_final`、`stage3_final_exists`、`html_exists`、`failed_stage_records` 和 `verdict`。`verdict` 取值为 `complete_ok_final`、`usable_degraded_final`、`in_progress`、`failed_no_final`、`invalid_artifacts`。只有 `usable_final: true` 才能交付最终答案；`$RUN_ID-index.md` 的 run status / validate status / verdict 必须来自 validate JSON。

7. 从 artifacts 读取最终答案：

```bash
cat ".llm-council-for-trae/runs/$FINAL_RUN_ID/stage3/final.md"
```

8. 在当前 workspace 根目录写出：
   - `$RUN_ID-final.md`：主席最终答案。
   - `$RUN_ID-index.md`：run id、run status、validate status、HTML 路径、Input mode、runtime_default_command、runtime_default_version、runtime_default_models_status、runtime_default_models_count、runtime_override_used、runtime_override_command、runtime_override_reason、runtime_override_version、runtime_override_doctor_ok、runtime_override_models_count、runtime_override_recommendation_members、runtime_used_by_lct、lct_search_allowed、lct_search_used、lct_web_tool_calls、lct_web_tool_effective_calls、lct_search_conversion_errors、agent_external_search_allowed、agent_external_search_used、agent_sources、agent_fact_pack_path、agent_added_context、final_answer_source、valid_stage1_models、quorum_default、quorum_effective、low_quorum_used、backfill_candidates、backfill_attempts、stage2_reviewers、stage1_backfill_members、stage2_reviewer_backfill、review_subject_count、reviewer_count、chairman_fallback_used、default attempt 状态、失败模型或 timeout。

## Report

向用户分开汇报：

- run id
- run status
- validate status
- validate verdict
- final answer path
- HTML report path
- live runtime：正常路径写 `live runtime: traecli`；override 路径写 `live runtime: coco via explicit --runtime-command override`；非 live 路径写 `live runtime: unavailable`
- Input mode: `raw original input` 或 `structured by Agent`
- runtime_default_command
- runtime_default_models_status
- runtime_override_used
- runtime_override_command
- runtime_override_reason
- runtime_used_by_lct
- lct_search_allowed：LCT member 是否允许 `WebSearch` / `WebFetch`
- lct_search_used：LCT artifacts 中是否实际观察到 `WebSearch` / `WebFetch` tool call
- lct_web_tool_calls：LCT artifacts 中的 Web 工具调用数量
- lct_web_tool_effective_calls：有证据证明搜索结果成功进入模型上下文的 Web 工具调用数量
- lct_search_conversion_errors：WebSearch / WebFetch 输出转换失败相关 warning 数量
- agent_external_search_allowed：外层 Agent 是否被允许在 LCT 之外自行检索
- agent_external_search_used：外层 Agent 是否实际在 LCT 之外自行检索
- agent_sources / agent_fact_pack_path：外层 Agent 补充给问题文件的来源或 fact pack
- final_answer_source：通常为 `stage3/final.md`
- valid_stage1_models：进入 Stage 2 / Stage 3 依据的有效 Stage 1 成员
- quorum_default / quorum_effective：默认 quorum 要求和最终有效成员数
- low_quorum_used：是否使用 low quorum 降级继续
- backfill_attempts：同一个 run 内 auto-backfill 实际尝试过的候补模型
- stage2_reviewers：实际参与 Stage 2 的 reviewer
- stage1_backfill_members：生成过新增 Stage 1 候选答案的 member backfill 模型
- stage2_reviewer_backfill：只补交 Stage 2 review 的 reviewer-only backfill 模型
- review_subject_count：Stage 2 实际被评审的有效 Stage 1 answers 数量
- reviewer_count：Stage 2 有效 reviewer 数量
- chairman_fallback_used：主席是否使用备选链
- failed models / timeout
- live `traecli` 是否可用

`--member-tool-mode search_enabled` 只代表搜索工具被允许，不代表模型实际搜索了。必须把 `lct_search_allowed` 和 `lct_search_used` 分开说；如果 manifest 中 tool call count 为 0，就明确说搜索被允许但未发生。外层 Agent 自己做的网页检索必须进入 `agent_external_search_*` 字段，不要混进 LCT 的 `lct_search_*` 字段。

如果 `traecli` 不可用、模型列表为空、run 未产生有效 artifacts，必须说清楚是 skipped / failed。不要把 fake runtime 结果说成 live traecli 结果。

## Hard Constraints

- 非 TTY run 必须显式指定模型路径：可用 `--default-models`、`--selected-members/--selected-chairman`、原生 `--members/--chairman` 或 `--profile`；不要把 Agent 非 TTY 简化成只能 `--default-models`。
- 必须使用 `--json`：外层 Agent 需要结构化输出。
- 必须运行 `validate`：run 完成不等于 artifact 可信。
- 默认 runtime 仍是 traecli；coco 只在显式 override 中使用。
- runtime override 必须先记录 `traecli models --json` 空列表、失败或超时证据，再证明 `coco models --json` 非空、`--runtime-command coco doctor` 可用、`recommendation.members` 和 `recommendation.chairman` 可用。
- runtime override 路径的 run 和 validate 必须都带 `--runtime-command coco`；不要只在 run 使用 override。
- runtime override 不是 CLI silent fallback；不要把 override 结果汇报成普通 live `traecli`。
- 默认恢复路径是 CLI 在同一个 run 内 auto-backfill；不要把推荐阵容另起整轮 run 当成主恢复路径。
- 只有 Stage 1 quorum 不足时才使用 member backfill 新增候选答案；Stage 2 reviewer-only backfill 不新增候选答案。
- 显式候补只能通过 `--backfill-members` 提供优先级；默认和显式候补都会硬排除 Seed/Doubao/GLM，但不会仅因 `GPT-5.5`、Beta 标记或 queue heat >=95% 自动排除。不要把未批准或被硬排除的模型伪装成可用候补。
- 不要在问题 workspace 中 clone LCT 仓库。
- 不要在 LCT 源码 repo 中跑用户问题；切换到干净问题 workspace。
- 不要修改 `.llm-council-for-trae/` 中的 artifacts；只读，必要时复制最终答案到 workspace 根目录。
- 不要把 fake runtime、fixture、单元测试或非 live 路径说成 live `traecli` smoke。

## Failure Handling

- `traecli` 不可用：报告阻断点；如果只是 `traecli models --json` 空列表、失败或超时，先按 Preflight 取证并 probe explicit runtime override；条件不满足才停止 live run。
- `coco` override 条件不满足：报告 `live runtime: unavailable`，停止 live run；允许做单元测试、fixture schema validation 或 HTML export fixture，但不得包装成 live LCT。
- `llm-council-for-trae` 不可用：提示完成 `~/.LCT` 全局安装。
- 当前目录疑似 LCT 源码 repo：要求切换到干净问题 workspace。
- run 超时：报告 timeout，建议调大 `--timeout` 后重试。
- quorum 不够：报告哪些 primary/backfill 模型失败、`quorum_default`、`quorum_effective`、`low_quorum_used` 和失败原因。
- validate 失败：报告具体 schema、模型一致性或 contamination 检查失败项。
- apparent hang / interruption：先读取 terminal manifest 并执行 `validate <run_id> --json`；如果 `verdict` 是 `complete_ok_final` 或 `usable_degraded_final`，不要 fallback。
