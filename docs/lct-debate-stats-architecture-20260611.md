# Track B 深化设计：质询轮（debate）与横评系统化（stats）

- 日期：2026-06-11
- 状态：深化设计，待用户拍板后执行
- 上游：`docs/lct-three-track-upgrade-architecture-20260611.md` §2、ADR-0002
- 基线代码事实（本轮实读确认）：
  - Stage 2 匿名机制：`stage2_collect_rankings()` 以 `Response A/B/C...` 标签呈现答案，`label_to_model` 落盘 `stage2/label_to_model.json` 并进 manifest metadata。
  - 评审文本结构：自由评价 prose ＋ 机器可解析的 `FINAL RANKING:` 区块（`parse_ranking_from_text` 以该 marker 切分）。
  - `provider.query_model()` 接受任意 `stage` 字符串，meta/stream sidecar 按 stage 目录落盘——Stage 2.5 无需改 provider。
  - manifest 已含 `metadata.aggregate_rankings`、`metadata.label_to_model`、`stages.stage2[].parsed_ranking`——stats 全部所需数据已在 manifest 内，不需要读 stage 文件。

---

## 1. B-1a 质询轮（rebuttal round）

### 1.1 协议位置与数据流

```
Stage 2 完成（aggregate_rankings 已落盘）
  │
  ├─ debate 未启用 ──────────────────────────▶ Stage 3（现行为，逐字节不变）
  │
  └─ debate 启用（--debate）
       │ 对每个有效 Stage 1 成员（stage1_record_is_valid）并发：
       │   输入 = 自己的 Stage 1 答案（含自己的 Response 标签）
       │        ＋ 全部有效 Stage 2 评审文本（去 FINAL RANKING 区块、去评审者身份）
       │   输出 = 一轮答辩（承认 / 反驳 / 修正）
       ▼
     stage2_5/<label>.rebuttal.md （+ prompt / meta / stream sidecar）
       │
       ▼
     Stage 3 prompt 注入「阶段 2.5 - 成员答辩」段，主席须区分原答案与答辩后修正
```

### 1.2 配置与接口契约

- `CouncilConfig.debate_enabled: bool = False`；CLI 新增 `--debate`（无 `--debate-rounds`，**首版轮次固定 1，不设配置项**，防复杂度走私）。
- 不新增 timeout 轴：成员级沿用 `query_timeout`；阶段级预算沿用 Stage 2 公式（`max(query_timeout + 30, 240)`）。
- `build_stage3_prompt()` 新增可选参数 `rebuttal_results: list[dict] | None = None`；`None` 时输出与现行为逐字节一致（golden 保护）。

### 1.3 答辩 prompt 契约（关键不变量，措辞执行期定夺）

输入材料的确定性变换：

1. **评审文本去排名**：以 `FINAL RANKING:` 为界截断，只保留评价 prose。理由：答辩动机应是论证质量，不是名次焦虑；且不向成员泄露同侪排序结果。
2. **评审者匿名**：评审文本标注为「评审 1..K」（K = 有效 Stage 2 记录数，顺序 = stage2 记录顺序），**不出现任何模型名**。
3. **成员知道自己的标签**（答辩必须知道辩护对象是哪份答案），但不知道其他答案归属。

任务指令必须要求三分结构（承认成立的批评 / 反驳不成立的批评并给论据 / 给出修正后立场或维持原立场），输出为自由 Markdown，**机器校验只要求非空**——不为答辩文本设解析格式，避免重蹈 Stage 2 ranking parse 的脆弱面。

### 1.4 失败语义（沿用 backfill 哲学，但有一处刻意不同）

