# COCO-llm-council

`COCO-llm-council` 是一个本地 council CLI **（注释：Command Line Interface，命令行工具）**：它用 COCO / `traecli` 调用多个模型，让它们先独立回答、再匿名互评、最后由主席模型综合成一个最终答案。

它复刻 `references/llm-council` 的核心三阶段 council protocol **（注释：议事协议，指模型按固定流程协作得出结论）**，但不引入原项目的 Web UI，不使用 OpenRouter API，也不依赖旧 TR。默认产物是可复盘的本地 artifact store **（注释：产物存储目录，保存每次运行的输入、输出、日志和校验证据）** 和单文件 HTML 报告。

默认读者语言是简体中文：即使输入问题是英文，CLC 也会在 Stage 1 / 2 / 3 prompt 中要求模型默认面向中文读者回答；如果用户问题明确指定其他输出语言，则遵循用户指定语言。HTML export 只渲染 artifacts，不在导出阶段翻译或改写主席答案。

## Highlights

- **三阶段 council run**：Stage 1 独立回答，Stage 2 匿名互评排序，Stage 3 主席综合。
- **COCO-first runtime**：默认通过 `traecli` 调用模型，不维护第二套模型清单。
- **主动模型选择**：只传问题文件时，CLI 会读取当前 `traecli models --json`，展示模型列表和推荐 council 套装，再询问是否采用。
- **可审计 artifact**：每次运行保存 input、config、manifest、每阶段 prompt / response / metadata、COCO stream JSON 和 HTML export。
- **模型防 fallback**：记录 expected model 和 actual model，模型不匹配、空响应、无效模型、Stage 2 parse failure 都会失败。
- **固定 subagent 成员**：支持通过 `profiles/subagents.json` 使用项目级 `.trae/agents/` council 成员。
- **本地 HTML 报告**：HTML export 只读 artifacts，不调用模型，不改写主席答案。
- **结构化 validate**：`validate` 会检查文件完整性、模型一致性、subagent evidence 和 schema contract **（注释：数据结构契约，规定 JSON 文件必须包含哪些字段以及字段类型）**。

## Quickstart

## Single-Doc Startup

如果把 `COCO-llm-council` 丢给一个新 workspace 或新 Agent，只需要指定本 `README.md` 作为唯一入口，再追加你的实际问题和补充要求。

新 Agent 应先按本 README 的 `Quickstart` 完成 `doctor`、`models`、direct run、`validate` 和 HTML export；需要排障时再跳到 `Project Docs` 表中对应文档。需要测试固定 COCO subagent 成员时，再执行 `Subagent Profile` 里的命令。

### 1. 确认 COCO / traecli 可用

本项目要求本机已经安装并登录 COCO，且 `traecli models --json` 能返回模型列表。

```bash
traecli --version
traecli doctor --json
traecli models --json
```

如果 COCO 还没安装或模型列表为空，先看：

```text
docs/COCO_INSTALLATION_AND_PATHS.md
```

### 2. 安装本地 CLI

```bash
make install-local
command -v coco-llm-council
```

安装后会在 `~/.local/bin/coco-llm-council` 创建一个轻量 wrapper。它直接指向当前 workspace 的 `src/`，适合本地开发和验证。

### 3. 跑 doctor 和模型列表

```bash
coco-llm-council doctor --json
coco-llm-council models --json
```

`doctor` 会检查：

- `traecli` 是否存在。
- `traecli doctor --json` 是否有 error。
- `traecli models --json` 是否能列出模型。
- `coco-llm-council` 自身是否能找到项目文件。

### 4. 运行一次 direct council

```bash
coco-llm-council run \
  --input examples/question.md \
  --run-id demo-direct \
  --timeout 180 \
  --json
```

如果没有传 `--members`、`--chairman`、`--profile` 或 `--default-models`，CLC 会先列出当前 COCO 可用模型，并给出推荐套装：

```text
CLC 检测到当前 COCO 可用模型：
  1. ...
  2. ...

推荐 council 模型套：
  members: GPT-5.4, GLM-5.1, DeepSeek-V4-Pro
  chairman: GPT-5.4

选择 [回车=使用推荐 / d=默认模型套 / c=自定义 / q=取消]:
```

`--members` 和 `--chairman` 都是可选参数。只提供 `--input` 时，CLI 会主动询问模型选择。明确想跳过询问时，传：

```bash
coco-llm-council run \
  --input examples/question.md \
  --default-models \
  --run-id demo-default \
  --json
```

默认模型套是：

```text
members: GPT-5.4, GLM-5.1
chairman: GPT-5.4
```

CLC 的模型询问是 CLI 自己的终端输入，不依赖 Agent 的 AskUserQuestion **（注释：Agent 用来向用户发起澄清问题的工具能力）**。如果外层 Agent 不能交互式输入，使用 `--default-models`、`--members/--chairman` 或 `--profile`。

成功后会生成：

```text
.coco-llm-council/runs/demo-direct/
```

打开 HTML 报告：

```bash
open .coco-llm-council/runs/demo-direct/html/index.html
```

### 5. 验证 run 是否可信

```bash
coco-llm-council validate demo-direct --json
```

`validate` 不是简单检查文件存在。它会确认 artifact 是否完整、Stage 2 是否解析成功、expected / actual model 是否一致、关键 JSON 是否满足 schema contract。

## Council Protocol

