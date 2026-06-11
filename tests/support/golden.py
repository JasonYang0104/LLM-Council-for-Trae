from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


VOLATILE_KEYS = {"created_at", "updated_at", "captured_at", "generated_at"}


def normalize_for_golden(value: Any, *, run_id: str, root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: "<TS>" if key in VOLATILE_KEYS else normalize_for_golden(item, run_id=run_id, root=root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_for_golden(item, run_id=run_id, root=root) for item in value]
    if isinstance(value, str):
        normalized = value.replace(run_id, "<RUN_ID>").replace(str(root), "<RUN_ROOT>")
        normalized = re.sub(r"/var/folders/[^\s\"']+", "<TMP>", normalized)
        normalized = re.sub(r"/tmp/[^\s\"']+", "<TMP>", normalized)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", "<TS>", normalized)
        return normalized
    return value


def json_file(root: Path, relative: str, *, run_id: str) -> Any:
    data = json.loads((root / relative).read_text(encoding="utf-8"))
    return normalize_for_golden(data, run_id=run_id, root=root)


def text_file(root: Path, relative: str, *, run_id: str) -> str:
    text = (root / relative).read_text(encoding="utf-8")
    return normalize_for_golden(text, run_id=run_id, root=root)


def snapshot_run(root: Path) -> dict[str, Any]:
    run_id = root.name
    files = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
    html = text_file(root, "html/index.html", run_id=run_id)
    return {
        "files": files,
        "manifest": json_file(root, "manifest.json", run_id=run_id),
        "config": json_file(root, "config.json", run_id=run_id),
        "stage1_meta": {
            label: json_file(root, f"stage1/{label}.meta.json", run_id=run_id)
            for label in ("A", "B", "C")
        },
        "stage2_reviews": {
            label: json_file(root, f"stage2/{label}.review.json", run_id=run_id)
            for label in ("A", "B", "C")
        },
        "stage2_meta": {
            label: json_file(root, f"stage2/{label}.meta.json", run_id=run_id)
            for label in ("A", "B", "C")
        },
        "stage3_final": json_file(root, "stage3/final.json", run_id=run_id),
        "stage3_meta": json_file(root, "stage3/final.meta.json", run_id=run_id),
        "html_export": json_file(root, "html/export.json", run_id=run_id),
        "user_text": {
            "input": text_file(root, "input.md", run_id=run_id),
            "final": text_file(root, "stage3/final.md", run_id=run_id),
        },
        "html_checks": {
            "contains_final_answer": "最终综合答案" in html,
            "contains_search_summary": "允许：" in html and "实际使用：" in html,
            "contains_stage1_appendix": "阶段 1" in html or "Stage 1" in html,
            "contains_stage2_appendix": "阶段 2" in html or "Stage 2" in html,
            "chars": len(html),
        },
    }