- 单成员答辩失败/超时：该成员在 Stage 3 素材中无答辩段，记 manifest warning，**不降级 run、不影响 quorum**。
- **不做答辩 backfill**：答辩是人格化行为，候补模型不能替别人辩护。这是与 Stage 1/2 backfill 语义的刻意分叉，写入契约测试。
- 全部答辩失败：`metadata.debate.failed_all = true`，Stage 3 回退无答辩路径（`rebuttal_results=None`），run 状态不因此失败。
- 答辩阶段任何异常都不得阻断 Stage 3：质询轮是增强素材，不是协议主干。

### 1.5 数据模型

manifest 新增（additive）：

```json
"stages": { "stage2_5": [ { "label": "Response A", "model": "...",
  "status": "ok|failed|timeout", "response_path": "stage2_5/A.rebuttal.md",
  "meta_path": "stage2_5/A.meta.json", "error": null } ] },
"metadata": { "debate": {
  "enabled": true, "rounds": 1,
  "participants": ["..."], "completed": ["..."], "failed": ["..."],
  "failed_all": false,
  "review_material": "stage2_reviews_ranking_stripped_reviewer_anonymized"
} }
```

- artifacts：`stage2_5/<label>.rebuttal.prompt.md`、`<label>.rebuttal.md`、`<label>.meta.json` ＋ runtime 对应 stream/stderr sidecar（direct 与未来 ACP 命名规则沿用各自 runtime helpers）。
- `store.create()` 的固定子目录不加 `stage2_5`，按需创建（legacy 目录布局不变）。

### 1.6 Stage 3 与 contribution_map 的交互

- Stage 3 prompt 新段：「阶段 2.5 - 成员答辩」，按标签列出答辩文本；指令补充：答辩中的让步/修正视为该成员**最新立场**，与原答案冲突时以答辩为准并可在综述中注明演变。
- **contribution_map 契约零变更**：答辩素材仍归属同一成员，attribution kind 枚举、blocks schema、validate 规则全部不动。分歧块如引用答辩内容，归因仍是该成员。

### 1.7 验证标准（交执行 Agent 的验收口径）

1. 契约测试：
   - `--debate` 未启用 → 全链路（prompt、manifest、HTML）与现行为逐字节一致（现有 golden 不重生成即通过）。
   - 答辩 prompt 内不含任何在场成员模型名（fixture 断言字符串缺席）。
   - 答辩 prompt 内不含 `FINAL RANKING:`。
   - 单成员失败 → warning ＋ 无该成员答辩段 ＋ run 状态不变；全失败 → `failed_all` ＋ Stage 3 无答辩段。
   - 不存在答辩 backfill 路径（结构性断言）。
2. golden：debate-on fixture 一套（manifest ＋ HTML 快照，连跑两次零漂移）。
3. validate（additive）：`metadata.debate.enabled` 时校验 completed 成员的 rebuttal 文件在、participants ⊆ 有效 Stage 1 成员；legacy run 无 debate 字段不失败。
4. HTML：新增可折叠「成员答辩」区（按标签渲染，确定性、只读 artifacts）；摘要卡加 debate 标记。
5. live E2E 一次，notes.md 记录成本增量（预期 +N 次调用、约 +1 个阶段墙钟时间）。

### 1.8 推翻条件

- 灰度发现答辩普遍是复读原观点（对 Stage 3 无素材增量）→ 退为实验 flag，不进默认文档，B-1b（1v1 多轮）不立项。
- 若成员从评审 prose 中可靠推断评审者身份并出现针对性攻击行为 → 评审文本改为主席预压缩的批评摘要（增加一次模型调用，当前不采纳是为保确定性与成本）。

---

## 2. B-2 横评系统化（stats）

### 2.1 命令契约

```
llm-council-for-trae stats [--store DIR] [--run-id ID ...] [--output DIR] [--json] [--html]
```

- `--store` 默认 `.llm-council-for-trae/runs`（与 run/validate 一致）；默认扫描该目录全部 run，`--run-id` 可显式圈定。
- **只读铁律**：不向任何 run 目录写一个字节；报告写到 `--output`（默认 cwd）：`stats-report.md`（默认）＋ `--json`/`--html` 可选。
- 不调模型、不联网，纯本地聚合。

