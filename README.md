# LLM-Council-for-Trae

`LLM-Council-for-Trae` 是一个本地 council CLI **（注释：Command Line Interface，命令行工具）**：它用 traecli 调用多个模型，让它们先独立回答、再匿名互评、最后由主席模型综合成一个最终答案。

它复刻上游 `llm-council` 的核心三阶段 council protocol **（注释：议事协议，指模型按固定流程协作得出结论）**，但不引入原项目的 Web UI，不使用 OpenRouter API，也不依赖旧 TR。默认产物是可复盘的本地 artifact store **（注释：产物存储目录，保存每次运行的输入、输出、日志和校验证据）** 和单文件 HTML 报告。

默认读者语言是简体中文：即使输入问题是英文，LCT（LLM-Council-for-Trae 的缩写）也会在 Stage 1 / 2 / 3 prompt 中要求模型默认面向中文读者回答；如果用户问题明确指定其他输出语言，则遵循用户指定语言。HTML export 只渲染 artifacts，不在导出阶段翻译或改写主席答案。

## Highlights

- **三阶段 council run**：Stage 1 独立回答，Stage 2 匿名互评排序，Stage 3 主席综合。
- **traecli-first runtime**：默认通过 `traecli` 调用模型，不维护第二套模型清单。
- **显式 runtime override**：默认 runtime 仍是 traecli；当 `traecli models --json` 返回空列表、失败或超时，但 `coco` 入口有证据可用时，外层 Agent 可以显式传 `--runtime-command coco`。coco 只在显式 override 中使用；这不是 CLI silent fallback，也不是把默认入口改写为 `coco`。
- **主动模型选择**：只传问题文件时，CLI 会读取当前 `traecli models --json`，展示模型列表和推荐 council 套装，再询问是否采用；models --recommend 只会从成员整体优先级中推荐可用模型，并排除 Seed/Doubao/GLM/GPT-5.5、Beta 和 Queue heat 过高模型。
- **可审计 artifact**：每次运行保存 input、config、manifest、每阶段 prompt / response / metadata、traecli stream JSON 和 HTML export。
- **模型防 fallback**：记录 expected model 和 actual model，模型不匹配、空响应、无效模型、Stage 2 parse failure 都会失败。
- **本地 HTML 报告**：HTML export 只读 artifacts，不调用模型，不改写主席答案。
- **结构化 validate**：`validate` 会检查文件完整性、模型一致性、subagent evidence 和 schema contract **（注释：数据结构契约，规定 JSON 文件必须包含哪些字段以及字段类型）**。

## Quickstart

### 日常使用：全局安装后在干净问题 workspace 提问

日常使用不要把 LCT 仓库 clone 到问题 workspace。默认路径是：从 GitHub `main` 安装到 `~/.LCT`，用 `~/.local/bin/llm-council-for-trae` wrapper 调用 `~/.LCT/src`，把 LCT Skill 安装到 `~/.agents/skills/llm-council-for-trae`，然后在干净问题 workspace 中提问。

自然语言安装入口：用户说 `请从 GitHub 仓库 https://github.com/JasonYang0104/LLM-Council-for-Trae 的最新版 LCT` 时，等同于从 GitHub main 安装或更新。必须使用 `~/.LCT + make install-global`：clone/fetch/pull `~/.LCT` 后运行 `make -C ~/.LCT install-global`；不得使用 `uv tool install`。安装成功必须同时证明：`~/.LCT HEAD == GitHub refs/heads/main`、`command -v llm-council-for-trae` 的 wrapper 包含 `.LCT/src`、Skill symlink 指向 `~/.LCT/skills/llm-council-for-trae`。

首次安装：

```bash
git clone https://github.com/JasonYang0104/LLM-Council-for-Trae.git ~/.LCT
```

已有 `~/.LCT` 时更新：

```bash
git -C ~/.LCT fetch origin --prune
git -C ~/.LCT checkout main
git -C ~/.LCT pull --ff-only origin main
```

安装 CLI wrapper 和用户级 Skill：

```bash
make -C ~/.LCT install-global
```

这个命令会安装两件事：

- `~/.local/bin/llm-council-for-trae`：wrapper 指向 `~/.LCT/src`。
- `~/.agents/skills/llm-council-for-trae`：用户级 Skill 链接到 `~/.LCT/skills/llm-council-for-trae`。

