# Notes

## 2026-06-01 LCT Global Install And Skill Iteration

- Started from a separate worktree on `origin/main` because the original workspace had unrelated dirty/untracked PR skill files and deleted `.codex/skills/*` files. Those files are not part of this branch.
- Read the requested handoff, deployment guide draft, original `AGENTS.md`, README, and Makefile before editing. The clean worktree does not track `AGENTS.md`, so the original workspace copy is treated as an instruction source, not a file to change.
- Scope is limited to global install, user-level Skill, documentation consistency, installer support, and tests. Runtime behavior and `validate` semantics are out of scope.
- The Skill path is `/Users/bytedance/.agents/skills`; old `~/.trae/skills` wording is forbidden in this iteration's user-facing install docs.
