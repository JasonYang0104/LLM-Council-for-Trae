# LCT Global Install And Clean Workspace Deployment Guide

Date: 2026-06-01
Audience: Agent operator, PM owner, and future maintainer.

## 1. Purpose

`LLM-Council-for-Trae` is a local CLI that calls `traecli` to run a three-stage council workflow:

1. Stage 1: member models answer independently.
2. Stage 2: members review anonymous answers.
3. Stage 3: the chairman synthesizes `stage3/final.md`.
4. HTML export: deterministic rendering from saved artifacts.

This guide defines the daily user install path. It is not a runtime hardening plan and does not change `validate` semantics.

## 2. Core Rule

Do not put the LCT development repository inside the workspace that contains the user's question.

The development repo contains source code, design notes, tests, `.trae/agents/`, `profiles/subagents.json`, and possibly dirty local artifacts. If `traecli` sees that context while answering an unrelated question, the council can be contaminated by LCT implementation details.

Keep three directories separate. 中文口径：开发仓库、`~/.LCT` 全局安装目录、干净问题 workspace 必须物理分离。

| Directory | Purpose | Should user questions run here? |
|---|---|---|
| Development repo | Code, docs, tests, review | No |
| `~/.LCT` | Global GitHub clone used by the wrapper | No |
| Clean problem workspace | User question and run artifacts | Yes |

## 3. Target Layout

```text
~/.LCT/
  src/llm_council_for_trae/
  examples/
  docs/
  skills/llm-council-for-trae/SKILL.md

~/.local/bin/llm-council-for-trae

/Users/bytedance/.agents/skills/
  llm-council-for-trae -> ~/.LCT/skills/llm-council-for-trae

<clean problem workspace>/
  _lct_question.md
  .llm-council-for-trae/
  <run_id>-final.md
  <run_id>-index.md
```

## 4. Prerequisites

Check `traecli` first:

```bash
traecli --version
traecli models --json
```

`traecli models --json` must return a non-empty model list. `traecli doctor --json` is useful, but LCT direct execution does not depend on external MCP servers. If `doctor` only reports MCP initialization errors while `traecli --version` and `traecli models --json` work, treat that as environment noise and let LCT record it in artifacts.

If `traecli` is not installed or not logged in, use `docs/traecli-installation-and-paths.md`.

Runtime override rule: 默认 runtime 仍是 traecli，coco 只在显式 override 中使用. If `traecli models --json` returns an empty list, fails, times out, or produces no structured output, the operator may probe `coco` before declaring live LCT unavailable. This is a runtime override, not CLI silent fallback.

The probe must record default-entry evidence and then check the override entry:

```bash
traecli --version
traecli models --json
coco --version
coco models --json
llm-council-for-trae --runtime-command coco doctor --json
llm-council-for-trae --runtime-command coco models --recommend --json
```

Only use `--runtime-command coco` when `coco models --json` is non-empty, `doctor` has no non-MCP blocking error, and the recommendation payload has usable `recommendation.members` and `recommendation.chairman`. The run and validate commands must use the same runtime command:

```bash
llm-council-for-trae --runtime-command coco run --input _lct_question.md --default-models --json
llm-council-for-trae --runtime-command coco validate <run_id> --json
```

## 5. Install Or Update LCT In `~/.LCT`

Fresh install:

```bash
git clone https://github.com/JasonYang0104/LLM-Council-for-Trae.git ~/.LCT
```

Update an existing install:

```bash
git -C ~/.LCT fetch origin --prune
git -C ~/.LCT checkout main
git -C ~/.LCT pull --ff-only origin main
```

Verification:

```bash
test -d ~/.LCT/.git
test -d ~/.LCT/src/llm_council_for_trae
git -C ~/.LCT remote get-url origin
git -C ~/.LCT rev-parse HEAD
git -C ~/.LCT rev-parse origin/main
git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main
LOCAL_HEAD="$(git -C ~/.LCT rev-parse HEAD)"
GITHUB_MAIN="$(git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main | awk '{print $1}')"
test "$LOCAL_HEAD" = "$GITHUB_MAIN"
git -C ~/.LCT status --short
git -C ~/.LCT log --oneline -3
```

For a user request to install the latest LCT from GitHub main, `~/.LCT HEAD == GitHub refs/heads/main` is required. The operator notes must record each actual command, exit code, key stdout/stderr, and pass/fail result, including the GitHub SHA comparison.

Keep `~/.LCT` clean. Do development work in a separate development repo or worktree.

## 6. Install The CLI Wrapper And Skill

Use the Makefile target from the global checkout:

```bash
make -C ~/.LCT install-global
```

This writes `~/.local/bin/llm-council-for-trae` with `PYTHONPATH` pointing at `~/.LCT/src`, then installs the Skill link at `/Users/bytedance/.agents/skills/llm-council-for-trae`.

Equivalent manual wrapper command:

```bash
mkdir -p ~/.local/bin

cat > ~/.local/bin/llm-council-for-trae << 'EOF'
#!/bin/sh
PYTHONPATH="$HOME/.LCT/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m llm_council_for_trae.cli "$@"
EOF

chmod +x ~/.local/bin/llm-council-for-trae
```

