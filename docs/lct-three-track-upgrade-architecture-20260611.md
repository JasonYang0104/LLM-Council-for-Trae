# LCT 三轨升级架构方案（体验 / 机制 / 架构）

- 日期：2026-06-11
- 作者：首席架构师（Claude）
- 状态：提案，待用户拍板后转 ADR「已采纳」
- 基线：`main @ 04a1b9b`（与 GitHub `origin/main` 一致）
- 关联：`DECISIONS.md` ADR-0001（体验升级四项）、ACP 研究线 worktree `COCO-llm-council-acp-disabled-tool-research-20260603`（本地分支 `codex/lct-acp-runtime-p0-p1-20260604`，ahead 9 / behind 56，未推送）

---

## 0. 结论先行

三条轨道互相独立，但共享同一条总原则（沿用 ADR-0001）：**升级落在 sidecar、展示层、Skill 编排层和新增只读命令上；三阶段协议、HTML 确定性导出、validate 证据链这三条主干不被任何一轨破坏。**

推荐的总体编排（详见 §4）：

| 批次 | 内容 | 风险 |
|---|---|---|
| 第一批 | C-1a：移植 ACP 研究线的 direct contract tests（先给主干上保险）＋ B-2：跨 run 横评只读命令 | 零协议风险 |
| 第二批 | A-1：`presentation_plan` sidecar ＋ 内容自适应 HTML 模板；C-2：用户级配置（roster / rubric） | 低（additive） |
| 第三批 | B-1a：质询轮（rebuttal round，opt-in 协议扩展） | 中（动协议，opt-in 隔离） |
| 第四批 | C-1b：ACP live transport probe（go/no-go 门槛）；A-2：Open Design 多形态交付（Skill 层配方） | 外部依赖驱动 |

什么证据会推翻这个编排：若 `traecli` 已确认支持 ACP serve 且 direct 路径近期频繁出问题，C-1b 提前；若用户对「模型对线」的需求最迫切，B-1a 可与第二批并行（它和 A/C 改动面不重叠）。

---

## 1. Track A：体验升级——制品风格跟着内容走 ＋ 多形态交付

### 1.1 需求本质

两件事，分层不同：

1. **风格自适应**：技术决策类问题该出结构化对比，创意类问题该出发散性展示。本质是「内容分类 → 渲染策略」。
2. **多形态交付**（PPT / 动画 / demo）：本质是「同一份 artifacts，多个渲染器」。

第一性判断：**分类是模型的工作（run 期），渲染是确定性的工作（export 期）**。现有红线「HTML export 只读 artifacts、不调模型、不重算」必须保住——所以分类结论必须在 run 期落盘成数据，export 期只消费。

### 1.2 方案选项

