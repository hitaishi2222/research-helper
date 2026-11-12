"""Project root discovery + .rh/ layout.

Priority: explicit --root, RH_ROOT, cwd walk-up for `.rh/`, cwd.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

RH_DIR = ".rh"

# Files kept under .rh/ (clean workspace). src/, results/, papers/ stay at root.
RH_ARTIFACTS = {
    "ENVIRONMENT.md": "environment_md",
    "PROBLEM.md": "problem_md",
    "PLAN.md": "plan_md",
    "STATUS.md": "status_md",
    "HANDOFF.md": "handoff_md",
    "LITERATURE.md": "literature_md",
    "OUTPUT_LAYOUT.md": "output_layout_md",
    "GAPS.md": "gaps_md",
    "MANUSCRIPT.md": "manuscript_md",
}


def find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    # walk up looking for .rh/ (everything lives inside it)
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


def _bak_dir(root: Path) -> Path:
    """A fresh `.rh/.bak/<timestamp>/` — never reusing one from the same second."""
    bak = rh_dir(root) / ".bak"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = bak / stamp
    n = 1
    while dest.exists():
        dest = bak / f"{stamp}-{n}"
        n += 1
    dest.mkdir(parents=True)
    return dest


def backup_file(root: Path, path: Path) -> Path:
    """Archive `path` to `.rh/.bak/<timestamp>/<name>`, return the backup copy."""
    dest = _bak_dir(root) / path.name
    shutil.copy2(path, dest)
    return dest


def archive_tree(root: Path, src: Path) -> Path:
    """Copy `src` aside, then remove it. Returns `.rh/.bak/<timestamp>/`.

    The copy is made *before* the removal, so a failed copy leaves `src`
    untouched. Used by `rh init --clean`, which must never delete what it could
    not archive (event logs, notes, env.json, tasks.json) — and must not throw
    away earlier archives either: they are re-filed beside the new one.
    """
    tmp = src.with_name(f"{src.name}.archiving-{os.getpid()}")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp, symlinks=True)
    old_bak = tmp / ".bak"
    saved = None
    if old_bak.exists():
        saved = tmp.with_name(f"{tmp.name}-bak")
        if saved.exists():
            shutil.rmtree(saved)
        old_bak.rename(saved)
    shutil.rmtree(src)
    dest = _bak_dir(root)
    shutil.rmtree(dest)  # empty placeholder; the archived tree takes its place
    tmp.rename(dest)
    if saved:
        bakdir = rh_dir(root) / ".bak"
        for old in sorted(saved.iterdir()):
            target = bakdir / old.name
            n = 1
            while target.exists():
                target = bakdir / f"{old.name}-{n}"
                n += 1
            old.rename(target)
        shutil.rmtree(saved)
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
    """The single config file (SKILL.md §2 config block)."""
    return rh_dir(root) / "env.json"


def environment_md(root: Path) -> Path:
    """The Orchestrator's phase-2 environment notes (prose, not config)."""
    return rh_dir(root) / "ENVIRONMENT.md"


def checklist_md(root: Path) -> Path:
    """The Orchestrator's generated setup + gate checklist."""
    return rh_dir(root) / "CHECKLIST.md"


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
    """Legacy pre-0.2 location, used only by the one-time migration."""
    return rh_dir(root) / "ENV.md" if rh_dir(root).exists() else root / "ENV.md"


def artifact_path(root: Path, name: str) -> Path:
    """Where SKILL.md artifact `name` lives: .rh/<name> if root has .rh, else root/<name>.

    Migration-safe: if the artifact already exists at root and not in .rh,
    callers should read from root and write through to .rh (or keep both in
    sync). Prefer .rh when initialized.

    ENVIRONMENT.md is always in .rh/ when initialized.
    """
    if name == "ENVIRONMENT.md":
        return environment_md(root)
    if name == "HANDOFF.md":
        return rh_dir(root) / name  # authored handoff, never mirrored at the root

    in_rh = rh_dir(root) / name
    legacy = root / name
    if in_rh.exists():
        return in_rh
    if legacy.exists():
        return legacy
    # new artifacts go in .rh/ when initialized
    return in_rh if rh_dir(root).exists() else legacy
