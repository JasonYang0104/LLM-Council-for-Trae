# LCT Global Install And Skill Design

Date: 2026-06-01
Audience: future Agent, reviewer, and PM owner.

## Decision

LCT daily usage should be installed once into the user environment and then invoked from a clean problem workspace. The LCT development repository must not be cloned into the workspace that holds the user's question.

The target layout is:

```text
~/.LCT/
  src/
  docs/
  examples/
  skills/llm-council-for-trae/SKILL.md

~/.local/bin/llm-council-for-trae

~/.agents/skills/
  llm-council-for-trae -> ~/.LCT/skills/llm-council-for-trae

<clean problem workspace>/
  _lct_question.md
  .llm-council-for-trae/
  <run_id>-final.md
  <run_id>-index.md
```

## Problem

The existing README still frames the default workflow as cloning this repository in another workspace and asking an Agent to use the repository root capability. That is the wrong default for daily usage.

Putting the LCT repository in the problem workspace can expose unrelated project context to `traecli`, including LCT source code, design documents, local run artifacts, `.trae/agents/`, and `profiles/subagents.json`. The council should answer the user's question, not the accidental contents of the LCT implementation repository.

## Scope

This iteration owns:

- README quickstart and install guidance.
- A canonical user-level Skill template in `skills/llm-council-for-trae/SKILL.md`.
- A deployment guide for `~/.LCT`, the wrapper, user-level Skill installation, and clean workspace smoke.
- Makefile support for a global user install path if tests require it.
- Repository contract tests that keep the documents, Skill, and installer behavior aligned.
- PM director handoff artifacts in Markdown and HTML.

This iteration does not own:

- Runtime hardening.
- `validate` semantics.
- Model roster changes.
- HTML report structure changes.
- OpenRouter, the old Web UI, or legacy TR paths.
- Any fake-runtime result presented as live `traecli` evidence.

This iteration does own one operator-level runtime override rule for the Skill and docs: 默认 runtime 仍是 traecli，coco 只在显式 override 中使用. If `traecli models --json` returns an empty list, fails, times out, or has no structured output, the outer Agent may probe `coco` and explicitly pass `--runtime-command coco` only after recording evidence. This is a runtime override, not CLI silent fallback, and it does not change the CLI default runtime.

## Directory Responsibilities

| Directory | Responsibility | Daily LCT question runs? |
|---|---|---|
| Development repo | Code, docs, tests, PR review | No |
| `~/.LCT` | GitHub clone used as global install root | No |
| `~/.agents/skills` | User-level Agent Skill registry | No |
| Clean problem workspace | User question, run artifacts, final answer, run index | Yes |

## README Strategy

The README should put the user path first:

1. Install or update `~/.LCT` from GitHub `main`.
2. Install the CLI wrapper into `~/.local/bin/llm-council-for-trae`.
3. Install the Skill into `~/.agents/skills/llm-council-for-trae`.
4. Run LCT from a clean problem workspace with `--default-models` and `--json`.
5. Run `validate`.
6. Read `stage3/final.md` and the HTML artifact path.

The developer path should remain available but clearly labeled as development-only. `make install-local` points the wrapper at the current checkout and is not the default daily install path.

## Skill Strategy

The repository should contain a canonical Skill template at:

```text
skills/llm-council-for-trae/SKILL.md
```

Installation should symlink or copy that directory into:

```text
~/.agents/skills/llm-council-for-trae
```

The Skill must make these constraints explicit:

- Stop if the current workspace looks like the LCT source repository.
- Check for `src/llm_council_for_trae/`, `.trae/agents/`, and `profiles/subagents.json`.
- Require `traecli --version`, `traecli models --json`, and `command -v llm-council-for-trae`.
- When `traecli models --json` is empty, failed, or timed out, require the operator to record default runtime evidence before probing `coco`.
- Allow explicit `--runtime-command coco` only when `coco models --json` is non-empty, `llm-council-for-trae --runtime-command coco doctor --json` has no non-MCP blocker, and `llm-council-for-trae --runtime-command coco models --recommend --json` returns usable `recommendation.members` and `recommendation.chairman`.
- Require `llm-council-for-trae --runtime-command coco run` and `llm-council-for-trae --runtime-command coco validate` to use the same override command.
- Use `--default-models` in non-interactive Agent runs.
- Use `--json` so outer Agents can parse results.
- Always run `validate`.
- Report live `traecli` status separately from non-live or fake-runtime verification.
- Report runtime override status separately: normal path `live runtime: traecli`, explicit override path `live runtime: coco via explicit --runtime-command override`, unavailable path `live runtime: unavailable`.
- Treat `.llm-council-for-trae/` as read-only artifacts after the run.

## Install Script Strategy

Keep `install-local` as the development install. Add a separate `install-global` target with explicit parameters:

```text
LCT_DIR ?= $(HOME)/.LCT
BIN_DIR ?= $(HOME)/.local/bin
SKILLS_DIR ?= $(HOME)/.agents/skills
```

`install-global` should:

- Write a wrapper whose `PYTHONPATH` points at `$(LCT_DIR)/src`.
- Install the Skill from `$(LCT_DIR)/skills/llm-council-for-trae`.
- Refuse to overwrite an existing non-symlink Skill directory.

This keeps the dev wrapper and daily-use wrapper separate and testable.

## Verification Strategy

Use repository contract tests for static behavior:

- README no longer describes cloning this repository into the problem workspace as the default path.
- README, deployment guide, and Skill agree on `~/.agents/skills`.
- No user-facing install doc uses the legacy Trae user skill registry path.
- `make install-local` is documented as development-only.
- The Skill template exists and contains the hard workflow constraints.
- `make install-global` creates a wrapper pointing to `~/.LCT/src` or the provided `LCT_DIR`, not the current checkout.

Use the standard project verification before completion:

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

When live `traecli` is available, additionally run:

```bash
rm -rf /tmp/lct-live-smoke
mkdir -p /tmp/lct-live-smoke
cd /tmp/lct-live-smoke
cp ~/.LCT/examples/question.md _lct_question.md
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input _lct_question.md --default-models --json
llm-council-for-trae validate <run_id> --json
```

If live `traecli` is unavailable, record the blocker and do not relabel fixture or fake-runtime results as live smoke.

When default `traecli` is specifically blocked by an empty/failed/timed-out model list but `coco` may be available, verify the explicit override probe before deciding whether to skip live smoke:

```bash
traecli --version
traecli models --json
coco --version
coco models --json
llm-council-for-trae --runtime-command coco doctor --json
llm-council-for-trae --runtime-command coco models --recommend --json
```

The `models --recommend --json` payload must expose `recommendation.members` and `recommendation.chairman`; do not infer the recommended roster from the raw model list alone.

## Subagent Review Contract

After implementation, use read-only subagents with this shared contract:

- Scope: README, deployment guide, Skill template, Makefile install behavior, and repository contract tests.
- Boundary: no runtime code, no `.llm-council-for-trae/`, no unrelated PR skill files.
- Output: `pass` or `fail`, P1 findings, P2 findings, and file/line references.
- Acceptance: no contradiction between the user install path, Skill path, wrapper target, clean workspace rule, local verification, live smoke, and fake-runtime wording.
- Escalation: any unclear or conflicting install path returns to the main thread.

Reviewer roles:

1. Fresh Install Reviewer.
2. Workspace Isolation Reviewer.
3. Operational Consistency Reviewer.
