# COCO-llm-council 启动方案

日期：2026-05-22

## 结论

新方向不再是“继续迭代旧 TR”，而是新建独立 workspace：`COCO-llm-council`。

目标是做一个独立 council CLI，名字暂定 `coco-llm-council`。它内部调用 `traecli`，一比一复刻 `llm-council` 的核心议事流程，同时排除原项目的 Web UI 和 OpenRouter API。COCO 是默认 runtime，COCO 自定义智能体是固定 council 成员的长期形态。

旧 TR 保留不动，不迁移、不改写、不作为未来入口。旧 TR 只能作为历史经验参考，不能污染新项目的命名、命令、provider 边界和文档口径。

## Workspace 定位

目标 workspace：

```text
.
├── README.md
├── docs/
│   ├── design.md
│   ├── COCO_INSTALLATION_AND_PATHS.md
│   ├── coco-subagents.md
│   ├── llm-council-parity.md
│   └── goal-prompt.md
├── references/
│   └── llm-council/
└── .trae/
    └── agents/
```

说明：

- `docs/design.md`：本方案的主设计文档。
- `docs/COCO_INSTALLATION_AND_PATHS.md`：COCO 安装、路径、鉴权、插件和模型说明。
- `docs/coco-subagents.md`：后续补 COCO subagent 配置、模型指定、fallback 风险和验证方式。
- `docs/llm-council-parity.md`：逐项对照 `llm-council` 的复刻清单。
- `docs/goal-prompt.md`：发给新会话的 `/goal` 启动提示词。
- `references/llm-council/`：克隆 `karpathy/llm-council`，固定 commit，当作可读参考资产。
- `.trae/agents/`：后续放 COCO 自定义智能体，例如 council member 和 chairman。

文档中的本地路径一律使用相对路径。绝对路径只出现在最终交付说明里，不写进 workspace 内部文档。

## 必须复用 llm-council 的资产

只要不和 COCO runtime、HTML 输出、长期可复盘目标冲突，就复用 `llm-council` 的已有资产，不重新发明。

必须复用或对齐：

- 三阶段 protocol：
  - Stage 1：同一个用户问题分别发给多个模型。
  - Stage 2：匿名化 Stage 1 回答，让模型互评并排序。
  - Stage 3：主席读取原问题、候选回答、互评结果，生成最终答案。
- 匿名标签形式：`Response A/B/C/...`。
- 聚合排名思想：把多个 reviewer 的排序合并为总排名。
- 核心函数边界：
  - `stage1_collect_responses`
  - `stage2_collect_rankings`
  - `parse_ranking_from_text`
  - `calculate_aggregate_rankings`
  - `stage3_synthesize_final`
  - `run_full_council`
- 前端展示思想：
  - Stage 1/2/3 分区展示。
  - Stage 1 回答可切换查看。
  - Stage 2 review 可展开查看。
  - Stage 3 final answer 作为最终主输出。

必须排除或替换：

- React / Vite Web UI：替换成单文件 HTML artifact。
- OpenRouter API：替换成 COCO / `traecli` provider。
- `.env` API key 模式：替换成本机 COCO 鉴权与配置。
- `data/conversations/` 弱存储：替换成可复盘 artifact store。
- 仅靠自由文本解析排名：可以兼容，但默认应优先结构化输出，避免 parse failure。

## 为什么是独立 CLI

`traecli` 是底层模型执行器，不是 council 编排器。

它能完成：

- 调用某个模型。
- 调用 COCO 自定义智能体。
- 输出 stream JSON。
- 记录 session log。

但 council runtime 还需要负责：

- 决定模型 roster。
- 并发执行 Stage 1。
- 匿名化候选答案。
- 生成 Stage 2 review prompt。
- 解析或修复 ranking。
- 聚合排名。
- 构造 chairman prompt。
- 落盘 artifacts。
- 复制 COCO session evidence。
- 生成 HTML artifact。
- 提供 replay、doctor、export、validate。

因此推荐方案是：

```text
coco-llm-council CLI
  -> 调用 traecli
  -> 读取 COCO 输出和 session log
  -> 写入本项目 artifact store
  -> 生成 HTML artifact
```

