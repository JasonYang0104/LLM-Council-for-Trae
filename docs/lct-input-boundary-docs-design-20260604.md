# LCT Input Boundary Docs Design

日期：2026-06-04
范围：README、LCT Skill、`.trae` Skill 和文档契约测试

## 一句话结论

`_lct_question.md` 只能承载 council 成员应该回答的问题、必要事实背景和输出要求；外层 Agent 的执行职责必须留在调用流程里，不能写进成员模型可见输入。

## 背景

v9 E2E 暴露了一个输入边界问题：外层 Agent 把“维护 `notes.md`”这类执行要求写进了 `_lct_question.md`，成员模型把它理解为自己的任务，进而尝试文件工具并触发 contamination。第三次运行用更窄的 council-only input 和 `answer_only` 通过，但这不代表默认策略应该改成 `answer_only`。

真正需要修的是文档与 Skill 的执行口径：调用 Agent 必须知道哪些内容属于 council input，哪些内容只属于 operator envelope。

## 两层输入

### Council input

可以进入 `_lct_question.md` 的内容：

- 用户真正要委员会回答的问题。
- 用户对答案结构、语言、重点和边界的要求。
- `Report topic: <中文议题>`，用于稳定 HTML 标题；它是报告元数据，不是成员任务指令。
- 外层 Agent 判断有必要时加入的 fact pack。fact pack 必须直接嵌入 `_lct_question.md`，放在用户原始问题后，清楚标注来源。

### Operator envelope

不得进入 `_lct_question.md` 的内容：

- “使用 LCT”“跑 validate”“写 final/index”“生成 HTML”。
- “维护 `notes.md`”“记录运行过程”“提交 PR”“开 branch”“跑测试”。
- 要求成员读取本地 sidecar 文件、创建文件、修改文件或维护运行记录。
- 外层 Agent 自己的 workflow、交付职责、Git 职责和验证职责。

这些指令仍然有效，但执行者是外层 Agent，不是 council 成员。

## Input Preparation 口径

默认保留用户原始实质问题。只有当用户明确要求“思考我真正需要的是什么”、要求拆解意图、重构问题、加入事实包或结构化输出时，外层 Agent 才使用 `structured by Agent`。

即便使用 `structured by Agent`，也必须保留原始用户问题，并明确哪些内容是 `Agent interpretation`。Agent 不得伪造用户没有表达过的事实、偏好或结论。

`Report topic` 可以追加，因为它是报告元数据；但它不能承载执行指令。

## `notes.md` 边界

`notes.md` 只由外层 Agent 维护，用来记录运行过程、关键决定、权衡、异常、验证和用户应该知道的事实。

如果用户要求“维护 `notes.md`”，调用 Agent 应执行这个要求，但不得把它写入 `_lct_question.md`，也不得要求 council 成员创建、读取、修改或维护 `notes.md`。

## Fact Pack 边界

外层 Agent 可以自行判断是否需要搜索、事实核验或本地资料整理。做了事实核验时，可以把 fact pack 直接嵌入 `_lct_question.md`，但必须满足三点：

- 标注来源。
- 只包含事实背景和来源。
- 不包含“请你搜索”“请你读文件”“请你维护 `notes.md`”等执行指令。

不要要求成员读取 `_lct_fact_pack.md` 或其他 sidecar 文件。

## 搜索与工具模式

本 PR 不改变 `--member-tool-mode` 默认值，不强制 `answer_only`，也不强制外层 Agent 先搜索。

外层 Agent 保留判断权，可以基于任务选择：

- 让 LCT 成员在 `search_enabled` 下自行使用 Web 工具。
- 外层 Agent 先做 fact pack，再让成员基于输入推理。
- 使用 `answer_only`，让成员只基于问题文件推理。
- 使用 `workspace_enabled`，处理只读代码或文件问题。

汇报必须分开记录：

- `lct_search_allowed`
- `lct_search_used`
- `lct_web_tool_calls`
- `agent_external_search_allowed`
- `agent_external_search_used`
- `agent_sources`

`search_enabled` 只表示 LCT 成员允许搜索，不表示实际搜索发生；外层 Agent 做过的搜索不能混进 `lct_search_*`。

## 为什么不改 CLI

这轮不写 CLI input classifier，也不让 runtime 自动剥离 operator envelope。理由：

- 当前问题来自 Skill/README 对调用 Agent 的输入准备指导不清，而不是 CLI 无法解析 Markdown。
- 自动 classifier 容易误删用户真正希望委员会回答的流程性问题。
- 只改 docs/Skill 可以最小化风险，同时通过文档契约测试防止口径回退。

## 验收口径

- README 的 quickstart 不再暗示整段外层请求可以原样写入 `_lct_question.md`。
- canonical Skill 和 `.trae` Skill 都明确区分 council input 与 operator envelope。
- Skill 明确 `notes.md` 由外层 Agent 维护，成员不要创建、读取、修改或维护它。
- Skill 明确 fact pack 可选、可嵌入、必须有来源，且不得包含执行指令。
- 文档不把 `answer_only` 写成默认或强制策略。
