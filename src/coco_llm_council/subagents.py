from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import get_models, model_names


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def inspect_subagents(project_root: Path, runtime_command: str = "traecli") -> dict[str, Any]:
    agents_dir = project_root / ".trae" / "agents"
    available_models = model_names(get_models(runtime_command))
    entries: list[dict[str, Any]] = []
    for path in sorted(agents_dir.glob("*.md")):
        frontmatter = parse_frontmatter(path)
        required = ["name", "description", "model"]
        missing = [key for key in required if not frontmatter.get(key)]
        model = frontmatter.get("model")
        entries.append(
            {
                "path": str(path),
                "file": path.name,
                "name": frontmatter.get("name"),
                "model": model,
                "missing": missing,
                "model_available": bool(model and model in available_models),
                "ok": not missing and bool(model and model in available_models),
            }
        )
    return {
        "agents_dir": str(agents_dir),
        "count": len(entries),
        "subagents": entries,
        "ok": bool(entries) and all(entry["ok"] for entry in entries),
    }
