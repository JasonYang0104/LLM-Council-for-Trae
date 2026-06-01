from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import read_json, utc_now


class RunLeaseError(RuntimeError):
    pass


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class RunLease:
    path: Path
    payload: dict[str, Any]
    stale_replaced: bool = False

    @classmethod
    def acquire(cls, store_base: Path, run_id: str) -> "RunLease":
        lock_dir = store_base / ".runtime"
        lock_dir.mkdir(parents=True, exist_ok=True)
        path = lock_dir / "run.lock"
        stale_replaced = False
        payload = {
            "run_id": run_id,
            "pid": os.getpid(),
            "created_at": utc_now(),
            "command": "llm-council-for-trae run",
        }
        while True:
            try:
                write_json_atomic_create(path, payload)
                return cls(path=path, payload=payload, stale_replaced=stale_replaced)
            except FileExistsError:
                existing = read_lock_payload(path)
                pid = existing.get("pid") if isinstance(existing, dict) else None
                if isinstance(pid, int) and process_is_alive(pid):
                    run = existing.get("run_id", "unknown") if isinstance(existing, dict) else "unknown"
                    raise RunLeaseError(f"another run is active: {run} (pid {pid})")
                stale_replaced = True
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def release(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "RunLease":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


def read_lock_payload(path: Path) -> dict[str, Any]:
    try:
        payload = read_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_atomic_create(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