不推荐把全部逻辑塞进一个 COCO subagent。subagent 适合作为 council member 或 chairman，不适合作为唯一编排器。

## 命令面设计

创建 CLI 时必须使用 Codex 的 `cli-creator` 方法论。

暂定命令名：

```text
coco-llm-council
```

最小命令面：

```bash
coco-llm-council --help
coco-llm-council doctor --json
coco-llm-council models --json
coco-llm-council run --input examples/question.md --json
coco-llm-council show <run_id> --json
coco-llm-council export <run_id> --format html
coco-llm-council replay <run_id> --stage stage3
coco-llm-council validate <run_id> --json
```

命令原则：

- `doctor` 先确认 `traecli` 是否存在、COCO 是否登录、模型是否可用、插件是否加载。
- `models` 读取 COCO 当前可用模型，不维护第二套过期模型清单。
- `run` 执行完整 Stage 1 -> Stage 2 -> Stage 3 -> HTML。
- `show` 只读 manifest，不调用模型。
- `export` 只读 artifacts，默认输出 HTML。
- `replay` 只展示某阶段 prompt，不调用模型。
- `validate` 检查 run 是否完整、模型是否符合预期、是否出现 fallback、parse failure 和缺失 artifact。
- 所有关键命令支持 `--json`，方便 Codex 和其他 Agent 消费。

## Provider 设计

### P1：direct `traecli` provider

第一阶段先实现 direct provider。每次模型调用都启动 `traecli`：

```bash
traecli -p "<prompt>" \
  -c model.name="GPT-5.4" \
  --output-format stream-json \
  --session-id "<run_id>-stage1-A"
```

这是最接近 `llm-council` 原始 `query_model(model, messages)` 的替代方式。

优点：

- 动态模型 roster 简单。
- 实现和测试路径清楚。
- 容易记录每次调用的 stream JSON 和 session log。
- 适合作为第一个可工作的版本。

硬要求：

- 每次调用必须记录期望模型和实际模型。
- 如果 COCO fallback 到默认模型，run 必须失败。
- session log 必须复制进 run artifacts。
- 超时、非零退出、空响应、parse failure 必须结构化记录。

### P2：COCO subagent provider

第二阶段实现 subagent provider。固定 council 成员写成项目级文件：

```text
.trae/agents/
  council-gpt54.md
  council-glm51.md
  council-gemini31.md
  council-chairman-gpt54.md
```

示例：

```yaml
---
name: council-gpt54
description: COCO-llm-council member using GPT-5.4
model: GPT-5.4
tools: []
---
你是 COCO-llm-council 的 council member。只回答当前阶段 prompt，不读取 workspace 外内容。
```

subagent provider 的价值：

- 固定 council 成员可文件化。
- 每个成员可以有独立模型、工具、权限和 skill。
- 适合长期沉淀“稳定议会成员”。

限制：

- 动态 roster 不适合全靠 subagent。
- subagent 文件需要验证 frontmatter。
- COCO 对无效模型可能 fallback，必须靠日志检查兜住。

## Artifact store

默认 run 目录：

```text
.coco-llm-council/runs/<run_id>/
├── input.md
├── config.json
├── manifest.json
├── events.jsonl
├── runtime/
│   ├── coco.version.json
│   ├── coco.models.json
│   └── doctor.json
├── stage1/
│   ├── member.prompt.md
│   ├── A.response.md
│   ├── A.meta.json
│   ├── A.coco.stream.jsonl
│   └── A.coco.session.log
├── stage2/
│   ├── review.prompt.md
│   ├── A.review.md
│   ├── A.review.json
│   ├── aggregate.json
│   └── label_to_model.json
├── stage3/
│   ├── chairman.prompt.md
│   ├── final.md
│   └── final.json
└── html/
    ├── artifact.prompt.md
    ├── index.html
    └── export.json
```

artifact store 的成功标准：

- 不依赖聊天窗口记忆。
- 不依赖 COCO cache 仍然存在。
- 后续 Agent 只读 run 目录，就能回答“为什么得到这个最终答案”。
- 每个模型调用都有 prompt、response、metadata、trace。
- 每个失败都能定位到 stage、member、命令、退出码、日志片段。

