from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .store import ArtifactStore
from .utils import read_text, utc_now


WEB_SEARCH_TOOLS = {"WebSearch", "WebFetch"}
TITLE_SUFFIX = "多模型智囊团评估"
GENERIC_INPUT_TITLES = {
    "original input",
    "input",
    "user input",
    "original question",
    "question",
    "输入",
    "输入提示词",
    "用户输入",
    "用户原始输入",
    "原始输入",
    "原始问题",
}
GENERIC_REPORT_TITLES = {
    "final answer",
    "answer",
    "summary",
    "conclusion",
    "analysis",
    "最终答案",
    "最终回答",
    "结论",
    "最终判断",
    "正面信号",
    "负面信号",
    "核心结论",
    "综合判断",
    "系统性评估",
    "我真正理解你的需求",
}
PREFERRED_TOPIC_SECTIONS = {
    "agent interpretation",
    "agent interpretation / framing",
    "suggested council focus",
    "council focus",
    "task focus",
    "问题理解",
    "任务理解",
    "议题概括",
    "讨论焦点",
}
EXPLICIT_TOPIC_LABELS = {
    "report topic",
    "topic",
    "title",
    "report title",
    "报告题名",
    "报告标题",
    "题名",
    "标题",
    "议题",
    "中文议题",
}

ARTIFACT_PROMPT = """traecli-llm-council HTML artifact rendering contract.

Do not call any model. Do not change the chairman synthesis. Render the existing artifacts only.
Default reader surface: stage3/final.md as Markdown HTML, with Stage 1, Stage 2, provider trace, and manifest metadata as collapsible evidence.
Default UI language: Simplified Chinese for Chinese readers. Do not translate artifact content in this export step.
Required controls: copy markdown, copy JSON, copy final prompt.
"""


def export_html(store: ArtifactStore) -> dict[str, Any]:
    manifest = store.read_manifest()
    store.write_text("html/artifact.prompt.md", ARTIFACT_PROMPT)
    html_text = render_html(store.root, manifest)
    store.write_text("html/index.html", html_text)
    export_record = {
        "run_id": manifest["run_id"],
        "generated_at": utc_now(),
        "format": "html",
        "path": "html/index.html",
        "source_manifest": "manifest.json",
    }
    store.write_json("html/export.json", export_record)
    manifest.setdefault("artifacts", {})["html"] = "html/index.html"
    manifest["artifacts"]["html_export"] = "html/export.json"
    store.write_manifest(manifest)
    return export_record


def _extract_title(input_text: str, max_chars: int = 60, final_text: str = "") -> str:
    input_lines = input_text.strip().splitlines() if input_text else []
    final_lines = final_text.strip().splitlines() if final_text else []
    topic = (
        _extract_explicit_topic(input_lines)
        or _extract_final_answer_topic(final_lines)
        or _extract_preferred_topic(input_lines)
        or _extract_first_content_line(input_lines)
        or "最终答案"
    )
    return _format_report_title(topic, max_chars=max_chars)


def _format_report_title(topic: str, max_chars: int = 60) -> str:
    topic = _strip_title_suffix(_clean_title_candidate(topic)) or "最终答案"
    if len(topic) > max_chars:
        topic = topic[:max_chars].rstrip() + "…"
    return f"{topic}：{TITLE_SUFFIX}"


def _strip_title_suffix(title: str) -> str:
    normalized_suffix = f"：{TITLE_SUFFIX}"
    if title.endswith(normalized_suffix):
        return title[: -len(normalized_suffix)].rstrip()
    if title.endswith(TITLE_SUFFIX):
        return title[: -len(TITLE_SUFFIX)].rstrip(" :：-")
    return title


def _extract_explicit_topic(lines: list[str]) -> str | None:
    for line in lines:
        label_match = re.match(r"^\s*([A-Za-z][A-Za-z /_-]{1,80}|[\u4e00-\u9fff][^:：]{0,30})\s*[:：]\s*(.+)$", line)
        if label_match and _normalize_title(label_match.group(1)) in EXPLICIT_TOPIC_LABELS:
            candidate = _clean_title_candidate(label_match.group(2))
            if _usable_topic(candidate, allow_english=True):
                return candidate
    return None


def _extract_final_answer_topic(lines: list[str]) -> str | None:
    for line in lines:
        if _is_section_separator(line):
            return None
        core_question = _core_question_topic(line)
        if core_question and _usable_topic(core_question, require_chinese=True):
            return core_question
        heading = _heading_text(line)
        if heading and _usable_topic(heading, require_chinese=True):
            return heading
    return None


