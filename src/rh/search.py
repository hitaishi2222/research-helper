"""Local search over .rh/ + SKILL.md artifacts. No indexing.

Uses rg when available (fast, gitignore-aware), falls back to a pure-Python
scan. Structures files with anchors so `rh add` grouping helps retrieval.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

SEARCHABLE_SUFFIXES = {".md", ".txt", ".json", ".bib", ".tex"}
SEARCHABLE_NAMES = {"ENV.md", "PROBLEM.md", "PLAN.md", "STATUS.md", "LITERATURE.md",
                    "OUTPUT_LAYOUT.md", "GAPS.md", "MANUSCRIPT.md", "tasks.json", "env.json"}


@dataclass
class Hit:
    path: Path
    line_no: int
    line: str
    context: list[str] = field(default_factory=list)

    def render(self, root: Path, width: int = 100) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        snippet = self.line.strip()
        if len(snippet) > width:
            snippet = snippet[: width - 1] + "…"
        out = [f"{rel}:{self.line_no}  {snippet}"]
        for ctx in self.context:
            out.append(f"    {ctx.strip()[:width]}")
        return "\n".join(out)


def candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    rh = paths.rh_dir(root)
    if rh.exists():
        for p in rh.rglob("*"):
            if p.is_file() and p.suffix in SEARCHABLE_SUFFIXES:
                files.append(p)
    for name in SEARCHABLE_NAMES - {"tasks.json", "env.json"}:
        for base in (root, rh):
            p = base / name
            if p.exists():
                files.append(p)
    for sub in ("src", "results"):
        d = root / sub
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file() and p.suffix in SEARCHABLE_SUFFIXES:
                    files.append(p)
    # dedupe, stable order
    seen, out = set(), []
    for f in files:
        key = str(f.resolve()) if f.exists() else str(f)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def search_rg(root: Path, query: str, *, smart_case: bool = True, max_hits: int = 50) -> list[Hit]:
    files = candidate_files(root)
    if not files:
        return []
    cmd = ["rg", "--no-heading", "--line-number", "--with-filename"]
    if smart_case:
        cmd.append("--smart-case")
    else:
        cmd.append("--ignore-case")
    cmd += ["-e", query, "--", *[str(f) for f in files]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    hits: list[Hit] = []
    if proc.returncode not in (0, 1):  # 1 = no matches
        return []
    for line in proc.stdout.splitlines()[:max_hits]:
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        fpath, lno, text = parts
        try:
            hits.append(Hit(Path(fpath), int(lno), text))
        except ValueError:
            continue
    return hits


def search_python(root: Path, query: str, *, max_hits: int = 50) -> list[Hit]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[Hit] = []
    for f in candidate_files(root):
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        heading = ""
        for i, line in enumerate(lines, 1):
            if line.startswith("#"):
                heading = line
            if pattern.search(line):
                ctx = [heading] if heading and heading not in line else []
                hits.append(Hit(f, i, line, ctx))
                if len(hits) >= max_hits:
                    return hits
    return hits


def search(root: Path, query: str, *, max_hits: int = 50) -> tuple[list[Hit], str]:
    """Return (hits, engine). Engine is 'rg' or 'python'."""
    if shutil.which("rg"):
        return search_rg(root, query, max_hits=max_hits), "rg"
    return search_python(root, query, max_hits=max_hits), "python"