## HTML artifact

默认输出是单文件 HTML，不是 Markdown。

HTML 生成提示词：

```text
用 HTML 制作一个 artifact，严格参考 https://thariqs.github.io/html-effectiveness/ 中某个或某些模板：
- 优先采用该站点所有示例的通用结构：TOC + 可折叠 sections + tabbed code + SVG / CSS Grid 可视化
- 强烈推荐包含交互（滑块/拖拽/实时渲染）和 export 按钮（copy as markdown / JSON / prompt），除非任务明确不需要
- 保持单文件自包含，直接在浏览器打开即可使用
```

HTML 必须包含：

- TOC。
- 可折叠 sections。
- Stage 1 / Stage 2 / Stage 3 tabs。
- SVG council flow。
- CSS Grid ranking matrix。
- copy as markdown。
- copy as JSON。
- copy final prompt。
- run metadata。
- provider trace。
- warnings / failures。

HTML 不应该做：

- 新建 Web app。
- 引入外链 JS/CSS。
- 为了视觉效果改写事实。
- 把 chairman synthesis 和 HTML generation 混成一步。

正确边界：

```text
Stage 3 负责 final answer。
HTML export 负责把 artifacts 变成可读报告。
```

## 输入边界

输入侧只认稳定文件合同：

```text
input.md
config/profile
```

Codex、Trae-CN、COCO 都只是输入来源，不是 runtime 边界。

- Codex 可以写 `input.md` 后调用 CLI。
- Trae-CN 可以作为用户整理问题的工作台，但 runtime 不读取 Trae-CN DOM。
- COCO 可以作为交互入口，但真正的 council 编排仍由 CLI 完成。

## 开发节奏

### Phase 0：Workspace 启动包

要做：

- 创建 workspace。
- 放入本设计文档。
- 放入 COCO 安装路径说明。
- 克隆 `llm-council` 到 `references/llm-council/`。
- 写 `docs/goal-prompt.md`。

验收：

- 新会话只读 workspace 文档，就能理解目标、边界、节奏和测试方式。

### Phase 1：CLI skeleton

要做：

- 使用 `cli-creator` 设计并创建 `coco-llm-council` CLI。
- 实现 `--help`、`doctor --json`、`models --json`。
- 确认从任意目录能调用命令。

测试：

```bash
command -v coco-llm-council
coco-llm-council --help
coco-llm-council doctor --json
coco-llm-council models --json
```

### Phase 2：llm-council parity core

要做：

- 复刻 Stage 1 / Stage 2 / Stage 3。
- 保持 `llm-council` 的核心函数边界。
- direct provider 调用 `traecli`。
- 写入 artifact store。

测试：

```bash
coco-llm-council run --input examples/question.md --members GPT-5.4,GLM-5.1 --chairman GPT-5.4 --json
coco-llm-council show <run_id> --json
coco-llm-council validate <run_id> --json
```

### Phase 3：COCO evidence hardening

要做：

- 捕获 stream JSON。
- 复制 session log。
- 校验 expected model vs actual model。
- 无效模型 fallback 必须 fail。

测试：

```bash
coco-llm-council run --input examples/question.md --members Invalid-Model,GPT-5.4 --chairman GPT-5.4 --json
```

期望：失败，并明确指出模型不可用或发生 fallback。

### Phase 4：HTML export

要做：

- 实现 `export --format html`。
- 生成单文件自包含 HTML。
- HTML 从 artifacts 渲染，不重新调用模型生成事实。

测试：

```bash
coco-llm-council export <run_id> --format html
open .coco-llm-council/runs/<run_id>/html/index.html
```

检查：

- HTML 能直接打开。
- Stage 1/2/3 都可读。
- ranking matrix 正确。
- copy buttons 可用。
- warnings/failures 可见。

### Phase 5：COCO subagent provider

要做：

- 在 `.trae/agents/` 放 member/chairman 模板。
- profile 支持 `provider.mode = "subagent"`。
- 校验 subagent frontmatter。
- 校验实际模型。

测试：

```bash
coco-llm-council run --input examples/question.md --profile profiles/subagents.json --json
coco-llm-council validate <run_id> --json
```