### 2.2 数据契约（manifest-only）

输入只取每个 run 的 terminal manifest（不读 stage 文件），所需字段全部已存在：

| 用途 | 字段 |
|---|---|
| 同侪位置（按评审员重算） | `stages.stage2[].parsed_ranking`（缺则由 `ranking` 文本经 `parse_ranking_from_text` 重算）＋ `metadata.label_to_model` |
| 成员有效性 / backfill | `metadata.quorum.*`、`stages.stage1[].status/attempt_role` |
| 评审可靠性 | `stages.stage2[].status/parse_status` |
| 主席可靠性 | `metadata.chairman`（fallback 链使用情况） |
| 问题分类维度 | `metadata.presentation.genre`（A-1 落地后自动获得；缺失归 `unclassified`） |

**不用 `metadata.aggregate_rankings` 做聚合**：其 `positions` 数组不携带评审者归属，无法做自评剔除；stats 必须从 stage2 记录逐评审员重算位置。这是硬性数据契约。

run 纳入规则：terminal status ∈ {ok, degraded_ok} 且 label_to_model 与 stage2 记录可解析；排除的 run 必须在报告附录列出 run_id ＋ 排除原因（可审计）。

### 2.3 指标定义（首版冻结）

按模型聚合，每格必须带样本量 n：

1. **同侪偏好**（核心新增维度）：
   - 原始平均位次 `mean_position` ＋ **归一化位次** `mean_normalized = mean((pos-1)/(n_subjects-1))`（跨 run 答案数不同，3 选 2 名与 4 选 2 名不可直接比，归一化是可比性前提）。
   - 首位率 `top1_rate`。
   - **自评剔除**：评审者对自己答案的位置（reviewer model == label_to_model[label]）一律剔除，剔除量单独报告。匿名标签下模型仍可能识别自身文风，这是剔除的依据。
2. **可靠性**：Stage 1 失败/超时率、Stage 2 parse 失败率、被 backfill 顶替次数、作为主席时 fallback 触发率。与 `model_benchmark.py`（主动探测：稳定性/格式/时延）并排呈现、**不合成单一分数**。
3. 维度切片：模型 × genre、模型 × 角色（member / chairman）。

### 2.4 呈现红线（与 ADR-0001 的张力解法，硬约束）

- 报告头部强制免责声明：「同侪偏好统计，非客观能力评测；受题目分布、position bias、文风识别偏差与样本量影响」。
- n < 5 的格子标灰「样本不足」。
- **禁止合成总分、禁止"第一名/最强"措辞**；表格默认按样本量 n 降序（不按位次排序），`--sort` 显式切换才按指标排。
- 单次 council 报告（HTML export）不引用 stats 结果，两个 surface 物理隔离。

### 2.5 模块边界

- 新模块 `stats.py`：纯函数核心（`collect_run_facts(manifest) -> RunFacts`、`aggregate(facts: list) -> StatsReport`），CLI 子命令只做 IO。复用 `parse_ranking_from_text`，不复制实现。
- 不动 `model_benchmark.py`；报告中引用其口径仅为文案并排。

### 2.6 验证标准

1. 单元：归一化公式、自评剔除、排除规则、n 阈值标灰。
2. 快照：固定 fixture run 集合 → `stats-report.md` 与 `--json` 输出确定性（连跑两次零漂移）。
3. 负向：损坏 manifest / 缺 label_to_model 的 run 被排除且出现在附录，不使命令失败。
4. 只读断言：跑完 stats 后对 runs 目录做 mtime/内容校验，零变更。

### 2.7 推翻条件

- stats 报告被当作模型排行榜截图误传 → 收紧为 `--json` only，去 md/html 渲染。
- 自评剔除后样本急剧缩水（小 roster 下剔除占比高）→ 改为「剔除版 / 全量版」双列并报。
