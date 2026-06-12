# M6 任务卡：ACP 转正实测（go/no-go 证据采集，交执行 Agent）

- 日期：2026-06-12
- 上游：`docs/lct-acp-migration-architecture-20260611.md` §4.4（默认切换判据）；用户裁决 2026-06-12：ACP 转为主路（默认 backend），本阶段为转正前的证据采集。
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m6-20260612`，分支 `codex/lct-acp-m6-promotion-probe-20260612`（从 `main @ 88f9836` 切出）
- 流程约束：纯本地测试与报告，**零产品代码改动**；不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 性质：本阶段产出是一份 go/no-go 报告 + 实测证据，默认值切换本身属 M7。

## 背景与基线事实

- `main @ 88f9836`：M1–M5 已合入并推 GitHub，`make test` 368 个 unittest 全绿。
- ACP live 实测记录目前仅 2 次：M5 内部 E2E（run-20260611T230225，complete_ok_final，497 checks 0 failures）+ 用户外部隔离 workspace E2E（lct-20260612-082820，complete_ok_final，零 backfill）。样本不足以支撑默认切换。
- §4.4 转正判据：≥3 组 direct/ACP 同题对照 + 1 次代表性长任务 E2E + 延迟/失败率对比 + 无进程残留 + validate 硬门全过。
- 本机 traecli 可用、已登录。direct 与 ACP 调的是同一批底层模型，对照的是**管道行为**差异，不是模型能力差异。

## 测试矩阵（4 组对照 = 8 次 live run）

每组同一输入分别跑两次：

```
llm-council-for-trae run --input <file> --default-models --timeout 300 --json                          # direct
llm-council-for-trae run --input <file> --default-models --timeout 300 --json --runtime-backend acp   # acp
```

每次 run 后立即 `validate <run_id> --json`（validate 不带 backend 参数，硬门自动交叉触发）。

- **P1 事实题**（短，答案可判对错）：自拟一个有确定答案的事实/计算问题。
- **P2 推理题**（中）：自拟一个需要多步推理的问题。
- **P3 开放论述题**（中长）：自拟一个开放分析问题。
- **L1 长任务**（代表性长 E2E）：构造一个长输入（≥3000 字材料 + 综合分析要求，可用本 repo 的某篇架构文档作材料），逼近真实重度使用。

输入文件与所有 run artifacts 留在 worktree 内（`.llm-council-for-trae/runs` 不进 commit；输入文件与报告进 commit）。

## 每组采集指标（写入报告对照表）

1. run exit code / `status`；validate `verdict`（期望 `complete_ok_final`）。
2. 成员有效数、失败模型数、backfill 次数。
3. 总 wall-clock 与分阶段耗时（manifest 时间戳推算即可，注明口径）。
4. ACP 侧证据完整性：每个 call 的 `*.acp.transcript.jsonl` 存在且 parser 可解析、`runtime_backend=acp` 全阶段一致。
5. 工具策略：`member_tool_mode` 与工具调用计数两侧一致。
6. 每组跑完后 `pgrep -f "acp serve"` 与孤儿 `traecli` 进程检查（证据记录输出）。

## go/no-go 判据（客观，逐项打勾）

GO 需全部满足：

1. 4/4 组 ACP run 的 validate verdict 为 `complete_ok_final`；个别成员模型 live 失败按 backfill 语义如实记录，但 ACP 侧失败率不得高于同组 direct。
2. L1 长任务 ACP 侧 `usable_final: true`。
3. ACP 总耗时 ≤ 同组 direct 的 2 倍（4 组中至少 3 组满足；超出的组如实记录原因分析）。
4. 全部 run 结束后零进程残留。
5. 零 validate failures（warnings 如实记录并逐条评估）。

任一不满足 → no-go 报告：写明失败项、证据、修复建议，**不要尝试自行修代码**。

## 产出

`docs/lct-acp-promotion-probe-20260612.md`：测试矩阵结果对照表、逐项判据打勾、go/no-go 结论、原始证据摘录（run_id、validate verdict、耗时、pgrep 输出）、遗留风险与对 M7 的建议（含 ACP 启动失败时的报错文案素材：实测一次 traecli 不可用场景的真实错误输出，供 M7 设计「如何提示用户退回 direct」）。

## 边界（不得越过）

1. 零 `src/` / `tests/` 改动；零 golden 改动；不打 tag。
2. 不评判两侧答案"谁写得更好"（同模型不同管道，内容差异是噪声）——只比结构化指标。
3. 模型 live 偶发失败不算 M6 失败，如实记录；但需重跑确认是否复现（同组最多重跑 1 次，重跑要声明）。
4. 报告内不得出现绝对路径个人目录之外的敏感信息；run_id、耗时、verdict 均可记录。

## 验收标准

1. 8 次 live run（+ 声明过的重跑）全部有 run_id、validate verdict、耗时记录。
2. go/no-go 结论有逐项判据证据支撑。
3. `git status` 干净（除报告与输入文件的 commit）；`make test` 全绿（确认零代码改动未破坏基线）。
4. 单 commit（`docs: ACP promotion probe report`），停在分支。

## 汇报要求

简体中文：go/no-go 结论先行，4 组对照表（verdict / 耗时 / 失败率 / 残留），判据逐项 pass/fail，异常与重跑声明，commit SHA，对 M7 的具体建议。如实报告，不粉饰。
