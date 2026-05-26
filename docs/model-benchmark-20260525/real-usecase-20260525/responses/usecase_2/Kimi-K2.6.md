现在我已经收集了足够的信息。让我为你整理一份全面的调研报告。

---

# 非开发者 + AI Agent + 黑客松：默认技术栈调研报告

## 一、核心场景约束分析

你的场景有五个关键约束：
1. **用户非开发者** — 不会排错、不懂依赖、不会读报错
2. **工具是 Trae-CN** — 有 SOLO 模式、Builder 模式、Skill 系统
3. **目标可演示** — 必须本地能跑、能展示
4. **多轮修改** — 从 PRD → 原型 → 修改 → 交付，至少 3-5 轮迭代
5. **时间有限** — 黑客松通常 24-48 小时

---

## 二、主要技术路线对比

### 路线 A：纯浏览器 AI App Builder（Lovable / Bolt.new / v0）

| 维度 | Lovable | Bolt.new | v0 |
|------|---------|----------|-----|
| **上手难度** | 极低，纯自然语言 | 低，浏览器内完成 | 中，需理解组件概念 |
| **代码导出** | ❌ 平台锁定 | ⚠️ 可导出但复杂 | ✅ 干净 React 组件 |
| **本地运行** | ❌ 不能 | ❌ 不能（WebContainer） | ✅ 可以 |
| **多轮修改** | 平台内迭代，易用 | Token 消耗极快 | 需开发者接手续写 |
| **调试难度** | 低（平台处理） | 中（错误循环烧 token） | 高（需自己排错） |
| **UI 美观度** | 高 | 中 | 高 |
| **适合非开发者** | ⭐⭐⭐ | ⭐⭐ | ⭐ |

**关键问题**：这些工具**不能本地运行**。黑客松需要现场演示、评委离线查看、或者部署到内网环境时，会卡壳。Lovable 和 Bolt 是"云端黑盒"，导出后非开发者根本跑不起来。

---

### 路线 B：Python + Streamlit / Gradio

| 维度 | Streamlit | Gradio |
|------|-----------|--------|
| **代码量** | 极少 | 极少 |
| **启动命令** | `streamlit run app.py` | `python app.py` |
| **UI 上限** | 中（数据看板强） | 低（AI Demo 强） |
| **AI 生成稳定性** | 高 | 高 |
| **多轮修改** | 极易 | 极易 |
| **部署** | 简单 | 简单 |

**优势**：单文件、无构建步骤、Python 报错相对直观、AI 生成准确率极高。

**劣势**：UI 难做好看（表单感重）、不适合复杂交互、做 Web MVP 有"工具感"而非"产品感"。

**适合**：数据看板、AI 小工具、内部表单。**不适合**：需要精美 UI 的面向用户产品。

---

### 路线 C：React + Next.js + shadcn/ui（v0 / Trae SOLO 默认输出）

| 维度 | 评价 |
|------|------|
| **项目结构** | 复杂（App Router / Pages Router、Server/Client 边界） |
| **依赖数量** | 多（React, Next, Tailwind, shadcn, 各种 utils） |
| **启动命令** | `npm run dev`（需 Node.js 环境） |
| **AI 修改稳定性** | ⚠️ **中低** — 多文件时蝴蝶效应严重 |
| **报错可理解性** | ❌ 差 — RSC 错误、hydration 错误非开发者看不懂 |
| **UI 美观度** | ⭐⭐⭐ 极高 |
| **部署** | Vercel 一键，但本地需环境 |

**关键问题**：
- Next.js 的 **Server/Client 组件边界** 是 AI 最容易搞混的地方
- **Hydration mismatch** 是非开发者的噩梦（页面闪一下、报错看不懂）
- **多轮修改后** 文件膨胀，AI context window 吃紧，"修 A 坏 B" 概率指数上升
- 需要 Node.js + npm 环境，非开发者安装就是第一道坎

---

### 路线 D：React + Vite SPA + Tailwind（单页应用，无 SSR）

| 维度 | 评价 |
|------|------|
| **项目结构** | 简单（src/App.jsx, index.html, vite.config.js） |
| **依赖数量** | 少（React, Vite, Tailwind） |
| **启动命令** | `npm run dev` |
| **AI 修改稳定性** | ⭐⭐⭐ **高** — 全客户端，无 SSR 边界问题 |
| **报错可理解性** | 中 — 浏览器控制台可见 |
| **UI 美观度** | 高（Tailwind + 组件库） |
| **构建输出** | 纯静态文件（dist/），任意 CDN/本地打开 |

