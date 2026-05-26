下面是我基于官方文档、官方 starter/template、以及官方平台实践做出的研究结论。先给结论，再给证据。

## 总结结论

如果目标是“非开发者 + AI coding agent + 黑客松交付”的 Web MVP/内部工具，我的默认推荐不是单看某个框架，而是按“前端壳 + UI + 数据层”来选：

### 结论排序

#### 1）最推荐默认栈
**React + Vite + Tailwind + shadcn/ui + Supabase（云）**

这是我认为最适合大多数“非开发者 + AI agent + 黑客松”场景的默认栈。

为什么排第一：
- 本地启动最轻，Vite 官方起步和模板非常直接，HMR 快，结构简单。
- UI 出效果最快，Tailwind + shadcn/ui 的组合几乎是现在“最快做出像样产品界面”的标准做法。
- Supabase 把 Auth / Database / Storage 一次性补齐，能让 AI agent 少自己搭后端。
- 对 AI agent 来说，React+Vite 的项目结构通常比 Next.js 更可预测，改错范围更小。

适用：
- 内部工具
- 账号体系不复杂的 Web MVP
- 黑客松 demo
- 希望先把前台页面和基础数据闭环做出来

不适用：
- 一开始就强依赖 SSR / Server Components / App Router / SEO
- 想把“服务端逻辑、鉴权、页面、部署”全压到一个框架里统一做

---

#### 2）次推荐默认栈
**Next.js + Tailwind + shadcn/ui + Supabase**

这是“更偏准产品化”的默认栈，不是“最轻最稳”的默认栈。

为什么排第二：
- Next.js 官方 starter/template 和 Vercel 模板生态极强，适合黑客松快速拼装。
- create-next-app 官方默认模板已经把 **TypeScript、ESLint、Tailwind CSS、App Router、AGENTS.md** 放进推荐路径里，这对 AI agent 很友好。
- Supabase 官方对 Next.js 的 SSR/Auth 集成支持更完整。

但它没排第一，因为：
- Next.js 的官方文档本身就暴露出更多开发期复杂度：Turbopack/webpack 切换、barrel files、图标大包、Tailwind 扫描范围、Docker 开发变慢、tracing 排障等。
- create-next-app 的可选项非常多，意味着“不是所有 Next 项目长得都一样”，AI agent 对现有项目做改动时，结构稳定性不如 React+Vite。

适用：
- 希望黑客松后继续往产品化推进
- 需要登录态、服务端渲染、Route Handlers、Server Actions
- 希望直接吃 Vercel/Next 的模板红利

不适用：
- 团队里没人能兜 Next.js 的框架复杂度
- 只是做一个简单内网工具或 CRUD 面板

---

#### 3）强备选：数据/分析/后台工具场景
**Streamlit**

它不是“通用 Web MVP 默认栈”，但在特定场景里极强。

为什么能排第三：
- 本地启动极快，官方就是 `streamlit run your_script.py`。
- 官方 Community Cloud 支持 **从 template 直接 fork + deploy**，甚至可以不配本地环境，走 GitHub Codespaces。
- 对“分析看板、数据探索、模型演示、内部运营工具”这类场景，非常适合黑客松交付。

为什么不是默认第一：
- 官方文档对“复杂前端结构、长期 Web 工程化、环境建模、开发/生产差异”讲得远不如 React/Next 清晰。
- 更适合“Python 脚本变网页”，不太适合“做成产品味很强的现代 Web 应用”。

适用：
- 数据分析工具
- 模型 demo
- 运营/分析内网工具
- Python-first 团队

不适用：
- 需要精细交互、复杂前端状态管理、强品牌化 UI

---

#### 4）本地离线/单机演示默认栈
**React + Vite + Tailwind + shadcn/ui + SQLite + Prisma**

如果你明确要求：
- 本地全跑
- 不依赖云
- 单人/单机 demo
- 黑客松现场网络不稳定

这是我会给的“本地优先默认栈”。