安装最新版不能只看 `llm-council-for-trae --version`，版本号可能没变，旧 uv tool wrapper 或旧 `site-packages` 仍可能被 shell 先找到。每次用户明确要求「从 GitHub main 全局安装最新版 LCT」时，执行 Agent 必须在 `notes.md` 记录 actual command、exit code、key stdout/stderr 和 pass/fail 结论，并跑下面的 freshness checks **（注释：新鲜度检查，证明当前命令实际来自最新源码，而不是旧安装包）**：

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

`~/.LCT HEAD == GitHub refs/heads/main` 是硬门槛。如果 `origin` 不是 `https://github.com/JasonYang0104/LLM-Council-for-Trae.git`、本地 `HEAD` 与 GitHub main SHA 不一致、`command -v` 指向 uv tool、`site-packages`、旧开发 checkout，或者 wrapper 中没有 `.LCT/src`，必须重新执行 `make -C ~/.LCT install-global` 并重做验证，不能继续跑 E2E。

在干净问题 workspace 里对 Agent 说：

```text
使用 LCT，回答："""<你的问题>"""
```

输入边界短例：

- 反例：不要写入 `_lct_question.md`：`使用LCT回答："""`
- 正确：`_lct_question.md` 只写真实问题：`分析解读这个 JD。先意图理解我为何有这个需求，而不是直接动手。`
- 外层 Agent 自己执行安装、validate、notes.md、HTML、Git/PR；这些不交给 council 成员。

Agent 应先确认 `_lct_question.md` 的输入边界：它只写 council-facing 问题、必要事实背景、输出要求和 `Report topic: <中文议题>`。`Report topic` 是报告元数据，供 HTML 标题稳定生成 `<中文议题>：多模型智囊团评估`，不是成员任务指令。外层执行指令不得写入 _lct_question.md：包括维护 notes.md、运行 validate、写 final/index、生成 HTML、Git/PR/测试职责、开 branch 或提交代码。

Agent 应按这条路径执行：确认当前目录不是 LCT 源码 repo（出现 `src/llm_council_for_trae/`、`.trae/agents/` 或 `profiles/subagents.json` 时停止）→ 确认 `traecli` 和 `llm-council-for-trae` 可用 → 检查 `traecli models --json` → 准备 `_lct_question.md` → 先记录 `models --recommend --json`，作为当前模型可用性和安全过滤参考 → 使用 `--default-models`、`--json` 非交互运行，auto-backfill **（注释：自动补位，指 CLI 在同一次运行里追加候补模型而不是重新跑整轮）** 默认启用，必要时可用 `--backfill-members` 显式提供候补优先级 → 如果默认成员失败、超时或不可用，CLI 在同一个 run 内追加 backfill 成员补足 quorum，不整轮重跑，不覆盖已成功 Stage 1 输出 → 如果 Stage 1 quorum 已满足但 Stage 2 reviewer 失败，CLI 只做 reviewer-only backfill **（注释：仅评审者补位，指候补模型只补交 Stage 2 评审，不新增 Stage 1 候选答案）** → 先读取 terminal manifest 并执行 `llm-council-for-trae validate <run_id> --json` → 只有 validate JSON 显示 `usable_final: true` 时读取 `stage3/final.md` → 在问题 workspace 根目录写出 `<run_id>-final.md` 和 `<run_id>-index.md`（必须包含 run status、validate status、validate verdict、HTML path、Input mode、runtime_default_command、runtime_default_version、runtime_default_models_status、runtime_default_models_count、runtime_override_used、runtime_override_command、runtime_override_reason、runtime_override_version、runtime_override_doctor_ok、runtime_override_models_count、runtime_override_recommendation_members、runtime_used_by_lct、lct_search_allowed、lct_search_used、lct_web_tool_calls、lct_web_tool_effective_calls、lct_search_conversion_errors、agent_external_search_allowed、agent_external_search_used、agent_sources、agent_fact_pack_path、agent_added_context、final_answer_source、valid_stage1_models、quorum_default、quorum_effective、low_quorum_used、backfill_candidates、backfill_attempts、stage2_reviewers、stage1_backfill_members、stage2_reviewer_backfill、review_subject_count、reviewer_count、chairman_fallback_used、failed models / timeout）→ 返回 run status、validate status、最终答案路径、HTML 报告路径和 live runtime。`degraded_ok 是可用结果`；成员失败不等于 run 失败。

