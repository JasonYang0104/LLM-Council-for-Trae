# 非开发者 + AI Agent + 黑客松默认技术栈调研报告

---

## 核心结论：明确推荐

**默认技术栈：Python + Streamlit（纯前端/数据工具类）**

**置信度：高**

**备选切换条件**：当项目需要复杂 UI、多人协作、正式发布时，切换至 Next.js + Vercel。

---

## 一、背景问题建模

在开始分析前，需要先明确这个场景的约束条件：

- **用户画像**：非开发者，通过自然语言描述需求，依赖 AI Agent 生成代码
- **交付目标**：可本地运行、可演示的 Web MVP
- **核心矛盾**：AI Agent 能快速生成代码，但**多轮修改后会引入复杂性和错误**
- **评测维度**：项目结构简单性、错误可修复性、依赖稳定性、启动命令复杂度、UI 可塑性、本地演示便利性

---

## 二、技术栈对比分析

### 2.1 Streamlit（Python）

**优势：**

1. **极简项目结构**：单文件 `app.py` 即可运行，文件树简单到 AI Agent 可以完整理解
2. **Python 原生**：非开发者可以读写 Python，错误信息是纯 Python traceback，可读性高
3. **启动命令简单**：`streamlit run app.py`，无构建步骤
4. **数据工具天然契合**：数据看板、表单流程、AI 小工具等场景下，Streamlit 有原生组件支持
5. **状态管理虽有问题但可学习**：`st.session_state` 虽有小坑，但模式固定，AI Agent 容易理解

**劣势：**

1. **UI 自定义能力有限**：主题定制需要 `config.toml`，对非开发者有一定门槛
2. **状态管理坑**：2025 年仍有 `st.rerun()` 在 debug 模式下的异常问题、`st.query_params` 刷新丢失等问题
3. **不适合正式 Web 产品**：URL 路由、SEO、多页面复杂交互等场景天然弱