为什么：
- SQLite 官方的核心卖点就是 **serverless / zero-configuration / no setup / no server process**。
- Prisma 的 SQLite quickstart 明确把 SQLite 定义为适合开发、原型和小应用。
- Prisma 的 `schema.prisma -> migrate dev -> generate` 流程对 AI agent 比较清晰。

为什么它不排更前：
- 一旦不是纯本地 demo，而是多人协作/登录/文件存储/后续线上化，它会很快碰到边界。
- Prisma 官方 quickstart 本身也暴露出不少额外步骤：adapter、ESM、Node/Bun 差异、Studio 限制等。

适用：
- 离线 demo
- 单机内部工具
- 黑客松现场本地展示
- 需要最小运维负担

不适用：
- 多用户协作
- 在线文件/对象存储
- 需要很快转成线上产品

---

#### 5）仅在 Python/ML 后端明确成立时采用
**FastAPI + 前端（通常 React/Vite）**

FastAPI 很好，但它不是“非开发者 Web MVP”的默认前台栈。

为什么：
- 官方 first steps 非常清晰：`fastapi dev`、自动 `/docs`、`/redoc`、`/openapi.json`，对 API 开发很友好。
- 但它提供的是 API 服务，不是现成业务界面。
- 官方部署文档清楚展示了后续运维复杂度：TLS termination proxy、进程托管、自动重启、多 worker、内存复制、容器编排、启动前任务。

适用：
- Python/ML/数据处理是核心
- 要做可扩展 API
- 你愿意前后端分离

不适用：
- 非开发者想尽快做出“像产品”的网页界面

---

#### 6）不建议作为默认栈
**Firebase（尤其本地 Emulator 驱动开发）**

Firebase 不是差，而是**不适合当默认**。

为什么不推荐默认：
- 官方 Emulator Suite 安装配置页直接暴露出环境复杂度：**Node + Java + Firebase CLI + 多模拟器端口 + project ID 对齐 + Rules 配置**。
- 文档明确提醒：
  - 多 project ID 会出问题
  - 不配 Rules 会变成 “open data security”
  - `--inspect-functions` 会进入 serialized execution mode，和云上行为不一致
  - 导入数据会覆盖内存里的现有数据

也就是说，Firebase 更像一个成熟平台栈，而不是“非开发者 + AI agent + 黑客松”下的最省心默认。

适用：
- 你已经在 Google/Firebase 生态里
- 强依赖移动端、Cloud Functions、Firebase Hosting、Analytics/Push
- 团队能处理规则与本地模拟器复杂度

不适用：
- 想低心智负担快速交付 Web MVP

---

## 分项结论

## 一、前端框架：React + Vite vs Next.js

### 我会怎么选
- **默认选 React + Vite**
- **需要准产品化/SSR/官方模板红利时选 Next.js**

### 为什么默认选 React + Vite
关键证据：
- Vite 官方 getting started 非常直接：`npm create vite@latest`
- 官方模板标准化，React/React-TS 都是第一层支持
- 官方强调 “sensible defaults” 和 “extremely fast HMR”
- 默认入口清晰：`index.html` + `src/...` + `vite.config.*`

这对 AI agent 很重要：
- 入口少，结构浅
- 改动局部组件时，更容易定位影响范围
- 调试路径短，自动修复更容易闭环

### 为什么 Next.js 不做第一默认
Next.js 的优势很强：
- create-next-app 官方默认模板很完整
- Vercel 官方模板生态极丰富，覆盖 AI、docs、blog、commerce、SaaS、portfolio、多租户等
- 对黑客松“从模板起步”非常有利

但官方文档也直接暴露复杂度：
- Turbopack 是默认 bundler，但还保留 `--webpack`
- 文档专门提示：
  - barrel files 会拖慢开发
  - 大图标包导入会把成千上万模块拖进来
  - Tailwind content 扫描范围过宽会拖慢
  - Docker 在 Mac/Windows 上本地开发更慢
  - 自定义 webpack 配置会增加复杂度
  - 需要 tracing 才能定位性能问题