`<run_id>-index.md` 的 `backfill_candidates` 必须来自 terminal manifest 的 `metadata.quorum.backfill_candidates`。如果 terminal manifest 没有记录该字段，写 `backfill_candidates: not recorded`；不得从默认成员阵容、不得从 models --recommend --json 的 primary roster、不得从实际有效 Stage 1 成员猜测候补池。

### 1. 确认 traecli 可用

本项目要求本机已经安装并登录 traecli，且 `traecli models --json` 能返回模型列表。

如果当前 traecli 临时不可用，可以先验证 CLI 自身、模型推荐逻辑、schema contract 和 HTML export fixture；不要把 fake runtime 或 fixture 结果说成 live traecli 验证。默认 runtime 仍是 traecli。

```bash
traecli --version
traecli doctor --json
traecli models --json
```

如果 `traecli models --json` 返回非空模型列表，继续日常默认路径。最终汇报写 `live runtime: traecli`，且 index 记录：

```text
runtime_default_command: traecli
runtime_default_models_status: ok
runtime_override_used: false
runtime_override_command: none
runtime_override_reason: none
runtime_used_by_lct: traecli
```

如果 `traecli models --json` 返回空列表、非 0 退出、明显超时或没有结构化输出，不要立刻启动 run，也不要直接放弃。先把默认入口阻断证据写入 notes/index，再 probe `coco`。这条路径叫 runtime override：默认 runtime 仍是 traecli，coco 只在显式 override 中使用；它不是 CLI silent fallback。

```bash
traecli --version
traecli models --json
coco --version
coco models --json
llm-council-for-trae --runtime-command coco doctor --json
llm-council-for-trae --runtime-command coco models --recommend --json
```

只有当 `coco models --json` 返回非空、`llm-council-for-trae --runtime-command coco doctor --json` 没有非 MCP 阻断错误，并且 `llm-council-for-trae --runtime-command coco models --recommend --json` 的 `recommendation.members` 与 `recommendation.chairman` 都可用时，外层 Agent 才能显式 override。本次 run 和 validate 必须保持同一个 runtime command：

```bash
llm-council-for-trae --runtime-command coco run \
  --input _lct_question.md \
  --default-models \
  --run-id "$RUN_ID" \
  --timeout 180 \
  --json

llm-council-for-trae --runtime-command coco validate "$RUN_ID" --json
```

override 路径的最终汇报写 `live runtime: coco via explicit --runtime-command override`，并在 index 记录：

```text
runtime_default_command: traecli
runtime_default_version: <value or error>
runtime_default_models_status: empty|failed|timeout
runtime_default_models_count: <number or none>
runtime_override_used: true
runtime_override_command: coco
runtime_override_reason: <short reason>
runtime_override_version: <value or none>
runtime_override_doctor_ok: true|false
runtime_override_models_count: <number or none>
runtime_override_recommendation_members: <models or none>
runtime_used_by_lct: coco
```

如果 `traecli` 和 `coco` 都不能证明模型可用，停止 live run。最终汇报写 `live runtime: unavailable`，只允许做 non-live 测试或 fixture validation。

如果 traecli 还没安装，先看：

```text
docs/traecli-installation-and-paths.md
```

### 2. 开发者路径：本地 checkout 验证

```bash
make install-local
command -v llm-council-for-trae
```

`make install-local` 是开发者路径。安装后会在 `~/.local/bin/llm-council-for-trae` 创建一个轻量 wrapper，直接指向当前 checkout 的 `src/`，适合本地开发和验证；它不是日常用户全局安装路径。

如果不想安装 wrapper，也可以在仓库根目录用零安装方式运行：

```bash
PYTHONPATH=src python3 -m llm_council_for_trae.cli --help
```