## 非目标

第一阶段不做：

- Web app。
- 多用户服务。
- 远程部署。
- 复杂权限系统。
- 花哨 UI。
- 把旧 TR 迁进来。
- 强行把所有模型成员都做成 subagent。

## 新会话 `/goal` 提示词

```text
/goal 在当前 workspace 中推进 COCO-llm-council。目标是创建一个独立 council CLI，命令名为 coco-llm-council，内部调用 traecli，一比一复刻 references/llm-council 的核心 council protocol，但排除原 Web UI 和 OpenRouter API。必须优先复用 llm-council 中不冲突的已有资产和函数边界；必须使用 Codex 的 cli-creator 方法论创建 CLI；COCO 是默认 runtime；后续支持 COCO 自定义 subagent 作为固定 council 成员。先阅读 README.md、docs/design.md、docs/COCO_INSTALLATION_AND_PATHS.md 和 references/llm-council/README.md，再给出实现计划。交付必须完整包含：CLI skeleton、doctor/models、Stage 1/2/3 council run、artifact store、expected vs actual model 校验、HTML export、验证命令和结果。开发可以分阶段推进，但每阶段必须有明确测试。不要依赖旧 TR，不要引入 Web app，不要把 HTML 生成和主席综合混成一步。
```

## 追加方案：Reader-first HTML 与 Trae-CN 模型选择

日期：2026-05-22

本节是下一轮迭代方案，只描述设计和验收，不代表已经实现。

### 结论

下一轮最值得做两件事：

1. HTML export 从“流程审计面板”改成“用户默认阅读的最终答案 artifact”。默认读者先看 `stage3/final.md` 渲染出的精致正文，Stage 1 / Stage 2 / provider trace 退到可折叠证据层。
2. 模型选择补一个薄的输入/推荐层。CLC core 仍只认 `input.md` + config/profile + CLI 参数；Trae-CN 可以在调用前用 `AskUserQuestion` 帮用户选择模型，但这个能力不进入 CLC core。

一句话：CLC 负责稳定运行、落盘和复盘；Trae-CN 负责把人的意图整理成结构化输入和参数。

### HTML 设计参考怎么落地

采用资产级引用，不按 repo 名泛泛引用。优先使用 `open-design` 已经蒸馏好的资产；只有 `open-design` 没覆盖、且内容明显适配 CLC 时，才回看其他优质示例。上游原始 repo 只保留为 provenance，不作为本轮执行要求来源。

