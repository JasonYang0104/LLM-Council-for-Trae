# Notes

## 2026-06-01 LCT Global Install And Skill Iteration

- Started from a separate worktree on `origin/main` because the original workspace had unrelated dirty/untracked PR skill files and deleted `.codex/skills/*` files. Those files are not part of this branch.
- Read the requested handoff, deployment guide draft, original `AGENTS.md`, README, and Makefile before editing. The clean worktree does not track `AGENTS.md`, so the original workspace copy is treated as an instruction source, not a file to change.
- Scope is limited to global install, user-level Skill, documentation consistency, installer support, and tests. Runtime behavior and `validate` semantics are out of scope.
- The Skill path is `/Users/bytedance/.agents/skills`; old `~/.trae/skills` wording is forbidden in this iteration's user-facing install docs.
- Test plan uses repository contract tests because this iteration changes installation/documentation behavior more than runtime code. The tests will still run through `make test` so the contract stays in the normal verification path.
- TDD slice 1 starts with a README contract test. The expected RED state is the old quickstart phrase that tells users to clone the repository into another workspace.
- TDD slice 1 GREEN changed only the README quickstart: default use is now `~/.LCT` + global wrapper + `/Users/bytedance/.agents/skills` + clean problem workspace. `make install-local` is now explicitly documented as development-only.
- TDD slice 2 starts with a Skill template contract test. Expected RED state: `skills/llm-council-for-trae/SKILL.md` is missing.
- TDD slice 2 GREEN adds the canonical user-level Skill template under `skills/llm-council-for-trae/`. It intentionally does not live under `.codex/skills/`, because this is for LCT users, not Codex development helpers.
- TDD slice 3 starts with a cross-doc path consistency test. Expected RED state: `docs/lct-deployment-guide-20260601.md` is missing from the clean `origin/main` branch.
