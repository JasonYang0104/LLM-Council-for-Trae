# M7 任务卡：ACP 默认切换（交执行 Agent）

- 日期：2026-06-12
- 上游：`docs/lct-acp-promotion-probe-20260612.md`（M6 转正实测，CONDITIONAL GO）；用户裁决 2026-06-12：ACP 转为主路。
- 工作区：worktree `/Users/bytedance/Documents/AI Coder/COCO-llm-council-acp-m7-20260612`，分支 `codex/lct-acp-m7-default-switch-20260612`（从 `main @ bd296ff` 切出）
- 流程约束：纯本地，不推 GitHub、不开 PR；完成后停在分支等架构师 review。
- 回滚锚点：`pre-acp-m7` 已打在 main。

## 背景与基线事实

- `main @ bd296ff`：M1–M6 已合入，`make test` 368 个 unittest 全绿。
- M6 实测：P1/P2/P3 三组 ACP `complete_ok_final`，耗时 0.77x–1.49x；L1 长任务 GPT-5.5 两次 timeout 降级 `usable_degraded_final`（backfill 正常，usable_final true）。
- 当前默认：`cli.py:72` `--runtime-backend` default="direct"。
- 已知约束：`cli.py:251` 在 `runtime_backend=acp` + `provider_mode=subagent` 时 raise ValueError。

## 目标

默认 backend 切换 direct → acp；direct 降级为显式回退选项；ACP 启动失败时用户可见的退回提示；README/Skill 文档补 ACP 主路说明。**不引入任何新抽象、新配置文件字段、新超时机制。**

## 改动清单

1. **默认值切换**：`cli.py` `--runtime-backend` default `"direct"` → `"acp"`，help 文案改为 ACP 为默认、direct 为回退（措辞如实，不写"experimental"）。
2. **subagent 兼容（红线：不得破坏现有 subagent 用户）**：`provider_mode=subagent` 且用户**未显式**传 `--runtime-backend` 时，backend 自动解析为 direct（不报错、不静默歧义——manifest 如实记录 direct）；用户**显式**传 `--runtime-backend acp` + subagent 时维持现有 ValueError。实现上需要区分"默认值"与"显式传参"（argparse 可用 default=None 后置解析等惯用法，自选最小实现）。
3. **启动失败退回提示**：当成员 meta `acp_startup_status: failed` 导致 run 失败时，run summary 的 `failures[]` 追加一条可读建议（简体中文或英文与现有 failures 风格一致）："ACP startup failed; retry with --runtime-backend direct to fall back to the direct runtime."（精确措辞可调，必须含 `--runtime-backend direct` 字样）。只追加提示文本，不改失败语义、不自动回落。
4. **HTML backend 可见性**：核对 M4 已有的 summary runtime backend 展示；若 run 级 backend（manifest config）在 HTML 头部/summary 不直接可见，补一个标注。已可见则不动，报告里说明核对结论。
5. **README + Skill 文档**：ACP 为默认主路的说明、direct 回退方式（`--runtime-backend direct`）、ACP 启动失败的排查两行（traecli 安装/PATH、acp serve 可用性）、已知行为一条（长任务下个别模型可能超时，由 backfill 兜底并在 verdict 如实降级）。安装契约（origin/main 安装路径）不动。
6. **契约测试更新（最小、逐项声明）**：`test_runtime_backend_contract.py` 中断言默认 backend 的用例 direct → acp；新增用例：subagent + 未显式 backend → direct；subagent + 显式 acp → ValueError；acp_startup_failed → failures[] 含退回提示。
7. **golden**：golden 生成路径显式固定 `--runtime-backend direct`（若当前依赖默认值）；目标是 `tests/golden/` **零内容漂移**——若 harness 需要加显式参数，作为 harness 改动声明，golden 文件本身字节不变。若发现 golden 内容必须变，停下来在报告里说明原因，不要擅自重生成。

## 边界（不得越过）

1. `EXPECTED_META_KEYS` 44 键不变；不新增 meta/manifest 字段。
2. 不实现：配置文件级 default_runtime_backend 覆盖（M6 报告 9.1.3 的建议**不采纳**）、自适应 timeout（9.2 长期方案不采纳）、transcript 压缩/大小上限（9.5 不采纳）。这些记入报告"未采纳建议"即可。
3. 不改 timeout 默认值；GPT-5.5 长任务超时只进文档"已知行为"，不进代码。
4. 不改 validate 逻辑（M4 交叉触发门已 backend 无关）。
5. M1–M5 既有测试除第 6 条声明的默认值断言外零改动。

## 验收标准

1. `make test` 全绿（368 + 新增用例数）。
2. 不带任何 backend 参数的 `run --help` 显示 acp 为默认；本机最小 live smoke：`run --input <一句话问题> --default-models --timeout 300 --json`（不带 backend 参数）实跑一次走 ACP，validate `complete_ok_final`，并验证 manifest `runtime_backend=acp`。
3. `--runtime-backend direct` 实跑一次最小 smoke，确认回退路径完好。
4. subagent 双用例（自动 direct / 显式 acp 报错）测试绿。
5. `git diff main..HEAD -- tests/golden/` 为空。
6. `git diff --check` 通过；notes.md 追加 M7 节；红绿提交粒度，停在分支。

## 汇报要求

简体中文：改动逐条与测试总数、两次 live smoke 的 run_id 与 verdict、golden 零漂移证明、契约测试改动精确范围、未采纳建议清单、commit SHA、遗留风险。如实报告。