**相比 Next.js 的核心优势**：
- 没有 Server Component / Client Component 的"隐形边界"
- AI 生成的代码**全部在浏览器运行**，不会出现 hydration 错误
- 构建产物是纯 HTML/CSS/JS，可以**直接双击打开**（或用 `npx serve dist`）
- 文件少，AI context window 压力小

---

### 路线 E：单文件 HTML + Tailwind CDN + Vanilla JS

| 维度 | 评价 |
|------|------|
| **文件数量** | 1 个 .html |
| **构建步骤** | 无 |
| **启动方式** | 双击打开，或用 `npx serve` |
| **AI 修改稳定性** | ⭐⭐⭐ **极高** — 全文可见，无跨文件依赖 |
| **调试难度** | 极低 — 浏览器 F12 直接看 |
| **UI 美观度** | 中（Tailwind 够用） |
| **功能上限** | 低（适合展示型、简单交互） |

**优势**：AI 处理单文件时**几乎不会出错**，非开发者能完全理解"这是一个文件"。

**劣势**：代码超过 500 行后难以维护、不好做路由、状态管理靠原生 JS。

---

## 三、Trae SOLO 模式的实际行为

根据调研，Trae 2.0 SOLO 模式的实际 workflow 是：

1. **输入自然语言需求** → AI 生成 PRD（Markdown）
2. **AI 自动设计架构** → 选择技术栈（默认倾向 Next.js + shadcn）
3. **AI 写代码** → 自动安装依赖、配置项目
4. **自动部署** → 推送到 Vercel 等平台

**对非开发者的隐患**：
- SOLO 默认输出 **Next.js + shadcn/ui**，这是"专业开发者栈"
- 生成的 PRD 和架构非开发者**无法验证合理性**
- 如果自动部署失败，非开发者**无法本地调试**
- 多轮修改时，SOLO 的"全自主"会变成"全黑盒"——用户不知道 AI 改了什么

---

## 四、关键洞察：哪些路线"看似简单，多轮后变难"

| 路线 | 初期体验 | 3-5 轮后 | 原因 |
|------|---------|---------|------|
| **Lovable / Bolt** | 极简单 | ❌ **死胡同** | 平台锁定，无法本地运行，导出后非开发者跑不起来 |
| **Next.js + shadcn** | UI 极好看 | ❌ **噩梦** | RSC/hydration 错误、依赖冲突、AI 上下文爆炸 |
| **Vite SPA** | 简单 | ✅ **可持续** | 结构简单，无 SSR 陷阱 |
| **单文件 HTML** | 最简单 | ⚠️ **代码膨胀** | 适合 < 500 行，超量后难以维护 |
| **Streamlit** | 简单 | ✅ **稳定** | 但 UI 天花板低，有"工具感" |

---

## 五、推荐结论

### 默认技术栈（置信度：高）

```
React + Vite + Tailwind CSS + shadcn/ui 组件（按需）
```

**具体配置**：
- **Vite**（而非 Next.js）— 纯客户端 SPA，无 SSR 复杂度
- **Tailwind CSS** — AI 生成类名最稳定的 CSS 方案
- **shadcn/ui** — 通过 `npx shadcn add <component>` 按需添加，不绑架项目
- **React Router**（如需多页面）— 客户端路由，无服务端配置
- **构建输出**：`dist/` 文件夹，纯静态文件

**为什么不是 Next.js**：
> "80% 的 AI 生成 Next.js 项目使用了零 SSR、零 API Routes、零 ISR——你在为不用的功能支付复杂度税。" —— Vibe Coder Blog

**为什么不是纯 HTML**：
单文件在 200 行以内是王者，但黑客松 MVP 通常需要路由、状态管理、组件复用，纯 HTML 会迅速膨胀到不可维护。

**为什么不是 Streamlit**：
如果目标是一个"产品感"的 Web MVP（如内部工具、数据看板、AI 小工具），Streamlit 的 UI 天花板太低，评委/用户会感觉到"这是一个脚本"而非"一个产品"。

---

### 触发条件下切换的备选技术栈

| 条件 | 切换至 |
|------|--------|
| 项目是纯数据看板 / 表单 / AI Demo | **Streamlit** |
| 项目 < 200 行代码且无需路由 | **单文件 HTML + Tailwind CDN** |
| 需要后端数据库 / 认证 | **Supabase + Vite SPA**（而非 Next.js 全栈） |
| 团队有前端开发者参与 | **Next.js + shadcn**（此时有人能排错） |
| 需要 SEO / 服务端渲染 | **Next.js**（但黑客松 MVP 几乎不需要） |

