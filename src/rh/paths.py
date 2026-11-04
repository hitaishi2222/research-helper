"""Project root discovery + .rh/ layout.

Priority: explicit --root, RH_ROOT, cwd walk-up for `.rh/` or ENV.md, cwd.
"""
from __future__ import annotations

import os
from pathlib import Path

RH_DIR = ".rh"

# Files kept under .rh/ (clean workspace). src/, results/, papers/ stay at root.
RH_ARTIFACTS = {
    "PROBLEM.md": "problem_md",
    "ENV.md": "env_md",
    "PLAN.md": "plan_md",
    "STATUS.md": "status_md",
    "LITERATURE.md": "literature_md",
    "OUTPUT_LAYOUT.md": "output_layout_md",
    "GAPS.md": "gaps_md",
    "MANUSCRIPT.md": "manuscript_md",
}


def find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    # walk up looking for .rh/ or ENV.md
    cur = start
    for parent in [cur, *cur.parents]:
        if (parent / RH_DIR).is_dir() or (parent / "ENV.md").exists():
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


def ensure_layout(root: Path) -> Path:
    """Create .rh/ subfolders. Returns the .rh path."""
    d = rh_dir(root)
    for sub in ("logs", "papers", "notes", "tasks", "tmp"):
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
    # SKILL.md papers/ at root; keep both: rh papers/ is managed, root papers/ legacy
    d = rh_dir(root) / "papers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifact_path(root: Path, name: str) -> Path:
    """Where SKILL.md artifact `name` lives: .rh/<name> if root has .rh, else root/<name>.

    Migration-safe: if the artifact already exists at root and not in .rh,
    callers should read from root and write through to .rh (or keep both in
    sync). Prefer .rh when initialized.
    """
    in_rh = rh_dir(root) / name
    legacy = root / name
    if in_rh.exists():
        return in_rh
    if legacy.exists():
        return legacy
    # new artifacts go in .rh/ when initialized
    return in_rh if rh_dir(root).exists() else legacy
