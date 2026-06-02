# LCT UX Evidence Hardening Design

Date: 2026-06-02
Audience: Agent operator, PM owner, and future maintainer.

## 1. Objective

This iteration makes LCT's daily usage path more honest and easier to review. It is not a broad model stability benchmark.

The work has four product boundaries:

1. Subagent profile is downgraded from daily path to legacy / experimental path, without deleting historical validation support.
2. Agent input preparation supports two explicit modes: raw original input and structured by Agent.
3. Search capability reporting separates `search_allowed` from `search_used`.
4. HTML reports collapse the input prompt by default while keeping it available in source, copy payloads, and Markdown export.

## 2. Non-goals

- Do not reintroduce the original Web UI.
- Do not add OpenRouter integration.
- Do not rely on old TR.
- Do not merge chairman synthesis with HTML export.
- Do not force model web search; record whether search happened.
- Do not run a large live model benchmark in this iteration.
- Do not delete `.trae/agents/` or `profiles/subagents.json` before tests prove historical artifact validation remains intact.

## 3. Current Problems

### 3.1 Subagent profile is still too visible

`README.md` currently advertises fixed subagent members in the top-level highlight list and presents `profiles/subagents.json` as an active usage path. Direct provider is the daily route; subagent provider has historical validation value but is sensitive to model drift because the current profile includes `GLM-5.1`.

Design decision: keep the files and validation logic, but describe them as legacy / experimental. The daily flow remains global install plus clean problem workspace plus direct provider.

### 3.2 Input shaping is currently implicit

The user-level Skill writes `_lct_question.md`, but it does not say whether the outer Agent may rewrite or structure the user's raw question.

Design decision: LCT core only consumes `input.md`; prompt shaping **（注释：Agent 对用户原文做轻量整理、拆解约束和补充评审维度，使委员会更稳定理解任务）** is an outer-Agent responsibility. The Skill should preserve the original text and may add clearly labeled interpretation / focus sections by default. If the user explicitly asks for raw-only execution, the Agent must write only the original input.

The final report and root-level index should state one of:

- `Input mode: raw original input`
- `Input mode: structured by Agent`

Structured mode must visually distinguish original input from Agent-added constraints.

### 3.3 `search_enabled` is being overread

`--member-tool-mode search_enabled` means WebSearch / WebFetch are allowed. It does not mean a model actually searched.

Design decision: docs, Skill, HTML, and metadata summaries must separate:

- `search_allowed`: web search tools were allowed by policy.
- `search_used`: at least one WebSearch or WebFetch tool call was observed.
- `tool_calls_count`: total observed tool calls.
- `forbidden_tool_calls`: disallowed tool calls that contaminate the run.

This iteration should reuse existing `allowed_tools`, `tool_calls_count`, and parsed `tool_calls` stage metadata. It does not need to change provider execution semantics.

### 3.4 Input prompt occupies the first reading surface

`html_export.py` currently expands `<p class="question-context">` in the hero. Long prompts push the final answer down.

Design decision: change it to a collapsed `<details id="input-prompt" class="question-context">` with a short summary. The input remains in the HTML source, copy payloads, and Markdown export. This is a reading-experience change, not a privacy feature.

## 4. Implementation Slices

### Slice A: Design and test plan

Add this design doc, a matching test plan, and a running `notes.md`.

### Slice B: HTML prompt collapse

Update `html_export.py` so the hero uses:

```html
<details id="input-prompt" class="question-context">
  <summary>输入提示词</summary>
  <div class="details-body">...</div>
</details>
```

Expected behavior:

- No `open` attribute.
- Input text still appears in the HTML source.
- Final answer remains the primary `<article id="final-answer">`.
- Existing evidence appendices stay collapsed.

### Slice C: Search evidence summary

Add a small metadata summary derived from stage records:

```json
{
  "search_allowed": true,
  "search_used": false,
  "web_tool_calls_count": 0,
  "tool_calls_count": 0
}
```

Search is allowed when any direct stage record allows `WebSearch` or `WebFetch`. Search is used when any parsed tool call name is `WebSearch` or `WebFetch`. If legacy records lack detailed `tool_calls`, fall back to `tool_calls_count` only for generic tool activity, not for `search_used=true`.

### Slice D: Skill and root-level index contract

Update `skills/llm-council-for-trae/SKILL.md`:

- Add light input-preparation rules.
- Preserve raw-only escape hatches.
- Require root-level index to state input mode.
- Require search reporting to say allowed versus used.
- Keep live / fake / fixture evidence separate.

### Slice E: README and docs downgrade subagent path

Update `README.md` and `docs/traecli-subagents.md`:

- Direct provider is daily P0.
- Subagent profile is legacy / experimental.
- `profiles/subagents.json` remains for historical artifact validation and future fixed-member experiments.
- Current model drift can break profile runs; do not present profile runs as the global default.

### Slice F: Model recommendation guardrail

Without running a large benchmark, add a deterministic recommendation rule that excludes Seed and Doubao model names from automatic recommended rosters unless the user explicitly specifies them. This protects the default recommendation from the current live roster drift observed in manual E2E.

## 5. Subagent Review Contract

After local TDD slices are green, run read-only reviewer subagents with disjoint scopes:

1. HTML / metadata reviewer: `src/llm_council_for_trae/html_export.py` and HTML tests.
2. Skill / docs reviewer: `README.md`, `skills/llm-council-for-trae/SKILL.md`, `docs/traecli-subagents.md`.
3. Evidence-contract reviewer: search reporting, model recommendation guardrail, and final brief evidence wording.

Reviewers must not edit files. They must return findings with file paths, severity, and exact contract violations.

## 6. Completion Evidence

Minimum fresh verification before claiming completion:

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

If live `traecli` is available, run only a small smoke and report it separately. If it is unavailable or too unstable, mark live smoke skipped or failed. Do not promote fake runtime, fixture checks, or unit tests as live success.
