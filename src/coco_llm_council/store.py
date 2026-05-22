from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .utils import DEFAULT_STORE_DIR, append_jsonl, read_json, utc_now, write_json, write_text


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.events_path = root / "events.jsonl"

    @classmethod
    def create(cls, base_dir: Path, run_id: str) -> "ArtifactStore":
        root = base_dir / run_id
        root.mkdir(parents=True, exist_ok=False)
        for child in ("runtime", "stage1", "stage2", "stage3", "html"):
            (root / child).mkdir(parents=True, exist_ok=True)
        store = cls(root)
        store.event("run_created", {"run_id": run_id})
        return store

    @classmethod
    def open(cls, base_dir: Path, run_id: str) -> "ArtifactStore":
        root = base_dir / run_id
        if not root.exists():
            raise FileNotFoundError(f"run not found: {root}")
        return cls(root)

    @staticmethod
    def default_base(cwd: Path | None = None) -> Path:
        return (cwd or Path.cwd()) / DEFAULT_STORE_DIR

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def write_text(self, relative: str, content: str) -> Path:
        path = self.root / relative
        write_text(path, content)
        return path

    def write_json(self, relative: str, data: Any) -> Path:
        path = self.root / relative
        write_json(path, data)
        return path

    def read_manifest(self) -> dict[str, Any]:
        return read_json(self.root / "manifest.json")

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = utc_now()
        self.write_json("manifest.json", manifest)

    def event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        append_jsonl(self.events_path, {"ts": utc_now(), "type": event_type, "payload": payload or {}})

    def copy_if_exists(self, src: Path, relative: str) -> str | None:
        if not src.exists():
            return None
        dest = self.root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return str(dest.relative_to(self.root))


def resolve_store_base(path: str | None) -> Path:
    return Path(path).expanduser().resolve() if path else ArtifactStore.default_base().resolve()