### 3. 跑 doctor 和模型列表

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
```

`doctor` 会检查：

- `traecli` 是否存在。
- `traecli doctor --json` 是否有 error。
- `traecli models --json` 是否能列出模型。
- `llm-council-for-trae` 自身是否能找到项目文件。

LCT 的 direct council run 不依赖外部 MCP server。如果 `traecli doctor --json` 只报告 MCP 初始化失败，但 `traecli --version` 和 `traecli models --json` 正常，LCT 会把这类 MCP-only error 记录到 `runtime/doctor.json` 的 `ignored_errors` 和 `manifest.warnings`，但不会阻断 run。非 MCP 的 doctor error、模型列表为空或模型缺失仍会失败。

### 4. 在干净问题 workspace 运行 direct council

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --default-models \
  --run-id demo-direct \
  --timeout 180 \
  --json
```

默认 direct run 不再传 `--yolo`，并使用 `--member-tool-mode search_enabled`：成员模型可使用 `WebSearch` / `WebFetch`，但 `Skill`、`Agent`、workspace 读写和 shell 会被禁止并由 provider 做污染检测。search_enabled 只表示搜索被允许，不表示模型实际搜索了；HTML 和索引应分开记录 `lct_search_allowed` 与 `lct_search_used`，并用 `agent_external_search_*` 单独记录外层 Agent 是否自己做了外部检索。只有明确需要绕过权限时才传 `--yolo`；普通 council 成员不应使用它。

可选工具模式：

```bash
llm-council-for-trae run --input _lct_question.md --default-models --member-tool-mode answer_only
llm-council-for-trae run --input _lct_question.md --default-models --member-tool-mode search_enabled
llm-council-for-trae run --input _lct_question.md --default-models --member-tool-mode workspace_enabled
```

answer_only 是可选工具模式，不强制 answer_only。外层 Agent 可以自行判断使用 LCT 内部搜索、先补 fact pack、使用 answer_only，或在只读代码/文件问题中使用 workspace_enabled；无论哪种路径，都必须在索引里保留 `agent_external_search_used` 等外层检索证据字段。

如果没有传 `--members`、`--chairman`、`--profile`、`--selected-members/--selected-chairman` 或 `--default-models`，LCT 会先列出当前 traecli 可用模型，并给出推荐套装（仅限交互终端）。在 Agent 或脚本等非交互场景，非 TTY run 必须显式指定模型路径：可用 `--default-models` 走默认套装，可用 `--selected-members/--selected-chairman` 走 agent-assisted 自选归一化入口，可用原生 `--members/--chairman` 走 power-user 精确路径，也可用 `--profile`：

```text
LCT 检测到当前 traecli 可用模型：
  1. ...
  2. ...

推荐 council 模型套：
  members: DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Kimi-K2.6
  chairman: DeepSeek-V4-Pro

选择 [回车=使用推荐 / d=默认模型套 / c=自定义 / q=取消]:
```

`--members` 和 `--chairman` 都是可选参数。只提供 `--input` 时，CLI 会主动询问模型选择。明确想跳过询问时，传：

```bash
llm-council-for-trae run \
  --input _lct_question.md \
  --default-models \
  --run-id demo-default \
  --json
```

默认模型套是：

```text
members: DeepSeek-V4-Pro, openrouter-1o, GPT-5.4, Kimi-K2.6
chairman: DeepSeek-V4-Pro
```

`--default-models` 始终使用这套静态默认阵容。run 内 auto-backfill 默认启用：默认 auto-backfill 只从成员整体优先级中选择候补，排除 primary members、已尝试成员、主席和当前不可用/不安全模型；不会追加未批准的 runtime safe models。显式传 `--backfill-members` 时，CLI 按显式列表过滤后使用。在同一个 run 内追加候补只为补足有效成员；它不整轮重跑，也不会把已成功 Stage 1 输出替换掉。交付索引里只能记录 terminal manifest 的 `metadata.quorum.backfill_candidates`；如果没有记录则写 `not recorded`，不得从默认成员阵容或 `models --recommend --json` 的 primary roster 替代。

如果用户明确要挑成员或指定主席，外层 Agent 可以进入 agent-assisted 自选模型路径：先读取当前模型清单，必要时用 `AskUserQuestionTool` 展示选择卡片；工具不可用时使用文本 fallback。该路径必须调用独立参数 `--selected-members` / `--selected-chairman`，不要复用原生 `--members`。原生 `--members` 是 power-user 精确路径，给几个跑几个，不补足、不裁剪；agent-assisted 自选路径才会归一化到 4 并记录 `selection_surface=agent_assisted`、用户请求、解析结果、补足成员、裁剪成员和最终 config。

