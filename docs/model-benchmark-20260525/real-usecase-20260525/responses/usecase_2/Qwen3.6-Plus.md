经过多轮搜索和深入分析，以下是完整的调研报告。

---

## 非开发者 + AI Agent + 黑客松：默认技术栈推荐报告

### 一、核心结论（先说答案）

**默认技术栈（占 80% 场景）：Vite + Vanilla JS + Tailwind CSS + shadcn/ui（或同类 UI 组件库）**

**理由一句话总结**：AI 模型对这组技术的训练数据量最大、生成质量最高、项目结构最扁平、构建工具零配置、`npm run dev` 一键启动、UI 开箱即好看，且经过多轮修改后仍可维护。

---

### 二、决策框架：非开发者在 AI 辅助下做 MVP 的关键约束

非开发者使用 AI Agent（Trae-CN / Cursor）做黑客松项目，和职业开发者使用 AI 辅助编程，本质上是**两个不同的问题**。评判技术栈必须基于以下约束：

| 约束维度 | 要求 |
|---|---|
| **启动复杂度** | `npm install` → `npm run dev` → 浏览器打开，不超过 3 步 |
| **项目结构** | 文件层级 ≤ 3 层，非开发者能看懂"哪个文件管什么" |
| **AI 生成质量** | 模型训练数据量大，生成代码一次成功率 > 80% |
| **可修复性** | 报错了 AI 能否自动定位并修好，而不是让用户读 stack trace |
| **UI 颜值下限** | 不需要手写 CSS，用组件库/工具类就能做出"像样"的界面 |
| **本地演示** | 纯前端可跑，或 `npm run dev` 包含前后端，不依赖外部服务 |
| **迭代韧性** | 经过 5-10 轮"改这里、加那个"后，项目不会崩塌 |

---

### 三、候选技术栈逐一分析

#### 方案 A：单 HTML 文件（CDN 引入 Tailwind + Alpine.js）

```
project/
└── index.html    ← 一切都在这个文件里
```

**优势**：
- 零依赖、零构建、零启动命令——双击打开即可
- 项目结构不可能更简单
- AI 生成一个文件的成功率极高
- 非常适合纯展示页、简单表单、数据看板

**致命缺陷（为什么不做默认）**：
1. **多轮修改后迅速崩塌**：3-4 轮迭代后，HTML 文件膨胀到 800+ 行，包含内联 JS 逻辑、CSS 样式、模板字符串。AI 在这个长度上开始出现"改 A 坏 B"的问题——修了按钮样式，不小心破坏了事件绑定。
2. **无法模块化**：非开发者面对一个 1000 行的单文件，即使 AI 标了注释，也完全不知道去哪里改什么。
3. **AI 上下文窗口压力**：每次对话都要携带整个文件内容，token 消耗大，容易丢上下文。
4. **无组件复用**：重复的导航栏、卡片、表单需要复制粘贴，AI 改一处不会自动同步。

**结论**：看起来最简，**但迭代韧性最差**。适合作为**条件触发的备选方案**（见下文）。

---

#### 方案 B：Next.js（App Router）+ React + TypeScript + Tailwind + shadcn/ui

这是目前 AI App Builder（Bolt.new、Lovable、v0）和大多数 vibe coding 教程的**默认输出栈**。DataCamp、Context Studios 等分析文章也推荐此组合。

**优势**：
- AI 训练数据量最大——Stack Overflow、GitHub、教程中 React + Next.js 占比最高
- shadcn/ui 提供了 50+ 高质量组件，AI 生成 UI 几乎不会丑
- Next.js App Router 天然包含前后端（Server Actions / API Routes），不需要另起服务器
- 部署简单（Vercel 一键）

**对非开发者的致命问题**：
1. **TypeScript 类型错误是噩梦**：多个 Reddit 讨论（r/vibecoding: "Build a Complete Full-Stack Website in 2 Days"）报告，非开发者在使用 TS 时，AI 频繁生成错误的类型定义，类型错误链式传播，AI 修了一个又冒出三个。有开发者明确说"切到 JS + Tailwind v3 后效率显著提升"。
2. **项目结构复杂**：`app/`、`components/`、`lib/`、`public/`、`package.json`、`next.config.js`、`tailwind.config.js`、`tsconfig.json`——文件数量 10+，非开发者迷失。
3. **Next.js 版本迭代快**：App Router 本身还在演进，AI 可能混用 Pages Router 和 App Router 的写法，产生运行时错误。
4. **依赖安装时间长**：`npm install` 在 Next.js 项目上经常需要 1-2 分钟，安装失败（网络、node 版本、native addon）的概率显著高于轻量项目。
5. **启动命令不只是 `npm run dev`**：可能需要先配环境变量、跑 `npx shadcn@latest init`、初始化数据库等。

