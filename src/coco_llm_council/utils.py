from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_DIR = ".coco-llm-council/runs"
DEFAULT_TRAECLI = "traecli"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "item"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def run_command(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".out", delete=False) as tmp_out:
            out_path = tmp_out.name
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".err", delete=False) as tmp_err:
            err_path = tmp_err.name
        try:
            shell_cmd = " ".join(shlex.quote(a) for a in args)
            rc = os.system(f"{shell_cmd} >{shlex.quote(out_path)} 2>{shlex.quote(err_path)}")
            actual_rc = rc >> 8 if os.name != "nt" else rc
            with open(out_path, "r") as f:
                stdout = f.read()
            with open(err_path, "r") as f:
                stderr = f.read()
            return subprocess.CompletedProcess(args=args, returncode=actual_rc, stdout=stdout, stderr=stderr)
        finally:
            os.unlink(out_path)
            os.unlink(err_path)


def parse_json_output(stdout: str) -> Any:
    return json.loads(stdout) if stdout.strip() else None


def project_relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