模型选择意图边界必须分清。用户只问“有什么模型”时，只展示 `models --recommend --json` / 当前模型清单和推荐套装，不擅自启动 run。用户说“我想指定模型”“我想自己选模型”“想挑成员/指定主席/比较模型阵容”，但想指定模型但没有给具体模型时，外层 Agent 应先读取当前模型清单和推荐阵容，再追问用户或给文本 fallback；拿到选择后再传 `--selected-members/--selected-chairman`。`--selected-chairman` 当前不能单独出现；如果只想指定主席且成员保持默认，需明确改用原生 `--members/--chairman` 并说明这是 power-user 精确路径。

主席贡献说明默认开启。默认 run 会请求 Stage 3 输出 `stage3/contribution_map.json`，让 HTML 正文按 blocks 展示「这一段来自单一成员、多成员共识、主席编者注、综合整理或无法可靠归因」；调用方不需要追加 `--chairman-contribution-map`。如果明确不想请求 contribution map，可追加 `--no-chairman-contribution-map`；`--chairman-contribution-map` 仍保留为兼容 alias。release / E2E strict gate 场景可追加 `--require-chairman-contribution-map`，即 `required=true`，要求 sidecar 缺失或结构非法时 validate hard fail。默认 requested 但不 required 时，manifest 记录 `metadata.chairman_contribution` 的 `requested / required / present / error`，HTML fallback 到 `stage3/final.md`，validate 记录非阻断 warning，不把可读 final answer 判死。Stage 3 会对 contribution map JSON 字符串里的常见未转义英文双引号做有限修复；无论 sidecar 是否可用，`stage3/final.md`、HTML 正文和复制 Markdown 都不会展示尾部 contribution JSON 块。单一成员和多成员共识来源会根据 `metadata.aggregate_rankings` 追加 `同侪#n`，作为主席无法改写的可验证锚点。legacy run 缺少 `metadata.chairman_contribution` 或显式 disabled 时不要求 sidecar。该功能不输出贡献百分比，也不把 Stage 2 同侪排序解释成模型能力排行。

补位语义分两类。Stage 1 member backfill **（注释：成员补位，指候补模型生成新的 Stage 1 候选答案）** 只在有效回答不足 quorum 时发生；只有 Stage 1 quorum 不足，CLI 才会新增候选答案。Stage 2 reviewer-only backfill 发生在 Stage 1 quorum 已经满足、但 Stage 2 reviewer 失败或不足时；候补模型只评审既有有效 Stage 1 answers，不新增候选答案，也不会进入 `stage2/label_to_model.json` 的 subject mapping。

LCT 的模型询问是 CLI 自己的终端输入，不依赖 Agent 的 AskUserQuestion **（注释：Agent 用来向用户发起澄清问题的工具能力）**。如果外层 Agent 不能交互式输入，仍可以先问用户再运行；最终命令必须显式选择一种模型路径：`--default-models`、`--selected-members/--selected-chairman`、原生 `--members/--chairman` 或 `--profile`。

CLI 直接产物：

```text
.llm-council-for-trae/runs/demo-direct/
.llm-council-for-trae/runs/demo-direct/stage3/final.md
.llm-council-for-trae/runs/demo-direct/html/index.html
```

如果是通过用户级 Skill 让外层 Agent 执行，Agent/Skill 额外落盘产物还包括：

```text
demo-direct-final.md
demo-direct-index.md
```

打开 HTML 报告：

```bash
open .llm-council-for-trae/runs/demo-direct/html/index.html
```

### 5. 验证 run 是否可信

```bash
llm-council-for-trae validate demo-direct --json
```

`validate` 不是简单检查文件存在。它会确认 artifact 是否完整、Stage 2 是否解析成功、expected / actual model 是否一致、关键 JSON 是否满足 schema contract。

## Council Protocol

`LLM-Council-for-Trae` 的核心流程已固化在本仓库实现和文档中，历史参考来自上游 `llm-council` protocol：