**结论**：专业开发者用 AI 辅助写 Next.js 很强，但对**非开发者在黑客松场景下是过度工程**。

---

#### 方案 C：Vite + Vanilla JS + Tailwind CSS（推荐默认）

```
project/
├── index.html
├── package.json          ← 只有 vite + tailwind 两个核心依赖
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── src/
│   ├── main.js           ← 入口，AI 和用户都知道"改这里"
│   ├── styles.css        ← Tailwind 入口
│   └── components/       ← 可选，AI 自动管理
```

**为什么这是最优默认**：

1. **AI 生成质量高**：Vanilla JS + Tailwind 的训练数据量仅次于 React。Vite 是标准工具链，AI 生成的 `vite.config.js` 几乎总是对的。
2. **项目结构极度扁平**：核心文件 5-6 个，`src/main.js` 是单一入口，非开发者能理解"逻辑在这里，样式在那里"。
3. **构建极快**：Vite 冷启动 < 2 秒，HMR（热更新）即时生效。非开发者改完代码不用等。
4. **零 TypeScript 烦恼**：没有类型系统，AI 不会生成错误的类型定义，报错只有运行时 JS 错误，AI 定位和修复能力强。
5. **Tailwind CSS 开箱即好**：AI 写 Tailwind class 的成功率极高，不需要手写 CSS，UI 颜值下限高。
6. **可渐进增强**：
   - 需要状态管理？引入 Alpine.js 或 Petite-Vue（CDN 一行引入，无需 npm）
   - 需要图表？引入 ECharts / Chart.js（CDN 一行）
   - 需要路由？引入 vanilla-router 或 hash-based 路由
   - 需要后端？加一个 Express/Python Flask 侧车，或直接用 browser localStorage
7. **npm 依赖极少**：通常只有 `vite`、`tailwindcss`、`postcss`、`autoprefixer` 四个包，安装快、冲突少。
8. **纯前端可演示**：不需要数据库、不需要后端服务，打开浏览器就能跑。数据用 mock JSON 或 localStorage。

**迭代韧性评估**：
- 5 轮以内：非常好，AI 定位文件精准
- 5-10 轮：仍然可控，文件数量可控在 10 个以内
- 10 轮以上：如果项目逻辑变得复杂，需要考虑拆分模块（但此时 AI 也能处理）

---

#### 方案 D：Vue 3 + Vite + Element Plus / Ant Design Vue

**优势**：Vue 的 template 语法对非开发者更直观（HTML 里写 `v-if`、`v-for`），Element Plus 组件丰富。

**问题**：
- AI 对 Vue 的训练数据量显著少于 React，生成质量略逊
- 在国内生态好，但在全球 AI 模型的训练权重中不是主流
- Element Plus 的 Tailwind 兼容性不如 shadcn/ui

**结论**：如果团队对 Vue 有偏好可用，但不作为默认推荐。

---

#### 方案 E：Python Streamlit / Gradio

**优势**：Python 非开发者熟悉度高（数据分析人群），纯 Python 写 UI，不需要 JS/HTML。

**问题**：
- UI 定制能力极弱——非开发者想要"这里改个颜色、那里换个布局"时非常痛苦
- 不适合做"看起来专业的 Web MVP"——黑客松评审看的是"产品感"
- 组件生态有限，表单流程/数据看板之外的场景（如 AI 工具、表单审批流）难以实现
- AI 生成 Streamlit 代码的质量一般，布局问题频发

**结论**：仅适合纯数据分析/ML demo，不做通用推荐。

---

### 四、推荐方案：默认 + 条件触发备选

#### 默认技术栈（覆盖 80% 场景）

| 层级 | 技术选择 | 理由 |
|---|---|---|
| 构建工具 | **Vite** | 零配置、秒启动、HMR 即时 |
| 语言 | **Vanilla JavaScript（ES6+）** | 无 TS 类型错误、AI 生成稳定 |
| 样式 | **Tailwind CSS v3** | AI 写 class 成功率高、无需手写 CSS |
| UI 组件 | **DaisyUI** 或 **Tailwind UI 组件** | 比 shadcn/ui 更轻（纯 CSS class，无需 npm 组件安装），非开发者更容易用 |
| 状态管理 | **Alpine.js**（CDN 引入） | 一行 `<script defer src="cdn...">` 即可，无需 npm 包 |
| 图表（按需） | **ECharts** 或 **Chart.js**（CDN） | 一行引入，AI 生成图表代码质量高 |
| 后端（按需） | **Mock JSON / localStorage** | 纯前端可演示，零后端依赖 |
| 路由（按需） | **Hash-based 路由** | 无需 router 库，手写 20 行即可 |

