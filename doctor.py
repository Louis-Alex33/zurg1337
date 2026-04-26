from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def run_doctor(root_dir: str | Path = ".") -> list[dict[str, Any]]:
    root = Path(root_dir)
    checks = [
        check_python_version(),
        check_dependency("requests"),
        check_dependency("bs4"),
        check_directory(root / "data", create=True),
        check_directory(root / "reports", create=True),
        check_directory(root / "reports" / "audits", create=True),
        check_writable(root / "data"),
        check_writable(root / "reports" / "audits"),
    ]
    return checks


def check_python_version() -> dict[str, Any]:
    ok = sys.version_info >= (3, 11)
    return {
        "check": "python_version",
        "ok": ok,
        "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def check_dependency(module_name: str) -> dict[str, Any]:
    found = importlib.util.find_spec(module_name) is not None
    return {"check": f"dependency_{module_name}", "ok": found, "detail": "installed" if found else "missing"}


def check_directory(path: Path, create: bool = False) -> dict[str, Any]:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return {"check": f"directory_{path}", "ok": path.exists() and path.is_dir(), "detail": str(path)}


def check_writable(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".doctor_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"check": f"writable_{path}", "ok": True, "detail": str(path)}
    except OSError as exc:
        return {"check": f"writable_{path}", "ok": False, "detail": str(exc)}


def format_doctor_results(checks: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for check in checks:
        status = "OK" if check.get("ok") else "FAIL"
        lines.append(f"{status} | {check.get('check')} | {check.get('detail')}")
    return lines
