下面是我的调研结论，按你要的结构来。

---

# 一、TL;DR — 默认栈 + 备选栈（不平均主义版）

**默认主栈（覆盖 70%+ 场景）：Next.js (App Router, TypeScript) + Tailwind CSS + shadcn/ui + SQLite (better-sqlite3) + Server Actions / Route Handlers，单仓库 npm run dev 启动。**

**备选栈 1（数据看板 / AI 小工具 / 偏 Python 数据处理）：Streamlit（单文件 Python，多页用 `pages/`） + SQLite + 官方 streamlit/agent-skills。**

**备选栈 2（极轻表单流程 / 静态原型，不需要后端逻辑）：Vite + React + Tailwind + shadcn/ui，LocalStorage 持久化。**

不推荐作为默认：纯 HTML/CSS/JS、Flask + Jinja、Django、SvelteKit、SolidStart、Remix（理由见第四节）。

置信度：**高**（对默认栈和 Streamlit 备选的判断），**中**（对 Vite 备选的边界判断）。

---

# 二、判断框架：非开发者 + AI Agent 黑客松，到底卡在哪

非开发者用 AI Agent 写代码，**真正的失败模式不是"第一次跑不起来"，而是这五件事**：

1. **第 3~5 轮修改后崩溃**：Agent 改了一半 import、漏了 schema migration、配置散落多处，非开发者无法人肉合拢。
2. **依赖装不上**：Python venv、Node 版本、原生编译、网络代理。Mac/Win 差异。
3. **报错读不懂**：栈帧太深、TypeScript 泛型噪音、CSS-in-JS 报错图灵补全级。
4. **UI 难看 / 难调**：非开发者最在意"演示像不像产品"，CSS 自由度过高 = 灾难。
5. **演示前 30 分钟启动失败**：环境变量没设、端口冲突、build 失败、CDN 拉不到。

**所以技术栈的评估维度应该是：**

| 维度 | 权重 | 说明 |
|---|---|---|
| Agent 可读性（AGENTS.md/官方 skills） | ★★★★★ | Agent 能不能一次写对、能不能自动定位错误 |
| 项目结构线性度 | ★★★★★ | 文件少、约定多、没有"在 5 个地方都能改的同一件事" |
| UI 默认就好看 | ★★★★ | 决定演示 demo 的"像不像产品" |
| 启动命令简单 | ★★★★ | `npm run dev` / `streamlit run app.py` 一条命令 |
| 错误信息可读 | ★★★ | 报错能直接喂回 Agent 让它修 |
| 依赖稳定性 | ★★★ | 本地 `npm install` / `pip install` 不爆 |
| 多轮修改抗性 | ★★★★★ | 改 10 次以后还能继续改 |
| 本地可演示 | ★★★ | 不依赖外网部署 |

---

# 三、为什么默认推荐 Next.js + Tailwind + shadcn/ui + SQLite

## 3.1 Agent 可读性是目前最强的（决定性证据）