**启动命令**：
```bash
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

**项目结构**（典型）：
```
my-hackathon-project/
├── index.html          ← 页面骨架，引入 Tailwind + Alpine
├── package.json        ← 只有 vite + tailwind
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.js         ← 所有 JS 逻辑入口
    └── style.css       ← @tailwind directives
```

---

#### 触发条件下的备选技术栈

| 触发条件 | 切换方案 | 原因 |
|---|---|---|
| **需要真实后端 + 数据库**（用户注册、数据持久化） | Vite + JS + **Supabase JS SDK** | Supabase 提供 BaaS，前端直接调，无需写后端代码 |
| **需要调用公司 API / LLM API** | 默认栈 + **Python FastAPI 侧车** | Python 做 API 代理，前端 fetch 调用，职责清晰 |
| **项目逻辑极其简单**（单页展示、简单表单，预计 < 3 轮修改） | **单 HTML 文件**（CDN Tailwind + Alpine） | 零构建、双击打开，足够用 |
| **强数据可视化需求**（仪表盘、BI 看板） | 默认栈 + **ECharts** / **Apache ECharts** | ECharts 对中文文档友好，AI 生成质量高 |
| **团队有 Python 背景 + 纯数据分析场景** | **Streamlit** | 仅限此场景，UI 不可定制是已知 tradeoff |
| **需要 AI 对话界面** | 默认栈 + **简单 chat UI 组件** | 不需要 LangChain 等框架，fetch 调 API 即可 |

---

### 五、"看似简单但多轮修改后变难"的路线

| 路线 | 为什么看似简单 | 多轮后为什么变难 |
|---|---|---|
| **单 HTML 文件** | 零依赖、双击打开 | 300 行后 AI 开始"改 A 坏 B"，非开发者面对单文件无法定位 |
| **Next.js + TypeScript** | AI 教程最多、一键模板 | TS 类型错误链式传播；App Router 写法不统一；依赖安装慢且易失败 |
| **Streamlit** | 纯 Python、不用写 HTML | UI 不可定制；布局问题 AI 修不好；黑客松评审"产品感"差 |
| **React + Create React App** | "React 官方推荐"的刻板印象 | CRA 已废弃，AI 仍可能生成；webpack 配置复杂；启动慢 |
| **纯手写 CSS（不用 Tailwind）** | "不需要学框架" | AI 写 CSS 容易冲突；非开发者无法调试样式；迭代后 CSS 文件变成 500 行泥潭 |

---

### 六、AI Agent 生成代码的关键对比维度

| 维度 | Vite+JS+Tailwind | Next.js+TS | 单 HTML | Streamlit |
|---|---|---|---|---|
| AI 生成准确率 | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★☆☆ |
| AI 修复错误能力 | ★★★★★ | ★★★☆☆（TS 类型链） | ★★★☆（文件太长） | ★★☆☆（布局难修） |
| 项目可理解性（非开发者） | ★★★★☆ | ★★☆☆ | ★★★★★（初期） | ★★★★☆ |
| UI 颜值下限 | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★☆☆ |
| 本地启动速度 | ★★★★★（< 2s） | ★★★☆☆（10-30s） | ★★★★★（0s） | ★★★★☆ |
| 依赖安装稳定性 | ★★★★★（4 个包） | ★★★☆☆（50+ 个包） | ★★★★★（0 个包） | ★★★★☆ |
| 5 轮后仍可维护 | ★★★★☆ | ★★★☆☆ | ★★☆☆ | ★★★☆☆ |
| 黑客松演示效果 | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★☆☆ |

---

### 七、明确推荐

> **默认技术栈 = Vite + Vanilla JS + Tailwind CSS + DaisyUI + Alpine.js（CDN）**
>
> 这个组合在 AI 生成质量、项目简洁度、启动速度、UI 颜值、迭代韧性五个维度上取得了最佳平衡。非开发者通过 Trae-CN 的 Agent 能力，可以在 2-4 小时内从零做出一个可本地运行、可演示的 Web MVP。

---

### 八、置信度与可推翻条件

**置信度：中高（Medium-High）**

**可能推翻此推荐的条件**：

1. **如果 Trae-CN 的 Skill 系统内置了某个框架的"一键模板 + 自动排错"能力**，那么被内置的框架应成为默认——因为工具链集成度会压倒通用技术栈优势。
2. **如果目标场景 > 60% 是纯数据分析/BI 看板**，Streamlit + ECharts 的纯 Python 路线可能更优。
3. **如果非开发者团队中有 Python 数据分析师占比 > 70%**，他们可能对 JS 生态完全陌生，此时 Python 路线更合适。
4. **如果黑客松要求必须部署到特定平台**（如 Vercel），Next.js 的部署便利性可能超过其复杂度劣势。
5. **如果有证据表明最新 AI 模型（GPT-5 / Claude 4+）在 TypeScript 项目上的自动排错能力已达到与 JS 同等水平**，TS 的类型安全性优势可能使其重新成为默认。

---

### 九、参考资料与支撑关系

| 资料来源 | 支撑的判断 |
|---|---|
| [DataCamp: Vibe Coding Tech Stack](https://www.datacamp.com/blog/vibe-coding-tech-stack) | 推荐 Next.js + Tailwind + shadcn/ui 作为专业开发者的 vibe coding 标准栈，反向证明了 Tailwind + 组件库是 UI 层的共识 |
| [Context Studios: Vibe Coding Tech Stack 2026](https://www.contextstudios.ai/blog/the-perfect-vibe-coding-tech-stack-2026-10-tools-every-app-needs/) | 确认 Next.js + React Compiler + Tailwind 是当前 AI coding 的主流，同时指出了 turbopack 和自动 memoization 的优势 |
| [Reddit r/vibecoding: "Build Full-Stack in 2 Days"](https://www.reddit.com/r/vibecoding/comments/1jy7xny/) | **关键证据**：开发者报告 TS + Tailwind v4 导致 AI 频繁生成错误类型定义，切换到 JS + Tailwind v3 后效率显著提升 |
| [Reddit r/cursor: "Best tech stack for vibe coding"](https://www.reddit.com/r/cursor/comments/1jomobu/) | 社区共识：React + Tailwind 是 AI tooling 训练数据最丰富的组合 |
| [Lovable vs Bolt vs Replit 对比](https://lovable.dev/guides/bolt-vs-replit-vs-lovable) | AI App Builder 默认输出 React/Vue 项目，证明了 AI 模型对这些框架的生成能力强；同时指出 Replit 在 Python 后端的优势 |
| [Reddit r/nocode: "Best stack for vibe coders long-term"](https://www.reddit.com/r/nocode/comments/1nysq3k/) | 非开发者讨论中，对"哪个栈最容易用 AI 做出来"的共识是：越简单的构建工具越好，避免 TypeScript 和复杂框架 |
| [MakerPad: No-Code Agent Ops 2026](https://www.makerpad.co/news/no-code-agent-ops-in-2026-a-practical-stack-for-makers-without-over-engineering) | 指出大多数 maker 项目失败的原因是**运维复杂度**而非模型质量，支持"技术栈必须降低运维负担"的判断 |
| [ExplainX: Agentic Fatigue meets Vibe Coding](https://explainx.ai/blog/agentic-fatigue-vibe-coding-ai-developer-productivity-paradox) | 揭示了 vibe coding 在后期的维护困境，支持"单 HTML 文件多轮后崩塌"的判断 |
| [TCS AI Hackathon for non-engineering students](https://www.tcs.com/who-we-are/newsroom/press-release/tcs-hosts-hackathon-for-non-engineering-students) | 大规模非工程学生 AI 黑客松的实践，证明非开发者使用 AI 做项目是可行的，但需要极简技术栈 |

---

### 十、实操建议：给黑客松组织者的"黑客松开发套件"配置

如果要将上述推荐落地为一个**"黑客松开发套件"**（预装在 Trae-CN 中，非开发者一键初始化），建议：

```bash
# 一键初始化命令（可由 Skill 自动执行）
npm create vite@latest my-project -- --template vanilla
cd my-project
npm install -D tailwindcss@3 postcss autoprefixer
npx tailwindcss init -p

# 在 index.html 中 CDN 引入 Alpine.js + DaisyUI
# 在 src/main.js 中预置基础模板

npm run dev  # 2 秒启动，浏览器打开即用
```

配合一个 **Trae Skill**，实现：
1. 需求 → PRD → 原型 → 代码的完整 pipeline
2. 默认生成上述技术栈
3. 内置常见场景模板（数据看板 / 表单流程 / AI 工具 / 内部工具）
4. 自动 mock 数据，确保本地可演示
