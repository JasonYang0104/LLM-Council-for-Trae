# LLM-Council-for-Trae

`LLM-Council-for-Trae` 是一个本地 council CLI **（注释：Command Line Interface，命令行工具）**：它用 traecli 调用多个模型，让它们先独立回答、再匿名互评、最后由主席模型综合成一个最终答案。

它复刻上游 `llm-council` 的核心三阶段 council protocol **（注释：议事协议，指模型按固定流程协作得出结论）**，但不引入原项目的 Web UI，不使用 OpenRouter API，也不依赖旧 TR。默认产物是可复盘的本地 artifact store **（注释：产物存储目录，保存每次运行的输入、输出、日志和校验证据）** 和单文件 HTML 报告。

默认读者语言是简体中文：即使输入问题是英文，LCT（LLM-Council-for-Trae 的缩写）也会在 Stage 1 / 2 / 3 prompt 中要求模型默认面向中文读者回答；如果用户问题明确指定其他输出语言，则遵循用户指定语言。HTML export 只渲染 artifacts，不在导出阶段翻译或改写主席答案。

## Highlights

- **三阶段 council run**：Stage 1 独立回答，Stage 2 匿名互评排序，Stage 3 主席综合。
- **traecli-first runtime**：默认通过 `traecli` 调用模型，不维护第二套模型清单。
- **主动模型选择**：只传问题文件时，CLI 会读取当前 `traecli models --json`，展示模型列表和推荐 council 套装，再询问是否采用。
- **可审计 artifact**：每次运行保存 input、config、manifest、每阶段 prompt / response / metadata、traecli stream JSON 和 HTML export。
- **模型防 fallback**：记录 expected model 和 actual model，模型不匹配、空响应、无效模型、Stage 2 parse failure 都会失败。
- **固定 subagent 成员**：支持通过 `profiles/subagents.json` 使用 council 成员。
- **本地 HTML 报告**：HTML export 只读 artifacts，不调用模型，不改写主席答案。
- **结构化 validate**：`validate` 会检查文件完整性、模型一致性、subagent evidence 和 schema contract **（注释：数据结构契约，规定 JSON 文件必须包含哪些字段以及字段类型）**。

## Quickstart

### Agent 一句话用法

在另一个 workspace clone 本仓库后，可以直接对 Agent 说：

```text
用根目录中的能力，给我跑 LCT，输入的问题是："""<你的问题>"""
```

Agent 应按这条路径执行：确认 `traecli` 可用 → 安装或定位本地 CLI → 把问题写入临时 `.md` 文件 → 使用 `--default-models` 非交互运行 → `validate` 校验 → 返回 `stage3/final.md` 摘要和 HTML 报告路径。

### 1. 确认 traecli 可用

本项目要求本机已经安装并登录 traecli，且 `traecli models --json` 能返回模型列表。

如果当前 traecli 临时不可用，可以先验证 CLI 自身、模型推荐逻辑、schema contract 和 HTML export fixture；不要把 fake runtime 或 fixture 结果说成 live traecli 验证。

```bash
traecli --version
traecli doctor --json
traecli models --json
```

如果 traecli 还没安装或模型列表为空，先看：

```text
docs/traecli-installation-and-paths.md
```

### 2. 安装本地 CLI

```bash
make install-local
command -v llm-council-for-trae
```

安装后会在 `~/.local/bin/llm-council-for-trae` 创建一个轻量 wrapper。它直接指向当前 workspace 的 `src/`，适合本地开发和验证。

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

### 4. 运行一次 direct council

```bash
llm-council-for-trae run \
  --input examples/question.md \
  --default-models \
  --run-id demo-direct \
  --timeout 180 \
  --json
```

默认 direct run 不再传 `--yolo`，并使用 `--member-tool-mode search_enabled`：成员模型可使用 `WebSearch` / `WebFetch`，但 `Skill`、`Agent`、workspace 读写和 shell 会被禁止并由 provider 做污染检测。只有明确需要绕过权限时才传 `--yolo`；普通 council 成员不应使用它。

可选工具模式：

