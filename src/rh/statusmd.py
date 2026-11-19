"""Read what `STATUS.md` says about state — its header and its waivers.

Two parsers, both tolerant of markdown emphasis (`phase: **6 IMPLEMENT**` is as
valid as `phase: 6 IMPLEMENT`). The checklist and `rh preflight` share them so a
file is never interpreted two ways.
"""
from __future__ import annotations

import re

_PHASE = re.compile(r"phase:\s*\**\s*(\d+)", re.IGNORECASE)
_STEP = re.compile(r"step:\s*\**\s*([^\s*|]+)", re.IGNORECASE)
_UPDATED = re.compile(r"updated:\s*\**\s*(\S+)", re.IGNORECASE)
_WAIVERS = re.compile(r"^\s*waivers\s*:", re.IGNORECASE)
_STOP = re.compile(r"^\s*[A-Za-z_]+\s*:")  # the next `key:` section
_RULE = re.compile(r"\brule\s*(\d+)", re.IGNORECASE)


def parse_header(text: str) -> dict:
    """`{phase, step, updated}`, each None when the header part is missing.

    Only the top of the file is searched: the header is the first few lines, and
    a `phase:` mentioned in prose must not be mistaken for it.
    """
    head = "\n".join((text or "").splitlines()[:12])
    phase = _PHASE.search(head)
    step = _STEP.search(head)
    updated = _UPDATED.search(head)
    return {
        "phase": int(phase.group(1)) if phase else None,
        "step": step.group(1).strip() if step else None,
        "updated": updated.group(1).strip() if updated else None,
    }


def waivers(text: str) -> set[int]:
    """Rule numbers waived under a `waivers:` list (rule 11).

    Only the list that follows the `waivers:` line counts: a `rule 7` mentioned
    in history is a sentence, not a waiver.
    """
    out: set[int] = set()
    inside = False
    for line in (text or "").splitlines():
        if _WAIVERS.match(line):
            inside = True
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped:
            inside = False
            continue
        if not stripped.startswith(("-", "*")) and _STOP.match(line):
            inside = False
            continue
        found = _RULE.search(stripped)
        if found:
            out.add(int(found.group(1)))
    return out