这说明 Next.js 更像“功能很强、上线更顺，但工程摩擦更高”的栈。

---

## 二、UI 层：Tailwind + shadcn/ui 是现在最合适的默认组合

### Tailwind 为什么该默认
官方安装路径已经足够短：
- Next.js 指南里就是安装依赖、加 PostCSS、在 `globals.css` 里 `@import "tailwindcss";`
- 这是典型“上手快、改样式快、AI 生成 class 很稳”的路线

适合 AI agent 的原因：
- class-based 改动原子化
- 不必跨很多 CSS 文件猜 cascade
- 局部修改更容易验证

### shadcn/ui 为什么该默认
这是这次调研里最明确“对 AI agent 友好”的 UI 方案之一。

官方介绍页直接给出的信号：
- “Works with your favorite frameworks and AI models.”
- “Open Source. Open Code.”
- “AI-Ready”
- “Beautiful Defaults”

它比传统 npm 组件库更适合 AI agent 的原因：
- 不是黑盒组件，而是把代码分发进项目
- 组件代码在你自己的仓库里，AI 改起来更直接
- 样式、结构、交互逻辑都可读、可改、可复用

### 但 shadcn/ui 也有复杂度
官方安装页本身就暴露出：
- 要先选框架（Next/Vite/React Router/Astro/TanStack Start/Laravel）
- 有 CLI、manual、registry、components.json、blocks、charts、themes 等多层概念
- 功能强，但认知成本比“装一个现成 UI 库”更高

结论：
- **默认 UI 组合就是 Tailwind + shadcn/ui**
- 但最好搭配更简单的壳（React+Vite 或 Next 官方默认模板），不要再叠加太多自定义工程层

---

## 三、数据层：Supabase vs SQLite/Prisma vs SQLite/Drizzle vs Firebase

### 1）默认云数据层：Supabase
我更推荐它作为默认云后端。

原因：
- 官方对 **Next.js** 和 **React** 都有专门教程
- React 教程路径很短：Vite -> 安装 `@supabase/supabase-js` -> 配 `.env.local` -> `createClient`
- Next.js 教程已经把 SSR/Auth/Cookie/路由结构讲清楚

这说明 Supabase 的“官方支持路径”非常明确，适合 AI agent 按官方惯例继续改。

但要注意一个大坑：
- **Supabase 本地开发不是轻量的**
- 官方 local development 直接要求 **Docker-compatible runtime**
- 首次运行要下载镜像
- 文档明确提醒不要把本地开发栈暴露到公网；连不可信网络时要额外做 Docker 网络和 `127.0.0.1` 绑定

所以我的结论是：
- **默认用 Supabase 云服务**
- **不要默认把“Supabase 本地全家桶”当作黑客松本地环境**

### 2）默认本地数据库：SQLite + Prisma
如果要完全本地跑，我会选 Prisma 而不是 Drizzle 当默认。

为什么 Prisma 更适合默认：
- 官方 quickstart 很明确：SQLite 是 file-based，适合 development / prototyping / small apps
- 数据模型集中在 `schema.prisma`
- 变更路径固定：
  - 改 schema
  - `prisma migrate dev`
  - `prisma generate`

这对 AI agent 很关键：流程标准、入口固定、出错路径相对可预测。

但官方文档也暴露坑点：
- 需要 adapter（Node/Bun 方案不同）
- 需要 ESM 配置
- Prisma Studio 有协议和运行时限制
- 示例甚至自定义了 generated client 输出路径

也就是说：
- **Prisma 是本地 SQLite 默认 ORM**
- 但它不是“完全零认知负担”

### 3）Drizzle 是高级备选，不是默认
Drizzle 官方 SQLite 文档一眼就能看出它更灵活，也更容易分叉：
- `libsql`
- `node:sqlite`
- `better-sqlite3`

这些选择本身就意味着：
- 工程路径不唯一
- 迁移、driver、远程/本地能力会因选型不同而变化
- AI agent 对一个陌生 Drizzle 项目做修改时，需要先识别具体 driver 和迁移方式

