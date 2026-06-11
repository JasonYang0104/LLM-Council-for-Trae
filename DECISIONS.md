# 决策记录（ADR）

本文件记录对项目结构、公共接口、数据模型、构建/协作方式有长期影响的决策。新决策追加在最上方。

---

## ADR-0002：LCT 三轨升级路线（体验 / 机制 / 架构）

- 日期：2026-06-11
- 状态：提案（待用户拍板；用户已给定三轨方向，批次编排与各轨方案选型为架构师推荐）
- 输入：`docs/lct-three-track-upgrade-architecture-20260611.md`

### 背景

用户提出三轨升级：①体验——制品风格随内容自适应（技术决策出结构化对比、创意问题出发散展示），并借 Open Design 把交付形态扩展到 PPT/动画/demo；②机制——让持不同观点的模型直接交锋，并把「N 模型同题作答」副产品系统化为轻量级横评；③架构——traecli 直调切 ACP 协议，并开放模型与评审规则自定义。

### 决策（推荐项）

总原则沿用 ADR-0001：升级落在 sidecar、展示层、Skill 层与新增只读命令；不破坏三阶段协议、HTML 确定性导出、validate 证据链。

1. **A-1 风格自适应**：`stage3/presentation_plan.json` sidecar（复用 contribution_map 的 fence 机制），genre 枚举首版 3 个（`decision_matrix` / `divergent_panorama` / `default`）；export 只消费不重算，缺失回退默认模板。
2. **A-2 多形态交付**：Open Design 接入在 Skill/Agent 层，core 不内置 PPTX；core 职责收敛为稳定的「artifact 消费契约」。
3. **B-1a 对线首版 = 全员质询轮**：opt-in `--debate` 插入 Stage 2.5，每成员对针对自己的匿名批评作一轮答辩；匿名标签不破、轮次固定 1、失败降级沿用 backfill 语义。1v1 多轮对线（B-1b）等灰度证据再立项。
4. **B-2 横评系统化**：独立只读 `stats` 命令跨 run 聚合同侪偏好统计；单次 council 报告维持「不做模型评比」红线；报告强制免责声明、带样本量、禁止合成总分。
5. **C-1 ACP**：研究分支（本地 9 commits）先 push 备份，再按 P0→P3 逐阶段移植新 main，不整体 merge；live transport 单独立项且以 traecli ACP 能力 probe 为 go/no-go 前提；默认 runtime 维持 direct 直至切换条件全部达成。
6. **C-2 可扩展性**：用户级 `config.toml`（四字段白名单：preferred_members / default_member_count / backfill_candidates / rubric_path）＋ rubric 注入 Stage 2 评审标准段；排名解析契约不可配；provenance 记 manifest。

批次编排（2026-06-11 用户裁决：机制升级与 ACP 切换为优先推进重点，A 轨后置）：第一批 M0–M2（备份分支 ＋ contract tests ＋ ModelRuntime port）＋ B-2 stats；第二批 B-1a 质询轮（面向 ModelRuntime 抽象开发）＋ M3–M4（offline ACP adapter ＋ evidence gate）；第三批 M5 live ACP transport（probe 清单前置）；A-1/A-2/C-2 顺延。每批独立 PR，validate / make test 逐层绿。

### 依据与取舍

- 分类是模型工作（run 期落盘）、渲染是确定性工作（export 期消费），是保住 HTML 确定性红线的唯一分层方式。
- 质询轮优先于 1v1 对线：无选边与轮次终止问题，复杂度最低且已构成真实交锋。
- stats 与单次报告分面，化解与 ADR-0001「排名≠贡献」红线的张力。
- ACP 不整体 merge 是研究线两个 reviewer 的一致结论（behind 56，混入 contribution_map 链路）。
- 否决：core 内置 PPTX / 视频（重依赖破坏确定性导出定位）；export 期调模型判风格（破红线）；插件式 runtime 注册（抽象先于需求）。

### 影响范围

- 数据模型：新增 `stage3/presentation_plan.json`（schema_version 1）、`stage2_5/*.rebuttal.md`、manifest `metadata.presentation` / `metadata.debate` / `metadata.user_config`。
- 公共接口：新增 `--debate`、`--config`、`stats` 子命令、（移植）`--runtime-backend`；现有参数语义全部不变。
- 协作：ACP 研究分支需 push 备份；后续每批独立 PR。

### 深化设计补充（2026-06-11）