---

### 能推翻推荐的证据或条件

1. **Trae SOLO 模式强制使用 Next.js** — 如果 SOLO 不支持自定义模板，只能接受其默认输出
2. **项目明确需要服务端渲染**（如 SEO、首屏速度）— 此时必须用 Next.js 或类似框架
3. **团队有专业前端开发者** — 可以驾驭 Next.js 的复杂度
4. **演示环境有稳定外网** — 可考虑 Lovable/Bolt 的云端部署，但离线演示时仍卡壳
5. **Vite 构建在特定企业内网环境出问题** — 此时回退到单文件 HTML

---

## 六、给黑客松组织者的建议

1. **预装环境**：提供预装好 Node.js + Vite 模板的开发机或容器
2. **提供 starter template**：一个配置好的 `vite + react + tailwind + shadcn` 模板，含示例页面
3. **禁止 AI 自动安装未知依赖** — 非开发者会因此引入版本冲突
4. **要求"可双击运行"的备份方案** — 即使构建失败，也要有一个 `index.html` 能展示
5. **培训 30 分钟**：教非开发者看懂浏览器 F12 控制台报错（这是最重要的调试技能）

---

## 七、参考来源

| 来源 | 支持判断 |
|------|---------|
| [Vibe Coder Blog: Vite vs Next.js](https://blog.vibecoder.me/vite-vs-nextjs-when-you-dont-need-framework) | Vite 更简单，Next.js 对无 SSR 需求是过度设计 |
| [Index.dev: v0 vs Bolt vs Lovable](https://www.index.dev/blog/v0-vs-bolt-ai-app-builder-review) | Bolt 的 token 消耗和错误循环问题；v0 前端-only 限制 |
| [NxCode: v0 vs Bolt vs Lovable 2026](https://www.nxcode.io/resources/news/v0-vs-bolt-vs-lovable-ai-app-builder-comparison-2025) | Lovable 最易用但平台锁定；Bolt 上下文退化；v0 需开发者接手续写 |
| [Smiansh: AI Coding Agents Struggles](https://www.smiansh.com/blogs/the-real-struggle-with-ai-coding-agents-and-how-to-overcome-it/) | 多轮修改的蝴蝶效应、非开发者调试噩梦 |
| [VentureBeat: Why AI Agents Aren't Production-Ready](https://venturebeat.com/ai/why-ai-coding-agents-arent-production-ready-brittle-context-windows-broken) | 上下文窗口限制、多文件重构失败、幻觉循环 |
| [Skywork: Trae vs Cursor 2025](https://skywork.ai/skypage/en/Trae-vs.-Cursor-My-2025-Deep-Dive-into-the-AI-Coding-Revolution/1973805651026702336) | Trae SOLO 模式的全自主 workflow，但默认输出 Next.js |
| [Oreate AI: Trae 2.0 SOLO Review](https://www.oreateai.com/blog/indepth-review-of-trae-20s-new-solo-mode-a-breakthrough-evolution-in-ai-fullprocess-development-paradigms/b7b78aa0c9349e620de56729b7ea5309) | SOLO 自动生成 PRD、架构、代码、部署 |
| [Reddit r/vibecoding: Non-dev tips](https://www.reddit.com/r/vibecoding/comments/1si245p/to_nondev_vibecoders_your_code_needs_upkeep_your/) | 非开发者需要维护代码、管理上下文 |
| [Reddit r/vibecoding: Success stories](https://www.reddit.com/r/vibecoding/comments/1spxxbw/so_where_are_the_success_stories_of_vibe_coding/) | 成功案例少，维护是核心问题 |
| [The AI Corner: AI Coding Tools 2026 Guide](https://www.the-ai-corner.com/p/ai-coding-tools-complete-guide-2026) | AI App Builders 适合零编码，但有平台锁定风险 |

---

**最终推荐**：**React + Vite + Tailwind + shadcn/ui（按需）**

这是"非开发者在 AI Agent 帮助下能稳定做出来、能继续改、能排错、能演示"的最优平衡点。它避开了 Next.js 的 SSR 陷阱、避开了平台锁定工具的离线风险、又比纯 HTML 有更高的 UI 天花板和可维护性。
