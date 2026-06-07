# LCT UX Evidence Hardening Test Plan

Date: 2026-06-02
Audience: implementer, reviewer, and future maintainer.

## 1. Test Philosophy

Use repository contract tests and public rendering behavior. Avoid tests that lock implementation details unless the implementation detail is itself a published artifact contract.

This plan follows TDD: one failing behavior test, one minimal implementation, then repeat.

## 2. Slice A: HTML Input Prompt Collapse

Public behavior:

- HTML report includes `<details id="input-prompt" class="question-context">`.
- That details element has no `open` attribute.
- The summary text includes `输入提示词`.
- The original input text remains in the HTML source.
- Copy payload `markdown` still includes the input text.
- Final answer remains inside `<article id="final-answer">`.
- Existing appendices A to E remain collapsed.

Suggested test location:

- `tests/test_core.py`, near the existing HTML export test.

Expected RED:

- Current HTML contains `<p class="question-context">`.
- No `id="input-prompt"` exists.

## 3. Slice B: Search Allowed Versus Search Used

Public behavior:

- Search summary reports `search_allowed=true` when any stage record has `allowed_tools` containing `WebSearch` or `WebFetch`.
- Search summary reports `search_used=true` only when stage metadata includes a parsed tool call named `WebSearch` or `WebFetch`.
- A run with `search_enabled`, `allowed_tools=["WebSearch", "WebFetch"]`, and `tool_calls_count=0` must report `search_allowed=true` and `search_used=false`.
- A run with one `WebSearch` tool call must report `search_used=true` and increment `web_tool_calls_count`.
- `forbidden_tool_calls` remains separate from search usage.

Suggested test location:

- `tests/test_core.py` for pure summary behavior.
- HTML export test should assert the report displays allowed and used separately.

Expected RED:

- Current HTML only shows generic provider trace rows; no explicit search summary exists.

## 4. Slice C: Skill Input Mode Contract

Public behavior:

- Skill allows Agent-side light intent understanding and prompt shaping by default.
- Skill requires preserving user original input in structured mode.
- Skill lists raw-only triggers: `按原始输入`, `不要改写`, `只用原文`, `评估 LCT 对原始问题的理解`.
- Skill requires final root-level index to state input mode.
- Skill requires search allowed / search used reporting.

Suggested test location:

- `tests/test_global_install_skill_docs.py`.

Expected RED:

- Current Skill does not mention raw / structured input modes.
- Current Skill does not require search used reporting.

## 5. Slice D: README And Subagent Downgrade

Public behavior:

- README no longer advertises fixed subagent members as a main highlight.
- README labels subagent profile as legacy / experimental.
- `docs/traecli-subagents.md` states direct provider is daily path and profile runs can drift with model availability.
- Docs do not delete validation evidence or claim subagent validation is obsolete.

Suggested test location:

- `tests/test_global_install_skill_docs.py`.

Expected RED:

- Current README highlight says `固定 subagent 成员`.
- Current subagent docs call subagent provider P2 but do not explicitly downgrade it.

## 6. Slice E: Recommendation Guardrail

Public behavior:

- `recommend_model_choice` excludes names containing `Seed` or `Doubao` from automatic recommended members and chairman when other usable models exist.
- Explicit user-provided `--members` / `--chairman` remains unaffected.
- OpenRouter exclusion remains in place.
- If every available model is excluded by policy, recommendation may fall back to usable names rather than returning an empty roster.

Suggested test location:

- Add focused tests for `model_selection.recommend_model_choice`.

Expected RED:

- Current fallback fill loop can include `Seed-Dogfooding-2.0`.

## 7. Subagent Review Checks

After TDD slices are green, run read-only reviewers:

- HTML reviewer: verify source/copy payload/final-answer behavior and no privacy overclaim.
- Docs reviewer: verify raw/structured, subagent downgrade, and clean workspace language.
- Evidence reviewer: verify search allowed / used and Seed/Doubao guardrail are not overstated.

Reviewers return only findings. Main thread integrates or rejects findings with explicit reasons.

## 8. Final Verification

Required:

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Optional if live runtime is available and cheap:

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
```

Live run is optional in this iteration because the handoff explicitly says not to turn this into another large model stability test.