所以我的判断：
- **默认不要选 Drizzle**
- **如果团队偏资深、重视 SQL/TS 原生掌控感，再选 Drizzle**

### 4）Firebase 不适合默认
Firebase 的问题不是能力不够，而是“本地与规则复杂度太早暴露”。

官方 Emulator 文档暴露的坑非常多：
- 需要 Node、Java、Firebase CLI
- 端口很多
- project ID 必须对齐
- 不配 Rules 会变成开放数据安全
- functions 调试模式与线上并发行为不一致
- import 会覆盖内存数据

对非开发者和 AI agent，这不是理想的默认复杂度曲线。

---

## 四、哪套最适合“本地演示 + 后续迭代”

### 最平衡
**React + Vite + Tailwind + shadcn/ui + Supabase（云）**
- 本地前端最轻
- 线上演示也轻
- 后续扩展 Auth/DB/Storage 方便
- AI agent 最容易持续修改

### 最适合后续产品化
**Next.js + Tailwind + shadcn/ui + Supabase**
- 黑客松结束后继续推进的路径最顺
- Vercel 模板生态很强
- 但开发复杂度更高

### 最适合纯本地/断网演示
**React + Vite + Tailwind + shadcn/ui + SQLite + Prisma**
- 网络依赖最低
- 演示最稳
- 但转线上时需要重新考虑数据层和后端能力

### 最适合数据工具类 demo
**Streamlit**
- 最快起 demo
- 最快改 demo
- 最快上 Cloud
- 但长期演进成通用 Web 产品的能力最弱

---

## 五、我会给团队的实际默认策略

### 默认策略 A：大多数情况
**React + Vite + Tailwind + shadcn/ui + Supabase（云）**

这是最适合“AI agent 高速迭代 + 黑客松交付 + 非开发者可参与”的默认栈。

### 默认策略 B：已经确定要产品化
**Next.js + Tailwind + shadcn/ui + Supabase**

只有当你明确需要：
- 更强模板生态
- SSR / Route Handlers / Server Actions
- 直接往 Vercel 走
才升级到这套。

### 默认策略 C：必须离线、本地全演示
**React + Vite + Tailwind + shadcn/ui + SQLite + Prisma**

### 默认策略 D：Python/数据类工具
**Streamlit**
如果要补 API，再外挂 FastAPI，而不是一开始就 FastAPI 当前台。

---

## 六、哪些官方文档其实已经把“复杂度/坑点”写出来了

### 1. Next.js 官方文档暴露的坑
- local development 文档直接讨论：
  - Turbopack/webpack 切换
  - barrel files
  - 图标大包导入
  - Tailwind 扫描范围
  - Docker on Mac/Windows 变慢
  - tracing 排查
- create-next-app 文档暴露：
  - JS/TS、ESLint/Biome、Tailwind、App Router、src 目录、Turbopack/Webpack、`--api`、`--empty` 等分叉很多
- 结论：**模板强，但结构可变性也高**

### 2. Supabase 官方文档暴露的坑
- 本地开发依赖 Docker-compatible runtime
- 首次运行要下载镜像
- 本地开发栈不要暴露到公网
- 公共网络场景要额外绑定 `127.0.0.1`/独立网络
- 结论：**云上很顺，本地全家桶并不轻**

### 3. Firebase 官方文档暴露的坑
- Node + Java + CLI
- project ID 一致性
- Rules 不配好会开放
- debug 模式与线上行为不同
- import 覆盖内存数据
- 结论：**平台化很强，但不适合默认 MVP 栈**

### 4. Prisma 官方文档暴露的坑
- adapter 分流
- ESM 设置
- Node/Bun 差异
- Studio 限制
- 结论：**比 Drizzle 更标准，但也不是“只有一条命令”**

### 5. Drizzle 官方文档暴露的坑
- driver 选择多
- 迁移信息分散在别处
- 结论：**灵活，但对默认栈不够收敛**