`COCO-llm-council` 的核心流程来自 `references/llm-council`：

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
| `coco-llm-council doctor --json` | 检查 COCO / `traecli` 和本 CLI 状态 | 否 |
| `coco-llm-council models --recommend --json` | 列出 `traecli` 当前可用模型和推荐 council 套装 | 否 |
| `coco-llm-council subagents --json` | 检查项目级 fixed council subagent 模板 | 否 |
| `coco-llm-council run --input <file> --json` | 先询问模型选择，再执行 Stage 1 / 2 / 3，并默认导出 HTML | 是 |
| `coco-llm-council show <run_id> --json` | 读取 run manifest | 否 |
| `coco-llm-council validate <run_id> --json` | 校验 artifact 完整性、模型一致性和 schema contract | 否 |
| `coco-llm-council replay <run_id> --stage stage3` | 打印已保存 prompt，方便复查 | 否 |
| `coco-llm-council export <run_id> --format html --json` | 从 artifacts 重新生成 HTML | 否 |
| `coco-llm-council raw ...` | 受限只读 escape hatch **（注释：安全出口，允许少量底层命令透传）** | 取决于子命令，默认只允许只读 |

查看完整参数：

```bash
coco-llm-council --help
coco-llm-council run --help
coco-llm-council replay --help
```

## Subagent Profile

direct provider **（注释：直接调用模型的执行方式）** 是默认路径，适合高频使用。subagent provider **（注释：通过 COCO 自定义子智能体调用固定成员的执行方式）** 用于固定 council 成员。

已提供的项目级 subagent 文件：

```text
.trae/agents/council-gpt54.md
.trae/agents/council-glm51.md
.trae/agents/council-chairman-gpt54.md
profiles/subagents.json
```

先检查 subagent profile：

```bash
coco-llm-council subagents --json
```

再运行：

```bash
coco-llm-council run \
  --input examples/question.md \
  --profile profiles/subagents.json \
  --run-id demo-subagents \
  --timeout 180 \
  --json
```

subagent 模式下，`validate` 会要求 COCO stream JSON 同时出现：

- Agent tool call。
- tool result。
- 子 agent `parent_tool_use_id`。
- 子 agent `_source_model`。
- expected / actual model 一致。

只有把 agent 名字写进 prompt、但没有真实 Agent tool evidence 的 run，会被 `validate` 判失败。

## Artifact Store

默认 run 目录：

```text
.coco-llm-council/runs/<run_id>/
```

关键文件：

```text
input.md
config.json
manifest.json
events.jsonl
runtime/doctor.json
runtime/coco.models.json
stage1/member.prompt.md
stage1/A.response.md
stage1/A.meta.json
stage1/A.coco.stream.jsonl
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

这个目录就是复盘边界：后续不用依赖聊天窗口，也不要求 COCO cache 仍然存在，只读 run 目录就能回答“这次最终答案是怎么来的”。

## Validation Contract

`validate` 当前会检查这些维度：

- 必需 artifact 文件是否存在且非空。
- manifest、stage meta、review json、final json、html export json 是否包含最小必填字段和正确类型。
- Stage 1 / 2 / 3 的 expected model 和 actual model 是否一致。
- Stage 2 ranking 是否能解析出有效排序。
- subagent mode 是否真的触发 COCO Agent tool，而不是普通 prompt 直答。
- HTML export JSON 是否存在并可被消费。

坏 artifact 不应该让 `validate` 崩溃。类型错误会返回结构化 failure，例如：

```text
schema:manifest.stages.stage1
schema:manifest.stages.stage2
schema:stage2.A.review.ranking
schema:stage3.final.response
schema:html.export.format
```

## HTML Export

HTML 报告位于：

```text
.coco-llm-council/runs/<run_id>/html/index.html
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
unittest: 14 tests passed
live-smoke-20260522161928: validate ok, 171 checks, 0 failures
subagent-hard-20260522165545: validate ok, 236 checks, 0 failures
```

常用开发命令：

```bash
PYTHONPATH=src python3 -m coco_llm_council.cli --help
PYTHONPATH=src python3 -m coco_llm_council.cli doctor --json
PYTHONPATH=src python3 -m coco_llm_council.cli run --input examples/question.md --default-models --json
```

## Project Docs

| 文档 | 读者 | 内容 |
|---|---|---|
| `docs/design.md` | 接手开发者 / Agent | 初始设计、协议边界、provider 设计、artifact store 设计 |
| `docs/COCO_INSTALLATION_AND_PATHS.md` | 本机排障者 | COCO 安装、登录、路径、插件、模型事实 |
| `docs/coco-subagents.md` | subagent 维护者 | 固定 council 成员、profile 和验证方式 |
| `docs/llm-council-parity.md` | 复刻审查者 | 与 `references/llm-council` 的对齐关系 |
| `docs/director-brief-20260522.md` | PM / director | 当前交付状态、验证结果、风险边界 |
| `references/llm-council/README.md` | 协议参考 | 原始 `llm-council` 行为和产品形态 |

## Non-goals

这些事情目前明确不做：

- 不引入 Web app。
- 不接 OpenRouter API。
- 不依赖旧 TR。
- 不把 HTML 生成和主席综合混成一步。
- 不维护一份脱离 `traecli models --json` 的静态模型清单。
- 不把 subagent profile 的 prompt-only 成功当成真实 subagent 成功。

## Current Status

`COCO-llm-council` 已达到第一版可用状态：可以从任意目录调用 CLI，完成 direct council run 和 subagent profile run，并生成可审计 artifacts 与 HTML 报告。

下一阶段更值得做的是 profile 管理、结构化 Stage 2 ranking 输出、更多模型 roster 配置，以及更完整的跨文件 schema 校验。