- **A-1（推荐）：`stage3/presentation_plan.json` sidecar**。主席在 Stage 3 输出第二个 fenced block（完全复用 `contribution_map` 的 fence 抽取机制，`contribution_map.py` 已验证该模式可行），声明本次报告的体裁（genre）。`html_export.py` 按 genre 选模板族；sidecar 缺失或非法 → 回退现行默认模板，绝不失败。
- **A-min（最小方案）**：不动协议，`html_export.py` 用启发式规则（问题关键词、Report topic）猜 genre。零协议变更，但属于假精确——中文问题措辞多样，规则猜错会把创意题渲染成对比矩阵，违反「不牺牲体验」红线。仅当用户不愿动 Stage 3 prompt 时采用。
- **A-2：多形态交付走 Skill 层，core 不做 PPTX**。[Open Design](https://github.com/nexu-io/open-design)（开源 skills 驱动设计系统，支持 HTML/PDF/PPTX/MP4 导出，由本地 coding agent 驱动）的正确接入位置是**外层 Agent / Skill**，不是 CLI core。core 只需保证「artifact 消费契约」稳定：run store 目录布局 ＋ `stage3/final.md` ＋ `contribution_map.json` ＋ `presentation_plan.json` 是只读数据接口，任何渲染器（含 Open Design 的 PPT skill）都从这里取数。LCT Skill 文档新增「report-to-deck」配方一节，指导外层 Agent 调用 Open Design skills 生成 PPT；动画 / 产品 demo 同理，远期按需加配方。

否决项：在 CLI core 内置 PPTX/视频生成（引入重依赖，破坏「单文件 HTML、零外部依赖」的确定性导出定位）；让 export 阶段调模型做风格判断（破确定性红线）。

### 1.3 接口契约与数据模型

`stage3/presentation_plan.json`（schema_version 1）：

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "stage3_chairman_fence",
  "genre": "decision_matrix | divergent_panorama | default",
  "rationale": "一句话：为何判为该体裁"
}
```

关键约束（机制不限，执行 Agent 定夺细节）：

- 首版 genre 枚举只给 3 个：`decision_matrix`（结构化对比：方案×维度矩阵、取舍并排）、`divergent_panorama`（发散展示：各成员观点全景并列、弱化收敛）、`default`（现行模板）。枚举宁缺勿滥，新体裁靠证据追加。
- genre 非法 / sidecar 缺失 / legacy run → 一律按 `default` 渲染 ＋ HTML 降级 banner，validate 只发非阻断 warning，不 hard fail（展示层不配 strict gate）。
- 模板族只改排版与信息组织，**不改变信息量**：contribution_map 署名、分歧块、quorum 元数据在所有 genre 下都必须完整呈现（ADR-0001 的可信红线对所有体裁生效）。
- manifest 增 `metadata.presentation = {"requested": true, "present": bool, "genre": "..."}`，模式照抄 `chairman_contribution`。

### 1.4 验证标准

- 单元：fence 抽取、枚举校验、缺失回退。
- golden：每个 genre 一个 fixture run，HTML 快照确定性（连跑两次零漂移，沿用研究线 golden 模式）。
- 契约：legacy run（无 sidecar）渲染结果与升级前逐字节一致。

### 1.5 推翻条件

- 若主席模型 genre 判断准确率低（灰度观察错判明显），降级为 A-min 启发式或干脆只保留用户显式 `--genre` 覆盖。
- 若 Open Design 上游不稳定 / skills 协议变动频繁，「report-to-deck」配方退为纯文档建议，不写入 Skill 必经路径。

---

## 2. Track B：机制升级——模型对线 ＋ 横评系统化

### 2.1 对线（debate）

**需求本质**：现在成员之间零交互（独立回答 → 匿名互评 → 主席综合），互评意见没有机会被回应。「对线」= 给被批评者一次答辩权，逼出更深论证。

**方案选项**：

- **B-1a（推荐首版）：全员质询轮（rebuttal round）**。opt-in `--debate`，在 Stage 2 之后插入 Stage 2.5：每个 Stage 1 有效成员收到「针对你这份匿名答案的同侪批评摘要」（从 Stage 2 评审文本按 Answer 标签切出），输出一次有界的反驳或修正。Stage 3 prompt 额外注入质询轮素材，并要求主席区分「原答案」与「答辩后修正」。
  - 优点：无选边问题、完全复用现有匿名标签机制（成员只见 `Answer X`，不见模型名）、失败语义直接沿用 backfill 哲学（某成员 rebuttal 失败 → 缺谁少谁，不毁 run、不重跑）。
  - 这是「对线」的最小可信形态：每个成员都和批评自己的人交锋一轮。
- **B-1b（二期）：1v1 多轮对线**。检测最强分歧轴，挑两个对立成员 K 轮互怼。更接近愿景，但需要三个新机制：分歧轴检测、选边、轮次终止判定。等 B-1a 灰度证明「答辩素材确实提升 Stage 3 质量」再立项，避免为戏剧性付复杂度。
- **B-min（最小方案）**：不加阶段，只把 Stage 2 评审原文更完整地喂给 Stage 3（现已部分喂入）。零协议风险，但没有交锋，不满足需求本质，仅作对照基线。

**架构不变量**：

- 匿名不破：质询轮全程使用 Stage 2 的 Answer 标签体系，成员永远看不到模型名。
- 轮次有界：首版固定 1 轮，无配置项（防止复杂度走私）。
- artifacts：`stage2_5/<member>.rebuttal.md` ＋ prompt/meta sidecar，目录与命名模式照抄 stage1/stage2。
- manifest：`metadata.debate = {"enabled": bool, "rebuttal_members": [...], "failed": [...]}`；validate additive 校验（enabled 时 rebuttal 文件与成员在场性一致；legacy run 不失败）。
- 默认关闭。`--debate` 未启用时，全链路行为与现行逐字节一致（golden 保护）。
- 成本边界：质询轮使 run 增加 N 次模型调用（N=有效成员数），timeout 预算沿用成员级 `--timeout`，不引入新预算轴。

**验证标准**：契约测试（匿名标签不泄漏模型名、失败降级、legacy 兼容）＋ golden（debate off 零漂移；debate on 一个 fixture）＋ 一次 live E2E 记入 notes.md。

**推翻条件**：若灰度发现 rebuttal 普遍是「重申原观点」而非真答辩（素材无增量），停止 B-1b 立项，本特性退为实验 flag 不进默认文档。

### 2.2 横评系统化（轻量级模型评测）

**需求本质**：每次 council run 天然产出「N 模型同题作答 ＋ 匿名同侪排序」。系统化 = 跨 run 聚合这个副产品。

**与 ADR-0001 红线的张力与解法**：ADR-0001 明确「呈现的是观点分歧，不是模型评比」「排名≠贡献」。该红线约束的是**单次 council 报告**。解法是分面：

- 单次报告：红线原样保留，绝不出现模型排行。
- 新增**独立只读命令** `llm-council-for-trae stats --runs <dir>`（命名执行期可定，避开 `eval` 这种暗示客观评测的词）：扫描多个 run 的 artifact store，聚合输出独立报告 `stats-report.md/html`，报告头部强制声明：「**同侪偏好统计，非客观能力评测**；排名反映匿名互评偏好，受题目分布、position bias、样本量影响」。

**数据模型与指标**（只读，不写回任何 run）：

- 数据源：terminal manifest ＋ `aggregate_rankings` ＋ stage meta（全部现有字段，零新增写路径）。
- 指标：同侪平均排名、首位率、Stage 2 parse 失败率、超时/失败率、backfill 触发率、时延分位数。`model_benchmark.py` 已覆盖「稳定性/格式/时延」，stats 命令补上「同侪偏好」维度，两者在报告中并排、不合成单一分数。
- 维度：模型 × genre（复用 Track A 的 `presentation_plan.genre` 作问题分类标签——A-1 落地后自动获得该维度，未落地时只按模型聚合）。
- 每项统计必须带样本量 n；n < 5 的格子显示数值但标灰提示置信不足。**不输出任何合成「总分」或「排行榜第一名」措辞**。

**验证标准**：固定 fixture run 集合 → stats 输出快照确定性；自评数据（若 Stage 2 含对自身答案的排序）必须排除并在测试中冻结该行为。

**推翻条件**：若实际使用中 stats 报告被截图当成「模型排行榜」传播造成误导，收紧为仅 JSON 输出、去 HTML 渲染。

---

## 3. Track C：架构升级——ACP runtime ＋ 可扩展性

### 3.1 ACP（traecli 直调 → ACP 协议）

**资产盘点（已实测确认）**：研究 worktree 本地分支 `codex/lct-acp-runtime-p0-p1-20260604`（9 commits，**未推送 GitHub**，behind main 56 commits）已完成：

- P0：direct runtime contract tests（spawn/argv/retry/status/cancellation 全冻结）＋ golden full-run
- P1：`ModelRuntime` protocol ＋ `runtime_backend` 配置轴（默认 `direct`）
- P2：offline ACP adapter（transcript parser ＋ `AcpTraeCliRuntime`，live transport 未实现）
- P3：ACP evidence hard gate（防伪造 transcript）＋ HTML 五态展示（Allowed/Disabled/Requested/Denied/Used）

**决策（沿用研究线两个 reviewer 的结论）**：

1. **不整体 merge**。behind 56，且其中包含 contribution_map 整条链路；按 P0 → P1 → P2 → P3 顺序在新 main 上逐阶段重落（cherry-pick ＋ 冲突重写），每阶段 `make test` 全绿再进下一阶段。
2. **先推备份**：把研究分支原样 push 到 origin（如 `backup/acp-runtime-p0-p3-20260604`），9 commits 目前只存在于一台机器的 worktree 里，是单点风险。
3. **C-1b live transport 单独立项，go/no-go 门槛前置**：实现前必须先验证 `traecli` 是否真支持 ACP serve（命令存在性、initialize 握手、session/new、permission broker 行为）。**这是当前最大的不确定性**——研究线只做了 offline adapter，traecli 侧 ACP 能力从未实测。probe 结论记入 notes.md，no-go 则 C-1b 冻结、direct 维持默认，已移植的 P0-P3 资产仍然有价值（contract tests 保护主干，evidence gate 备用）。
4. **默认 runtime 切换条件**（缺一不可，达成前 `direct` 永远是默认）：live ACP E2E 全绿且 validate evidence gate 通过；用 `model_benchmark.py` 口径对比，ACP 路径时延/失败率不劣于 direct；灰度期内无 transcript 证据缺失案例。

### 3.2 可扩展性（自定义模型、自定义评审规则）

**需求本质**：用户不被默认配置锁死。现有扩展点：`--members` 精确语义、`profiles/subagents.json`、`--selected-members` 归一化通道。缺的是**持久的用户级配置**和**评审规则定制**。

**方案（推荐）**：用户级配置文件 ＋ rubric 注入。

- 配置文件：`~/.config/llm-council-for-trae/config.toml`（或 `--config <path>` 显式指定；TOML 选型理由：stdlib `tomllib` 零依赖、可注释）。首版可配字段严格收敛为四个：
  - `roster.preferred_members`（覆盖 `PREFERRED_MEMBERS` 顺序）
  - `roster.default_member_count`（默认 4，下限受现有最低有效成员 3 约束）
  - `roster.backfill_candidates`
  - `review.rubric_path`（指向用户自定义评审标准文件）
- **优先级链**：CLI 显式参数 > 用户 config > 内置默认。CLI 现有参数语义一概不变（`--members` 仍精确、`--default-models` 仍走内置链路时遵循 config 覆盖后的 roster）。
- **rubric 契约**：rubric 是一段 Markdown，注入 `build_stage2_prompt` 的「评审标准」段；**排名输出格式指令与解析契约（`parse_ranking_from_text`）不可配**——用户能改「按什么标准评」，不能改「评完怎么报告」，这是 parse 稳定性的硬边界。
- **provenance**：manifest `metadata.user_config = {"path": "...", "sha256": "...", "fields_applied": [...]}`；rubric 同样记 hash。validate additive 校验 hash 与字段合法性；无 config 文件 = 现行为，零破坏。

**最小方案**：只做 `roster.preferred_members` 覆盖，rubric 二期。若用户当前痛点只是模型清单，取此项。

**否决项**：插件式 runtime 注册机制（允许任意第三方 runtime 命令）——现阶段没有第二个真实 runtime 需求（coco 已由 `--runtime-command` override 覆盖），抽象先于需求。

**验证标准**：契约测试冻结优先级链与「无 config 零漂移」；恶意 config（不存在的模型名、rubric 试图改输出格式指令）被拦截的负向用例；provenance 字段进 manifest 的 schema 测试。

**推翻条件**：出现真实的第二 runtime 接入需求（非 traecli/coco 系）时，再评估 runtime 注册抽象；用户反馈 TOML 心智负担高则降级为纯 CLI flags ＋ shell alias 文档。

---

## 4. 总体编排与依赖

```
C-1a (contract tests 移植)  ──保护──▶  所有后续改动
A-1 (presentation_plan)     ──提供 genre 标签──▶  B-2 (stats 的问题分类维度，弱依赖)
A-1 (消费契约落定)          ──前置──▶  A-2 (Open Design 配方)
B-1a (质询轮)               ──灰度证据──▶  B-1b (1v1 对线，二期)
C-1b (live probe)           ──go/no-go──▶  默认 runtime 切换（远期）
```

- 每批独立 PR、独立 commit，`validate` 与 `make test` 逐层绿（沿用 ADR-0001 推进纪律）。
- B-1a 与 A/C 改动面不重叠（stage2.5 新目录 vs html/config），用户若急可提前并行。
- 任何一批失败回退不影响其他批次。

## 5. 交执行 Agent（codex）的任务卡索引

每张任务卡按「目标 / 边界 / 接口契约 / 验收标准」展开后再交付，本文档 §1-§3 已含契约与验收口径：

1. **C-1a**：push 研究分支备份 → 按 P0→P3 逐阶段移植到新分支，每阶段 `make test` 绿 ＋ golden 重生成说明。边界：不实现 live transport，不动默认 runtime。
2. **B-2**：新增 `stats` 只读命令 ＋ 报告模板。边界：零写路径、强制免责声明、禁止合成总分。
3. **A-1**：Stage 3 prompt 增 presentation fence → sidecar 抽取 → 3 genre 模板。边界：export 不调模型、legacy 逐字节兼容。
4. **C-2**：config.toml 加载 ＋ 优先级链 ＋ rubric 注入 ＋ provenance。边界：四字段白名单、解析契约不可配。
5. **B-1a**：`--debate` 质询轮。边界：匿名标签体系、1 轮固定、失败降级语义沿用 backfill。
6. **C-1b**：traecli ACP 能力 probe（只产证据报告，不写产品代码）。
7. **A-2**：Skill 文档「report-to-deck」配方（Open Design 接入指引，文档型任务）。

---

## 附：本方案引用的外部事实

- Open Design：开源 skills 驱动设计生成系统（[nexu-io/open-design](https://github.com/nexu-io/open-design)，[官网](https://open-design.ai/)），由 Claude Code / Codex 等本地 coding agent 驱动，含 PPT skill（guizang-ppt，单文件 HTML 演示，支持 PPTX/PDF/MP4 导出）。接入面为 Agent/Skill 层，与本判断一致。
- traecli ACP 支持情况：**未验证**，是 C-1b 的 go/no-go 前提。