| 用途 | 采用资产 | CLC 用法 | 不采用 |
|---|---|---|---|
| 设计哲学与质量门禁 | `open-design/apps/daemon/src/prompts/discovery.ts` | 使用其中 `huashu-distilled` 的 specialist、anti-AI-slop、Junior-pass、5-dim critique 思路，转成 CLC HTML export 的自检规则。 | 不使用 discovery form、Tweaks、视频/旁白、移动原型、幻灯片工作流。 |
| 设计方向库 | `open-design/apps/daemon/src/prompts/directions.ts` | 作为未来 `--style` preset 的来源；它已经蒸馏了 `huashu-design` 的“5 schools x 20 philosophies”方向选择思路。 | P1 不做方向选择 UI，不让用户先选一堆风格。 |
| 模板前置读取规则 | `open-design/apps/daemon/src/prompts/system.ts` 的 `derivePreflight()` | 借用“先读 template / layouts / checklist，再生成”的纪律；CLC 若未来引入模板包，也按这个顺序执行。 | P1 不引入外部模板包，也不复制 deck framework。 |
| 长文阅读与排版 | `open-design/craft/typography.md`、`open-design/craft/typography-hierarchy-editorial.md` | 直接转成 CSS 约束：正文 `60-75ch`，body `15-18px`，line-height `1.5-1.7`，heading / body / code 层级清楚。 | 不使用夸张杂志封面来压过最终答案。 |
| 反 AI 味 | `open-design/craft/anti-ai-slop.md`、`open-design/craft/color.md` | 禁止紫蓝渐变、emoji feature icon、假指标、filler copy；accent 限量，只表达状态、导航和关键 action。 | 不用“漂亮但无证据”的 metric cards、quote、装饰图标。 |
| 可访问性 | `open-design/craft/accessibility-baseline.md` | 使用原生语义结构、focus-visible、键盘可达、对比度和 heading hierarchy。 | 不发明 ARIA，不把按钮写成不可访问的 div。 |
| 主阅读页结构 | `open-design/design-templates/docs-page/SKILL.md`、`open-design/design-templates/blog-post/SKILL.md` | 借三栏 docs / article body / TOC / code block / 长文阅读结构，作为 `stage3/final.md` 的 reader-first 默认形态。 | 不照搬博客的 hero image、author footer、related posts。 |
| 证据层结构 | `open-design/design-templates/eng-runbook/SKILL.md`、`open-design/design-templates/github-dashboard/SKILL.md` | 借 runbook 的程序块、表格、清单和 GitHub dashboard 的高密度工程信息呈现，用于 Stage 1 / Stage 2 / trace / metadata。 | 不把证据层做成营销 dashboard，不编造 KPI。 |
| 自评审报告 | `open-design/design-templates/critique/SKILL.md` | 只借 5 维度评审维度：philosophy / hierarchy / detail / functionality / innovation。 | 不为每次 CLC run 额外生成一个独立 critique HTML。 |
| Deck / magazine 形态 | `open-design/design-templates/guizang-ppt/` | 只作为未来 `--style magazine` 或 deck export 的来源；该目录已经按 Open Design 方式捆绑并保留 LICENSE。 | 默认 HTML export 不使用横向 deck、WebGL、slide nav、Swiss locked layout、S01-S22、ASCII canvas、地图组件。 |
| HTML effectiveness 结构 | `https://thariqs.github.io/html-effectiveness/` | 保留 TOC、collapsible sections、tabbed code、SVG / CSS Grid visualization、copy/export buttons。 | 不让这些交互抢走最终答案主线。 |

当前明确不用的资产：

- 未进入 `open-design` 且不直接服务 CLC reader-first artifact 的原始 repo 工作流。
- `open-design` 的 Web app / daemon 运行时、question-form UI、artifact emission 协议。
- React / Vite / Web app。
- 任何会让 HTML 生成变成第二个模型综合步骤的方案。

### Reader-first HTML 信息架构

当前 `html_export.py` 的主要问题不是功能缺失，而是主次倒置：`stage3/final.md` 被放进 `<pre>`，Markdown 结构不可读；Stage 1 / Stage 2 / trace 更像调试面板。

下一版默认页面顺序：

```text
Header
  run_id / status / warnings-failures 摘要 / copy buttons

Main Reading
  Stage 3 Final Answer
  final.md -> Markdown HTML
  正文限宽 60-75ch

Decision Summary
  aggregate ranking
  member roster
  chairman model

Evidence
  Stage 1 responses tabs，默认折叠
  Stage 2 reviews tabs，默认折叠
  provider trace，默认折叠
  manifest / metadata，默认折叠
```

视觉规则：

- 首屏必须让用户马上读到最终答案，而不是先读运行流程。
- `stage3/final.md` 必须渲染为真实 Markdown HTML：标题、段落、列表、表格、代码块、引用都要保留结构。
- 正文阅读栏宽控制在 `60-75ch`，证据层可以使用宽屏 grid。
- 颜色只表达状态、导航和关键 action；禁止紫蓝渐变、emoji icon、假指标、装饰卡片。
- copy buttons 放在工具栏或 side rail，不插进正文阅读流。
- warnings / failures 必须在顶部可见；失败 run 不允许藏在 metadata 里。
- 页面使用原生语义结构：`header`、`nav`、`main`、`section`、`details`、`button`。

最小实现方案：

- 继续改现有 `src/coco_llm_council/html_export.py`。
- 增加一个小型 Markdown renderer，不引入前端构建链。
- 输出仍是单文件自包含 HTML。
- `html/artifact.prompt.md` 改成“HTML artifact rendering contract”，不再像提示模型生成 HTML。

以后可以加的 style preset 必须有明确资产来源：

