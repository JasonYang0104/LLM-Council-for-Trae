# LCT v19 主席评注与默认模型调整设计 / 测试方案

日期：2026-06-06
分支：`codex/lct-v19-chairman-note-kimi-default-20260606`

## 目标

本轮只做两个调整：

1. 主席贡献图中的 `editor_note` 渲染为独立的「主席评注」黄色边框块。
2. 成员整体优先级中 `Kimi-K2.6` 与 `Gemini-3.1-Pro-Preview` 调换位置，使默认 direct 成员变为 `DeepSeek-V4-Pro`、`openrouter-1o`、`GPT-5.4`、`Kimi-K2.6`。

不改 runtime provider、不改 Stage 1/2/3 protocol、不改 validate verdict 语义、不改原生 `--members` 的兼容边界。

## 现状

### 主席评注

当前 `render_contribution_map(...)` 遇到 `block.type == "editor_note"` 时输出：

```html
<aside class="warning-banner">
  <strong>编者注</strong>
  <p>主席注：...</p>
  <p class="meta">来源：主席编者注</p>
</aside>
```

这有三个问题：

- 标题不是用户要求的「主席评注」。
- 主体内容可能保留模型生成的 `主席注：` 前缀。
- renderer 追加了 `来源：主席编者注`，用户要求省去。

### 默认模型

当前事实源：

- `src/llm_council_for_trae/council.py`：`DEFAULT_MEMBERS` 仍包含 `Gemini-3.1-Pro-Preview` 作为第 4 个成员。
- `src/llm_council_for_trae/model_selection.py`：`PREFERRED_MEMBERS` 中 `Gemini-3.1-Pro-Preview` 位于第 4，`Kimi-K2.6` 位于第 7。
- README、Skill、`.trae` Skill、设计文档和若干测试仍记录旧默认阵容。

## 设计选项

### 方案 A：复用 `warning-banner`

继续使用 `.warning-banner`，只改标题和去掉来源行。

优点：diff 小。
缺点：`warning-banner` 同时用于 quorum 降级等运行警告，主席评注会和 warning 语义混在一起；后续视觉调整容易互相影响。

### 方案 B：新增专用 `chairman-note`

为 `editor_note` 新增专用 HTML/CSS：

```html
<aside class="chairman-note">
  <strong>主席评注</strong>
  <p>...</p>
</aside>
```

样式沿用现有报告色系，但独立于警告：

- 黄色边框：`#d6a642`
- 浅黄底：`#fff8df`
- 标题用 `var(--mono)`，固定显示「主席评注」。
- 不渲染来源 meta。

优点：语义清楚，符合用户要求，避免和真正 warning 混用。
缺点：多一个 CSS class。

### 方案 C：把 `editor_note` 渲染为普通段落加黄色左边线

类似 mockup 早期 `.editor-note`，只做左边线提示。

优点：视觉轻。
缺点：用户明确说「都用黄色边框框起来」，左边线不满足。

## 选定方案

采用方案 B。

实现细节：

- `render_contribution_map(...)` 对 `editor_note` 使用 `.chairman-note`。
- 新增 `clean_chairman_note_text(...)`：
  - 去掉开头 `主席注：`、`主席注:`、`主席评注：`、`主席评注:`。
  - 去掉尾部单独来源文本：`来源：主席编者注` 或 `来源: 主席编者注`。
  - 只处理首尾包装文案，不改写正文判断。
- `contribution_source_html(...)` 对 `kind == "editor_note"` 返回空字符串，避免再追加来源 meta。
- 保持 `validation.py` 对 `editor_note` 的 schema 校验不变；这是展示层调整，不扩大 sidecar contract。

## 模型优先级设计

用户要求是「默认成员模型中，用 kimi 2.6 替换 Gemini-3.1-Pro-Preview，即整体优先级上，这两个模型调换位置」。

落地为精确调换：

```text
旧优先级：
DeepSeek-V4-Pro → openrouter-1o → GPT-5.4 → Gemini-3.1-Pro-Preview → GPT-5.2 → openrouter-1 → Kimi-K2.6 → ...

新优先级：
DeepSeek-V4-Pro → openrouter-1o → GPT-5.4 → Kimi-K2.6 → GPT-5.2 → openrouter-1 → Gemini-3.1-Pro-Preview → ...
```

