# 非开发者 + AI Agent + 黑客松开发套件：默认技术栈推荐

> 调研时间：2026-05-27
> 定位：面向 Trae-CN / Cursor 等 AI IDE 环境下，非开发者在黑客松中从想法到可演示 MVP 的技术栈选择

---

## 一句话结论

**默认技术栈：Python + Streamlit + SQLite**
**触发条件下切换的备选：Node.js + Next.js (App Router) + shadcn/ui + Tailwind**
**特殊场景触发：单文件 HTML（纯展示 / 零后端）或 Gradio（纯 ML demo）**

置信度：**中高**。能推翻它的条件见文末。

---

## 一、评估框架：AI Agent 生成代码的 7 个核心维度

对非开发者而言，AI Agent 写代码不是"写好就行"，而是整个生命周期：

| 维度 | 为什么重要 |
|------|-----------|
| 1. 项目结构简单度 | 文件少、层级浅，Agent 不容易迷路，非开发者打开不懵 |
| 2. Agent 自动排错能力 | Agent 能否自己读懂报错并修复？错误栈越浅越好 |
| 3. 依赖稳定性 | `pip install` vs `npm install` 的失败率和 node_modules 体积 |
| 4. 启动命令简单度 | `streamlit run app.py` vs `npm run dev` vs 复杂配置 |
| 5. UI 美观度下限 | 不写 CSS 能不能做出像样的界面？ |
| 6. 本地演示难度 | 能否一键启动、浏览器自动打开、无需注册云服务 |
| 7. 多轮修改后的可控性 | 改到第 5 轮、第 10 轮后，项目是否还能被 Agent 理解并继续改 |

---

## 二、主流候选技术栈逐一分析

### A. Python + Streamlit + SQLite

**项目结构：**
```
my-app/
├── app.py          # 通常就这一个文件
├── requirements.txt
└── data.db          # SQLite 自动创建，零配置
```

**AI Agent 友好度分析：**

| 维度 | 评价 | 说明 |
|------|------|------|
| 项目结构 | ★★★★★ | 单文件即可跑完整应用，非开发者打开一眼看懂 |
| Agent 排错 | ★★★★☆ | Python 报错栈清晰，Streamlit 错误会直接显示在浏览器页面上，Agent 能直接看到 |
| 依赖稳定性 | ★★★★★ | `pip install` 成熟稳定，国内镜像源丰富，极少出问题 |
| 启动命令 | ★★★★★ | `streamlit run app.py`，零配置，自动打开浏览器 |
| UI 美观度 | ★★★☆☆ | 内置组件够用但定制化有限，非专业设计也"不太丑" |
| 本地演示 | ★★★★★ | 自带 local server + 浏览器自动打开 |
| 多轮修改后 | ★★★★☆ | 单文件结构在 500-800 行内 Agent 完全掌控；超过 1000 行可拆模块，但 Streamlit 天然鼓励单文件 |

