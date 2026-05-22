# COCO-llm-council Director Brief

日期：2026-05-22

## 一句话结论

`COCO-llm-council` 已从启动方案落成可执行 CLI：`coco-llm-council`。它不依赖旧 TR，不引入 Web app，不使用 OpenRouter API；默认通过 COCO / `traecli` 执行模型调用，复刻 `references/llm-council` 的 Stage 1 / Stage 2 / Stage 3 council protocol，并把全过程写入可复盘 artifact store。

## 已交付

- CLI skeleton：`pyproject.toml`、`Makefile`、`src/coco_llm_council/`。
- 命令面：`doctor`、`models`、`subagents`、`run`、`show`、`validate`、`replay`、`export`、`raw`。
- Council core：保留 `llm-council` 的函数边界，包括 `stage1_collect_responses`、`stage2_collect_rankings`、`parse_ranking_from_text`、`calculate_aggregate_rankings`、`stage3_synthesize_final`、`run_full_council`。
- Runtime provider：direct `traecli` provider；subagent profile provider 也可执行。
- Artifact store：`.coco-llm-council/runs/<run_id>/`，保存 input、config、manifest、events、runtime doctor/models、每阶段 prompt/response/meta、COCO stream/session evidence。
- Expected vs actual model 校验：模型不存在、fallback、空响应、Stage 2 ranking parse 不完整都会让 run 失败。
- HTML export：单文件 `html/index.html`，从 artifacts 渲染，不调用模型，不改写主席答案。
- 固定 COCO subagent 成员：`.trae/agents/council-gpt54.md`、`.trae/agents/council-glm51.md`、`.trae/agents/council-chairman-gpt54.md` 和 `profiles/subagents.json`。
- Schema contract：`validate` 已接入 manifest、stage meta、review json、final json、html export json 的最小必填字段和类型检查；本轮没有修改 Stage 2 prompt。

## 验证结果

### 本地结构与单元测试

```bash
PYTHONPATH=src python3 -m compileall src
make test
```

结果：

```text
compileall: pass
unittest: 10 tests passed
```

覆盖点：

- ranking parser 只采信 `FINAL RANKING:` 区段。
- aggregate ranking 正确计算平均名次。
- direct `traecli` stream JSON 能提取 actual model。
- subagent stream JSON 能优先提取子 agent `_source_model`。
- HTML export + validate 能在 fixture artifact 上通过。
- Schema contract 能证明缺少 manifest 必填字段会失败。
- Schema contract 能证明 stage meta、review json、final json、html export json 缺少必填字段会失败。
- Schema contract 能证明 `manifest.stages.stage1/stage2` 类型错误或数组 item 非 object 时，`validate` 返回结构化失败而不是崩溃。

### CLI 安装与基础命令

```bash
make install-local
command -v coco-llm-council
coco-llm-council --help
coco-llm-council --json doctor
coco-llm-council doctor --json
coco-llm-council models --json
coco-llm-council subagents --json
```

结果：

```text
command: /Users/bytedance/.local/bin/coco-llm-council
doctor ok: true
models count: 23
subagents ok: true
subagents count: 3
```

说明：`traecli doctor` 当前仍返回 MCP warning，因此原始 exit code 是 `1`，但 summary 是 `7 info / 1 warning / 0 error`。CLI 把它记录为 warning，不阻断 council run。

### 无效模型与 fallback 防线

```bash
coco-llm-council run \
  --input examples/question.md \
  --members Invalid-Model,GPT-5.4 \
  --chairman GPT-5.4 \
  --run-id invalid-model-smoke \
  --json
```

结果：

```text
status: failed
failure: Invalid-Model not available in traecli models --json
```

结论：无效模型在调用模型前被阻断，不会静默 fallback 到默认模型。

### Direct provider 完整 council run

```bash
coco-llm-council run \
  --input examples/question.md \
  --members GPT-5.4,GLM-5.1 \
  --chairman GPT-5.4 \
  --run-id live-smoke-20260522161928 \
  --timeout 180 \
  --json
```

结果：

```text
status: ok
html: .coco-llm-council/runs/live-smoke-20260522161928/html/index.html
failures: []
```

后验验证：

```bash
coco-llm-council validate live-smoke-20260522161928 --json
```

结果：

```text
status: ok
checks: 171
failures: 0
Stage 1 expected/actual: GPT-5.4 -> GPT-5.4, GLM-5.1 -> GLM-5.1
Stage 2 expected/actual: GPT-5.4 -> GPT-5.4, GLM-5.1 -> GLM-5.1
Stage 2 parse: ok, ok
Stage 3 expected/actual: GPT-5.4 -> GPT-5.4
```