```text
--style reader
  默认，长文阅读 + 折叠证据
  来源：craft/typography*.md + design-templates/docs-page + design-templates/blog-post

--style technical
  工程复盘，代码、trace、schema 更强
  来源：design-templates/eng-runbook + design-templates/github-dashboard

--style executive
  PM / director brief，首屏结论和决策更强
  来源：docs-page 的 TOC/article 结构 + critique 的 verdict/action list 结构

--style magazine
  需要对外展示时才启用
  来源：design-templates/guizang-ppt 或 editorial design-system
  限制：不能引入 deck runtime / WebGL / slide nav，除非用户明确要 deck
```

但 P1 不需要做 `--style`，先把默认 reader 形态做对。

HTML 验收：

```bash
coco-llm-council export <run_id> --format html --json
open .coco-llm-council/runs/<run_id>/html/index.html
```

必须检查：

- `stage3/final.md` 内容完整进入 HTML，且不是整块 `<pre>`。
- final answer 是默认主阅读区。
- Stage 1 / Stage 2 / provider trace 默认折叠但可打开。
- copy as markdown / JSON / final prompt 可用。
- 375px、768px、1440px 三个视口可读。
- tabs、details、buttons 可键盘操作。
- 浏览器 console 无错误。

### 用户自定义模型：输入阶段指定

用户指定模型必须结构化，不要靠 Stage 1 prompt 自己“猜”。

推荐的输入 frontmatter：

```markdown
---
members:
  - GPT-5.4
  - GLM-5.1
  - Gemini-3.1-Pro-Preview
chairman: GPT-5.4
provider_mode: direct
---

这里写用户问题。
```

CLI 行为：

- `--members` / `--chairman` 仍保留，适合命令行直接调用。
- `--profile` 仍保留，适合 subagent provider。
- 新增输入 frontmatter 只作为便捷入口，解析后仍进入 `CouncilConfig`。
- 优先级建议：显式 CLI 参数 > `--profile` > input frontmatter > 默认值。
- run 前仍调用 `traecli models --json`，并用 `require_models_available` 阻断无效模型。

验收：

```bash
coco-llm-council run --input examples/question-with-models.md --json
coco-llm-council show <run_id> --json
coco-llm-council validate <run_id> --json
```

必须满足：

- `manifest.config.members` 等于 frontmatter 指定值。
- `manifest.config.chairman` 等于 frontmatter 指定值。
- `runtime/coco.models.json` 保存当次完整可用模型快照。
- Stage 1 / Stage 2 / Stage 3 的 expected model 和 actual model 一致。
- 无效模型在调用前失败，不发生静默 fallback。

不要做：

- 不要让用户在正文里写“用三个强模型”后由模型自由解释。
- 不要维护一份脱离 `traecli models --json` 的静态模型名单。
- 不要为了 frontmatter 破坏现有 `--members` / `--chairman` / `--profile`。

### 启动前列全量模型并推荐三个

当前事实源仍然是：

```bash
coco-llm-council models --json
```

2026-05-22 本机实测当前返回 23 个模型，包括：

```text
Seed-Dogfooding-2.0
Doubao-Seed-2.0-Code
Doubao-Seed-1.8
Doubao-Seed-Code
openrouter-2o
openrouter-1o
openrouter-1
MiniMax-M2.7
MiniMax-M2.5
GLM-5.1
GLM-5V-Turbo
GLM-5
Gemini-3.1-Pro-Preview
Gemini-3-Flash-Preview
DeepSeek-V4-Pro
DeepSeek-V4-Flash
Kimi-K2.6
Kimi-K2.5
GPT-5.5
GPT-5.4
GPT-5.2
Qwen3.6-Plus
Qwen3.5-Plus
```

注意：这个列表是当前机器当前时间的事实，不能写死进推荐逻辑。`openrouter-*` 当前输出带 quota / L4 repo 限制说明，默认不应进入推荐组合。

推荐逻辑建议放在 CLC CLI 内，而不是写在 Trae-CN prompt 里。新增命令可以是：

```bash
coco-llm-council recommend-models --task-mode general --json
```

最小规则：