### 6. FastAPI 官方文档暴露的坑
- 部署概念页直接把 TLS、进程托管、自动重启、多 worker、内存复制、容器编排全摆出来
- 结论：**做 API 很好，做“非开发者默认 Web MVP”不是最轻路**

### 7. Streamlit 官方文档暴露的边界
- 本地运行和模板部署非常简单
- 但官方“工程化复杂前端”的信息密度明显更低
- Python 版本改动甚至可能需要删除并重新部署
- 结论：**极强 demo 工具，不是通用 Web 产品默认栈**

---

## 最终建议

如果你要一个真正可执行的默认建议，我会这么定：

### 默认栈
**React + Vite + Tailwind + shadcn/ui + Supabase（云）**

### 升级栈
**Next.js + Tailwind + shadcn/ui + Supabase**

### 离线栈
**React + Vite + Tailwind + shadcn/ui + SQLite + Prisma**

### 特例栈
- **Streamlit**：数据/分析/模型 demo
- **FastAPI**：Python API 后端
- **Firebase**：已有 Firebase/Google 生态强绑定时再用
- **Drizzle**：工程经验足够、明确要 SQL/driver 控制时再用

如果你愿意，我下一步可以继续把这份结论整理成一张更实用的表：
“按场景选栈决策树（黑客松 / 内部工具 / 离线 demo / 准产品化 / Python 数据工具）”。

Sources:
- [Getting Started | Vite](https://vite.dev/guide/)
- [Getting Started: Installation | Next.js](https://nextjs.org/docs/app/getting-started/installation)
- [Guides: Development Environment | Next.js](https://nextjs.org/docs/app/guides/local-development)
- [CLI: create-next-app | Next.js](https://nextjs.org/docs/app/api-reference/cli/create-next-app)
- [Next.js starter templates and themes | Vercel Templates](https://vercel.com/templates/next.js)
- [Supabase Local Development & CLI](https://supabase.com/docs/guides/local-development)
- [Supabase CLI Getting Started](https://supabase.com/docs/guides/local-development/cli/getting-started)
- [Build a User Management App with Next.js | Supabase Docs](https://supabase.com/docs/guides/getting-started/tutorials/with-nextjs)
- [Build a User Management App with React | Supabase Docs](https://supabase.com/docs/guides/getting-started/tutorials/with-react)
- [Install, configure and integrate Local Emulator Suite | Firebase](https://firebase.google.com/docs/emulator-suite/install_and_configure)
- [Introduction to Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite)
- [First Steps - FastAPI](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Deployments Concepts - FastAPI](https://fastapi.tiangolo.com/deployment/concepts/)
- [Get started with Streamlit](https://docs.streamlit.io/get-started)
- [Run your Streamlit app](https://docs.streamlit.io/develop/concepts/architecture/run-your-app)
- [Deploy an app from a template - Streamlit Docs](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/deploy-from-a-template)
- [Install Tailwind CSS with Next.js - Tailwind CSS](https://tailwindcss.com/docs/guides/nextjs)
- [Framework guides - Tailwind CSS](https://tailwindcss.com/docs/installation/framework-guides)
- [shadcn/ui Introduction](https://ui.shadcn.com/docs)
- [shadcn/ui Installation](https://ui.shadcn.com/docs/installation)
- [shadcn/ui Next.js Installation](https://ui.shadcn.com/docs/installation/next)
- [shadcn/ui Vite Installation](https://ui.shadcn.com/docs/installation/vite)
- [Prisma ORM with SQLite Quickstart](https://www.prisma.io/docs/getting-started/prisma-orm/quickstart/sqlite)
- [Add Prisma ORM to an existing project using SQLite](https://www.prisma.io/docs/prisma-orm/add-to-existing-project/sqlite)
- [Drizzle ORM - SQLite](https://orm.drizzle.team/docs/get-started-sqlite)
- [SQLite Zero-Configuration](https://sqlite.org/zeroconf.html)
- [About SQLite](https://sqlite.org/about.html)
