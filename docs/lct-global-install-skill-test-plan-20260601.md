# LCT Global Install And Skill Test Plan

Date: 2026-06-01

## Testing Principle

Use TDD vertical slices. Each slice starts with one failing repository contract test, then the smallest documentation, Skill, or Makefile change needed to pass it.

The tests should verify user-observable contracts through public repository files and commands. They should not inspect private implementation details that can change without changing the install behavior.

## Slice 1: README Default Workflow

Behavior:

- README no longer tells users to clone this repository into another workspace as the default Agent workflow.
- README puts the global install path first: `~/.LCT`, `~/.local/bin/llm-council-for-trae`, `/Users/bytedance/.agents/skills`, and a clean problem workspace.
- README keeps development usage, but labels `make install-local` as development-only.

RED:

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_readme_defaults_to_global_install_and_clean_workspace -v
```

Expected initial failure: README still contains the old clone-workspace default.

GREEN:

- Rewrite README Quickstart.
- Keep runtime, model selection, artifact, and validation sections intact unless wording must be aligned.

## Slice 2: Canonical Skill Template

Behavior:

- `skills/llm-council-for-trae/SKILL.md` exists.
- It has frontmatter with `name` and `description`.
- It requires `--default-models`, `--json`, and `validate`.
- It stops when the current workspace looks like the LCT source repo.
- It checks for `src/llm_council_for_trae/`, `.trae/agents/`, and `profiles/subagents.json`.
- It reports live `traecli` availability separately from fake or non-live validation.

RED:

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_skill_template_has_required_workflow_contract -v
```

Expected initial failure: the Skill template file does not exist.

GREEN:

- Add `skills/llm-council-for-trae/SKILL.md`.
- Do not put this user-level Skill under `.codex/skills/`.

## Slice 3: Documentation Path Consistency

Behavior:

- README, deployment guide, and Skill all use `/Users/bytedance/.agents/skills`.
- User-facing install docs do not use the stale `~/.trae/skills` path.
- The deployment guide exists and states that the development repo, `~/.LCT`, and problem workspace are separate directories.
- Local verification, live smoke, validate, and fake-runtime verification are not collapsed into one success claim.

RED:

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_docs_use_current_user_skill_path_and_no_stale_skill_path -v
```

Expected initial failure: the deployment guide is absent on `origin/main`.

GREEN:

- Add `docs/lct-deployment-guide-20260601.md`.
- Align README and Skill wording with the deployment guide.

## Slice 4: Global Installer

Behavior:

- `make install-global` writes a wrapper to `$(BIN_DIR)/llm-council-for-trae`.
- The wrapper points at `$(LCT_DIR)/src`, not `$(CURDIR)/src`.
- `install-global` installs the user-level Skill from `$(LCT_DIR)/skills/llm-council-for-trae` into `$(SKILLS_DIR)/llm-council-for-trae`.
- `make install-local` remains the development-only target and keeps pointing at the current checkout.

RED:

```bash
PYTHONPATH=src python3 -m unittest tests.test_global_install_skill_docs.GlobalInstallSkillDocsTests.test_make_install_global_writes_global_wrapper_and_skill_link -v
```

Expected initial failure: `install-global` does not exist.

GREEN:

- Add `install-global` and `install-skill` Makefile targets.
- Keep target parameters overridable for tests: `LCT_DIR`, `BIN_DIR`, and `SKILLS_DIR`.
- Refuse to overwrite an existing non-symlink Skill directory.

## Slice 5: Final Contract Sweep

Behavior:

- All repository contract tests pass together.
- Existing core/runtime tests still pass.
- The branch has no whitespace errors.

Commands:

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

Optional live smoke, only if live `traecli` and global LCT command are available:

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

If live smoke cannot run, record exactly which prerequisite failed and keep the result marked as skipped. Do not substitute fixture or fake-runtime E2E for live smoke.

## Subagent Acceptance Checks

After the TDD slices pass, run three read-only subagent reviews:

| Reviewer | Scope | Must answer |
|---|---|---|
| Fresh Install Reviewer | README + deployment guide | Can a new Agent install from GitHub `main` into `~/.LCT` without using the development checkout? |
| Workspace Isolation Reviewer | README + Skill + deployment guide | Is the clean problem workspace rule enforceable, including source repo guard markers? |
| Operational Consistency Reviewer | README + deployment guide + Skill + Makefile + tests | Do the docs and installer targets contradict each other anywhere? |

Each review must return:

```text
结论：pass / fail
P1 findings:
P2 findings:
引用文件与行号:
```