**关键数据：**
- 2025 年 Fortune 50 公司中超过 90% 在使用 Streamlit
- 有专门的 [Streamlit Agent Skills](https://github.com/streamlit/agent-skills) 支持 AI 编码
- 2025 年已发布官方 vibe coding 指南，使用 AGENTS.md 增强 AI 理解

### 2.2 Next.js（JavaScript/TypeScript）

**优势：**

1. **AI 调试大幅改善**：Next.js 16.2（2026 年 3 月）引入了 `AGENTS.md`、浏览器日志转发、`next-browser` 等专门针对 AI Agent 的调试工具
2. **生态系统成熟**：shadcn/ui、Tailwind CSS 等 UI 组件丰富，UI 容易做得好看
3. **Vercel 部署简单**：一行命令即可部署，演示方便

**劣势：**

1. **项目结构复杂**：默认生成的文件数量多，非开发者难以理解全局
2. **调试仍有问题**：2025 年 10 月 v16 发布时，用户向 AI Agent 说"fix the error"但 Agent 无法看到浏览器状态，导致调试困难（这个问题在 16.2 中部分解决）
3. **依赖更复杂**：npm 包版本冲突在 AI 幻觉引入不存在包时尤其严重
4. **上下文窗口压力**：多轮修改后，文件数量增加，AI Agent 上下文窗口压力大，理解能力下降

**关键数据：**
- Next.js 16.2 的 AI 调试改进使 pass rate 达到 100%（对比 skill-based 方式）
- 但这是针对**有经验的开发者**而言，对非开发者价值有限

### 2.3 对比矩阵

| 维度 | Streamlit | Next.js |
|------|-----------|---------|
| 项目结构 | ★★★★★ | ★★☆☆☆ |
| 错误可修复性 | ★★★★☆ | ★★★☆☆ |
| 依赖稳定性 | ★★★★★ | ★★☆☆☆ |
| 启动命令 | ★★★★★ | ★★★☆☆ |
| UI 可塑性 | ★★☆☆☆ | ★★★★★ |
| 本地演示 | ★★★★☆ | ★★★★☆ |
| 非开发者友好度 | ★★★★★ | ★★☆☆☆ |

---

## 三、AI Agent 生成代码的深层挑战

### 3.1 多轮修改后的复杂度累积

这是最容易被低估的问题。根据多项调研：

- **43%** 的 AI 生成代码变更在生产环境需要调试
- **45%** 的开发者最大挫折感来自"AI 方案几乎对但不完全对"
- **70%+** 的 Java 实现中 AI 生成代码失败率超过 70%

对于非开发者来说，这意味着：

1. **第一轮** AI 生成代码可以工作
2. **第三轮** 修改后，AI 开始引入隐藏错误
3. **第五轮** 后，错误定位和修复变得困难

**Streamlit 的优势**：单文件结构使得 AI 每次都可以完整理解项目，降低幻觉率

**Next.js 的劣势**：多文件结构中，AI 可能引入路径错误、导入错误，且错误信息分散

### 3.2 依赖幻觉问题

2025-2026 年的关键发现：AI Agent 会**发明不存在的 npm 包**。

这对非开发者是致命打击：
- 非开发者无法判断 `npm install some-fake-package` 失败的原因
- 无法区分是 AI 幻觉还是真实依赖问题
- Streamlit 的 Python 生态相对简单，幻觉空间更小

---

## 四、"看似简单但多轮后变难"的路线

### 4.1 Next.js 看似主流但有多轮修改陷阱

- 初始生成体验好，但每次功能增加，文件数量指数增长
- App Router 的服务端/客户端组件边界，对非开发者是黑箱
- AI Agent 在第二轮修改时最容易引入"看似对但运行时错"的代码

### 4.2 纯 HTML/CSS/JS 方案

- 看似最简单，实际上 AI 生成代码质量参差不齐
- 缺乏框架约束，代码结构很快变得混乱
- 不适合数据看板、表单流程等结构化场景

### 4.3 低代码平台（Lovable、Bolt.new）

- 对非开发者最友好，但存在**供应商锁定**
- 如果黑客松后要本地运行或继续开发，可能需要重建
- 2025 年已有数据泄露等安全事件

---

## 五、具体推荐方案

### 5.1 默认技术栈（非开发者首选）

```
前端：Streamlit（Python）
AI 集成：LangChain / 直接调用 API
数据存储：SQLite 或 JSON 文件
演示：streamlit run app.py --server.headless false
```

**推荐理由：**
- 项目结构最简单，AI Agent 可完整理解
- Python 错误信息可读性强
- 启动命令简单
- 非常适合数据看板、表单流程、AI 小工具

**适合场景：**
- 数据分析看板
- 表单收集工具
- AI 对话界面
- 内部小工具

### 5.2 备选技术栈（触发条件切换）

**触发条件**：当需要更复杂 UI、多人协作、或最终要发布时

```
前端：Next.js + shadcn/ui + Tailwind CSS
后端：Next.js API Routes 或 FastAPI
部署：Vercel
状态管理：React Context 或 Zustand
```

**推荐理由：**
- Next.js 16.2 的 AI 调试工具已改善
- shadcn/ui 提供高质量组件，非开发者可通过 AI 生成使用
- Vercel 部署零门槛

**切换时机：**
- 当 Streamlit 的 UI 定制化无法满足需求时
- 当需要多人协作开发时
- 当需要发布到公网时

---

## 六、推翻当前推荐的证据或条件

以下条件如果出现，推荐可能需要调整：

1. **Trae-CN 的 Skill 生态成熟度**：如果 Trae-CN 对 Streamlit 有专门的 Skill 支持，Streamlit 优势将进一步放大
2. **公司内部技术栈偏好**：如果公司已有 Next.js 技术积累，切换成本低
3. **项目复杂度**：如果黑客松项目涉及用户认证、支付、多人协作，即使非开发者也应选择 Next.js 并寻求开发者帮助
4. **安全要求**：如果涉及敏感数据，Streamlit 的安全模型需要额外审计

---

## 七、参考资料

1. [Hackathon Tech Stack Guide - Since AI](https://medium.com/@sinceai/hackathon-tech-stack-guide-4e4243ea0a5d)
   - 支持：明确的 hackathon 堆栈推荐，强调"6 小时出 demo"

2. [Vibe Coding Examples: 10 Real Projects Reviewed](https://justinmckelvey.com/blog/vibe-coding-examples)
   - 支持：内部工具是 vibe coding 的最佳场景，营销站点次之

3. [Building Next.js for an agentic future - Next.js](https://nextjs.org/blog/agentic-future)
   - 支持：Next.js v16 的 AI Agent 调试问题，说明非开发者使用 Next.js 的挑战

4. [Next.js 16.2 AI Improvements](https://nextjs.org/blog/next-16-2-ai)
   - 支持：Next.js 在改善 AI Agent 调试方面的具体努力

5. [Streamlit vs Gradio 2025 Comparison](https://www.squadbase.dev/en/blog/streamlit-vs-gradio-in-2025-a-framework-comparison-for-ai-apps)
   - 支持：Streamlit 是 AI 应用轻量级框架首选

6. [Vibe Coding Best Practices - Softr](https://www.softr.io/blog/vibe-coding-best-practices)
   - 支持：PRD 重要性、框架选择建议

7. [The 80% Problem: AI Agents Technical Debt - Augment Code](https://www.augmentcode.com/guides/the-80-percent-problem-ai-agents-technical-debt)
   - 支持：AI Agent 产生技术债务的比例和原因

8. [Are bugs inevitable with AI coding agents? - Stack Overflow](https://stackoverflow.blog/2026/01/28/are-bugs-and-incidents-inevitable-with-ai-coding-agents/)
   - 支持：45% 开发者最大挫折是 AI 方案"几乎对"

9. [Streamlit Agent Skills - GitHub](https://github.com/streamlit/agent-skills)
   - 支持：Streamlit 已有官方 Agent Skills 支持

10. [AI-Generated Code Is Not Reproducible - ArXiv](https://arxiv.org/html/2512.22387v3)
    - 支持：Python 依赖问题比 JavaScript 少（数据科学和脚本场景）

---

## 八、结论

对于公司内部黑客松场景中的非开发者：

**默认选 Streamlit**，因为它在"非开发者 + AI Agent"这个特定组合下，在项目结构简单性、错误可修复性、依赖稳定性、启动命令复杂度等所有关键维度都表现最优。

**Next.js 是备选**，当且仅当 Streamlit 确实无法满足 UI 需求时切换，且需要准备付出更高的学习成本和调试复杂度。

核心逻辑：**黑客松追求的是"6 小时出 demo"，而不是"用最酷炫的框架"。Streamlit 让非开发者在 AI Agent 帮助下稳定出活，Next.js 让他们在第三轮修改后开始怀疑人生。**