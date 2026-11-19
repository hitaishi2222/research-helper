"""`rh verify` — pair every manuscript claim with the files that carry it.

Rule 7 says no number exists without the file that produced it. Past a few dozen
numbers nobody checks by hand, so each claim block carries its own evidence line
(`evidence: results/S07.csv, LITERATURE.md`) and this module checks the claim
against exactly those files — never against the whole project.

What it can prove: the cited file exists, and every number in the claim appears
in it. What it cannot prove: that the number was copied into the right sentence,
or that a coincidental match elsewhere in the cited file is the intended one.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import paths

NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
EVIDENCE = re.compile(r"^\s*(?:[-*]\s*)?\**evidence\**\s*:\s*(.+)$", re.IGNORECASE)
BRACKETED = re.compile(r"\[[^\]]*\]")
MAX_READ = 5_000_000  # shortcut: a bigger results file is read truncated, upgrade if that bites


def blocks(text: str) -> list[tuple[int, list[str]]]:
    """Blank-line separated blocks outside fenced code, with their 1-based line."""
    out: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start = 0
    fenced = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if not line.strip():
            if current:
                out.append((start, current))
                current = []
            continue
        if not current:
            start = i
        current.append(line)
    if current:
        out.append((start, current))
    return out


def _cites(value: str) -> list[str]:
    return [c.strip().strip("`") for c in re.split(r"[,\s]+", value) if c.strip()]


def _segments(start: int, lines: list[str]):
    """Split one block at its `evidence:` lines: (line_no, claim_lines, cites).

    A claim block ends with its evidence line, so the text before it is the claim
    and anything after starts the next one. A block that is only an evidence line
    yields no claim lines, which the caller attaches to the previous claim.
    """
    pending: list[str] = []
    pending_start = start
    for offset, line in enumerate(lines):
        match = EVIDENCE.match(line.strip())
        if match:
            yield pending_start, pending, _cites(match.group(1))
            pending = []
            pending_start = start + offset + 1
            continue
        if not pending:
            pending_start = start + offset
        pending.append(line)
    if pending:
        yield pending_start, pending, []


def _is_heading(lines: list[str]) -> bool:
    return all(not line.strip() or line.lstrip().startswith("#") for line in lines)


def numbers(text: str) -> list[str]:
    """Numeric tokens in a claim, minus citation brackets and bare years."""
    cleaned = BRACKETED.sub(" ", text)
    out: list[str] = []
    for match in NUMBER.finditer(cleaned):
        token = match.group(0)
        if re.fullmatch(r"\d{4}", token) and 1900 <= int(token) <= 2100:
            continue  # a year is a citation, not a measurement
        out.append(token)
    return out


def _values(path: Path) -> set[float] | None:
    """Every number in a cited file, by value; None when it cannot be read."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(MAX_READ)
    except OSError:
        return None
    return {float(t) for t in NUMBER.findall(text)}


def check(root: Path) -> dict:
    manuscript = paths.artifact_path(root, "MANUSCRIPT.md")
    if not manuscript.is_file():
        return {
            "root": str(root),
            "file": str(manuscript),
            "claims": 0,
            "findings": [],
            "ok": True,
            "message": "no manuscript yet — nothing to verify",
        }
    text = manuscript.read_text(encoding="utf-8", errors="replace")
    claims: list[dict] = []
    for start, lines in blocks(text):
        for line_no, claim_lines, cites in _segments(start, lines):
            if not claim_lines:
                # a bare `evidence:` block belongs to the claim above it
                if cites and claims:
                    claims[-1]["cites"].extend(cites)
                continue
            if _is_heading(claim_lines):
                continue
            claims.append(
                {"line": line_no, "text": "\n".join(claim_lines), "cites": list(cites)}
            )

    findings: list[dict] = []
    cache: dict[str, set[float] | None] = {}
    for claim in claims:
        if not claim["cites"]:
            findings.append(
                {
                    "type": "no-evidence",
                    "line": claim["line"],
                    "message": "claim has no `evidence:` line",
                    "rule": 7,
                }
            )
            continue
        found: set[float] = set()
        missing_any = False
        for cite in claim["cites"]:
            path = Path(cite)
            path = path if path.is_absolute() else root / path
            if path.is_absolute() and manuscript.resolve() == path.resolve():
                continue  # never cite the manuscript itself
            if cite not in cache:
                cache[cite] = _values(path) if path.is_file() else None
            if cache[cite] is None:
                missing_any = True
                findings.append(
                    {
                        "type": "missing-file",
                        "line": claim["line"],
                        "path": cite,
                        "message": f"cited file {cite} does not exist",
                        "rule": 7,
                    }
                )
                continue
            found |= cache[cite]
        if missing_any:
            continue  # one actionable finding beats one per number
        for token in numbers(claim["text"]):
            if float(token) not in found:
                findings.append(
                    {
                        "type": "unmatched-number",
                        "line": claim["line"],
                        "number": token,
                        "cites": list(claim["cites"]),
                        "message": f"{token} appears in none of {', '.join(claim['cites'])}",
                        "rule": 7,
                    }
                )

    hard = [f for f in findings if f["type"] != "no-evidence"]
    return {
        "root": str(root),
        "file": str(manuscript),
        "claims": len(claims),
        "findings": findings,
        "ok": not hard,
        "message": "",
    }
