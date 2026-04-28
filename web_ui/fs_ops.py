from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import unquote

from utils import CLIError

from . import _root_dir

ROOT_DIR = _root_dir()
UPLOAD_DIR = "uploads/gsc"
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".tsv", ".txt"}


def resolve_local_file(requested_path: str) -> Path:
    if not requested_path:
        raise CLIError("Chemin de fichier manquant.")
    root_dir = _root_dir()
    resolved = (root_dir / unquote(requested_path)).resolve()
    if root_dir not in resolved.parents and resolved != root_dir:
        raise CLIError("Chemin non autorise.")
    return resolved


def save_uploaded_gsc_file(filename: str, payload: bytes) -> str:
    if not filename:
        raise CLIError("Nom de fichier upload manquant.")
    if not payload:
        raise CLIError(f"Fichier upload vide: {filename}")

    safe_name = sanitize_upload_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_SUFFIXES))
        raise CLIError(f"Extension non supportee pour {filename}. Extensions autorisees: {allowed}")

    root_dir = _root_dir()
    upload_dir = (root_dir / UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = (upload_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}").resolve()
    if upload_dir not in target.parents:
        raise CLIError("Chemin d'upload non autorise.")
    target.write_bytes(payload)
    return str(target.relative_to(root_dir))


def sanitize_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = name.strip("._")
    return name or "gsc_export.csv"


def delete_managed_file(requested_path: str, cascade: bool = False) -> list[str]:
    root_dir = _root_dir()
    path = resolve_local_file(requested_path)
    relative = str(path.relative_to(root_dir))
    allowed = {
        "data/domains_raw.csv",
        "data/domains_scored.csv",
        "data/domains_scored.json",
    }
    if relative not in allowed:
        raise CLIError("Suppression non autorisee pour ce fichier.")

    deleted: list[str] = []
    targets = [path]
    if cascade and relative == "data/domains_scored.csv":
        targets.append((root_dir / "data/domains_scored.json").resolve())

    for target in targets:
        if not target.exists():
            continue
        target.unlink()
        deleted.append(str(target.relative_to(root_dir)))
    return deleted


def reset_pipeline_outputs() -> list[str]:
    root_dir = _root_dir()
    deleted: list[str] = []
    candidate_files = [
        "data/domains_raw.csv",
        "data/domains_scored.csv",
        "data/domains_scored.json",
        "reports/gsc_report.csv",
        "reports/gsc_report.json",
        "reports/gsc_report.html",
        "reports/audits/audit_summary.csv",
    ]
    for relative in candidate_files:
        target = (root_dir / relative).resolve()
        if target.exists():
            target.unlink()
            deleted.append(relative)

    audits_dir = (root_dir / "reports/audits").resolve()
    if audits_dir.exists():
        for json_file in sorted(audits_dir.glob("*.json")):
            json_file.unlink()
            deleted.append(str(json_file.relative_to(root_dir)))

    return deleted