- Track B 深化：`docs/lct-debate-stats-architecture-20260611.md`——质询轮固定 1 轮、评审材料去 FINAL RANKING ＋ 评审者匿名、无答辩 backfill（刻意分叉）、debate 失败永不阻断 Stage 3；stats 为 manifest-only 只读、逐评审员重算位置（不用 aggregate_rankings，因其无评审者归属）、自评剔除、归一化位次。
- Track C-1 深化：`docs/lct-acp-migration-architecture-20260611.md`——**本机实测 `traecli acp serve` 握手通过**（initialize protocolVersion 1、session/new 返回 availableModels、启动 flags 含 --disallowed-tool），go/no-go 首关已过；移植路线 M0–M5，M5 live transport 前置 5 项 probe 清单（模型选择机制、permission 语义、actual model 证据、stop reason、进程残留）。
- B-1a 依赖建议：先完成 M2（ModelRuntime port），质询轮直接面向 `ModelRuntime` 抽象开发，自动兼容未来 ACP backend。

### 流程裁决（2026-06-11，用户拍板）

- ACP 路线优先启动；**GitHub 推送暂缓**——M0 的远端备份分支改为本地 bundle 备份（`lct-acp-research-backup-20260611.bundle`，verify 通过；研究目录实为主 repo worktree，9 commits 已在主 repo object store 内）。
- 开发验证流程：本机测试 ＋ 架构师 review ＋ 隔离 worktree，每阶段完成后停在分支等 review，不自行合并 main、不开 PR。恢复推送 GitHub 的时机由用户后续裁决。
- M1 基线已锚定：`main @ 04a1b9b`，`make test` 295 个 unittest 全绿（2026-06-11 本机实测）；M1 worktree：`COCO-llm-council-acp-m1-20260611`，任务卡 `docs/lct-acp-m1-task-card-20260611.md`。

### 推翻条件

- A-1：主席 genre 错判率高 → 降级启发式或仅 `--genre` 显式覆盖。
- B-1a：rebuttal 普遍无增量 → 退为实验 flag，B-1b 不立项。
- B-2：stats 被当排行榜误传 → 收紧为 JSON only。
- C-1b：traecli probe no-go → live ACP 冻结，已移植 contract tests 仍保留。
- C-2：出现真实第二 runtime 需求 → 再评估 runtime 注册抽象。

---

## ADR-0001：LCT 体验升级方向（四项）

- 日期：2026-06-06
- 状态：已采纳（待分批实现）
- 输入：`docs/lct-experience-upgrade-architect-brief-20260606.md`
- 决策人：用户拍板 ② 与模型优先级；其余为架构师默认，用户未反对

### 背景

`LLM-Council-for-Trae`（LCT）三阶段流程已可用。本次是体验升级，不是 runtime 重写。目标是让用户更容易看懂模型阵容、看出主席答案如何吸收各模型贡献、清楚输入是否被改写、以及自选模型时系统如何处理。**核心约束：不破坏现有可用链路**（非交互 run、显式模型、runtime override、`validate` 门槛、HTML 确定性、输入边界、search accounting、backfill provenance）。

### 决策

**总原则**：升级只落在展示层、Skill 编排层与可选附属文件；不动三阶段协议、默认成员上限 4、最低有效成员 3、默认 runtime。

1. **报告顶部卡片（HTML summary card）**
   - 选择：把 `Quorum 状态 4/3` 技术文案替换为「成员模型」卡片，内容取**实际有效参与的 Stage 1 成员**（`metadata.quorum.effective_stage1_members`）。
   - fallback 收紧（执行前审查 A4）：**仅当 `metadata.quorum` 整体缺失（legacy run）才回退 `config.members`**；若 `quorum` 存在但 `effective_stage1_members` 为空/缺失，**不得**显示 `config.members`（会把失败成员冒充参与者），应如实呈现（空/降级提示）。新 run 下 `effective_stage1_members` 是唯一事实源。
   - quorum 与 backfill 细节**不删除**，迁移到 metadata / evidence / 降级 banner，保留可审计性。
   - 落点：仅 `html_export.py` + 单元测试。
   - 标注：「有效 vs 配置」取有效，为架构师默认。

