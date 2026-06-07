# LCT Input Boundary Docs Test Plan

日期：2026-06-04
范围：文档契约测试和最终验证命令

## 测试目标

本轮是 docs/Skill-only PR。测试不验证 runtime 行为，而是锁住调用 Agent 会实际遵循的文档契约，防止输入边界口径回退。

## TDD 策略

优先修改 `tests/test_global_install_skill_docs.py`。新增或收紧测试后，先运行目标测试观察红灯，再修改 README 和 Skill 文档让测试变绿。

如果单独提交红灯测试会让分支历史留下故意失败节点，则在 `notes.md` 记录红灯命令和失败点，并只提交绿灯后的测试 diff。

## 行为覆盖

### Skill 区分 council input 和 operator envelope

测试要求 canonical Skill 和 `.trae` Skill 同时包含：

- `council input`
- `operator envelope`
- `_lct_question.md`
- `外层执行指令不得写入 _lct_question.md`
- `Report topic`
- `报告元数据`

同时禁止把“维护 `notes.md`”写成成员任务。

### `notes.md` 只由外层 Agent 维护

测试要求 canonical Skill 和 `.trae` Skill 同时说明：

- `notes.md`
- `只由外层 Agent 维护`
- `不要要求 council 成员创建、读取、修改或维护 notes.md`
- 如果用户要求维护 `notes.md`，调用 Agent 执行，但不得写入 council input。

### Fact pack 可选且有来源

测试要求 canonical Skill 和 `.trae` Skill 同时说明：

- `fact pack`
- `直接嵌入 _lct_question.md`
- `标注来源`
- fact pack 只能包含事实背景和来源。
- 不要求模型读取 sidecar 文件。

### 不强制 `answer_only`

测试要求 README 和两个 Skill 都保留工具模式判断权：

- `answer_only` 是可选工具模式。
- `search_enabled` 只表示允许搜索，不表示实际搜索发生。
- 外层 Agent 可以自行判断是否使用 LCT 内部搜索、外层 fact pack、`answer_only` 或 `workspace_enabled`。

测试同时禁止出现把 `answer_only` 写成默认强制策略的句式。

### README quickstart 不泄露 operator envelope

测试要求 README 在日常路径中说明：

- `_lct_question.md` 只写 council-facing 问题、必要事实背景、输出要求和 `Report topic`。
- 外层 Agent 的运行职责、验证职责、`notes.md`、Git/PR/测试职责不得写入 `_lct_question.md`。
- 索引继续拆开记录 LCT 内部搜索和外层 Agent 外部检索证据。

## 命令

目标测试：

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs
```

最终验证：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check main..HEAD
```

## 验收标准

- 新增文档契约测试先能证明旧口径不足。
- README、canonical Skill 和 `.trae` Skill 全部通过同一套边界测试。
- 最终完整验证命令退出码为 0。
- 分支不包含 `.llm-council-for-trae/` 或其他 run artifacts。