```bash
llm-council-for-trae run --input examples/question.md --default-models --member-tool-mode answer_only
llm-council-for-trae run --input examples/question.md --default-models --member-tool-mode search_enabled
llm-council-for-trae run --input examples/question.md --default-models --member-tool-mode workspace_enabled
```

如果没有传 `--members`、`--chairman`、`--profile` 或 `--default-models`，LCT 会先列出当前 traecli 可用模型，并给出推荐套装（仅限交互终端）。在 Agent 或脚本等非交互场景，必须显式指定 `--default-models`、`--members/--chairman` 或 `--profile`：

```text
LCT 检测到当前 traecli 可用模型：
  1. ...
  2. ...

推荐 council 模型套：
  members: GPT-5.4, GLM-5.1, DeepSeek-V4-Pro
  chairman: GPT-5.4

选择 [回车=使用推荐 / d=默认模型套 / c=自定义 / q=取消]:
```

`--members` 和 `--chairman` 都是可选参数。只提供 `--input` 时，CLI 会主动询问模型选择。明确想跳过询问时，传：

```bash
llm-council-for-trae run \
  --input examples/question.md \
  --default-models \
  --run-id demo-default \
  --json
```

默认模型套是：

```text
members: GPT-5.4, GLM-5.1, Qwen3.6-Plus, Kimi-K2.6, DeepSeek-V4-Pro, Gemini-3.1-Pro-Preview
chairman: Kimi-K2.6
```

LCT 的模型询问是 CLI 自己的终端输入，不依赖 Agent 的 AskUserQuestion **（注释：Agent 用来向用户发起澄清问题的工具能力）**。如果外层 Agent 不能交互式输入，使用 `--default-models`、`--members/--chairman` 或 `--profile`。

成功后会生成：

```text
.llm-council-for-trae/runs/demo-direct/
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

## Subagent Profile

direct provider **（注释：直接调用模型的执行方式）** 是默认路径，适合高频使用。subagent provider **（注释：通过 traecli 自定义子智能体调用固定成员的执行方式）** 用于固定 council 成员。

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

坏 artifact 不应该让 `validate` 崩溃。类型错误会返回结构化 failure，例如：

```text
schema:manifest.stages.stage1
schema:manifest.stages.stage2
schema:stage2.A.review.ranking
schema:stage3.final.response
schema:html.export.format
```

`run --json` 在失败时会额外输出 `recommendations`。例如某个模型出现 timeout、`context deadline exceeded` 或 `traecli result error`，CLI 会提示提高 `--timeout`，或先用本次 Stage 1 已成功响应的模型组合重跑。

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

当前验证基线：

```text
unittest: 78 tests passed
P0-P3 全部落地，3 个梯度 E2E 用例通过
```

常用开发命令：

```bash
PYTHONPATH=src python3 -m llm_council_for_trae.cli --help
PYTHONPATH=src python3 -m llm_council_for_trae.cli doctor --json
PYTHONPATH=src python3 -m llm_council_for_trae.cli run --input examples/question.md --default-models --json
```

## Project Docs

| 文档 | 读者 | 内容 |
|---|---|---|
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
- 不维护一份脱离 `traecli models --json` 的静态模型清单。
- 不把 subagent profile 的 prompt-only 成功当成真实 subagent 成功。

## Current Status

`LLM-Council-for-Trae` v1.1.2：CLI skeleton、doctor/models、Stage 1/2/3 council run、artifact store、expected vs actual model 校验、HTML export、subagent evidence validation、主动模型选择和中文默认输出全部落地。P0（failure 隐藏 + 主席综述 prompt）、P1（阵容代码落地）、P2（quorum 重试）、P3（E2E 验证）全部完成，78 个单元测试通过。HTML 报告 h1 动态标题和问题摘要已上线，subagent profile 已对齐 6 成员全阵容。当前下一阶段是 runtime hardening：重点解决并发互斥、Stage 2 超时、timeout 真值源、优雅退出和降级收场。

模型阵容：6 成员（GPT-5.4、GLM-5.1、Qwen3.6-Plus、Kimi-K2.6、DeepSeek-V4-Pro、Gemini-3.1-Pro-Preview）+ Kimi-K2.6 主席 + DeepSeek-V4-Pro/GPT-5.4 备选链。HTML 报告结构已稳定化。