- Vercel 官方在 **AGENTS.md 评测**中报告：给 Next.js 仓库放一个 AGENTS.md 后，Agent 在他们 evals 上**100% pass**，比 skill-based 还高（Vercel 自己的发现）。([Vercel: AGENTS.md outperforms skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)、[Next.js Agentic Future](https://nextjs.org/blog/agentic-future))
- Cursor、Claude Code、Copilot 都默认读 AGENTS.md；Next.js 是目前**Agent 生态最厚的 Web 框架**，连 Next.js 16.2 都把 `/next-browser` 这种 Agent 浏览器调试做进官方流程。([Next.js 16.2: AI Improvements](https://nextjs.org/blog/next-16-2-ai))
- 直接判断：**Agent 写错的概率最低、自动修复的能力最强的 Web 框架，目前就是 Next.js**。

## 3.2 shadcn/ui 是非开发者拿到"像样 UI"的最短路径

- shadcn/ui 不是 npm 黑盒包，是把组件源码**直接 copy 进项目**——这恰好是 AI Agent 最会处理的形态：可以读、可以改、可以重命名，不会"包升级把样式打飞"。([shadcn/ui AI-native](https://www.shadcn.io/))
- v0 / Lovable / Bolt 生成的产物默认就是 shadcn/ui + Tailwind，整个生态对齐到这一组件库。([LayoutPrompts: Vibe Coding Tools Compared](https://layoutprompts.com/blog/vibe-coding-tools-compared))
- Tailwind 的"原子类"设计意外地对 Agent 极友好：每条样式独立、可局部替换，不像 CSS Modules / styled-components 那样需要跨文件编排。

## 3.3 项目结构线性度

- App Router 的"约定优于配置"：`app/<route>/page.tsx`、`app/<route>/route.ts`，**Agent 创建一条新功能只要新建一个目录**，不需要去注册路由、改 `_app.tsx`、改 `pages.json`。
- Server Actions 让"前端按钮触发后端逻辑"写在同一个文件里，**非开发者不需要理解前后端分离**——这一条直接把 React + Express、React + FastAPI 两类组合的复杂度抹掉了。

## 3.4 SQLite 而不是 Postgres

- 单文件、零安装、不需要 Docker、不需要密码。([SQLite Is the Best Database for AI Agents](https://dev.to/nathanhamlett/sqlite-is-the-best-database-for-ai-agents-and-youre-overcomplicating-it-1a5g))
- Mac 上原生支持，better-sqlite3 同步 API 让 Agent 写出来的代码不容易因为 async 错而卡住。
- 演示场景永远 < 1k QPS，不需要 Postgres 的复杂度。

## 3.5 风险清单（默认栈也不是没坑）

- **Server Actions + Client Components 边界**：Agent 偶尔会把 `"use client"` 漏了或加错位置——但报错信息很明确，能让 Agent 自动修。
- **TypeScript 泛型报错**：偶尔会产生一段非开发者看不懂的红色噪音。**对策：在 AGENTS.md 里写一行"优先用 `any` 或简单类型，不要追求严格泛型"**。
- **next dev 偶尔卡缓存**：标准解法 `rm -rf .next` 写进 README 即可。

---

# 四、备选栈与触发条件

## 4.1 备选栈 1：Streamlit（**强烈推荐用于"数据看板 / 内部 AI 小工具"**）

**触发条件（满足任一即切换）：**
- 项目主线是"上传 CSV → 处理 → 出图表"
- 项目主线是"调一个 Python 模型 / API → 给个交互界面"
- 用户已经有 Python 脚本，要"包一层 UI"
- 不需要复杂多页路由、不需要鉴权

**为什么是它：**
- 官方有 `streamlit/agent-skills` 仓库 + AGENTS.md 范本，Streamlit 团队**主动**在让 Agent 更会写 Streamlit。([Streamlit blog: Vibe code with AGENTS.md](https://blog.streamlit.io/vibe-code-streamlit-apps-with-ai-using-agents-md-04b7480f754e)、[streamlit/agent-skills](https://github.com/streamlit/agent-skills))
- 一个 `app.py` 文件就能跑出可演示的看板。**没有前后端，没有路由，没有 build。**
- 错误信息**直接打在网页上**，非开发者复制粘贴就能给 Agent 修。
- `pip install streamlit` 一行依赖。

**风险：**
- 多用户、自定义路由、登录逻辑、复杂表单交互——Streamlit 会越改越拧巴。([Sider.ai: Gradio Alternatives](https://sider.ai/blog/ai-tools/gradio-alternatives-that-don-t-make-you-gradio-sly-angry-the-hands-on-guide))
- 不要用 Streamlit 做"长得像产品"的 SaaS Demo，不像。

## 4.2 备选栈 2：Vite + React + Tailwind + shadcn/ui（轻原型）

**触发条件：**
- 不需要后端 / 后端只是一个外部 API
- 纯前端可视化、纯表单、纯静态原型
- 演示场景就是浏览器一开就完事

**优点：** 启动比 Next.js 还快，Agent 改起来心智更直接（没有 server / client 边界）。
**何时不要选：** 一旦要"存数据"或"调一个需要密钥的 API"，必须切回 Next.js 或 Streamlit。

---

# 五、看似简单、改几轮就变难的路线（避雷）

| 路线 | 第一印象 | 第 N 轮后的真实成本 |
|---|---|---|
| **纯 HTML/CSS/JS + 一个 index.html** | "最简单" | UI 难看，没组件库；任何状态管理都会让 Agent 把 vanilla JS 写成意大利面。**强烈不推荐**。 |
| **Flask + Jinja 模板** | "Python 全栈最短路径" | Jinja 语法 + JS + CSS 混在一个文件，Agent 容易写串；UI 风格全靠手搓。 |
| **Django** | "全家桶很安心" | 对非开发者是地狱：app/migrations/settings/admin 四处分散，迁移命令链条长，第一轮就劝退。 |
| **Gradio** | "AI demo 一键起" | 表单类还行，但**自定义布局、登录、多页全部是反模式**，改两轮就拧死。([Markaicode: Streamlit vs Gradio](https://markaicode.com/vs/streamlit-vs-gradio-in/)) |
| **SvelteKit / SolidStart / Remix** | "更现代" | Agent 训练数据少于 Next.js，错误率高，社区 AGENTS.md 不成熟。([Reddit r/reactjs: Remix/Next vs Vite for AI agent](https://www.reddit.com/r/reactjs/comments/1iyolnd/remixnextjs_or_vite_for_a_web_ai_coding_agent/)) |
| **v0 / Lovable / Bolt 在线生成 → 导出本地** | "vibe coding 神器" | 有人统计 May 2025 在线 vibe coding 项目里 170/n 在导出后即跑不起来；导出后的代码结构对持续修改不友好。([buildwithlovable / vibecoding.app rankings](https://vibecoding.app/blog/best-vibe-coding-tools))。**可以用作"先出原型再喂给 Cursor 接管"，但不要作为主栈。** |
| **Postgres + Docker** | "正式" | 黑客松早上 9 点 docker desktop 没启 = 全员 30 分钟黑屏。**留给上线后再迁移。** |

---

# 六、决策树（给非开发者 + Agent 套件用的）

```
项目主线是不是"数据 / 模型 / Python 脚本 + 一个 UI"？
├─ 是 → Streamlit（主栈是它）
└─ 否 →
   需不需要存数据 / 调带密钥的服务？
   ├─ 不需要 → Vite + React + Tailwind + shadcn/ui
   └─ 需要 → Next.js (App Router, TS) + Tailwind + shadcn/ui + SQLite （默认主栈）
```

把这个决策树塞进黑客松发的"启动包"里，让非开发者照着选，不要让 AI Agent 自己选——Agent 选栈的口味偏好不稳定。

---

# 七、配套约定（必须随默认栈一起发，否则推荐打折一半）

1. **每个仓库根放 AGENTS.md**：写明栈版本、启动命令、约束（"不要引入 ORM"、"UI 一律用 shadcn/ui"、"不要拆前后端"）。Vercel evals 证明这一招能把 Agent 通过率拉到 100%。
2. **锁版本 + 给 Agent 一个 `package.json` / `requirements.txt`** 起步模板。不要让 Agent 自由选包。
3. **`make demo` / `npm run demo`** 一条命令完成 install + db init + dev server。
4. **统一在 README 顶部写"演示前 5 分钟自检清单"**：端口、env、db file 三件事。

---

# 八、置信度与可被推翻的条件

**默认主栈（Next.js + shadcn/ui + SQLite）置信度：高**

会推翻这个推荐的证据/条件：
- 你们参赛者大部分是数据科学背景、写过 Python，**没碰过 JS/TS** —— 这种情况 Streamlit 升为默认。
- 黑客松规则要求作品**必须是单文件 / 必须 30 行内可读** —— 切 Streamlit。
- 公司内网无法装 npm 包 / Node —— 切 Streamlit + 内部 PyPI 镜像。
- Trae-CN 内置 skill 对某个特定栈（比如 Vue + Element Plus）做了深度优化，已经超过 Next.js 的 AGENTS.md 通用收益 —— 这条**需要你查 Trae-CN 内部数据**才能推翻；如果有，按内部数据走。

**Streamlit 备选置信度：高**（场景一旦匹配，几乎无替代）

**Vite 备选置信度：中**（边界容易越界，越界后非开发者会卡）

---

# 九、参考资料（按支持的判断分组）

**支持"Next.js 是 Agent 友好度最高的 Web 框架"：**
- [Vercel: AGENTS.md outperforms skills in our agent evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) — 100% pass rate 的核心数据来源
- [Next.js: AI Coding Agents 指南](https://nextjs.org/docs/app/guides/ai-agents) — 官方对 Cursor/Claude/Copilot 的兼容路径
- [Next.js 16.2: AI Improvements](https://nextjs.org/blog/next-16-2-ai) — `/next-browser` 等 Agent-first 功能
- [Building Next.js for an agentic future](https://nextjs.org/blog/agentic-future) — Vercel 把 Agent 当一等公民的策略
- [vercel-labs/agent-skills: react-best-practices](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/AGENTS.md) — 给 Agent 用的 40+ React 规则

**支持"shadcn/ui + Tailwind 是 Agent 默认组件栈"：**
- [shadcn/ui AI-native 介绍](https://www.shadcn.io/) — copy-source-into-repo 模型
- [LayoutPrompts: v0/Bolt/Cursor/Lovable 同 prompt 对比](https://layoutprompts.com/blog/vibe-coding-tools-compared) — 全部产出 shadcn/ui + Tailwind
- [Builder.io: The Perfect Cursor AI setup for React/Next.js](https://www.builder.io/blog/cursor-ai-tips-react-nextjs) — Cursor + Next.js 的实操经验

**支持"Streamlit 是非开发者数据看板/AI 工具最佳"：**
- [Streamlit blog: Vibe code Streamlit apps with AGENTS.md](https://blog.streamlit.io/vibe-code-streamlit-apps-with-ai-using-agents-md-04b7480f754e) — 官方主动适配 Agent
- [streamlit/agent-skills GitHub](https://github.com/streamlit/agent-skills) — Streamlit 官方 skill 集合
- [Markaicode: Streamlit vs Gradio in 2026](https://markaicode.com/vs/streamlit-vs-gradio-in/) — 对比下 Streamlit 的多页/状态优势
- [Squadbase: Streamlit vs Gradio 2025](https://www.squadbase.dev/en/blog/streamlit-vs-gradio-in-2025-a-framework-comparison-for-ai-apps) — 自定义 UI 与运维健壮性的对比

**支持"vibe coding 多轮后会爆炸 / 需要约束"：**
- [Graphite: Limitations of vibe coding](https://graphite.com/guides/limitations-of-vibe-coding)
- [Glide: Top 5 problems with vibe coding](https://www.glideapps.com/blog/vibe-coding-risks)
- [thothbaboon: The Hard Limits of Vibe Coding](https://thothbaboon.github.io/blog/the-hard-limits-of-vibe-coding/) — 真实代码库 Agent 性能下降的观察
- [Softwaremind: Rise and Risk of Vibe Coding](https://softwaremind.com/blog/the-rise-and-risk-of-vibe-coding-whats-worth-knowing/) — 多个 vibe-coded MVP 后期不可维护的案例

**支持"SQLite 优于 Postgres 用于本地 Agent 项目"：**
- [SQLite Is the Best Database for AI Agents (DEV)](https://dev.to/nathanhamlett/sqlite-is-the-best-database-for-ai-agents-and-youre-overcomplicating-it-1a5g) — 实战经验
- [Local-first RAG with SQLite (PingCAP/OpenClaw)](https://www.pingcap.com/blog/local-first-rag-using-sqlite-ai-agent-memory-openclaw/) — "Zero-Ops" 论点

**支持"v0 / Lovable / Bolt 适合先出原型，不适合作为主栈"：**
- [vibecoding.app: Best Vibe Coding Tools 2026 Ranked](https://vibecoding.app/blog/best-vibe-coding-tools) — graduate workflow（先 Lovable/Bolt，再 Cursor 接管）
- [Anna Arteeva: Choosing your AI prototyping stack](https://annaarteeva.medium.com/choosing-your-ai-prototyping-stack-lovable-v0-bolt-replit-cursor-magic-patterns-compared-9a5194f163e9) — 各工具能力边界
- [TAIKAI: 5 AI Vibe Coding Tools for Hackathons](https://taikai.network/en/blog/5-ai-vibe-coding-tools-for-hackathons) — 黑客松场景的工具组合建议

**支持"Vite 适合纯前端原型边界"：**
- [Reddit r/reactjs: Remix/Next.js or Vite for AI coding agent?](https://www.reddit.com/r/reactjs/comments/1iyolnd/remixnextjs_or_vite_for_a_web_ai_coding_agent/) — 社区对 Agent 友好度的实战讨论
- [Strapi: Vite vs Next.js 2025](https://strapi.io/blog/vite-vs-nextjs-2025-developer-framework-comparison) — 边界对比
- [DesignRevision: Vite vs Next.js 2026](https://designrevision.com/blog/vite-vs-nextjs)

---

# 十、给你（赛事组织方）的一句话落地建议

发一个**起步包仓库**，里面只有两个分支：`starter-nextjs` 和 `starter-streamlit`，每个分支根目录有：
1. `AGENTS.md`（写死栈、UI、DB、命令约束）
2. 一行能跑的 demo（"待办列表"或"上传 CSV 出图"）
3. `make demo` / `npm run demo` / `streamlit run app.py`
4. README 顶部"演示前 5 分钟自检清单"

参赛者只需选一个分支 fork，剩下的交给 Trae-CN + Agent。这样你就把"非开发者用 AI 做不出来"的失败模式从概率事件压成了小概率事件。