**关键优势：**
- **Streamlit 官方已发布 Agent Skills**（[streamlit/agent-skills](https://github.com/streamlit/agent-skills)），专门给 Cursor / Claude Code 等 AI 编码工具用的指令集。这是目前唯一一个官方为 AI Agent 做了专项优化的 Web 框架
- Reddit r/cursor 高票推荐"Streamlit + Python + SQLite"作为 vibe coding 首选栈
- 训练数据中 Streamlit 代码样本极多，LLM 生成质量高
- SQLite 零配置，不需要装数据库服务

**关键劣势：**
- 不适合做复杂的多页 SPA（Single Page Application）
- 状态管理是 Streamlit 的固有难点（每次交互重跑整个脚本），但 AI Agent 可以通过 `st.session_state` 模式解决
- UI 上限不高，做不了高度定制的交互

### B. Node.js + Next.js (App Router) + shadcn/ui + Tailwind

**项目结构：**
```
my-app/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   └── ...
├── components/
│   └── ui/           # shadcn 组件，每个组件一个文件
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

**AI Agent 友好度分析：**

| 维度 | 评价 | 说明 |
|------|------|------|
| 项目结构 | ★★☆☆☆ | 文件多、层级深、约定复杂（App Router 的文件路由规则） |
| Agent 排错 | ★★★☆☆ | TypeScript 类型错误容易定位，但 hydration error / server component 错误难排查 |
| 依赖稳定性 | ★★☆☆☆ | `npm install` 在 Windows/旧 Node 上经常出问题；node_modules 体积大 |
| 启动命令 | ★★★☆☆ | `npm install && npm run dev`，但前置条件（Node.js 版本、npm 版本）容易卡住 |
| UI 美观度 | ★★★★★ | shadcn/ui + Tailwind 是目前 AI 生成 UI 的天花板，Cursor 的 .cursorrules 社区模板最丰富的就是这套 |
| 本地演示 | ★★★★☆ | `npm run dev` 后自动开浏览器，但依赖链问题可能导致首次启动失败 |
| 多轮修改后 | ★★☆☆☆ | **这是最大隐患**：App Router + Server Components + Client Components 的边界在多次修改后极易混乱 |

**关键优势：**
- **AI 生成 UI 质量最高**：shadcn/ui 是目前所有 AI coding 工具（Cursor, Bolt, Lovable, v0）的默认 UI 方案
- Cursor 官方推荐模板和 .cursorrules 社区资源最丰富的就是 Next.js + shadcn
- 适合做需要"卖相好"的演示
- 生态丰富，任何功能都能找到库

**关键劣势：**
- **复杂性炸弹**：Hacker News 上大量讨论（[#43672449](https://news.ycombinator.com/item?id=43672449), [#45099922](https://news.ycombinator.com/item?id=45099922)）指出 Next.js 抽象层太多，99% 的项目不需要
- Server Component / Client Component 边界：AI Agent 在多次修改后经常在两者之间搞混，产生 hydration 错误
- `npm` 生态的依赖地狱在非开发者机器上极易爆发
- 项目文件多，Agent 在大型 codebase 中容易"迷路"

### C. Python + Gradio

**项目结构：**
```
my-app/
├── app.py
└── requirements.txt
```

**AI Agent 友好度：**

| 维度 | 评价 |
|------|------|
| 项目结构 | ★★★★★ 单文件，极简 |
| UI 美观度 | ★★☆☆☆ 模板化严重，基本就是"输入框+按钮+输出" |
| 多轮修改后 | ★★★☆☆ 超过 2-3 个输入输出就会变得笨重 |

**定位：** 仅适合纯 ML 模型 demo（上传图片→输出分类、输入文本→输出摘要）。一旦需要做表单流程、数据看板、多页交互，Gradio 就撑不住了。HN 社区共识："Gradio 适合 tiny demo，Streamlit 适合超出 demo 的一切"。

### D. 单文件 HTML + CSS + JS（零框架）

**项目结构：**
```
index.html  # 就这一个文件
```

**AI Agent 友好度：**

| 维度 | 评价 |
|------|------|
| 项目结构 | ★★★★★ 不可能更简单 |
| 启动命令 | ★★★★★ 双击打开 / `python -m http.server` |
| 依赖 | ★★★★★ 零依赖 |
| UI 美观度 | ★★★☆☆ AI 能写出还行的 CSS，但缺少组件库支撑 |
| 多轮修改后 | ★★☆☆☆ 单个 HTML 文件超过 500 行后，JS/CSS/HTML 混在一起，Agent 也容易混乱 |
| 功能上限 | ★☆☆☆☆ 没有后端、没有数据库、没有状态管理 |

**定位：** 适合纯展示的着陆页（landing page）、静态信息页、简单的交互原型。一旦需要数据存储、API 调用、用户输入处理，就不够了。

### E. Python + FastAPI + HTMX + SQLite

**项目结构：**
```
my-app/
├── main.py
├── templates/
│   └── index.html
├── static/
└── requirements.txt
```

**评价：** 这是一个"中间路线"——比纯 Python 脚本多了后端 API 层，但比 React/Next.js 简单。HTMX 让前端不需要 JavaScript 框架。

**问题：**
- HTMX 在 AI 训练数据中的样本量远小于 React
- AI Agent 对 HTMX 的生成质量不如主流框架
- 非开发者看到"template + static + API 路由"会困惑
- 黑客松场景下，"多一个概念就多一分风险"

**结论：不推荐作为默认栈**，但在需要 REST API + 简单前端的场景可作为备选。

---

## 三、明确推荐

### 默认技术栈：Python + Streamlit + SQLite

**适用场景：** 黑客松 80% 的项目——数据看板、内部工具、表单流程、AI 小工具、CRUD 管理后台。

**理由：**
1. **非开发者门槛最低**：`pip install streamlit` → `streamlit run app.py` → 浏览器自动打开，三步完成
2. **AI Agent 排错最容易**：Streamlit 错误直接在浏览器页面显示，Agent 不需要看终端日志就能修复
3. **官方 AI Agent 支持**：Streamlit 团队已发布 [agent-skills](https://github.com/streamlit/agent-skills) 项目，专门为 Cursor、Claude Code 等 AI IDE 提供指令
4. **训练数据丰富**：GitHub 上 Streamlit 项目超过 30k，LLM 生成质量极高
5. **依赖零摩擦**：Python 环境 + pip 在国内企业环境中普及率远高于 Node.js
6. **SQLite 零配置**：不需要装数据库、不需要连云服务、不需要配置环境变量
7. **修改后的可控性最好**：单文件结构意味着 Agent 始终能看到"全貌"

### 触发条件下切换的备选技术栈

| 触发条件 | 切换为 | 理由 |
|----------|--------|------|
| **对 UI 卖相有极高要求**（要向高管演示、需要"看起来很专业"） | Node.js + Next.js + shadcn/ui + Tailwind | shadcn/ui 是目前 AI 生成 UI 的上限，卖相碾压 Streamlit |
| **需要复杂的多页面、用户系统、实时交互**（类似 SaaS 产品） | 同上 | Streamlit 做不了复杂 SPA |
| **纯 ML 模型 demo**（上传图片→分类、输入→输出） | Python + Gradio | Gradio 为 ML demo 而生，两行代码搞定 |
| **纯静态展示页**（landing page、信息页） | 单文件 HTML + Tailwind CDN | 零依赖、双击打开 |
| **需要对接公司内部已有 API / 微服务** | Python + FastAPI（前端仍可用 Streamlit） | FastAPI 做 API 层，Streamlit 做展示层 |

---

## 四、哪些路线看似简单，但多轮修改后会变难

### 1. Next.js App Router（复杂性炸弹）

**看似简单的原因：** AI 能一键生成漂亮的 Next.js 项目，第一眼看效果极好。

**多轮修改后的问题：**
- Server Component 和 Client Component 边界混乱：AI 在第 3-5 轮修改后经常在两者之间放错代码，导致 hydration 错误
- 文件路由规则复杂：`app/(auth)/login/page.tsx` vs `app/api/route.ts` vs `components/`，AI 在文件多的情况下容易放错位置
- 依赖版本冲突：Next.js 13→14→15 的 breaking changes 频繁，AI 可能混用新旧 API
- Hacker News 上大量讨论确认：Next.js 的抽象层对即使是专业开发者都"overwhelming"，对非开发者+AI 来说更是定时炸弹

### 2. React + Vite + 各种库的手动拼装

**看似简单的原因：** 教程多，AI 能生成。

**多轮修改后的问题：**
- 路由（React Router）、状态管理（Zustand/Redux）、UI 库（MUI/Ant Design）的选择和组合会让 AI 在不同轮次中做出不一致的决策
- 非开发者无法判断"这个报错是 React 的问题还是某个库的问题"

### 3. Streamlit 的大型应用（超过 1000 行单文件）

**看似简单的原因：** 单文件确实简单。

**多轮修改后的问题：**
- 单文件超过 800-1000 行后，AI Agent 在理解代码全貌时 token 消耗大，容易遗漏已有逻辑
- 但这个问题可以通过"早期提醒 Agent 拆分模块"来缓解，且拆分成 `pages/` 和 `utils/` 仍然比 Next.js 简单

---

## 五、置信度与推翻条件

**置信度：中高（70-80%）**

**能推翻本推荐的条件：**

1. **如果目标用户群体已经装了 Node.js 且熟悉 npm**（比如数据分析师已用惯了 JS 工具链），那么 Next.js 路线的启动摩擦消失，推荐可能翻转
2. **如果 Streamlit 官方 Agent Skills 被发现质量不佳**（生成代码有系统性 bug），则需要重新评估
3. **如果 Trae-CN / Cursor 的 AI 模型对 TypeScript 的理解能力远超 Python**（目前不成立，两者相当），则 JS 生态的优势会放大
4. **如果黑客松评审标准极度看重 UI 卖相而非功能完整性**，则 shadcn/ui 的视觉优势可能值得承担复杂度风险
5. **如果企业内部有强制的技术栈要求**（比如必须用某个前端框架或后端语言），则默认栈必须适配

---

## 六、给黑客松套件的具体建议

### 预置模板

提供两个预置模板（ZIP 或 git clone）：

```
hackathon-starter/
├── streamlit-template/     # 默认
│   ├── app.py
│   ├── requirements.txt
│   ├── .cursorrules        # AI Agent 指令
│   └── AGENTS.md           # 更详细的 agent 引导
│
└── nextjs-template/        # 备选（UI 卖相优先）
    ├── app/
    ├── components/
    ├── package.json
    ├── .cursorrules
    └── AGENTS.md
```

### `.cursorrules` 关键内容

对于 Streamlit 模板，应包含：
- 使用 `st.session_state` 管理状态的模式
- 使用 `st.columns` / `st.tabs` 做布局
- 使用 `sqlite3` 做持久化
- 禁止使用过于实验性的 Streamlit 特性

对于 Next.js 模板，应包含：
- 严格区分 Server Component 和 Client Component 的规则
- 使用 shadcn/ui 而非手写样式
- 禁止混用 Pages Router 和 App Router 的约定

### 技能包（Skills）

- **需求澄清 Skill**：引导非开发者用结构化方式描述需求
- **PRD 生成 Skill**：从想法生成一页 PRD
- **原型迭代 Skill**：基于截图/描述修改 UI
- **数据库 Skill**：为 SQLite 生成 schema 和 CRUD 操作
- **演示准备 Skill**：自动生成演示脚本和 mock 数据

---

## 七、参考资料与对应判断

| 资料 | 链接 | 支持的判断 |
|------|------|-----------|
| Streamlit Agent Skills（官方） | [github.com/streamlit/agent-skills](https://github.com/streamlit/agent-skills) | Streamlit 是唯一为 AI Agent 发布官方指令集的 Web 框架，证明其 AI 友好度被官方认证 |
| Reddit r/cursor: "Best technology stack for vibe coding" | [reddit.com/r/cursor/comments/1jomobu](https://www.reddit.com/r/cursor/comments/1jomobu/best_technology_stack_for_vibe_coding_ie_what/) | 社区高票推荐 "Streamlit + Python + SQLite" 作为 vibe coding 首选 |
| Streamlit 官方博客: "Vibe code Streamlit apps with AI" | [blog.streamlit.io/vibe-code-streamlit-apps-with-ai](https://blog.streamlit.io/vibe-code-streamlit-apps-with-ai-using-agents-md-04b7480f754e) | Streamlit 官方指导如何用 AGENTS.md 指导 AI 编码工具构建应用 |
| HN: "Next.js is infuriating" | [news.ycombinator.com/item?id=45099922](https://news.ycombinator.com/item?id=45099922) | Next.js 抽象层过多，对简单项目来说是过度工程 |
| HN: "The whole NextJS situation is overwhelming" | [news.ycombinator.com/item?id=43672449](https://news.ycombinator.com/item?id=43672449) | Next.js 的复杂性对非专业开发者来说令人不知所措 |
| HN: "I used Gradio and Streamlit extensively" | [news.ycombinator.com/item?id=29588893](https://news.ycombinator.com/item?id=29588893) | 社区共识：Gradio 适合 tiny demo，定制性差；Streamlit 适合更大的应用 |
| HN: "It's not just you, Next.js is getting harder" | [news.ycombinator.com/item?id=40828610](https://news.ycombinator.com/item?id=40828610) | Server/Client component 边界问题是实际开发中的痛点 |
| Builder.io: "Perfect Cursor AI setup for React and Next.js" | [builder.io/blog/cursor-ai-tips-react-nextjs](https://www.builder.io/blog/cursor-ai-tips-react-nextjs) | 证明 Next.js + shadcn/ui 是 Cursor 生态中最被优化的 Web 栈（作为备选的依据） |
| Vibe Coding Tools 对比（NxCode） | [nxcode.io/resources/news/v0-vs-bolt-vs-lovable](https://www.nxcode.io/resources/news/v0-vs-bolt-vs-lovable-ai-app-builder-comparison-2025) | AI 生成的应用是"60-70% 的解决方案"，复杂度越高，后续修复成本越高——支持简单栈优先 |
| Claude Code + Python 环境问题 | [blog.vibe-eval.com/content/posts/uv-python-environment-management](https://blog.vibe-eval.com/content/posts/uv-python-environment-management-2026/) | Python 虚拟环境管理是 AI Agent 的痛点，但 `pip install` 在简单场景下远比 `npm` 的 node_modules 问题少 |
| Cursor 非开发者体验（Cursor 论坛） | [forum.cursor.com/t/an-idiot-s-guide-to-smaller-projects](https://forum.cursor.com/t/an-idiot-s-guide-to-smaller-projects-or-how-i-built-a-site-without-writing-a-single-line-of-code/86689) | 非开发者用 Cursor 从零构建项目时，项目越简单、文件越少，成功率越高 |
| shadcn.io 官方定位 | [shadcn.io](https://www.shadcn.io/) | shadcn/ui 明确定位"AI-Native"，专门为 AI 辅助开发设计——支持其作为备选栈的 UI 优势 |
| Google Mesop vs Streamlit vs Gradio | [news.ycombinator.com/item?id=41249717](https://news.ycombinator.com/item?id=41249717) | Mesop 等新框架生态太小，AI 训练数据不足，生成质量不如 Streamlit |
