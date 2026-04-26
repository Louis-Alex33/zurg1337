from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().with_name("web_ui")

# Compatibility shim: this repository now stores the UI in the web_ui/
# package, but a root-level web_ui.py can still be imported by Python first.
__path__ = [str(_PACKAGE_DIR)]  # type: ignore[var-annotated]
__package__ = __name__

_init_path = _PACKAGE_DIR / "__init__.py"
exec(compile(_init_path.read_text(encoding="utf-8"), str(_init_path), "exec"), globals(), globals())
