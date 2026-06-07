# LCT Input Boundary Docs Director Brief

日期：2026-06-04
分支：`codex/lct-input-boundary-docs-20260604`
范围：docs / Skill / 文档契约测试

## 一句话结论

本轮把 LCT 的输入边界写成了可测试的文档合同：`_lct_question.md` 只承载 council 成员要回答的问题、必要事实背景、输出要求和 `Report topic`；外层 Agent 的运行职责留在外层，不再泄露给成员模型。

## 为什么做

v9 E2E 暴露的问题不是 runtime 坏了，而是调用说明含糊。前两次 run 把“维护 `notes.md`”这类外层执行要求带进了成员可见输入，成员模型把它当成自己的任务，尝试文件工具后触发 tool contamination。第三次用更窄的 council-only input 和 `answer_only` 通过，但这只能证明收窄输入有效，不能证明默认工具模式应该改成 `answer_only`。

真正的修复点是 Skill 和 README：调用 Agent 必须知道什么能写进 `_lct_question.md`，什么只能作为 operator envelope 留在外层执行。

## 改了什么

- README quickstart 明确：`_lct_question.md` 只写 council-facing 问题、必要事实背景、输出要求和 `Report topic`。
- canonical Skill 明确区分 `council input` 和 `operator envelope`。
- `.trae` Skill 同步同一套输入边界，避免项目级 Skill 和全局 Skill 口径漂移。
- `notes.md` 被明确限定为外层 Agent 维护；如果用户要求维护 notes，调用 Agent 执行，但不得把该要求写入 council input。
- fact pack 被限定为可选、直接嵌入 `_lct_question.md`、必须标注来源、只包含事实背景和来源、不能包含执行指令。
- 新增文档契约测试，覆盖输入边界、raw input 默认、fact pack、notes、工具模式判断权和 README quickstart。

## 没改什么

- 不改 runtime。
- 不改 validate。
- 不改 `--member-tool-mode` 默认值。
- 不强制 `answer_only`。
- 不强制外层 Agent 先搜索。
- 不新增 CLI input classifier。
- 不把 ACP 或 sidecar 文件方案混进本 PR。

## 产品口径

默认保留用户原始实质问题。只有用户明确要求思考真实意图、拆解问题、重构输入、加入事实包或结构化输出时，外层 Agent 才使用 `structured by Agent`，并且必须保留 `Original input`，把额外解释标成 `Agent interpretation`。

搜索和工具模式保持由外层 Agent 判断：可以让 LCT 成员在 `search_enabled` 下搜索，可以由外层 Agent 先补 fact pack，也可以使用 `answer_only` 或 `workspace_enabled`。汇报必须继续拆开 `lct_search_allowed`、`lct_search_used` 和 `agent_external_search_used`。

## 测试与验证证据

TDD 红灯证据：

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs
```

新增测试后旧口径失败：22 个测试中 10 个 subtest 失败，集中在工具模式判断权、`.trae` Skill 输入边界和 canonical Skill 默认 `structured by Agent`。

绿灯后目标测试：

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs
```

结果：22 tests passed。

最终主线程验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check main..HEAD
```

结果：`compileall` exit 0；`make test` 191 tests passed；`git diff --check main..HEAD` exit 0。

subagent review：

- Findings: None。
- 确认未强制 `answer_only`，未强制外层搜索，未触碰 runtime。
- 确认 `notes.md` 和 fact pack 边界符合本轮设计。

## 残余风险

新增测试是文档契约字符串测试，不是自然语言语义解析器。它能防止关键短语和显式口径回退，但不能证明所有同义错误措辞都会被捕获。这个风险在 docs/Skill-only PR 中可接受；如果未来输入泄露再次发生，再考虑更重的 CLI classifier 或运行前 lint。

## 交付索引

- 设计：`docs/lct-input-boundary-docs-design-20260604.md`
- 测试方案：`docs/lct-input-boundary-docs-test-plan-20260604.md`
- Markdown 简报：`docs/lct-input-boundary-docs-brief-20260604.md`
- HTML 简报：`docs/lct-input-boundary-docs-brief-20260604.html`
- 运行记录：`notes.md`
