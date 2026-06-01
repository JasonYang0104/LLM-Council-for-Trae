# llm-council Parity Checklist

目标：一比一复刻上游 `llm-council` 的核心 council protocol，同时排除 Web UI 和 OpenRouter API。

## 必须对齐

| llm-council 资产 | LLM-Council-for-Trae 对应物 | 状态 |
| --- | --- | --- |
| `backend/council.py` | `src/llm_council_for_trae/council.py` | 已实现 |
| `stage1_collect_responses` | Stage 1 member calls | 已实现 |
| `stage2_collect_rankings` | Stage 2 anonymous review | 已实现 |
| `parse_ranking_from_text` | ranking parser / JSON parser fallback | 已实现 |
| `calculate_aggregate_rankings` | aggregate ranking | 已实现 |
| `stage3_synthesize_final` | chairman synthesis | 已实现 |
| `run_full_council` | full run command | 已实现 |
| `frontend/src/components/Stage1.jsx` | HTML Stage 1 section | 已实现为单文件 HTML |
| `frontend/src/components/Stage2.jsx` | HTML Stage 2 section | 已实现为单文件 HTML |
| `frontend/src/components/Stage3.jsx` | HTML Stage 3 section | 已实现为单文件 HTML |

## 必须替换

| llm-council 资产 | 替换原因 | LLM-Council-for-Trae 替代物 |
| --- | --- | --- |
| `backend/openrouter.py` | 不使用 OpenRouter API | `traecli` provider |
| `.env` API key | Trae CLI 已有鉴权 | Trae CLI 本机配置 |
| React / Vite app | 不做 Web app | 单文件 HTML artifact |
| `data/conversations/` | 长期复盘能力弱 | `.llm-council-for-trae/runs/<run_id>/` |

## 已验证 run

当前 parity 目标已经落到 CLI：`run` 可以在未显式传 `--members` / `--chairman` 时先用当前 Trae CLI 模型列表推荐 council 套装，再执行同一套 Stage 1 / 2 / 3 protocol。模型选择是 Trae CLI 适配层能力，不改变 `llm-council` 的核心 protocol。

```text
run_id: live-smoke-20260522161928
members: GPT-5.4, GLM-5.1
chairman: GPT-5.4
status: ok
html: .llm-council-for-trae/runs/live-smoke-20260522161928/html/index.html
```

`validate` 已确认 Stage 1 / Stage 2 / Stage 3 的 expected model 和 actual model 完全一致，Stage 2 ranking parse 为 `ok`，HTML artifact 存在。

另有 subagent provider 验证：

```text
run_id: subagent-hard-20260522165545
provider_mode: subagent
members: council-gpt54, council-glm51
chairman: council-chairman-gpt54
status: ok
validate failures: 0
subagent invocation checks: 5 / 5 passed
```

## 复用原则

只要不冲突，优先复制并改造原项目的 prompt shape、函数边界、Stage 命名和展示结构；不要为了“重写”而重写。