| Stage | 目的 | 产物 |
|---|---|---|
| Stage 1 | 多个模型分别回答同一个问题 | `stage1/*.response.md`、`stage1/*.meta.json` |
| Stage 2 | 把 Stage 1 回答匿名成 `Response A/B/C`，让模型互评排序 | `stage2/*.review.md`、`stage2/*.review.json`、`stage2/aggregate.json` |
| Stage 3 | 主席模型读取问题、候选回答、互评结果，生成最终答案 | `stage3/final.md`、`stage3/final.json` |
| HTML | 把已保存 artifacts 渲染成单文件报告 | `html/index.html`、`html/export.json` |

HTML export 是独立步骤。主席模型只负责 Stage 3 综合，HTML 只负责报告呈现。

## Command Reference

| 命令 | 用途 | 是否调用模型 |
|---|---|---|
| `llm-council-for-trae doctor --json` | 检查 traecli 和本 CLI 状态 | 否 |
| `llm-council-for-trae models --recommend --json` | 列出 `traecli` 当前可用模型和推荐 council 套装 | 否 |
| `llm-council-for-trae subagents --json` | 检查项目级 fixed council subagent 模板 | 否 |
| `llm-council-for-trae run --input <file> --json` | 先询问模型选择，再执行 Stage 1 / 2 / 3，并默认导出 HTML | 是 |
| `llm-council-for-trae show <run_id> --json` | 读取 run manifest | 否 |
| `llm-council-for-trae validate <run_id> --json` | 校验 artifact 完整性、模型一致性和 schema contract | 否 |
| `llm-council-for-trae replay <run_id> --stage stage3` | 打印已保存 prompt，方便复查 | 否 |
| `llm-council-for-trae export <run_id> --format html --json` | 从 artifacts 重新生成 HTML | 否 |
| `llm-council-for-trae raw ...` | 受限只读 escape hatch **（注释：安全出口，允许少量底层命令透传）** | 取决于子命令，默认只允许只读 |

查看完整参数：

```bash
llm-council-for-trae --help
llm-council-for-trae run --help
llm-council-for-trae replay --help
```

## Legacy / Experimental Subagent Profile

direct provider **（注释：直接调用模型的执行方式）** 是默认路径，适合高频使用。subagent provider **（注释：通过 traecli 自定义子智能体调用固定成员的执行方式）** 现在是 legacy / experimental 路径：它保留用于历史 artifact validation **（注释：产物校验，检查已保存运行记录是否完整可信）** 和未来固定成员实验，不是日常全局安装后的主路径。

`profiles/subagents.json` 可能因为当前 `traecli models --json` 模型漂移而失败，例如 profile 中的模型已经不在 live roster 里。不要把 subagent profile run 当成默认 smoke；除非你正在验证 subagent provider 本身，否则优先使用 direct provider。

先检查 subagent profile：

```bash
llm-council-for-trae subagents --json
```

再运行：

```bash
llm-council-for-trae run \
  --input examples/question.md \
  --profile profiles/subagents.json \
  --run-id demo-subagents \
  --timeout 180 \
  --json
```

subagent 模式下，`validate` 会要求 traecli stream JSON 同时出现：

- Agent tool call。
- tool result。
- 子 agent `parent_tool_use_id`。
- 子 agent `_source_model`。
- expected / actual model 一致。

只有把 agent 名字写进 prompt、但没有真实 Agent tool evidence 的 run，会被 `validate` 判失败。

## Artifact Store

默认 run 目录：

```text
.llm-council-for-trae/runs/<run_id>/
```

关键文件：

```text
input.md
config.json
manifest.json
events.jsonl
runtime/doctor.json
runtime/traecli.models.json
stage1/member.prompt.md
stage1/A.response.md
stage1/A.meta.json
stage1/A.traecli.stream.jsonl
stage2/review.prompt.md
stage2/A.review.md
stage2/A.review.json
stage2/aggregate.json
stage2/label_to_model.json
stage3/chairman.prompt.md
stage3/final.md
stage3/final.json
stage3/final.meta.json
html/index.html
html/export.json
```

这个目录就是复盘边界：后续不用依赖聊天窗口，也不要求 traecli cache 仍然存在，只读 run 目录就能回答“这次最终答案是怎么来的”。

## Validation Contract

`validate` 当前会检查这些维度：

