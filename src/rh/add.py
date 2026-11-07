"""`rh add` — append under a heading/DOI, creating it if missing.

Targets:
  note        -> .rh/notes/<title-token>.md  (heading-created files)
  literature  -> LITERATURE.md  (SKILL.md §3: citation + DOI + take/reject)
  layout      -> OUTPUT_LAYOUT.md  (SKILL.md §3: output skeleton + paper patterns)
  gaps        -> GAPS.md
  problem     -> PROBLEM.md
  plan        -> PLAN.md
  status      -> STATUS.md
  manuscript  -> MANUSCRIPT.md
  log         -> .rh/logs/YYYY-MM-DD-HHMM-<role>-<title-token>.md
  task        -> .rh/tasks.json via TaskStore
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import paths

ADD_TARGETS = {
    "note": "notes",
    "literature": "LITERATURE.md",
    "layout": "OUTPUT_LAYOUT.md",
    "gaps": "GAPS.md",
    "problem": "PROBLEM.md",
    "plan": "PLAN.md",
    "status": "STATUS.md",
    "manuscript": "MANUSCRIPT.md",
    "log": "log",
    "task": "task",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "untitled"


def _heading_re(heading: str) -> re.Pattern:
    # match `## <heading>` exactly (case-insensitive)
    return re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)


def _doi_re(doi: str) -> re.Pattern:
    clean = doi.strip().removeprefix("https://doi.org/")
    return re.compile(rf"doi[:\s]*{re.escape(clean)}", re.IGNORECASE)


def append_under(artifact: Path, heading: str, body: str, *, use_doi: bool = False) -> str:
    """Append `body` under `heading` (or create it). Returns 'created'|'appended'."""
    artifact.parent.mkdir(parents=True, exist_ok=True)
    text = artifact.read_text(encoding="utf-8") if artifact.exists() else ""
    pattern = _doi_re(heading) if use_doi else _heading_re(heading)
    m = pattern.search(text)
    block = body.strip("\n") + "\n"
    if m:
        # append at end of that section: before next ## heading or EOF
        nxt = re.search(r"\n## ", text[m.end():])
        if nxt:
            insert_at = m.end() + nxt.start()
            text = text[:insert_at].rstrip() + "\n\n" + block + text[insert_at:].lstrip("\n")
        else:
            text = text.rstrip() + "\n\n" + block
        result = "appended"
    else:
        title = heading if use_doi else f"## {heading}"
        if use_doi:
            title = f"## {heading}\n\nDOI: {heading}"
        text = (text.rstrip() + "\n\n" if text.strip() else "") + title + "\n\n" + block
        result = "created"
    artifact.write_text(text, encoding="utf-8")
    return result


def add_note(root: Path, heading_or_file: str, body: str, *, file: str | None = None) -> tuple[Path, str]:
    """Note: file defaults to kebab of heading; heading is the ## section."""
    name = file or f"{slugify(heading_or_file)}.md"
    target = paths.notes_dir(root) / name
    result = append_under(target, heading_or_file, body)
    return target, result


def add_log(root: Path, role: str, title: str, body: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    target = paths.logs_dir(root) / f"{ts}-{slugify(role)}-{slugify(title)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = f"# {title}\n- phase / step: \n- what was tried: \n- outcome: \n- evidence: \n- decision taken + why: \n- what a future agent must not redo: \n\n{body.strip()}\n"
    target.write_text(text, encoding="utf-8")
    return target


def add_text(root: Path, target_kind: str, heading_or_doi: str, body: str) -> tuple[Path, str]:
    if target_kind not in ADD_TARGETS or target_kind in ("note", "log", "task"):
        raise ValueError(f"unknown add target {target_kind!r}; choices: {sorted(ADD_TARGETS)}")
    artifact = paths.artifact_path(root, ADD_TARGETS[target_kind])
    use_doi = target_kind == "literature" and re.search(
        r"\b10\.\d{4,9}/", heading_or_doi, re.IGNORECASE
    ) is not None
    result = append_under(artifact, heading_or_doi, body, use_doi=use_doi)
    return artifact, result
