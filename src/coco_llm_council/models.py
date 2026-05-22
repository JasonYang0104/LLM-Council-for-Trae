from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .utils import DEFAULT_TRAECLI, parse_json_output, run_command


@dataclass
class RuntimeHealth:
    ok: bool
    command: str
    version: str | None
    doctor_exit_code: int | None
    doctor: dict[str, Any] | None
    models: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]


def get_models(runtime_command: str = DEFAULT_TRAECLI) -> list[dict[str, Any]]:
    proc = run_command([runtime_command, "models", "--json"], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "traecli models failed")
    data = parse_json_output(proc.stdout)
    if not isinstance(data, list):
        raise RuntimeError("traecli models --json did not return a list")
    return data


def model_names(models: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for model in models:
        name = model.get("name")
        real_name = model.get("real_name")
        if isinstance(name, str):
            names.add(name)
        if isinstance(real_name, str):
            names.add(real_name)
    return names


def require_models_available(expected: list[str], models: list[dict[str, Any]]) -> None:
    available = model_names(models)
    missing = [name for name in expected if name not in available]
    if missing:
        raise ValueError(
            "Model(s) not available in traecli models --json: "
            + ", ".join(missing)
            + ". Available: "
            + ", ".join(sorted(available))
        )


def doctor(runtime_command: str = DEFAULT_TRAECLI) -> RuntimeHealth:
    errors: list[str] = []
    warnings: list[str] = []

    version_proc = run_command([runtime_command, "--version"], timeout=30)
    version = version_proc.stdout.strip() or version_proc.stderr.strip() or None
    if version_proc.returncode != 0:
        errors.append(f"{runtime_command} --version failed: {version or version_proc.returncode}")

    doctor_proc = run_command([runtime_command, "doctor", "--json"], timeout=60)
    doctor_json: dict[str, Any] | None = None
    if doctor_proc.stdout.strip():
        try:
            parsed = parse_json_output(doctor_proc.stdout)
            if isinstance(parsed, dict):
                doctor_json = parsed
        except Exception as exc:  # pragma: no cover - defensive reporting
            errors.append(f"could not parse doctor JSON: {exc}")
    if doctor_proc.returncode >= 2:
        errors.append(doctor_proc.stderr.strip() or doctor_proc.stdout.strip() or "traecli doctor reported errors")
    elif doctor_proc.returncode == 1:
        warnings.append("traecli doctor reported warnings")

    models: list[dict[str, Any]] = []
    try:
        models = get_models(runtime_command)
    except Exception as exc:
        errors.append(str(exc))

    if not models:
        errors.append("no models returned by traecli models --json")

    return RuntimeHealth(
        ok=not errors,
        command=runtime_command,
        version=version,
        doctor_exit_code=doctor_proc.returncode,
        doctor=doctor_json,
        models=models,
        errors=errors,
        warnings=warnings,
    )