- 必需 artifact 文件是否存在且非空。
- manifest、stage meta、review json、final json、html export json 是否包含最小必填字段和正确类型。
- Stage 1 / 2 / 3 的 expected model 和 actual model 是否一致。
- Stage 2 ranking 是否能解析出有效排序。
- subagent mode 是否真的触发 traecli Agent tool，而不是普通 prompt 直答。
- HTML export JSON 是否存在并可被消费。

`validate <run_id> --json` 会输出终局判定字段：`terminal`、`usable_final`、`stage3_final_exists`、`html_exists`、`failed_stage_records`、`verdict`。`verdict` 取值为 `complete_ok_final`、`usable_degraded_final`、`in_progress`、`failed_no_final`、`invalid_artifacts`。交付或写 `<run_id>-index.md` 前，状态必须来自 terminal manifest 加 validate JSON；不要用中途目录为空、run JSON 为空或自然语言观察判 failed。`degraded_ok 是可用结果`，成员失败不等于 run 失败。

带 auto-backfill 的 run 还会在 manifest / validate / HTML 中暴露 quorum 和补位 provenance **（注释：来源证据，指结果由哪些模型、哪些补位和哪些降级规则组成）**。索引和汇报至少记录：`valid_stage1_models`、`quorum_default`、`quorum_effective`、`low_quorum_used`、`backfill_attempts`、`stage2_reviewers`、`stage1_backfill_members`、`stage2_reviewer_backfill`、`review_subject_count`、`reviewer_count`、`chairman_fallback_used`。

坏 artifact 不应该让 `validate` 崩溃。类型错误会返回结构化 failure，例如：

```text
schema:manifest.stages.stage1
schema:manifest.stages.stage2
schema:stage2.A.review.ranking
schema:stage3.final.response
schema:html.export.format
```

`run --json` 在失败时会额外输出 `recommendations`。例如某个模型出现 timeout、`context deadline exceeded` 或 `traecli result error`，CLI 会提示提高 `--timeout`、检查 backfill candidates，或说明 auto-backfill 耗尽后仍无法达到可用 quorum。

## HTML Export

HTML 报告位于：

```text
.llm-council-for-trae/runs/<run_id>/html/index.html
```

页面包含：

- 运行摘要。
- 阶段 1 候选回答。
- 阶段 2 reviewer 排序和 aggregate ranking。
- 阶段 3 最终答案。
- Provider trace。
- 复制 Markdown / JSON / 主席提示词按钮。

HTML export 是确定性本地渲染，不调用模型，不改变主席答案。页面外壳默认使用中文；正文语言来自已保存的 `stage3/final.md`。

## Development

本地测试：

```bash
PYTHONPATH=src python3 -m compileall src
make test
```

当前验证基线以 `make test` 的最新输出为准。README 不记录固定测试数量，避免把历史数字误读成当前真值。

常用开发命令：

```bash
PYTHONPATH=src python3 -m llm_council_for_trae.cli --help
PYTHONPATH=src python3 -m llm_council_for_trae.cli doctor --json
PYTHONPATH=src python3 -m llm_council_for_trae.cli run --input examples/question.md --default-models --json
```

## Project Docs

