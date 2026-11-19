"""Per-agent runtime state — `.rh/agents/<name>.json`, one file per spawned agent.

Written when an agent is opened and rewritten by `rh agent done`. `rh agent
status` reads this directory; `.rh/logs/spawns.jsonl` stays the append-only
spawn history. The name keys the brief (`.rh/briefs/`), the report
(`.rh/reports/`) and this file, so a second agent of one role can never
overwrite the first one's work.

States: `open` (a session is expected to report) and the outcomes it can report
— `ok`, `blocked`, `failed`, `closed`. `closed` records a rule-13 close with no
report, which is the only outcome that does not demand one.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .add import slugify

OPEN = "open"
# What an agent reports. `ok` is recorded as state `done` so `rh agent status`
# reads like a sentence; the outcome keeps the agent's own word. `closed` is the
# rule-13 close of a pane that never reported.
OUTCOMES = ("ok", "blocked", "failed", "closed")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_name(name: str) -> str:
    """A name is a file stem: lowercase, no separators that escape the dir."""
    return (
        re.sub(r"[^a-z0-9._-]+", "-", (name or "").strip().lower()).strip("-.")
        or "agent"
    )


def agents_dir(root: Path) -> Path:
    return paths.rh_dir(root) / "agents"


def state_file(root: Path, name: str) -> Path:
    return agents_dir(root) / f"{clean_name(name)}.json"


def brief_path(root: Path, name: str) -> Path:
    return paths.rh_dir(root) / "briefs" / f"{clean_name(name)}.md"


def report_path(root: Path, name: str) -> Path:
    return paths.rh_dir(root) / "reports" / f"{clean_name(name)}.md"


def names_in_use(root: Path) -> set[str]:
    """Every name a state file already holds — open or finished.

    Finished names count too: reusing one would overwrite the record and the
    report path of an agent whose work is still evidence.
    """
    d = agents_dir(root)
    if not d.is_dir():
        return set()
    return {f.stem for f in d.glob("*.json") if f.is_file()}


def derive_name(root: Path, env: dict, role: str, suffix: str = "") -> str:
    """`rh-<project>-<role>`, then `-2`, `-3` … when that name is in use.

    The suffix is mechanical on purpose: uniqueness must not depend on someone
    remembering to pass `--name`. A `--name` value is used as the suffix when
    given, and still falls back to a number if that exact name is taken.
    """
    project = slugify(str((env.get("project") or {}).get("name") or "")) or "project"
    base = f"rh-{project}-{clean_name(role)}"
    used = names_in_use(root)
    if suffix and suffix.strip():
        forced = f"{base}-{clean_name(suffix)}"
        if forced not in used:
            return forced
        base = forced
    if base not in used:
        return base
    n = 2
    while f"{base}-{n}" in used:
        n += 1
    return f"{base}-{n}"


def load(root: Path, name: str) -> dict | None:
    f = state_file(root, name)
    try:
        rec = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return rec if isinstance(rec, dict) and rec.get("name") else None


def all_records(root: Path) -> list[dict]:
    d = agents_dir(root)
    if not d.is_dir():
        return []
    rows: list[dict] = []
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # a torn state file must not hide the others
        if isinstance(rec, dict) and rec.get("name"):
            rows.append(rec)
    return sorted(rows, key=lambda r: str(r.get("started") or ""))


def open_records(root: Path) -> list[dict]:
    return [r for r in all_records(root) if r.get("state") == OPEN]


def open_names(root: Path) -> list[str]:
    return [str(r["name"]) for r in open_records(root)]


def save(root: Path, rec: dict) -> Path:
    f = state_file(root, str(rec["name"]))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f


def write_open(
    root: Path,
    *,
    name: str,
    role: str,
    model: str = "",
    mode: str = "",
    report: str = "",
    brief: str = "",
    source: str = "",
    pid: int | None = None,
) -> dict:
    """Record a freshly opened agent. Called by `rh spawn` after it opens."""
    stamp = now_iso()
    rec = {
        "name": clean_name(name),
        "role": role,
        "state": OPEN,
        "outcome": "",
        "report": report,
        "brief": brief,
        "model": model,
        "mode": mode,
        "source": source,
        "pid": pid,
        "started": stamp,
        "updated": stamp,
    }
    save(root, rec)
    return rec


def _resolve(root: Path, report: str) -> Path:
    p = Path(report)
    return p if p.is_absolute() else (root / p)


def mark_done(
    root: Path,
    name: str,
    *,
    report: str | None = None,
    outcome: str = "ok",
) -> dict:
    """Record an agent's completion. Raises ValueError when it may not.

    `ok`, `blocked` and `failed` need a report file with something in it: the
    marker exists so the Orchestrator has an answer to read, and an empty file
    is not an answer. `closed` is the rule-13 close and needs no report.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}, got {outcome!r}")
    rec = load(root, name)
    if rec is None:
        raise ValueError(
            f"no agent named {clean_name(name)!r} — `rh agent status` lists what is open"
        )
    path = report or rec.get("report") or str(report_path(root, clean_name(name)))
    target = _resolve(root, str(path))
    if outcome != "closed":
        if not target.is_file():
            raise ValueError(
                f"no report at {target} — write it first, or close the agent with "
                "`--outcome closed` (rule 13)"
            )
        if target.stat().st_size == 0:
            raise ValueError(f"{target} is empty — an empty report is not an answer")
    rec["state"] = "done" if outcome == "ok" else outcome
    rec["outcome"] = outcome
    rec["report"] = str(path)
    rec["updated"] = now_iso()
    save(root, rec)
    return rec
