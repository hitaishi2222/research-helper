"""Project root discovery + .rh/ layout.

Priority: explicit --root, RH_ROOT, cwd walk-up for `.rh/` (ENV.md is inside .rh/), cwd.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

RH_DIR = ".rh"

# Files kept under .rh/ (clean workspace). src/, results/, papers/ stay at root.
RH_ARTIFACTS = {
    "PROBLEM.md": "problem_md",
    "PLAN.md": "plan_md",
    "STATUS.md": "status_md",
    "LITERATURE.md": "literature_md",
    "OUTPUT_LAYOUT.md": "output_layout_md",
    "GAPS.md": "gaps_md",
    "MANUSCRIPT.md": "manuscript_md",
}


def find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    # walk up looking for .rh/ (ENV.md is now inside .rh/)
    cur = start
    for parent in [cur, *cur.parents]:
        if (parent / RH_DIR).is_dir():
            return parent
    return start


def resolve_root(cli_root: str | None = None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env = os.environ.get("RH_ROOT") or os.environ.get("RH_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return find_project_root()


def rh_dir(root: Path) -> Path:
    return root / RH_DIR


def backup_file(root: Path, path: Path) -> Path:
    """Archive `path` to `.rh/.bak/<timestamp>/<name>`, return the backup copy."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = rh_dir(root) / ".bak" / stamp / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def ensure_layout(root: Path) -> Path:
    """Create .rh/ subfolders. Returns the .rh path."""
    d = rh_dir(root)
    for sub in ("logs", "notes", "tasks", "tmp"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "papers").mkdir(parents=True, exist_ok=True)
    return d


def env_json(root: Path) -> Path:
    return rh_dir(root) / "env.json"


def tasks_json(root: Path) -> Path:
    return rh_dir(root) / "tasks.json"


def notes_dir(root: Path) -> Path:
    return rh_dir(root) / "notes"


def logs_dir(root: Path) -> Path:
    return rh_dir(root) / "logs"


def papers_dir(root: Path) -> Path:
    """Downloaded PDFs live at the project root: ./papers/ (never deleted by rh)."""
    d = root / "papers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def env_md(root: Path) -> Path:
    """ENV.md lives inside .rh/ (config block + environment notes)."""
    return rh_dir(root) / "ENV.md" if rh_dir(root).exists() else root / "ENV.md"


def artifact_path(root: Path, name: str) -> Path:
    """Where SKILL.md artifact `name` lives: .rh/<name> if root has .rh, else root/<name>.

    Migration-safe: if the artifact already exists at root and not in .rh,
    callers should read from root and write through to .rh (or keep both in
    sync). Prefer .rh when initialized.

    ENV.md is always in .rh/ when initialized.
    """
    if name == "ENV.md":
        return env_md(root)

    in_rh = rh_dir(root) / name
    legacy = root / name
    if in_rh.exists():
        return in_rh
    if legacy.exists():
        return legacy
    # new artifacts go in .rh/ when initialized
    return in_rh if rh_dir(root).exists() else legacy
