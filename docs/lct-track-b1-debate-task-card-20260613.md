# B1 任务卡：Stage 2.5 质询轮（debate）

- 日期：2026-06-13
- 分支：`codex/lct-track-b1-debate-20260613`
- 工作区：`/Users/bytedance/Documents/AI Coder/COCO-llm-council-track-b1-20260613`
- 上游：`docs/lct-track-b-execution-architecture-20260613.md`、`docs/lct-debate-stats-architecture-20260611.md` §1、ADR-0003
- 回滚锚：`pre-track-b1` = `4d766c9504b9b35bd73062dbfc4e8ccde924e2be`

## 目标

实现 opt-in `--debate`：在 Stage 2 匿名互评之后、Stage 3 主席综合之前，插入固定一轮 Stage 2.5 质询/答辩。每个有效 Stage 1 成员读取针对自己的匿名批评材料，输出一份有界答辩；主席综合时同时读取 Stage 1 原答案、Stage 2 批评排序和 Stage 2.5 答辩。

默认不启用 debate，未传 `--debate` 时现有全链路行为与 golden 保持逐字节一致。

## 范围

1. `CouncilConfig` / CLI
   - 新增 `debate_enabled: bool = False`。
   - `run` 子命令新增 `--debate`，不新增 `--debate-rounds`。
   - `config.json` / manifest config 记录 `debate_enabled`。

2. Stage 2.5 orchestration
   - 新增 `build_stage2_5_prompt()`：输入用户问题、目标成员自己的 `Response X`、有效 Stage 2 评审 prose。
   - 评审材料必须去掉 `FINAL RANKING:` 及之后内容。
   - 评审者匿名为 `评审 1..K`，prompt 内不得出现任何在场成员模型名。
   - 成员知道自己的 `Response X` 标签，但不知道其他答案归属。
   - 输出为自由 Markdown，只要求非空。

3. Artifact / manifest
   - 新增按需目录 `stage2_5/`。
   - 成功或失败都写 `stage2_5/<label>.rebuttal.prompt.md`、`stage2_5/<label>.rebuttal.md`、`stage2_5/<label>.meta.json`，并按 runtime 写 `.traecli.stream.jsonl` 或 `.acp.transcript.jsonl` sidecar。
   - manifest 新增 `stages.stage2_5[]` 与 `metadata.debate`：
     - `enabled`
     - `rounds: 1`
     - `participants`
     - `completed`
     - `failed`
     - `failed_all`
     - `review_material: stage2_reviews_ranking_stripped_reviewer_anonymized`

4. 失败语义
   - 单成员答辩失败/超时：记录 warning 和 failed item，不影响 quorum，不降级 run。
   - 全部答辩失败：`metadata.debate.failed_all = true`，Stage 3 按无答辩路径继续。
   - 不做 rebuttal backfill；候补模型不能替别人辩护。

5. Stage 3
   - `build_stage3_prompt()` 新增可选 `rebuttal_results`。
   - `None` 或空列表时输出必须与现行为一致。
   - 有答辩时新增“阶段 2.5 - 成员答辩”段，要求主席把答辩中的让步/修正视为该成员最新立场。

6. Validation / schema
   - `STAGES_SCHEMA` 接受 additive `stage2_5`。
   - `validate_run()` 在 `metadata.debate.enabled` 时校验：
     - completed/participants 都属于有效 Stage 1 成员。
     - completed item 的 rebuttal 文件存在且非空。
     - legacy run 无 debate 字段不失败。
   - `stage2_5` 的 manifest record 与 meta 必须进入 M4 ACP evidence hard gate：只要 config / stage record / meta 任一声明 ACP，就触发 ACP transcript 校验。

7. HTML
   - 新增折叠区“成员答辩”，按 `Response X` 渲染已有答辩。
   - 摘要区展示 debate 启用状态、完成数、失败数。
   - HTML export 只读 artifacts，不重算、不调用模型。

## 验收

1. TDD / 单元
   - `--debate` 未启用时，Stage 3 prompt 与现有 prompt 逐字节一致。
   - `--debate` 解析进 config。
   - Stage 2.5 prompt 不含 `FINAL RANKING:`，不含任何在场模型名。
   - 单成员答辩失败不阻断 Stage 3；全部失败仍产出 Stage 3。
   - 不存在 rebuttal backfill。
   - validate 覆盖 `stage2_5` 文件、参与者和 ACP evidence gate。
   - HTML 出现成员答辩折叠区和摘要状态。

2. Golden / fixture
   - debate-off 现有 golden 不漂移。
   - 新增 debate-on fixture 或 focused full-run 测试，连跑稳定。

3. 命令

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

4. Runtime smoke
   - direct：至少一次 `--runtime-backend direct --debate` fake/deterministic smoke。
   - acp：默认 backend live smoke 可用时跑 `--debate` live E2E 并 `validate`；如果 live runtime 不可用，明确 skipped 和阻断点，不把 fake 结果说成 live。

## 出口标准

- 所有验收命令通过。
- `validate` 对 Stage 2.5 的 ACP 证据路径有负向测试。
- 最终汇报列出 commit、验证命令、是否完成 live smoke、遗留风险。
