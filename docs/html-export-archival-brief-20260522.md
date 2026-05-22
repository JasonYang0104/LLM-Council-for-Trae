# COCO-llm-council HTML Export Archival Brief

日期：2026-05-22

## 一句话结论

HTML export 已从“工程报告页”升级为 “Archival Paper” 调性：最终答案像一份可归档、可引用的纸本文档先出现，Stage 1 / Stage 2 / trace / manifest 作为 appendix 折叠在后面。页面外壳默认面向中文读者；它仍然是确定性本地渲染，不调用模型，不改写主席综合结果。

## 为什么原版本显得丑

- 信息层级太像 dashboard：右侧目录、卡片、标签、工具栏同时抢注意力，削弱了最终答案的权威感。
- 审美语言太通用：浅色卡片、SaaS 式边框、密集元信息，让页面像后台工具截图，不像一个可以被转发或归档的 council artifact。
- 证据层太早进入视野：Stage 1/2/trace 的存在是价值，但首屏不该和最终答案竞争。
- 复制控件过于系统化：全大写按钮和过多导航让页面的“机器味”超过了“文档味”。

## 用户选择

本轮看了 A / D / E 三个方向，最后选择 E：Archival Paper。

这个选择的本质不是“复古风格”，而是产品判断：CLC 的核心价值是可信答案和可复盘证据，因此 HTML export 应该像一份带出处的归档件，而不是像一个运营后台。

## 本轮改动

- `src/coco_llm_council/html_export.py`
  - 改为 centered paper sheet、warm archival palette、serif reading typography。
  - 首屏保留 folio、run status、copy controls、final answer，并把页面 chrome 改为中文。
  - 移除顶部索引，避免首屏重新变成工具页。
  - Evidence 改为 appendix 叙事：Appendix A 到 E。
  - 保留 `copy-payloads` 的安全 JSON 注入，不把 copy payload 放进 HTML-escaped 文本节点。
  - Clipboard API 只在明确有 `clipboard-write` 权限时使用，否则直接走 textarea fallback，避免浏览器控制台出现 permission error。
- `tests/test_core.py`
  - 增加 Archive Copy、sheet、Appendix A、verified stage 3 的结构断言。
  - 保留原有 Markdown 渲染、copy payload 原文、Stage 1/2/trace/metadata 默认折叠的测试。

## 验证结果

命令：

```bash
python3 -m compileall src
make test
coco-llm-council export live-smoke-20260522161928 --format html --json
coco-llm-council validate live-smoke-20260522161928 --json
```

结果：

```text
compileall: pass
unittest: 14 tests passed
export: html/index.html regenerated
validate: ok, 171 checks, 0 failures
```

静态 artifact 检查：

```text
归档副本: present
class="sheet": present
附录 A: present
final answer before stage1: true
external script src: none
stylesheet link: none
img dependency: none
```

浏览器验收：

```text
1440px: no horizontal overflow, console issues 0
768px: no horizontal overflow, console issues 0
375px: no horizontal overflow, console issues 0
copy markdown/json/prompt: fallback prepared valid payloads
stage1 accordion: opens and reveals candidate evidence
```

截图证据：

```text
/tmp/clc-archival-1440.png
/tmp/clc-archival-768.png
/tmp/clc-archival-375.png
/tmp/clc-archival-interaction.png
```

HTML artifact：

```text
/Users/bytedance/Documents/AI Coder/COCO-llm-council/.coco-llm-council/runs/live-smoke-20260522161928/html/index.html
```

## Director 判断

这轮不只是换颜色，而是把 CLC 的产品语义调准了：最终答案是主文，证据链是附录，copy/export 是低干扰工具。现在的 HTML export 更适合发给 reviewer、PM director 或后续 agent 作为可信 artifact 阅读。

剩余边界：当前 Markdown renderer 是项目内置的轻量实现，不是完整 CommonMark；如果未来要承载更复杂表格、脚注、数学公式，再单独引入渲染器。