2. **主席贡献说明 —— 方案 B+（编辑定位版，用户多轮拍板）**

   **主席定位（根）**：资深编辑 / 客观记者，核心价值是**可信**——让读者永远能分清"成员真说的（素材）"与"主席自己加的（评注）"。防止单一主席模型用自身观点劫持多模型集体结论。
   - **默认 = 忠实整理**：把成员素材压缩、归并、重组成**适中结构化的编辑式综述**——用章节标题（h3 量级）组织，**标题为编辑结构、不署名；正文段落逐段署名**；好读但不做过度提纲。忠实 ≠ 逐字照搬（系统本就禁止抄 Stage 1 原文，仍须重组），但**不注入无成员来源的观点**。
   - **例外 = 评注**：主席原创想法一律隔离成明确标注的「✎ 编者注」，视觉独立、可扫读、克制使用。**评注尺度（用户拍板）**：可含取舍建议/折中方案，但**必须从成员已有观点延伸而来，不凭空发明无依据的新方案**。
   - **分歧 = 真有才显示**：成员确实对立才呈现"观点甲 / 观点乙"，**绝不为可读性编造对立**；主席对分歧的取舍意见归入「编者注」，不当成"答案"。

   **数据与展示（用自然描述；具体数据形态交执行 Agent 定夺）**：
   - **全覆盖逐段署名**：final answer 每段正文都带一条来源，取四类之一——单一成员（附同侪排名）、多成员共识（≥2 在场成员）、编者注（主席原创、须基于成员素材延伸、视觉隔离）、综合整理（拆不到具体成员，不强行归因）。**章节标题属编辑结构整理、不署名；段落逐段署名。**
   - **真分歧用独立"分歧块"呈现**：两个对立观点各自的成员来源 + 同侪排名 + 编者注；分歧块是独立展示构造，不是四类来源标签之一；无实质分歧不使用、不编造对立。
   - **同侪排名为可验证锚点**：来源旁的"同侪#n"由 `aggregate_rankings` 确定性带出（主席改不了）。主席三个核心输入 = Stage 1 答案、Stage 2 同侪互评、Stage 2 综合排序（现 `build_stage3_prompt` 已喂入）。
   - 落为附属文件（如 `stage3/contribution_map.json`）+ HTML 由其确定性渲染（只读不重算）。
   - **结构化展示的具体数据形态——字段名、枚举写法、正文与来源的对齐机制（块序列 / 锚点映射 / 其它）——交执行 Agent 定夺；架构只约束下列不变量，不规定模板。**

   **架构不变量（实现须满足，机制不限）**：
   - 每段正文与其来源必须可靠对应，HTML 导出阶段不得错位。
   - 来源/分歧引用的成员必须真在场、可校验；标"多成员共识"须 ≥2 在场成员；拆不到就标"综合整理"。
   - `validate` 校验引用合法性（成员在场、共识 ≥2、类型合法）；声明启用贡献说明而结构非法才失败。
   - 缺附属文件的 legacy run 不失败，回退现有 `render_markdown`；HTML 不调模型、不在导出阶段重算归因。

   **红线**：
   - **排名 ≠ 贡献**，系统只并排展示，绝不自动判定"排名高=贡献大"（brief §6）。
   - **呈现的是"观点分歧"，不是"模型评比"**（不得变成"GPT 比 DeepSeek 强"的排行）。
   - 保守措辞、**禁止百分比**、判断不了输出 `not_attributable`、不得在 HTML export 阶段重算（确定性红线）。第一版采用默认关闭灰度；2026-06-06 后续裁决已改为默认开启、显式关闭、显式强校验。

   **附带收益**：评注被隔离 → 读者可扫读"主席掺了多少私货"，评注越少越忠于成员，本身即一种可信度透明，无需额外做。
   - 否决 A（主席自由文字，不可机器校验，瞎编风险最高）与 C（文字相似度，中文改写后不准，假精确，最复杂）。
   - 落点：council prompt + store（拆 sidecar）+ validation + html_export + 兼容测试。

3. **输入改写规则**
   - 选择：维持 Skill 内「矩阵式规则」（raw / structured / fact pack / operator envelope 四态），**不下沉到 CLI**；补文档契约测试，明确高频触发语与负向用例（`详细分析`/`深入一点`/`给完整方案` 不得单凭字面触发改写）。
   - 落点：Skill 文档 + 契约测试，不改 core 代码。

4. **用户自选模型**
   - 选择：交互/展示（意图识别、模型清单、`AskUserQuestionTool` 卡片）在 Skill/Agent 层，且 `AskUserQuestionTool` 为**可选体验、非 core 依赖**，必须有文本 fallback；**归一化到 4（补足/裁剪）与 provenance 在 CLI 自选归一化入口**（非交互路径也要走且需落 manifest 可审计）。
   - 规则（简化，用户拍板）：把用户选择**归一化到恰好 4 个成员**——不足按 `PREFERRED_MEMBERS` 优先级补足、超过按优先级裁剪（用户选的非排名模型排最后、优先被裁）、正好 4 原样。运行中失败由**现有 auto-backfill**顶上，摘要只显示有效成员，**本期不为"选了但失败"的成员单独提示**。匹配仅 exact / case-insensitive / 编号（**不加 fuzzy**）；不存在/拼错的名字仍拦或追问、**不静默替换**。归一化**只在自选体验路径**；**原生 `--members` 直接 CLI 参数维持精确语义（§9 保护"给几个跑几个"），不自动补足/裁剪**；`profile`/`subagent`/`--default-models` 同样不动。
   - **模型优先级顺序维持现状（用户拍板不改）**：`PREFERRED_MEMBERS`（`model_selection.py`）。注：该顺序为人工编辑选择，项目基准测试只测稳定性/格式/时延，不测答案质量。
   - 落点：`model_selection.py` + `cli.py` + manifest provenance + validation（additive）。