- 只从 `models --json` 的当前返回中选。
- 默认推荐 3 个 member models + 1 个 chairman。
- 推荐结果必须带 `generated_at`、完整模型快照 hash 或 path、推荐理由。
- 如果某个首选模型不可用，按同族或同能力降级，但要把替换原因写进 JSON。

默认推荐策略：

```text
general / reasoning:
  members: GPT-5.4, GLM-5.1, Gemini-3.1-Pro-Preview
  chairman: GPT-5.4

high-reasoning / expensive-ok:
  members: GPT-5.5, GPT-5.4, Gemini-3.1-Pro-Preview
  chairman: GPT-5.5 或 GPT-5.4，取决于 queue heat 和可用性

fast / cheap:
  members: GPT-5.4, DeepSeek-V4-Flash, Gemini-3-Flash-Preview
  chairman: GPT-5.4

code:
  members: GPT-5.4, Doubao-Seed-2.0-Code, DeepSeek-V4-Pro
  chairman: GPT-5.4
```

这里的推荐不是“模型真理”，只是启动默认值。真正可信边界仍是 run 里的 expected/actual model 校验和 artifact evidence。

### Trae-CN 调用 CLC 时怎么用 AskUserQuestion

`AskUserQuestion` 可以放在 Trae-CN wrapper flow 中使用，但不要进入 CLC core。

推荐流程：

```text
Trae-CN
  1. 整理用户问题为 input.md
  2. 调用 coco-llm-council models --json
  3. 调用 coco-llm-council recommend-models --task-mode <mode> --json
  4. 如果用户没有显式指定模型，用 AskUserQuestion 展示：
     - 推荐组合
     - 快速组合
     - 高推理组合
  5. 用户选择后，Trae-CN 调用：
     coco-llm-council run --input input.md --members ... --chairman ... --json
  6. 返回 html/index.html 路径
```

边界：

- CLC core 不主动问用户。
- CLC core 不依赖 Trae-CN DOM、selector、UI 工具或 AskUserQuestion。
- Trae-CN 的问题卡片只是更好的前置体验；没有它，CLI 也必须能 headless 跑。
- 如果未来 COCO / traecli 提供稳定、可脚本化、非 UI 依赖的 ask-user primitive，并且能写进 artifact store，可以考虑作为 optional preflight；现在不做。

### 下一轮实现节奏

建议分两轮，不要一次全做：

1. HTML reader-first
   - 改 `html_export.py`。
   - 增加 Markdown rendering。
   - 调整 HTML 信息架构和 CSS。
   - 补 HTML export 测试和浏览器验证。

2. 模型选择输入层
   - 支持 input frontmatter。
   - 新增 `recommend-models --json`。
   - 写 Trae-CN wrapper prompt / usage guide。
   - 验证无效模型、fallback、expected/actual model。

第一轮优先级更高，因为它直接影响用户阅读体验；第二轮影响启动体验和可配置性。

### 给执行会话的提示词

```text
/goal 在当前 workspace 推进 COCO-llm-council 的下一轮迭代。先阅读 README.md、docs/design.md，重点看“追加方案：Reader-first HTML 与 Trae-CN 模型选择”。本轮只实现第一部分：把 HTML export 改成 reader-first artifact。要求：HTML 默认以 stage3/final.md 渲染出的最终答案为主阅读区，不再把 final.md 整块放进 pre；Stage 1、Stage 2、provider trace、manifest metadata 作为可折叠证据层；保留 copy as markdown / JSON / final prompt；单文件自包含；不引入 React/Vite/Web app；不重新调用模型生成 HTML；不改变 Stage 3 final answer。设计资产只使用 open-design 中明确适配的文件：craft/typography.md、craft/typography-hierarchy-editorial.md、craft/anti-ai-slop.md、craft/color.md、craft/accessibility-baseline.md、design-templates/docs-page/SKILL.md、design-templates/blog-post/SKILL.md、design-templates/eng-runbook/SKILL.md、design-templates/github-dashboard/SKILL.md；不要直接引用 huashu-design 或 guizang-ppt-skill 原始 repo。完成后必须运行单元测试、导出既有可信 run 的 HTML、验证 375px/768px/1440px 可读、console 无错误，并汇报 artifact 路径。
```