| 文档 | 读者 | 内容 |
|---|---|---|
| `docs/lct-deployment-guide-20260601.md` | Agent / 用户安装者 | `~/.LCT` 全局安装、用户级 Skill、干净问题 workspace 和 live smoke 边界 |
| `docs/lct-global-install-skill-design-20260601.md` | 接手开发者 / reviewer | 全局安装、Skill 模板、安装器和验证边界设计 |
| `docs/lct-global-install-skill-test-plan-20260601.md` | 接手开发者 / reviewer | 全局安装与 Skill 的 TDD 切片和验收计划 |
| `docs/lct-auto-backfill-quorum-design-20260603.md` | 接手开发者 / reviewer | 同 run auto-backfill、quorum、low quorum、Stage 2 reviewer eligibility 和可见性设计 |
| `docs/lct-auto-backfill-implementation-handoff-20260603.md` | 新会话 Agent / 接手开发者 | auto-backfill 实施顺序、TDD 切片、subagent review 和验收约束 |
| `docs/lct-stage2-reviewer-only-backfill-handoff-20260603.md` | 新会话 Agent / 接手开发者 | Stage 2 reviewer-only backfill 修正、TDD 切片、验证口径和最终 brief 约束 |
| `docs/lct-auto-backfill-implementation-brief-20260603.md` | PM / director | 本轮 auto-backfill 实施背景、关键决策、测试证据和剩余风险 |
| `docs/lct-validate-title-hardening-handoff-20260603.md` | 新会话 Agent / 接手开发者 | 下一轮 validate 判定硬化、中文报告标题契约、TDD 节奏和 handoff 约束 |
| `docs/lct-validate-title-contract-design-20260603.md` | 接手开发者 / reviewer | validate 终局判定和中文报告标题契约设计 |
| `docs/lct-validate-title-contract-test-plan-20260603.md` | 接手开发者 / reviewer | validate 状态字段、标题抽取和 Skill 硬规则的测试计划 |
| `docs/runtime-hardening-handoff-20260601.md` | 新会话 Agent / 接手开发者 | 这轮 runtime hardening 的背景、问题归因、索引文档、推进方式和交接口径 |
| `docs/runtime-hardening-director-brief-20260601.md` | PM / director | 为什么要做 runtime hardening、优先级、策略和阶段目标的简报版 |
| `docs/design.md` | 接手开发者 / Agent | 初始设计、协议边界、provider 设计、artifact store 设计 |
| `docs/traecli-installation-and-paths.md` | 本机排障者 | traecli 安装、登录、路径、插件、模型事实 |
| `docs/traecli-subagents.md` | subagent 维护者 | 固定 council 成员、profile 和验证方式 |
| `docs/llm-council-parity.md` | 复刻审查者 | 与上游 `llm-council` protocol 的对齐关系 |

## Non-goals

这些事情目前明确不做：

- 不引入 Web app。
- 不接 OpenRouter API。
- 不依赖旧 TR。
- 不把 HTML 生成和主席综合混成一步。
- 不维护脱离 `traecli models --json` 过滤的 runtime 推荐；静态默认阵容和优先级必须与代码、测试、Skill 文档同步。
- 不把 subagent profile 的 prompt-only 成功当成真实 subagent 成功。

## Current Status

`LLM-Council-for-Trae` v1.1.2：CLI skeleton、doctor/models、Stage 1/2/3 council run、artifact store、expected vs actual model 校验、HTML export、subagent evidence validation、主动模型选择和中文默认输出全部落地。默认 direct 阵容已收敛为 4 成员：DeepSeek-V4-Pro、openrouter-1o、GPT-5.4、Kimi-K2.6，主席为 DeepSeek-V4-Pro。models --recommend 只会从成员整体优先级中推荐可用模型，并排除 Seed/Doubao/GLM/GPT-5.5、Beta 和 Queue heat ≥95% 的模型；默认 auto-backfill 只从同一份成员整体优先级里选择剩余候补。测试数量以 `make test` 的当前输出为准。HTML 报告 h1 动态标题、问题摘要和 LCT 搜索证据摘要已上线；标题抽取会跳过“核心内容”等通用章节名，缺少 `Report topic` 时优先使用可识别的文章题名或具体议题。subagent profile 是 legacy / experimental 路径，不再代表 direct 默认阵容。当前下一阶段是 runtime hardening：重点解决并发互斥、Stage 2 超时、timeout 真值源、优雅退出和降级收场。

模型阵容：direct 默认 4 成员取成员整体优先级前 4 个（DeepSeek-V4-Pro、openrouter-1o、GPT-5.4、Kimi-K2.6）+ DeepSeek-V4-Pro 主席。成员整体优先级按 `model_selection.py`：DeepSeek-V4-Pro、openrouter-1o、GPT-5.4、Kimi-K2.6、GPT-5.2、openrouter-1、Gemini-3.1-Pro-Preview、DeepSeek-V4-Flash、MiniMax-M2.7、Qwen3.6-Plus。默认 backfill 只使用这份成员优先级中尚未作为 primary/attempted/chairman 的可用模型。主席备选链为 Kimi-K2.6 → DeepSeek-V4-Flash → GPT-5.2 → openrouter-1。subagent profile 是 legacy / experimental 路径，不作为 direct 默认阵容的源头；当前 profile 仅镜像 direct 默认 4 成员，避免旧 GLM profile 被误跑。HTML 报告结构已稳定化。