影响：

- `DEFAULT_MEMBERS` 第 4 位变成 `Kimi-K2.6`。
- `recommend_model_choice(...)` 在两者都可用时优先推荐 Kimi。
- selected-members 不足 4 的补足顺序跟随新 `PREFERRED_MEMBERS`。
- selected-members 超过 4 的裁剪顺序跟随新 `PREFERRED_MEMBERS`。
- 默认 backfill 候补中，`Gemini-3.1-Pro-Preview` 从 primary 成员移入剩余优先级候补；`Kimi-K2.6` 不再是默认 backfill 候补，因为它已经是 primary。
- 主席默认仍是 `DeepSeek-V4-Pro`；主席 fallback chain 不变，仍以 `Kimi-K2.6` 为第一 fallback。

## 测试方案

### TDD 红灯 1：主席评注 HTML

目标测试：`tests/test_core.py::CouncilCoreTests.test_html_renders_chairman_note_as_yellow_callout`

fixture：

- enabled contribution map。
- blocks 含 `type=editor_note`，text 为 `主席注：这是主席扩展判断。\n\n来源：主席编者注`。

断言：

- HTML 包含 `chairman-note`。
- HTML 包含 `主席评注`。
- HTML 包含清理后的 `这是主席扩展判断。`。
- HTML 不包含 `主席注：`。
- HTML 不包含 `来源：主席编者注`。
- HTML 不把 editor note 渲染为 `warning-banner`。

### TDD 红灯 2：默认成员与优先级

目标测试：

- `tests/test_lct_model_productization.py::test_default_roster_uses_current_priority_suite`
- `tests/test_core.py::test_default_direct_roster_uses_current_priority_suite`
- `tests/test_lct_model_productization.py::test_recommendation_caps_primary_members_at_four`

断言：

- `DEFAULT_MEMBERS == ["DeepSeek-V4-Pro", "openrouter-1o", "GPT-5.4", "Kimi-K2.6"]`
- 推荐模型在 Gemini 与 Kimi 都可用时选 Kimi 作为第 4 member。
- `PREFERRED_MEMBERS` 中 Kimi 的 index 小于 Gemini。

### TDD 红灯 3：selected-members 补足 / 裁剪跟随新优先级

目标测试：

- `test_normalize_user_model_selection_fills_to_four_by_preferred_members`
- `test_normalize_user_model_selection_trims_to_four_by_preferred_members`

断言：

- 用户只选 `GPT-5.4` 时，补足顺序应优先包含 `Kimi-K2.6`，不是 `Gemini-3.1-Pro-Preview`。
- 用户选择超过 4 且包含 Kimi/Gemini 时，Kimi 留在前 4，Gemini 被裁剪或排在 Kimi 之后。

### 文档契约

更新并验证：

- `README.md`
- `skills/llm-council-for-trae/SKILL.md`
- `.trae/skills/llm-council-for-trae/SKILL.md`
- `docs/design.md`
- `docs/traecli-subagents.md`
- 相关 v16/v18 历史执行文档只作为历史记录，不批量重写。

文档测试应覆盖默认成员新阵容，避免 Skill / README 继续宣称 Gemini 是默认成员。

## 本地验证门

实现后必须跑：

```bash
PYTHONPATH=src python3 -m compileall src
make test
git diff --check
```

如果 live runtime 可用，merge 后在 v19 fresh workspace 执行：

```bash
llm-council-for-trae doctor --json
llm-council-for-trae models --recommend --json
llm-council-for-trae run --input _lct_question.md --default-models --chairman-contribution-map --json
llm-council-for-trae validate <run_id> --json
```

E2E 验收：

- fresh workspace HEAD 等于最新 GitHub main。
- recommended/default members 包含 `Kimi-K2.6`，不包含 `Gemini-3.1-Pro-Preview` 作为 primary。
- enabled contribution map 存在。
- HTML 中主席评注为黄色边框块，标题为「主席评注」，无 `主席注：` 前缀，无 `来源：主席编者注`。
- validate verdict 为 `complete_ok_final`。