def _extract_preferred_topic(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        heading = _heading_text(line)
        if heading and _normalize_title(heading) in PREFERRED_TOPIC_SECTIONS:
            candidate = _first_content_after(lines, index + 1)
            if candidate and _usable_topic(candidate, allow_english=True):
                return candidate
        label_match = re.match(r"^\s*([A-Za-z][A-Za-z /_-]{2,80}|[\u4e00-\u9fff][^:：]{1,30})\s*[:：]\s*(.+)$", line)
        if label_match and _normalize_title(label_match.group(1)) in PREFERRED_TOPIC_SECTIONS:
            candidate = _clean_title_candidate(label_match.group(2))
            if candidate and _usable_topic(candidate, allow_english=True):
                return candidate
    return None


def _extract_first_content_line(lines: list[str]) -> str | None:
    for line in lines:
        candidate = _clean_title_candidate(line)
        if candidate and _usable_topic(candidate, allow_english=True):
            return candidate
    return None


def _first_content_after(lines: list[str], start: int) -> str | None:
    for line in lines[start:]:
        if _heading_text(line):
            return None
        candidate = _clean_title_candidate(line)
        if candidate and _usable_topic(candidate, allow_english=True):
            return candidate
    return None


def _heading_text(line: str) -> str | None:
    heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
    if not heading:
        return None
    return _clean_title_candidate(heading.group(1))


def _is_section_separator(line: str) -> bool:
    return bool(re.match(r"^\s*-{3,}\s*$", line.strip()))


def _core_question_topic(line: str) -> str | None:
    match = re.search(r"核心问题是\s*[:：]\s*(.+)$", line)
    if not match:
        return None
    return _clean_title_candidate(match.group(1)).rstrip("。")


def _clean_title_candidate(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^#{1,6}\s+", "", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+[.)]\s+", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = text.strip("`*_ \t")
    text = re.sub(r"\s+", " ", text)
    return text


def _is_generic_input_title(title: str) -> bool:
    return _normalize_title(title) in GENERIC_INPUT_TITLES


def _is_generic_report_title(title: str) -> bool:
    return _normalize_title(title) in GENERIC_REPORT_TITLES


def _usable_topic(candidate: str, allow_english: bool = False, require_chinese: bool = False) -> bool:
    if not candidate:
        return False
    normalized = _normalize_title(candidate)
    if (
        _is_generic_input_title(candidate)
        or _is_generic_report_title(candidate)
        or normalized in PREFERRED_TOPIC_SECTIONS
        or normalized in EXPLICIT_TOPIC_LABELS
    ):
        return False
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", candidate))
    if require_chinese and not has_chinese:
        return False
    if not has_chinese and not allow_english:
        return False
    if _looks_like_english_long_sentence(candidate):
        return False
    return True


def _looks_like_english_long_sentence(candidate: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", candidate):
        return False
    words = re.findall(r"[A-Za-z]+", candidate)
    return len(words) >= 9


def _normalize_title(title: str) -> str:
    title = _clean_title_candidate(title).casefold()
    return re.sub(r"\s+", " ", title).strip(" :：-")


def render_html(root: Path, manifest: dict[str, Any]) -> str:
    input_text = safe_read(root / "input.md")
    final_text = safe_read(root / "stage3" / "final.md")
    page_title = _extract_title(input_text, final_text=final_text)
    chairman_prompt = safe_read(root / "stage3" / "chairman.prompt.md")
    markdown_export = build_markdown_export(manifest, input_text, final_text)
    json_export = json.dumps(manifest, ensure_ascii=False, indent=2)
    copy_payloads = {
        "json": json_export,
        "markdown": markdown_export,
        "prompt": chairman_prompt,
    }
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    stage1 = stages.get("stage1") if isinstance(stages.get("stage1"), list) else []
    stage2 = stages.get("stage2") if isinstance(stages.get("stage2"), list) else []
    stage3 = stages.get("stage3") if isinstance(stages.get("stage3"), dict) else {}
    aggregate = metadata.get("aggregate_rankings") if isinstance(metadata.get("aggregate_rankings"), list) else []
    failures = manifest.get("failures") if isinstance(manifest.get("failures"), list) else []
    warnings = manifest.get("warnings") if isinstance(manifest.get("warnings"), list) else []
    generated_at = utc_now()

    stage1_tabs = render_tabs(
        "stage1",
        [
            (
                item.get("file_label", "?"),
                _render_stage1_tab_content(item),
            )
            for item in stage1
            if isinstance(item, dict)
        ],
    )
    stage2_tabs = render_tabs(
        "stage2",
        [
            (
                item.get("reviewer_label", "?"),
                f"<h3>评审者 {esc(item.get('reviewer_label'))} · {esc(item.get('model'))}</h3>"
                f"<p class='meta'>期望模型：{esc(item.get('expected_model'))} · 实际模型：{esc(item.get('actual_model'))} · 解析：{esc(item.get('parse_status'))}</p>"
                f"<p><strong>解析排序：</strong> {esc(', '.join(item.get('parsed_ranking') or []))}</p>"
                f"<pre><code>{esc(item.get('ranking'))}</code></pre>",
            )
            for item in stage2
            if isinstance(item, dict)
        ],
    )

    final_html = render_markdown(final_text)
    metadata_html = render_metadata(manifest, warnings, failures)
    trace_html = render_trace(stage1, stage2, stage3)
    ranking_html = render_ranking_matrix(aggregate)
    manifest_html = f"<pre><code>{esc(json.dumps(manifest, ensure_ascii=False, indent=2))}</code></pre>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(page_title)}</title>
<style>
:root {{
  --bg:#e9e0cf;
  --paper:#fbf6ea;
  --paper-deep:#f3ead9;
  --ink:#221b14;
  --body:#33291f;
  --muted:#766b5a;
  --line:#b9a98f;
  --line-soft:#d6c7ad;
  --accent:#7b2d26;
  --accent-soft:#efe1d7;
  --bad:#9f1d16;
  --warn:#8c4a12;
  --code:#241d17;
  --code-ink:#fbf6ea;
  --shadow:0 24px 70px rgba(55,42,22,.16);
  --serif:Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0;
  font:17px/1.72 var(--serif);
  color:var(--ink);
  background:var(--bg);
}}
a {{ color:var(--accent); text-decoration-thickness:1px; text-underline-offset:3px; }}
button, summary {{ font:inherit; }}
button {{
  border:1px solid var(--line);
  background:transparent;
  color:var(--ink);
  border-radius:2px;
  padding:8px 11px;
  cursor:pointer;
  font:13px/1.2 var(--sans);
  text-transform:none;
  letter-spacing:0;
}}
button:hover, button:focus-visible {{ border-color:var(--accent); color:var(--accent); outline:2px solid transparent; }}
button:focus-visible, a:focus-visible, summary:focus-visible {{ outline:3px solid rgba(123,45,38,.25); outline-offset:2px; }}
.archive-shell {{
  padding:32px 18px 70px;
}}
.sheet {{
  max-width:980px;
  margin:0 auto;
  background:var(--paper);
  border:1px solid rgba(90,72,45,.28);
  box-shadow:var(--shadow);
  padding:52px 64px 58px;
}}
.folio {{
  display:flex;
  justify-content:space-between;
  gap:16px;
  border-bottom:1px solid var(--line);
  padding-bottom:12px;
  color:var(--muted);
  font:12px/1.4 var(--mono);
  text-transform:uppercase;
  letter-spacing:.06em;
}}
.archive-hero {{
  display:block;
  padding:42px 0 28px;
  border-bottom:1px solid var(--line);
}}
h1 {{ margin:0; font-size:58px; line-height:1.05; font-weight:400; letter-spacing:0; }}
.question-context {{
  margin:18px 0 0;
  padding:16px 20px;
  border-left:3px solid var(--accent);
  background:var(--accent-soft);
  color:var(--body);
  font:15px/1.65 var(--serif);
  max-width:72ch;
}}
.question-context summary {{
  cursor:pointer;
  font-weight:600;
  color:var(--ink);
}}
.question-context .details-body {{
  margin-top:12px;
  padding-top:12px;
  border-top:1px solid rgba(123,45,38,.25);
  white-space:pre-line;
}}
.run-meta {{ margin:14px 0 0; color:var(--muted); font:13px/1.55 var(--mono); }}
.toolbar {{ display:flex; flex-wrap:wrap; justify-content:flex-start; gap:8px; max-width:420px; margin-top:24px; }}
.copy-status {{ width:100%; color:var(--muted); font:12px/1.5 var(--mono); text-align:left; min-height:20px; }}
.copy-fallback {{
  width:100%;
  min-height:92px;
  margin-top:8px;
  border:1px solid var(--line);
  border-radius:2px;
  padding:8px;
  font:12px/1.45 var(--mono);
  color:var(--ink);
  background:var(--paper-deep);
}}
.reader {{ min-width:0; }}
.answer {{
  position:relative;
  padding:34px 0 18px;
}}
.reader-label {{ margin:0 0 14px; color:var(--accent); font:12px/1.4 var(--mono); text-transform:uppercase; letter-spacing:.06em; }}
.stamp {{
  float:right;
  margin:0 0 18px 30px;
  border:1px solid var(--accent);
  color:var(--accent);
  padding:10px 12px;
  font:12px/1.3 var(--mono);
  text-transform:uppercase;
  letter-spacing:.06em;
  transform:rotate(1deg);
}}
.markdown-body {{ max-width:72ch; color:var(--body); }}
.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {{
  letter-spacing:0;
  line-height:1.2;
  margin:1.45em 0 .55em;
  color:var(--ink);
  font-weight:400;
}}
.markdown-body h1:first-child, .markdown-body h2:first-child, .markdown-body h3:first-child {{ margin-top:0; }}
.markdown-body h1 {{ font-size:34px; }}
.markdown-body h2 {{ font-size:27px; }}
.markdown-body h3 {{ font-size:20px; }}
.markdown-body p {{ margin:.8em 0; }}
.markdown-body ul, .markdown-body ol {{ padding-left:1.35rem; }}
.markdown-body li + li {{ margin-top:.25em; }}
.markdown-body blockquote {{ margin:1.1em 0; padding:2px 0 2px 16px; border-left:3px solid var(--accent); color:#4b3f32; }}
pre {{
  white-space:pre-wrap;
  overflow:auto;
  background:var(--code);
  color:var(--code-ink);
  border-radius:2px;
  padding:14px;
}}
code {{ font-family:var(--mono); font-size:.92em; }}
:not(pre) > code {{ background:var(--paper-deep); color:var(--ink); padding:1px 4px; border-radius:2px; }}
table {{ width:100%; border-collapse:collapse; margin:1em 0; font-size:14px; }}
th, td {{ border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }}
th {{ background:var(--paper-deep); }}
.status-ok {{ color:var(--accent); }}
.status-failed {{ color:var(--bad); }}
.status-degraded_ok {{ color:var(--warn); }}
.summary-strip {{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  border-top:1px solid var(--line);
  border-bottom:1px solid var(--line);
  margin:0 0 24px;
}}
.summary-card {{ padding:14px; border-right:1px solid var(--line); min-width:0; }}
.summary-card:last-child {{ border-right:0; }}
.summary-card h3 {{ margin:0 0 6px; color:var(--muted); font:11px/1.4 var(--mono); text-transform:uppercase; letter-spacing:.06em; }}
.summary-card p {{ margin:0; color:var(--ink); font-size:15px; overflow-wrap:anywhere; }}
.appendix {{ margin-top:26px; }}
.appendix-title {{
  margin:0 0 10px;
  color:var(--muted);
  font:12px/1.4 var(--mono);
  text-transform:uppercase;
  letter-spacing:.06em;
}}
.appendix details {{
  border-top:1px solid var(--line);
  padding:0;
}}
.appendix details:last-child {{ border-bottom:1px solid var(--line); }}
.appendix summary {{
  cursor:pointer;
  padding:16px 0;
  font-weight:600;
  color:var(--ink);
}}
.details-body {{ border-top:1px solid var(--line-soft); padding:16px 0 18px; overflow:auto; }}
.meta {{ color:var(--muted); font:13px/1.55 var(--sans); }}
.matrix {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; }}
.cell {{ border:1px solid var(--line); background:rgba(255,255,255,.28); padding:12px; }}
.cell h3 {{ margin:0 0 8px; font-size:16px; }}
.cell p {{ margin:5px 0; }}
.tabs {{ border:1px solid var(--line); background:rgba(255,255,255,.28); overflow:hidden; }}
.tab-buttons {{ display:flex; flex-wrap:wrap; gap:4px; padding:8px; border-bottom:1px solid var(--line); background:var(--paper-deep); }}
.tab-panel {{ display:none; padding:16px; }}
.tab-panel.active {{ display:block; }}
.warning {{ color:var(--warn); }}
.failure-banner {{ border:1px solid var(--bad); background:#fff1eb; padding:12px 14px; margin:16px 0; }}
.warning-banner {{ border:1px solid #c48233; background:#fff6df; padding:12px 14px; margin:16px 0; }}
svg {{ width:100%; max-width:760px; height:auto; display:block; }}
@media (max-width: 860px) {{
  .archive-shell {{ padding:0; }}
  .sheet {{ max-width:none; min-height:100vh; border-left:0; border-right:0; box-shadow:none; padding:34px 24px 44px; }}
  .archive-hero {{ padding:34px 0 24px; }}
  .toolbar {{ justify-content:flex-start; }}
  .copy-status {{ text-align:left; }}
  h1 {{ font-size:46px; }}
  .summary-strip {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .summary-card:nth-child(2n) {{ border-right:0; }}
  .summary-card:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }}
}}
@media (max-width: 520px) {{
  body {{ font-size:16px; }}
  .sheet {{ padding:28px 18px 38px; }}
  .folio {{ display:block; }}
  .folio span {{ display:block; margin-bottom:6px; overflow-wrap:anywhere; }}
  h1 {{ font-size:40px; }}
  .stamp {{ float:none; display:inline-block; margin:0 0 18px; }}
  .summary-strip {{ grid-template-columns:1fr; }}
  .summary-card, .summary-card:nth-child(2n) {{ border-right:0; border-bottom:1px solid var(--line); }}
  .summary-card:last-child {{ border-bottom:0; }}
  button {{ padding:7px 9px; }}
}}
</style>
</head>
<body>
<main class="archive-shell">
  <div class="sheet">
    <header class="folio">
      <span>LLM Council for Trae / 归档副本</span>
      <span>{esc(manifest.get('run_id'))}</span>
    </header>
    <section class="archive-hero" aria-label="运行标题">
      <div>
      <h1>{esc(page_title)}</h1>
      <details id="input-prompt" class="question-context"><summary>输入提示词</summary><div class="details-body">{esc(input_text.strip())}</div></details>
      <p class="run-meta">运行 {esc(manifest.get('run_id'))} · 状态 <strong class="status-{esc(manifest.get('status'))}">{esc(manifest.get('status'))}</strong> · 导出 {esc(generated_at)}</p>
    </div>
    <div class="toolbar" aria-label="导出操作">
      <button type="button" onclick="copyPayload('markdown')">复制 Markdown</button>
      <button type="button" onclick="copyPayload('json')">复制 JSON</button>
      <button type="button" onclick="copyPayload('prompt')">复制主席提示词</button>
      <div id="copy-status" class="copy-status" role="status" aria-live="polite"></div>
      <textarea id="copy-fallback" class="copy-fallback" hidden aria-label="复制备用文本"></textarea>
    </div>
    </section>
    {render_alerts(warnings, failures, manifest.get('status', 'ok'), manifest=manifest)}
    <section id="decision-summary" class="summary-strip" aria-label="决策摘要">
      {render_summary_cards(manifest, aggregate)}
    </section>
    <article id="final-answer" class="reader answer">
      <div class="stamp">已验证<br>阶段 3</div>
      <p class="reader-label">阶段 3 · 主席综合</p>
      <div class="markdown-body">
        {final_html or "<p class='meta'>未找到最终答案内容。</p>"}
      </div>
    </article>
    <section id="evidence" class="appendix" aria-label="证据层">
      <h2 class="appendix-title">证据附录</h2>
      <details id="stage1"><summary>附录 A · 阶段 1 候选回答</summary><div class="details-body">{stage1_tabs}</div></details>
      <details id="stage2"><summary>附录 B · 阶段 2 匿名互评</summary><div class="details-body">{ranking_html}{stage2_tabs}</div></details>
      <details id="trace"><summary>附录 C · Provider trace</summary><div class="details-body">{trace_html}</div></details>
      <details id="metadata"><summary>附录 D · Manifest metadata</summary><div class="details-body">{metadata_html}{manifest_html}</div></details>
      <details id="flow"><summary>附录 E · Council flow</summary><div class="details-body">{render_flow_svg()}</div></details>
    </section>
  </div>
</main>
<script type="application/json" id="copy-payloads">{json_for_script(copy_payloads)}</script>
<script>
function activateTab(group, index) {{
  document.querySelectorAll('[data-tab-group="'+group+'"]').forEach(function(el) {{ el.classList.remove('active'); }});
  var target = document.querySelector('[data-tab-group="'+group+'"][data-tab-index="'+index+'"]');
  if (target) target.classList.add('active');
}}
async function copyPayload(key) {{
  var status = document.getElementById('copy-status');
  var el = document.getElementById('copy-payloads');
  var payloads = el ? JSON.parse(el.textContent) : {{}};
  var text = payloads[key] || '';
  var copied = false;
  var canUseClipboard = false;
  if (navigator.clipboard && window.isSecureContext && navigator.permissions && navigator.permissions.query) {{
    try {{
      var permission = await navigator.permissions.query({{ name: 'clipboard-write' }});
      canUseClipboard = permission.state === 'granted';
    }} catch (err) {{
      canUseClipboard = false;
    }}
  }}
  if (canUseClipboard) {{
    try {{
      await navigator.clipboard.writeText(text);
      copied = true;
    }} catch (err) {{
      copied = false;
    }}
  }}
  if (!copied) {{
    var ta = document.getElementById('copy-fallback');
    if (!ta) {{
      ta = document.createElement('textarea');
      ta.id = 'copy-fallback';
      ta.className = 'copy-fallback';
      ta.setAttribute('aria-label', '复制备用文本');
      document.body.appendChild(ta);
    }}
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.hidden = false;
    ta.select();
    copied = document.execCommand('copy');
  }}
  if (copied) {{
    if (status) status.textContent = '已复制 ' + key + '。';
  }} else {{
    if (status) status.textContent = '已准备 ' + key + '，可手动复制。';
  }}
}}
</script>
</body>
</html>
"""


def render_markdown(markdown_text: str) -> str:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{render_inline(' '.join(paragraph).strip())}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        fence = re.match(r"^```([A-Za-z0-9_-]+)?\s*$", stripped)
        if fence:
            flush_paragraph()
            language = fence.group(1) or ""
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            class_name = f" class='language-{esc(language)}'" if language else ""
            blocks.append(f"<pre><code{class_name}>{esc(chr(10).join(code_lines))}</code></pre>")
            continue

        if is_table_start(lines, i):
            flush_paragraph()
            table_lines = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            blocks.append(render_table(table_lines))
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{render_inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            blocks.append("<hr>")
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(f"<blockquote>{render_markdown(chr(10).join(quote_lines))}</blockquote>")
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            items: list[str] = []
            while i < len(lines):
                match = re.match(r"^[-*+]\s+(.+)$", lines[i].strip())
                if not match:
                    break
                items.append(f"<li>{render_inline(match.group(1).strip())}</li>")
                i += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines):
                match = re.match(r"^\d+\.\s+(.+)$", lines[i].strip())
                if not match:
                    break
                items.append(f"<li>{render_inline(match.group(1).strip())}</li>")
                i += 1
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    return "\n".join(blocks)


def render_inline(text: str) -> str:
    parts = re.split(r"(`[^`]*`)", text)
    rendered: list[str] = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            rendered.append(f"<code>{esc(part[1:-1])}</code>")
            continue
        escaped = esc(part)
        escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
        rendered.append(escaped)
    return "".join(rendered)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    header = lines[index].strip()
    divider = lines[index + 1].strip()
    return "|" in header and re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", divider) is not None


def render_table(table_lines: list[str]) -> str:
    rows = [split_table_row(line) for line in table_lines]
    if len(rows) < 2:
        return ""
    header = rows[0]
    body = rows[2:]
    head_html = "".join(f"<th>{render_inline(cell)}</th>" for cell in header)
    body_html = "".join("<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>" for row in body)
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _render_stage1_tab_content(item: dict[str, Any]) -> str:
    badge = ""
    if item.get("status") == "failed" and item.get("raw_partial_recoverable"):
        badge = " <span class='warning' style='border:1px solid #c48233;padding:2px 6px;border-radius:2px;'>部分输出可恢复</span>"
    return (
        f"<h3>{esc(item.get('label'))} · {esc(item.get('model'))}</h3>"
        f"<p class='meta'>期望模型：{esc(item.get('expected_model'))} · 实际模型：{esc(item.get('actual_model'))} · 状态：{esc(item.get('status'))}{badge}</p>"
        f"<div class='evidence-text'>{render_markdown(str(item.get('response') or ''))}</div>"
    )


def render_tabs(group: str, entries: list[tuple[str, str]]) -> str:
    if not entries:
        return "<p class='meta'>暂无条目。</p>"
    buttons = "".join(
        f"<button type='button' onclick=\"activateTab('{group}', '{i}')\">{esc(label)}</button>" for i, (label, _) in enumerate(entries)
    )
    panels = "".join(
        f"<div class='tab-panel {'active' if i == 0 else ''}' data-tab-group='{group}' data-tab-index='{i}'>{content}</div>"
        for i, (_, content) in enumerate(entries)
    )
    return f"<div class='tabs'><div class='tab-buttons'>{buttons}</div>{panels}</div>"


def render_ranking_matrix(aggregate: list[dict[str, Any]]) -> str:
    cells = "".join(
        f"<div class='cell'><h3>#{i + 1} {esc(item.get('model'))}</h3><p>平均名次：{esc(item.get('average_rank'))}</p><p class='meta'>投票数：{esc(item.get('rankings_count'))} · 位置：{esc(item.get('positions'))}</p></div>"
        for i, item in enumerate(aggregate)
        if isinstance(item, dict)
    )
    empty = '<p class="meta">暂无聚合排序。</p>'
    return f"<div class='matrix'>{cells or empty}</div>"


def render_summary_cards(manifest: dict[str, Any], aggregate: list[dict[str, Any]]) -> str:
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    quorum = metadata.get("quorum") if isinstance(metadata.get("quorum"), dict) else {}
    chairman = metadata.get("chairman") if isinstance(metadata.get("chairman"), dict) else {}
    top_model = aggregate[0].get("model") if aggregate and isinstance(aggregate[0], dict) else "暂无聚合排序"
    search = summarize_search_usage(manifest)
    search_text = f"允许：{yes_no(search['lct_search_allowed'])} · 实际使用：{yes_no(search['lct_search_used'])}"
    search_meta = f"Web 工具调用：{search['lct_web_tool_calls']} · 总工具调用：{search['tool_calls_count']}"
    cards = [
        f"<div class='summary-card'><h3>最高排序成员</h3><p>{esc(top_model)}</p></div>"
    ]
    if quorum:
        effective = quorum.get("effective_valid_members")
        minimum = quorum.get("min_valid_members")
        quorum_status = "low quorum" if quorum.get("low_quorum_used") else ("normal quorum" if quorum.get("normal_quorum_met") else "quorum failed")
        members = ", ".join(str(item) for item in quorum.get("effective_stage1_members") or [])
        backfill = ", ".join(str(item) for item in quorum.get("backfill_attempted") or [])
        meta_parts = []
        if members:
            meta_parts.append(f"有效成员：{members}")
        if backfill:
            meta_parts.append(f"auto-backfill：{backfill}")
        cards.append(
            f"<div class='summary-card'><h3>Quorum 状态</h3><p>{esc(effective)} / {esc(minimum)} · {esc(quorum_status)}</p>"
            f"<p class='meta'>{esc(' · '.join(meta_parts))}</p></div>"
        )
    else:
        cards.append(f"<div class='summary-card'><h3>成员模型</h3><p>{esc(', '.join(config.get('members') or []))}</p></div>")

    if chairman.get("fallback_used") or chairman.get("fallback_from"):
        fallback_from = chairman.get("fallback_from") or config.get("chairman")
        used = chairman.get("used")
        cards.append(
            f"<div class='summary-card'><h3>主席备选</h3><p>{esc(fallback_from)} -> {esc(used)}</p></div>"
        )
    else:
        cards.append(f"<div class='summary-card'><h3>主席模型</h3><p>{esc(config.get('chairman'))}</p></div>")
    cards.append(f"<div class='summary-card'><h3>搜索工具</h3><p>{esc(search_text)}</p><p class='meta'>{esc(search_meta)}</p></div>")
    return "".join(cards)


def summarize_search_usage(manifest: dict[str, Any]) -> dict[str, Any]:
    search_allowed = False
    web_tool_calls_count = 0
    web_tool_call_keys: set[str] = set()
    tool_calls_count = 0
    forbidden_tool_calls_count = 0

    def record_web_tool_call(call: dict[str, Any]) -> None:
        nonlocal web_tool_calls_count
        if call.get("name") not in WEB_SEARCH_TOOLS:
            return
        key = str(call.get("id") or (call.get("name"), call.get("arguments"), call.get("turn_index")))
        if key in web_tool_call_keys:
            return
        web_tool_call_keys.add(key)
        web_tool_calls_count += 1

    for item in iter_stage_records(manifest):
        allowed_tools = item.get("allowed_tools")
        if isinstance(allowed_tools, list) and any(tool in WEB_SEARCH_TOOLS for tool in allowed_tools):
            search_allowed = True

        raw_count = item.get("tool_calls_count")
        if isinstance(raw_count, int):
            tool_calls_count += raw_count

        tool_calls = item.get("tool_calls")
        if isinstance(tool_calls, list):
            if not isinstance(raw_count, int):
                tool_calls_count += len(tool_calls)
            for call in tool_calls:
                if isinstance(call, dict):
                    record_web_tool_call(call)

        forbidden_tool_calls = item.get("forbidden_tool_calls")
        if isinstance(forbidden_tool_calls, list):
            forbidden_tool_calls_count += len(forbidden_tool_calls)
            for call in forbidden_tool_calls:
                if isinstance(call, dict):
                    record_web_tool_call(call)

    return {
        "lct_search_allowed": search_allowed,
        "lct_search_used": web_tool_calls_count > 0,
        "lct_web_tool_calls": web_tool_calls_count,
        "search_allowed": search_allowed,
        "search_used": web_tool_calls_count > 0,
        "web_tool_calls_count": web_tool_calls_count,
        "tool_calls_count": tool_calls_count,
        "forbidden_tool_calls_count": forbidden_tool_calls_count,
    }


def iter_stage_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    records: list[dict[str, Any]] = []
    for stage_name in ("stage1", "stage2"):
        stage_items = stages.get(stage_name)
        if isinstance(stage_items, list):
            records.extend(item for item in stage_items if isinstance(item, dict))
    stage3 = stages.get("stage3")
    if isinstance(stage3, dict):
        records.append(stage3)
    return records


def yes_no(value: bool) -> str:
    return "是" if value else "否"


def render_model_performance_summary(manifest: dict[str, Any]) -> str:
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    stage1 = stages.get("stage1") if isinstance(stages.get("stage1"), list) else []
    stage2 = stages.get("stage2") if isinstance(stages.get("stage2"), list) else []
    stage3 = stages.get("stage3") if isinstance(stages.get("stage3"), dict) else {}
    rows = []
    for item in stage1:
        if not isinstance(item, dict):
            continue
        rows.append(_performance_row(item.get("model", "?"), "阶段 1", item))
    for item in stage2:
        if not isinstance(item, dict):
            continue
        rows.append(_performance_row(item.get("model", "?"), "阶段 2", item))
    if stage3:
        rows.append(_performance_row(stage3.get("model", "?"), "阶段 3", stage3))
    if not rows:
        return ""
    header = "<tr><th>模型</th><th>阶段</th><th>状态</th><th>工具调用</th><th>轮次</th><th>备注</th></tr>"
    return (
        f"<div class='model-performance' aria-label='模型表现摘要'>"
        f"<h2 class='appendix-title'>模型表现摘要</h2>"
        f"<table><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"
        f"</div>"
    )


def _performance_row(model, stage_label, item):
    status = item.get("status", "?")
    status_class = f"status-{esc(status)}" if status in ("ok", "failed", "degraded_ok") else ""
    tc = item.get("tool_calls_count")
    turns = item.get("turns_count")
    remarks = []
    if item.get("raw_partial_recoverable"):
        remarks.append("部分输出可恢复")
    if item.get("tool_budget_status") and item.get("tool_budget_status") not in ("ok", None):
        remarks.append(f"工具预算：{item.get('tool_budget_status')}")
    return (
        f"<tr><td>{esc(model)}</td><td>{esc(stage_label)}</td>"
        f"<td class='{status_class}'>{esc(status)}</td>"
        f"<td>{esc(str(tc)) if tc is not None else '—'}</td>"
        f"<td>{esc(str(turns)) if turns is not None else '—'}</td>"
        f"<td>{esc('；'.join(remarks)) if remarks else '—'}</td></tr>"
    )


def render_metadata(manifest: dict[str, Any], warnings: list[Any], failures: list[Any]) -> str:
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    failure_html = "<p class='status-ok'>无失败项。</p>" if not failures else f"<pre><code>{esc(json.dumps(failures, ensure_ascii=False, indent=2))}</code></pre>"
    warning_html = "" if not warnings else f"<pre class='warning'><code>{esc(json.dumps(warnings, ensure_ascii=False, indent=2))}</code></pre>"
    return (
        "<div class='matrix'>"
        f"<div class='cell'><h3>模型阵容</h3><p>成员：{esc(', '.join(config.get('members') or []))}</p><p>主席：{esc(config.get('chairman'))}</p></div>"
        f"<div class='cell'><h3>运行时</h3><p>Provider：{esc(config.get('provider_mode'))}</p><p>命令：{esc(config.get('runtime_command'))}</p></div>"
        f"<div class='cell'><h3>警告 / 失败</h3>{warning_html}{failure_html}</div>"
        "</div>"
    )


def render_alerts(
    warnings: list[Any],
    failures: list[Any],
    manifest_status: str = "ok",
    manifest: dict[str, Any] | None = None,
) -> str:
    manifest = manifest or {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    quorum = metadata.get("quorum") if isinstance(metadata.get("quorum"), dict) else {}
    alerts: list[str] = []
    if manifest_status == "degraded_ok" and quorum.get("low_quorum_used"):
        effective = quorum.get("effective_valid_members")
        minimum = quorum.get("min_valid_members")
        alerts.append(
            "<section class='warning-banner'><strong>Quorum 降级</strong>"
            f"<p>本报告为 degraded fallback：仅 {esc(effective)} 个有效成员参与最终综合，低于默认 {esc(minimum)}-member quorum。</p></section>"
        )
    return "".join(alerts)


def render_trace(stage1: list[Any], stage2: list[Any], stage3: dict[str, Any] | None) -> str:
    rows: list[str] = []
    for stage_name, items in (("stage1", stage1), ("stage2", stage2)):
        for item in items:
            if not isinstance(item, dict):
                continue
            budget_html = ""
            tool_budget_status = item.get("tool_budget_status")
            if tool_budget_status and tool_budget_status not in ("ok", None):
                budget_html = f" · <span class='warning'>工具预算：{esc(tool_budget_status)}</span>"
            rows.append(
                f"<div class='cell'><h3>{esc(stage_name)} · {esc(item.get('file_label') or item.get('reviewer_label'))}</h3>"
                f"<p>{esc(item.get('expected_model'))} -> {esc(item.get('actual_model'))}</p><p class='meta'>{esc(item.get('status'))}{budget_html}</p></div>"
            )
    if stage3:
        budget_html = ""
        tool_budget_status = stage3.get("tool_budget_status")
        if tool_budget_status and tool_budget_status not in ("ok", None):
            budget_html = f" · <span class='warning'>工具预算：{esc(tool_budget_status)}</span>"
        rows.append(
            f"<div class='cell'><h3>stage3 · 主席</h3><p>{esc(stage3.get('expected_model'))} -> {esc(stage3.get('actual_model'))}</p><p class='meta'>{esc(stage3.get('status'))}{budget_html}</p></div>"
        )
    return "<div class='matrix'>" + "".join(rows) + "</div>"


def render_flow_svg() -> str:
    return """<svg viewBox="0 0 760 170" role="img" aria-label="Council flow">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#7b2d26"/></marker></defs>
<rect x="20" y="55" width="130" height="60" rx="4" fill="#fbf6ea" stroke="#b9a98f"/><text x="85" y="90" text-anchor="middle">输入</text>
<line x1="150" y1="85" x2="230" y2="85" stroke="#7b2d26" stroke-width="2" marker-end="url(#arrow)"/>
<rect x="230" y="30" width="140" height="110" rx="4" fill="#fbf6ea" stroke="#b9a98f"/><text x="300" y="72" text-anchor="middle">阶段 1</text><text x="300" y="98" text-anchor="middle">成员回答</text>
<line x1="370" y1="85" x2="450" y2="85" stroke="#7b2d26" stroke-width="2" marker-end="url(#arrow)"/>
<rect x="450" y="30" width="140" height="110" rx="4" fill="#fbf6ea" stroke="#b9a98f"/><text x="520" y="72" text-anchor="middle">阶段 2</text><text x="520" y="98" text-anchor="middle">互评</text>
<line x1="590" y1="85" x2="660" y2="85" stroke="#7b2d26" stroke-width="2" marker-end="url(#arrow)"/>
<rect x="660" y="55" width="80" height="60" rx="4" fill="#fbf6ea" stroke="#b9a98f"/><text x="700" y="90" text-anchor="middle">最终</text>
</svg>"""


def build_markdown_export(manifest: dict[str, Any], input_text: str, final_text: str) -> str:
    aggregate = manifest.get("metadata", {}).get("aggregate_rankings") or []
    ranking = "\n".join(f"- {item.get('model')}: average rank {item.get('average_rank')}" for item in aggregate)
    return f"""# LLM Council for Trae 运行 {manifest.get('run_id')}

状态：{manifest.get('status')}

## 输入

{input_text}

## 聚合排序

{ranking or '暂无聚合排序。'}

## 最终答案

{final_text}
"""


def safe_read(path: Path) -> str:
    return read_text(path) if path.exists() else ""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def json_for_script(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False)
    return (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