5. **推进节奏**
   - 第一批（零协议风险）：报告卡片 + 输入改写文档矩阵 + 自选模型触发边界文档 + 契约测试。
   - 第二批（改 CLI 内核）：自选模型裁剪 + provenance + fail-closed；Skill 接可选交互卡片 + 文本 fallback。
   - 第三批（最重最后、第一版默认先关）：贡献说明方案 B 全链路 + 兼容测试；2026-06-06 后续裁决已把该能力改为默认 requested，并补 opt-out / strict gate。
   - 不并入同一 PR；若同轮则拆独立 commit，`validate` 逐层绿。

### 依据

- 体验痛点真实（quorum 黑话、贡献不透明、改写边界糊、挑模型盲取前 4）。
- 方案 B 是唯一能机器校验「引用模型是否真在场」的归因方式，能挡住硬性瞎编；A 不可验证、C 假精确。
- 输入改写本质是 outer Agent 的意图理解，属 Agent 职责，下沉 CLI 会破坏 runtime/Agent 无关边界。
- 裁剪/provenance 必须 CLI 内核：非交互 Agent 路径也要走，且需落 manifest 供事后审计。

### 取舍

- 贡献说明残余风险：`validate` 只能查「模型是否存在」，查不了「归因是否真实」，靠保守措辞、`not_attributable`、默认 soft validation、HTML fallback 和 strict gate 兜底。
- 报告卡片取「有效成员」会在降级 run 下与「配置成员」不同；以降级 banner + metadata 兜可见性。
- 自选体验路径把选择归一化到 4（补足/裁剪）是行为变更；以「原生 `--members` / `--default-models` / `profile` / `subagent` 维持精确语义」隔离，不破 §9。

### 影响范围

- 数据模型：新增 `stage3/contribution_map.json`（schema_version 1）；manifest.metadata 新增 model_selection provenance 字段。
- 公共接口：**新增自选归一化入口**（独立 opt-in 通道，如 `--selected-members`/`--selected-chairman`），**原生 `--members` 行为不变**；归一化入口对用户自选 members 执行补足/裁剪并写 `selection_surface` provenance。`validate` 新增 additive 校验（legacy run 不因缺新字段失败）。
- 协作：新增本决策记录文件；新增 feature 开关控制贡献说明灰度。

### 实现层补充（2026-06-06）

- 自选归一化入口采用 `--selected-members` / `--selected-chairman`。
- 原生 `--members` / `--chairman` 仍是 power-user 精确路径，不补足、不裁剪。
- `normalize_user_model_selection(...)` 是唯一归一化函数，CLI TTY custom 和 agent-assisted 自选都走它。
- `CouncilConfig.model_selection_provenance` 是持久通道；`initial_manifest()` 将其写入 `metadata.model_selection`。
- provenance 至少记录：`selection_surface`、`requested_members`、`requested_chairman`、`resolved_requested_members`、`resolved_members`、`resolved_chairman`、`filled_members`、`trimmed_members`、`final_members`、`final_chairman`。
- 主席贡献说明默认 requested。`--chairman-contribution-map` 保留为兼容 alias；`--no-chairman-contribution-map` 显式关闭；`--require-chairman-contribution-map` 打开 strict gate。
- manifest 使用 `metadata.chairman_contribution = {"enabled": true, "requested": true, "required": false, "present": true|false, "path": "stage3/contribution_map.json", ...}` 标记 sidecar 状态和错误。
- `stage3/contribution_map.json` 使用 blocks contract：`schema_version=1`、`enabled=true`、`source`、`blocks[]`；block type 只允许 `heading`、`paragraph`、`editor_note`、`disagreement`；attribution kind 只允许 `single_member`、`multi_member_consensus`、`editor_note`、`synthesis`、`not_attributable`。
- `validate` 在 `requested=true, required=false` 时执行 sidecar 检查但只产生非阻断 warning；`required=true` 时缺 sidecar、schema 非法、成员引用非法或 consensus 成员少于 2 才 hard fail。legacy run 缺 metadata 不失败。校验范围是结构与成员引用合法性，不声称验证真实贡献程度。

### 推翻条件

- 报告卡片：若用户反馈更想看「配置成员」而非「有效成员」，改回 `config.members`。
- 贡献说明：若灰度中观察到稳定的高质量归因，可改为默认开启；若持续出现无法校验的编造，回退为「只做 ①③④、不做 ②」。
- 输入改写：若多宿主需脱离 Skill prose 保持一致，再评估升级为 CLI 可读 input policy。
- 自选模型：若出现需要别名/模糊匹配的强需求，再评估放开匹配策略。
- 模型优先级：用户随时可重排（按直接报序 / 厂商偏好 / 跑基准 / 精简候选池）。
