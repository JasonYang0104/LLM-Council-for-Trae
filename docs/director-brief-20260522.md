# COCO-llm-council Director Brief

日期：2026-05-22

## 一句话结论

`COCO-llm-council` 已从启动方案落成可执行、可审计、可复盘的本地 CLI：`coco-llm-council`。它不依赖旧 TR，不引入 Web app，不使用 OpenRouter API；默认通过 COCO / `traecli` 执行模型调用，复刻 `references/llm-council` 的 Stage 1 / Stage 2 / Stage 3 council protocol，并把全过程写入 artifact store 和单文件 HTML 报告。

最新阶段还补齐了一个关键产品体验：用户只传问题文件时，CLC 会读取当前模型列表，给出推荐 council 模型套，并在 CLI 内主动询问是否采用；不再要求用户先手写 `--members` / `--chairman`。

## 当前交付范围

- CLI skeleton：`pyproject.toml`、`Makefile`、`src/coco_llm_council/`。
- 命令面：`doctor`、`models --recommend`、`subagents`、`run`、`show`、`validate`、`replay`、`export`、`raw`。
- Council core：保留 `llm-council` 的函数边界，包括 `stage1_collect_responses`、`stage2_collect_rankings`、`parse_ranking_from_text`、`calculate_aggregate_rankings`、`stage3_synthesize_final`、`run_full_council`。
- 主动模型选择：`run --input <file>` 会在 TTY 中展示当前 COCO 模型列表、推荐成员和主席；`--default-models`、`--members/--chairman`、`--profile` 可跳过询问。
- Runtime provider：direct `traecli` provider；subagent profile provider 也已实现。
- Artifact store：`.coco-llm-council/runs/<run_id>/`，保存 input、config、manifest、events、runtime doctor/models、每阶段 prompt/response/meta、COCO stream/session evidence。
- Expected vs actual model 校验：模型不存在、fallback、空响应、Stage 2 ranking parse 不完整都会让 run 失败。
- HTML export：单文件 `html/index.html`，从 artifacts 渲染，不调用模型，不改写主席答案；页面外壳默认中文。
- 固定 COCO subagent 成员：`.trae/agents/council-gpt54.md`、`.trae/agents/council-glm51.md`、`.trae/agents/council-chairman-gpt54.md` 和 `profiles/subagents.json`。
- Schema contract：`validate` 已接入 manifest、stage meta、review json、final json、html export json 的最小必填字段和类型检查。
- Git 管理：项目已初始化 git，关键提交包括 `53305a4 Initial COCO llm council CLI` 和 `d225163 Add interactive model selection`。

## 最新验证

### 不依赖 live COCO 的验证

2026-05-22 阶段收尾时，用户确认 COCO 当前不可用；因此本轮没有声称新的 live COCO smoke 结果，只复验不依赖真实 COCO 的部分。

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
PYTHONPATH=src python3 -m coco_llm_council.cli --runtime-command /tmp/fake-traecli-clc models --recommend --json
PYTHONPATH=src python3 -m coco_llm_council.cli run --input examples/question.md --skip-html --json
PYTHONPATH=src python3 -m coco_llm_council.cli --runtime-command /tmp/fake-traecli-clc --store /tmp/clc-fake-runs run --input examples/question.md --run-id fake-interactive --json
PYTHONPATH=src python3 -m coco_llm_council.cli --store /tmp/clc-fake-runs validate fake-interactive --json
```

结果：

```text
compileall: pass
unittest: 14 tests passed
git diff --check: pass
models --recommend: members GPT-5.4, GLM-5.1, DeepSeek-V4-Pro; chairman GPT-5.4
non-interactive run without model selection: structured failure, no hang
fake runtime run: status ok, HTML generated
fake runtime validate: ok, 218 checks, 0 failures
```

### 已保留的 live COCO 历史证据

以下 run 是早前 COCO 可用时完成的 live evidence；它们仍可作为已保存 artifact 的历史验证，但不是本轮重新跑出的结果。

Direct provider：

```text
run_id: live-smoke-20260522161928
members: GPT-5.4, GLM-5.1
chairman: GPT-5.4
status: ok
validate: ok, 171 checks, 0 failures
```

Subagent provider：

```text
run_id: subagent-hard-20260522165545
provider_mode: subagent
members: council-gpt54, council-glm51
chairman: council-chairman-gpt54
status: ok
validate: ok, 236 checks, 0 failures
subagent invocation checks: 5 / 5 passed
```

## 用户交互口径

默认命令现在应该是：

```bash
coco-llm-council run --input examples/question.md --json
```

交互式终端中，CLC 会：

1. 调用 `traecli models --json`。
2. 展示当前可用模型。
3. 推荐 3 个 member models 和 1 个 chairman。
4. 让用户选择：回车使用推荐、`d` 使用默认模型套、`c` 自定义、`q` 取消。

如果外层 Agent 不支持交互式输入，不会受 AskUserQuestion 能力影响。CLC 的询问是普通 CLI 终端输入；非 TTY 环境会失败得很早，并提示调用方传 `--default-models`、`--members/--chairman` 或 `--profile`。

## 风险与边界

- Live COCO 当前不可用时，只能验证 CLI 和 artifact 逻辑，不能声称完成新的 live model run。
- Subagent provider 已可跑通，并且 validate 会硬校验 Agent tool call、tool result、子 agent `parent_tool_use_id` 和 `_source_model`。它比 direct provider 慢，因为 COCO 会多一层 Agent 委派；默认仍推荐 direct provider 做高频 council run。
- Stage 2 仍是自由文本 `FINAL RANKING:` 协议。CLI 已把 parse 不完整设为 run failure，但长期可以再加结构化 JSON ranking 输出。
- Schema contract 当前是最小合同，只覆盖 artifact 可复盘所需的必填字段和类型；它不是完整 JSON Schema，也不做跨文件深层一致性校验。
- HTML export 是确定性本地渲染，不是模型生成。主席综合只负责最终答案，HTML 只负责报告呈现。

## Director 判断

这个版本已经达到“第一版可用”的标准：命令面完整，产物可审计，模型 fallback 有防线，subagent 真实调用有证据门禁，用户不再必须手写成员模型。下一阶段不该回头做 Web UI，也不该接 OpenRouter；更值得做的是 profile 管理、结构化 Stage 2 ranking 输出、更多推荐策略，以及更完整的跨文件 schema 校验。