Verification:

```bash
command -v llm-council-for-trae
head -5 "$(command -v llm-council-for-trae)"
grep -F '.LCT/src' "$(command -v llm-council-for-trae)"
llm-council-for-trae --help
PYTHONPATH="$HOME/.LCT/src${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from pathlib import Path
import llm_council_for_trae.contribution_map as cm

source = Path(cm.__file__).resolve()
expected = (Path.home() / ".LCT" / "src").resolve()
print(source)
assert str(source).startswith(str(expected)), source
assert hasattr(cm, "extract_contribution_map")
assert hasattr(cm, "strip_contribution_map_fence")
PY
```

Do not accept an old uv tool wrapper, `site-packages` import, or stale development checkout as a fresh GitHub main install. `llm-council-for-trae --version` alone is not sufficient freshness evidence because the version can stay unchanged across source-only fixes. If the wrapper path, `.LCT/src` grep, Python import source, or `extract_contribution_map` / `strip_contribution_map_fence` assertions fail, rerun `make -C ~/.LCT install-global` and repeat the checks before any E2E run.

`make install-local` is development-only. It writes a wrapper that points at the current checkout's `src/`, which is exactly what a developer wants and exactly what daily users should avoid.

## 7. Verify The User-Level Skill

The canonical Skill template lives in:

```text
~/.LCT/skills/llm-council-for-trae/SKILL.md
```

`make install-global` links it into the user-level Agent Skill directory. Manual equivalent:

```bash
mkdir -p /Users/bytedance/.agents/skills
ln -sfn ~/.LCT/skills/llm-council-for-trae /Users/bytedance/.agents/skills/llm-council-for-trae
```

Verification:

```bash
test -f /Users/bytedance/.agents/skills/llm-council-for-trae/SKILL.md
test "$(readlink /Users/bytedance/.agents/skills/llm-council-for-trae)" = "$HOME/.LCT/skills/llm-council-for-trae"
```

The Skill tells the outer Agent to reject LCT source repositories as problem workspaces, require `--default-models`, require `--json`, run `validate`, and report live `traecli` status separately from fake or non-live checks.

## 8. Run From A Clean Problem Workspace

Create or enter a workspace that only contains the question and expected local outputs:

```bash
mkdir -p ~/workspaces/lct-questions
cd ~/workspaces/lct-questions
```

This workspace should not contain:

- LCT repo source.
- `src/llm_council_for_trae/`.
- `.trae/agents/`.
- `profiles/subagents.json`.
- unrelated project files unless the question explicitly requires them.

Ask the Agent:

```text
使用 LCT，回答："""<你的问题>"""
```

The Agent should:

1. Write `_lct_question.md`.
2. Run `llm-council-for-trae run --input _lct_question.md --default-models --json`, unless the prerequisite checks justified explicit `llm-council-for-trae --runtime-command coco run --input _lct_question.md --default-models --json`.
3. Run `llm-council-for-trae validate <run_id> --json`, or `llm-council-for-trae --runtime-command coco validate <run_id> --json` for the explicit override path.
4. Read `.llm-council-for-trae/runs/<run_id>/stage3/final.md`.
5. Write `<run_id>-final.md` and `<run_id>-index.md` in the problem workspace root.
6. Report run status, validate status, HTML path, failed models, timeout, live runtime, and whether runtime override was used. Normal path reports `live runtime: traecli`; override path reports `live runtime: coco via explicit --runtime-command override`; non-live path reports `live runtime: unavailable`.

## 9. Validation Boundaries

Do not collapse these checks into one claim:

| Check | Runs where | Proves |
|---|---|---|
| Local tests | Development repo | Code and repository contracts pass |
| `validate` | Any run artifact store | Artifacts satisfy schema and consistency contracts |
| User install smoke | Clean problem workspace | `~/.LCT` + wrapper + Skill path works |
| live smoke | Clean problem workspace with working `traecli` | Real model execution worked |
| fake runtime | Test fixture or fake provider | Non-live code path works |

Before claiming the branch is complete, run:

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

If live `traecli` is available, run:

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

If live `traecli` is unavailable, mark live smoke as skipped and name the missing prerequisite. Do not say fake runtime, fixtures, unit tests, or repository contract tests are live smoke. 中文口径：不要把 fake runtime 结果说成 live smoke，也不要把它说成 live `traecli` 结果。

## 10. Upgrade And Uninstall

Upgrade:

```bash
git -C ~/.LCT fetch origin --prune
git -C ~/.LCT checkout main
git -C ~/.LCT pull --ff-only origin main
llm-council-for-trae --help
llm-council-for-trae doctor --json
```

Uninstall:

```bash
rm -rf ~/.LCT
rm -f ~/.local/bin/llm-council-for-trae
rm -rf /Users/bytedance/.agents/skills/llm-council-for-trae
```

Uninstalling LCT does not remove existing `.llm-council-for-trae/` run artifacts in problem workspaces.

## 11. Known Limits

- Stage 1 quorum retry remains future work.
- `make install-local` remains development-only.
- live smoke depends on current `traecli` authentication, model availability, and provider stability.
- HTML export remains deterministic and artifact-only; it must not be merged with chairman synthesis.