### Subagent provider 完整 council run

```bash
coco-llm-council run \
  --input /Users/bytedance/Documents/AI\ Coder/COCO-llm-council/examples/question.md \
  --profile /Users/bytedance/Documents/AI\ Coder/COCO-llm-council/profiles/subagents.json \
  --run-id subagent-hard-20260522165545 \
  --timeout 180 \
  --json
```

结果：

```text
status: ok
provider_mode: subagent
member_agents: council-gpt54, council-glm51
runtime_cwd: /Users/bytedance/Documents/AI Coder/COCO-llm-council
html: .coco-llm-council/runs/subagent-hard-20260522165545/html/index.html
failures: []
```

后验验证：

```bash
coco-llm-council validate subagent-hard-20260522165545 --json
```

结果：

```text
status: ok
checks: 236
failures: 0
Stage 1 expected/actual: GPT-5.4 -> GPT-5.4, GLM-5.1 -> GLM-5.1
Stage 2 expected/actual: GPT-5.4 -> GPT-5.4, GLM-5.1 -> GLM-5.1
Stage 2 parse: ok, ok
Stage 3 expected/actual: GPT-5.4 -> GPT-5.4
Subagent invocation evidence: 5 / 5 passed
```

### HTML artifact

```bash
coco-llm-council export live-smoke-20260522161928 --format html --json
rg -n "TOC|Stage 1|Stage 2|Stage 3|Provider Trace|Copy as markdown|Average rank" \
  .coco-llm-council/runs/live-smoke-20260522161928/html/index.html
```

结果：

```text
TOC: present
Stage 1/2/3 sections: present
tabs: present
SVG council flow: present
ranking matrix: present
copy as markdown / JSON / final prompt: present
copy payload: JSON script payload parsed back to raw JSON/Markdown/prompt, not HTML-escaped text
provider trace: present
```

### Schema contract

本轮只做 schema contract，不改 Stage 2 prompt。`validate` 新增最小必填字段和类型检查：

```text
manifest.json: schema_version, run_id, created_at, updated_at, status, input_chars, config, artifacts, stages, metadata, warnings, failures
manifest.config: members, chairman, provider_mode, runtime_command, query_timeout, export_html
manifest.stages: stage1, stage2, stage3
manifest.metadata: label_to_model, aggregate_rankings
stage meta: expected_model, actual_model, response_chars, status, session_id, command, exit_code, stdout_path, stderr_path, copied_session_files, raw_model_markers, error, captured_at
review json: reviewer_label, model, expected_model, actual_model, ranking, parsed_ranking, parse_status, status, error, review_path, json_path
final json: model, expected_model, actual_model, response, status, error, prompt_path, response_path, json_path
html export json: run_id, generated_at, format, path, source_manifest
```

新增测试覆盖：

```text
test_validate_fails_when_manifest_required_field_missing
test_validate_fails_when_sidecar_required_fields_missing
test_validate_reports_stage_collection_type_errors_without_crashing
```

现有 run 回归结果：

```text
live-smoke-20260522161928: validate ok, 171 checks, 0 failures
subagent-hard-20260522165545: validate ok, 236 checks, 0 failures
```

## 风险与边界

- 当前 workspace 不是 git repository，因此交付证据来自文件树、命令输出和 artifact store，不来自 git history。
- Subagent provider 已可跑通，并且 validate 会硬校验 Agent tool call、tool result、子 agent `parent_tool_use_id` 和 `_source_model`。它比 direct provider 慢，因为 COCO 会多一层 Agent 委派；默认仍推荐 direct provider 做高频 council run。
- Stage 2 仍兼容自由文本 ranking parse。CLI 已把 parse 不完整设为 run failure，但长期可以再加结构化 JSON ranking prompt。
- Schema contract 当前是最小合同，只覆盖 artifact 可复盘所需的必填字段和类型；它不是完整 JSON Schema，也不做跨文件深层一致性校验。
- HTML export 是确定性本地渲染，不是模型生成。这个边界是刻意保留的：主席综合只负责最终答案，HTML 只负责报告呈现。

## Director 判断

这个版本已经达到“可用、可审计、可复盘”的第一版标准。它不是 demo script，而是可从任意目录调用的 CLI，并且每次模型调用都有 trace。Schema contract 已经从“下一步建议”变成当前 validate 的硬门槛。下一阶段不该回头做 Web UI，也不该接 OpenRouter；更值得做的是扩大 profile 管理，并在不破坏现有 protocol 的前提下增加结构化 ranking 输出。
