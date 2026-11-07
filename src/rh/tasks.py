"""Task board — openspec-inspired but single-file (.rh/tasks.json).

Avoids spec bloat: one JSON file, phases + steps + subtasks, states
idle | working | complete. PLAN.md steps are mirrored here so `rh tasks`
and `rh status` have a machine-readable source.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import paths

TASK_STATES = ("idle", "working", "complete")
PHASES = [
    (0, "CONFIG"),
    (1, "INTAKE"),
    (2, "ENVIRONMENT"),
    (3, "LITERATURE"),
    (4, "PLAN"),
    (5, "STATE"),
    (6, "IMPLEMENT"),
    (7, "CRITIQUE"),
    (8, "MANUSCRIPT"),
    (9, "CLOSE"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def phase_name(phase: int) -> str:
    name = dict(PHASES).get(phase, "?")
    return f"{phase} {name}"


class TaskStore:
    def __init__(self, root: Path):
        self.root = root
        self.file = paths.tasks_json(root)

    def load(self) -> dict:
        if not self.file.exists():
            return {"version": 1, "project_name": "", "current_phase": 0, "tasks": []}
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "project_name": "", "current_phase": 0, "tasks": []}
        data.setdefault("tasks", [])
        if "project_slug" in data:  # renamed in 0.2
            data.setdefault("project_name", data.pop("project_slug"))
        data.setdefault("current_phase", 0)
        for t in data["tasks"]:
            if not isinstance(t.get("phase"), int):
                m = re.search(r"\d+", str(t.get("phase", "")))
                t["phase"] = int(m.group()) if m else 0
        return data

    def save(self, data: dict) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    # -- CRUD -----------------------------------------------------------------
    def add(
        self,
        title: str,
        *,
        task_id: str | None = None,
        phase: int = 6,
        owner: str = "researcher",
        state: str = "idle",
        deliverable: str = "",
        verify: str = "",
        depends_on: list[str] | None = None,
        risk: str = "",
        kind: str = "build",
        timebox: str = "",
        subtasks: list[str] | None = None,
    ) -> dict:
        data = self.load()
        task_id = task_id or f"T-{uuid.uuid4().hex[:6]}"
        if any(t["id"] == task_id for t in data["tasks"]):
            raise ValueError(f"task {task_id} already exists")
        if state not in TASK_STATES:
            raise ValueError(f"state must be one of {TASK_STATES}")
        task = {
            "id": task_id,
            "title": title,
            "phase": phase,
            "phase_name": phase_name(phase),
            "owner": owner,
            "state": state,
            "deliverable": deliverable,
            "verify": verify,
            "depends_on": depends_on or [],
            "risk": risk,
            "kind": kind,
            "timebox": timebox,
            "subtasks": [
                {"id": f"{task_id}.{i+1}", "title": s, "state": "idle"}
                for i, s in enumerate(subtasks or [])
            ],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        data["tasks"].append(task)
        self.save(data)
        return task

    def get(self, task_id: str) -> dict | None:
        for t in self.load()["tasks"]:
            if t["id"] == task_id:
                return t
            for st in t.get("subtasks", []):
                if st["id"] == task_id:
                    return {**st, "parent": t["id"], "subtask": True}
        return None

    def set_state(self, task_id: str, state: str) -> dict:
        if state not in TASK_STATES:
            raise ValueError(f"state must be one of {TASK_STATES}, got {state!r}")
        data = self.load()
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["state"] = state
                t["updated_at"] = now_iso()
                self.save(data)
                return t
            for st in t.get("subtasks", []):
                if st["id"] == task_id:
                    st["state"] = state
                    self.save(data)
                    return st
        raise KeyError(f"no task {task_id}")

    def list(self, *, phase: int | None = None, state: str | None = None) -> list[dict]:
        data = self.load()
        out = data["tasks"]
        if phase is not None:
            out = [t for t in out if t["phase"] == phase]
        if state:
            out = [t for t in out if t["state"] == state]
        return out

    def set_phase(self, phase: int) -> None:
        data = self.load()
        data["current_phase"] = phase
        self.save(data)

    def current_phase(self) -> int:
        return int(self.load().get("current_phase", 0))

    def summary(self) -> dict:
        data = self.load()
        tasks = data["tasks"]
        total = len(tasks)
        complete = sum(1 for t in tasks if t["state"] == "complete")
        working = sum(1 for t in tasks if t["state"] == "working")
        subtasks_total = sum(len(t.get("subtasks", [])) for t in tasks)
        subtasks_complete = sum(
            1 for t in tasks for s in t.get("subtasks", []) if s["state"] == "complete"
        )
        return {
            "total": total,
            "complete": complete,
            "working": working,
            "idle": total - complete - working,
            "subtasks_total": subtasks_total,
            "subtasks_complete": subtasks_complete,
            "current_phase": int(data.get("current_phase", 0)),
            "pct": round(100 * complete / total) if total else 0,
        }


# --- PLAN.md <-> tasks import -------------------------------------------------
#
# PLAN.md is the user's file (or an agent's), so the parser is forgiving about shape and
# strict only about the fields it actually uses. Step lines are recognised in this order
# of preference — first shape found in the file wins, so a plan is never half-guessed:
#
#   1. a heading carrying an explicit id, at any level   ## S07 — Dispersion screen
#   2. any heading at level >= 3                         ### Dispersion screen
#   3. a numbered heading, when no level>=3 heading exists  ## 1. Dispersion screen
#   4. a numbered line at column 0                       1. Dispersion screen
#   5. a bullet at column 0                              - Dispersion screen
#
# A heading that is not a step is a **section boundary**: it ends the current step and
# starts nothing (`## 1. What works` never becomes a task). Bullet lines inside a step are
# its **subtasks** (`- [ ] profile one cell` or `  - profile one cell`), except in the
# bullet shape where column-0 bullets are the steps and only indented ones are subtasks.
# Steps without an explicit id get a positional one (`S01`, `S02`, …).
#
# Fields read from the step body, all optional: `owner:` `deliverable:` `verify:` `risk:`
# `depends on:` `kind:` `timebox:`.

_EXPLICIT_ID = re.compile(r"^(S\d+[a-zA-Z]?|T-\S+)\s*[—–:.\-]\s*(.+)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_NUMBERED = re.compile(r"^(\d{1,3})[.)]\s+(.+?)\s*$")
_NUMBERED_ANY = re.compile(r"^(?:\d{1,3}[.)]|step\s+\d+\s*[:.)])\s+(.+?)\s*$", re.IGNORECASE)
_BULLET = re.compile(r"^[-*+]\s+(?:\[([ xX])\]\s*)?(.+?)\s*$", re.MULTILINE)
_BULLET_ANY = re.compile(r"^\s*[-*+]\s+(?:\[([ xX])\]\s*)?(.+?)\s*$", re.MULTILINE)
_INDENTED_BULLET = re.compile(r"^\s+[-*+]\s+(?:\[([ xX])\]\s*)?(.+?)\s*$", re.MULTILINE)

# Exit gate text per phase (SKILL.md §3) — shown by `rh phase`, never enforced alone.
PHASE_EXIT = {
    0: ".rh/env.json parses and the user confirmed it",
    1: "PROBLEM.md has all six sections, user approved",
    2: ".rh/ENVIRONMENT.md notes the tools/versions the user named",
    3: "LITERATURE.md (+ OUTPUT_LAYOUT.md when the output is a paper/report), or a user-agreed skip",
    4: "PLAN.md: both planners agreed + the user approved it",
    5: "STATUS.md describes reality (phase, step, blockers, history)",
    6: "plan steps checked, tests green, results/ reproduces from a clean run",
    7: "zero open blocking questions from Critique",
    8: "every claim has an evidence line, Critique signed off",
    9: "all steps checked, close log written, push question answered",
}


def phase_exit(phase: int, user_plans: bool = False) -> str:
    """The phase's exit gate, as text.

    Phase 4 names its author: with no planner configured the user is the planner
    (`agents.planners.models = []` / `none`), so the gate is user-authored + user
    approval rather than two planners plus the user.
    """
    if phase == 4 and user_plans:
        return (
            "PLAN.md: written by the user (no planner models configured) + user approval"
        )
    return PHASE_EXIT.get(phase, "")


def _clean_title(title: str) -> str:
    """Bold/italic markers and whitespace only — inner backticks belong to the title."""
    return title.strip().strip("*_ ").strip()


def _step_starts(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """(shape, [(line_index, id_or_empty, title)]).

    `shape` is "heading", "numbered", "bullet" or "none" — it decides whether a
    column-0 bullet is a step (bullet shape) or a subtask (everything else).
    """
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    numbered: list[int] = []
    bulleted: list[int] = []
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2)))
            continue
        if line and not line[0].isspace():
            if _NUMBERED.match(line):
                numbered.append(i)
            elif _BULLET.match(line):
                bulleted.append(i)

    ided = []
    plain = []
    for i, level, body in headings:
        m = _EXPLICIT_ID.match(body)
        if m:
            ided.append((i, m.group(1), _clean_title(m.group(2))))
        elif level >= 3:
            plain.append((i, "", _clean_title(body)))
    if ided or plain:
        return "heading", sorted(ided + plain)
    # No level>=3 step headings: a numbered heading (`## 1. Dispersion screen`) is the step
    # list, and its bullets are subtasks. This is how a hand-written plan usually looks.
    numbered_headings = []
    for i, _level, body in headings:
        m = _NUMBERED_ANY.match(body)
        if m:
            numbered_headings.append((i, "", _clean_title(m.group(1))))
    if numbered_headings:
        return "heading", numbered_headings
    if numbered:
        return "numbered", [(i, "", _clean_title(_NUMBERED.match(lines[i]).group(2)))
                             for i in numbered]
    if bulleted:
        return "bullet", [(i, "", _clean_title(_BULLET.match(lines[i]).group(2)))
                           for i in bulleted]
    return "none", []


def _step_blocks(text: str) -> list[tuple[str, str, str, list[str]]]:
    """[(step_id, title, body, subtasks)] — positional ids when the plan carries none."""
    shape, starts = _step_starts(text)
    if not starts:
        return []
    lines = text.splitlines()
    stop_lines = {i for i, line in enumerate(lines) if _HEADING.match(line)}
    stop_lines |= {i for i, _id, _title in starts}
    sub_re = _INDENTED_BULLET if shape == "bullet" else _BULLET_ANY

    blocks = []
    used: set[str] = set()
    for n, (start, step_id, title) in enumerate(starts, start=1):
        positional = f"S{n:02d}"
        step_id = step_id or positional
        if step_id in used:
            step_id = positional if positional not in used else f"{positional}-{n}"
        used.add(step_id)
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if j in stop_lines:
                end = j
                break
        body_lines = lines[start + 1:end]
        body = "\n".join(body_lines)
        subtasks = [_clean_title(m.group(2)) for m in sub_re.finditer(body)
                    if m.group(2).strip()]
        blocks.append((step_id, title, body, subtasks))
    return blocks


def _field(body: str, pattern: str) -> str:
    """A step field, case-insensitive — a hand-written plan says `Owner:` as often as `owner:`."""
    m = re.search(pattern, body, re.IGNORECASE)
    return (m.group(1).strip().strip("`") if m else "")


def parse_plan_steps(text: str, default_phase: int = 4) -> list[dict]:
    """Parse PLAN.md into task dicts — see the shape rules above the regexes."""
    out = []
    for step_id, title, body, subtasks in _step_blocks(text):
        deps = _field(body, r"depends on:\s*([^|\n]+)")
        out.append({
            "id": step_id,
            "title": title,
            "subtasks": subtasks,
            "owner": _field(body, r"owner:\s*([\w-]+)"),
            "deliverable": (_field(body, r"deliverable:\s*`([^`]+)`")
                            or _field(body, r"deliverable:\s*([^|\n]+)")),
            "verify": _field(body, r"verify:\s*`([^`]+)`"),
            "kind": _field(body, r"kind:\s*([\w-]+)"),
            "timebox": _field(body, r"timebox:\s*(\S+)"),
            "risk": _field(body, r"risk:\s*([^|\n]+)"),
            "depends_on": [d.strip() for d in deps.split(",")
                           if d.strip() and d.strip().lower() not in ("none", "-", "n/a")],
            "phase": default_phase,
        })
    return out


def _next_subtask_id(task: dict) -> int:
    """Highest `parent.N` suffix already used, so appended subtasks never reuse an id."""
    top = 0
    for st in task.get("subtasks", []):
        _parent, _sep, suffix = str(st.get("id", "")).rpartition(".")
        if suffix.isdigit():
            top = max(top, int(suffix))
    return top + 1


def import_plan_md(root: Path, dry_run: bool = False) -> list[dict]:
    """Parse PLAN.md steps into tasks; existing ids get their fields refreshed.
    Read-only for PLAN.md: this function never writes PLAN.md (user file stays put).

    PLAN.md is the truth (SKILL.md §10 contract 3): a retired title must not
    survive on the board. Fields are refreshed; **state is never touched**. Subtasks
    are matched by title and only ever appended — a subtask that disappears from
    PLAN.md keeps its row and its state, because deleting it would delete evidence of
    work done.
    """
    plan = paths.artifact_path(root, "PLAN.md")
    if not plan.exists():
        return []
    store = TaskStore(root)
    data = store.load()
    existing = {t["id"]: t for t in data["tasks"]}
    changed = []
    for step in parse_plan_steps(plan.read_text(encoding="utf-8")):
        step_id = step.pop("id")
        subtasks = step.pop("subtasks")
        task = existing.get(step_id)
        if task is None:
            if dry_run:
                row = {"id": step_id, "title": step["title"], "action": "added"}
                if subtasks:
                    row["subtasks"] = len(subtasks)
                changed.append(row)
            else:
                task = store.add(step["title"], task_id=step_id, phase=step["phase"],
                                 owner=step["owner"] or "researcher",
                                 deliverable=step["deliverable"], verify=step["verify"],
                                 kind=step["kind"] or "build", timebox=step["timebox"],
                                 risk=step["risk"], depends_on=step["depends_on"],
                                 subtasks=subtasks)
                existing[step_id] = task
                data["tasks"].append(task)  # keep the snapshot we save at the end consistent
                row = {"id": step_id, "title": task["title"], "action": "added"}
                if subtasks:
                    row["subtasks"] = len(subtasks)
                changed.append(row)
            continue
        updates = {k: v for k, v in step.items() if k != "phase" and v and task.get(k) != v}
        known = {st["title"] for st in task.get("subtasks", [])}
        fresh = [title for title in subtasks if title not in known]
        if not updates and not fresh:
            continue
        if not dry_run:
            for k, v in updates.items():
                task[k] = v
            nxt = _next_subtask_id(task)
            for offset, title in enumerate(fresh):
                task.setdefault("subtasks", []).append(
                    {"id": f"{step_id}.{nxt + offset}", "title": title, "state": "idle"})
            task["updated_at"] = now_iso()
        fields = sorted(updates) + (["subtasks"] if fresh else [])
        changed.append({"id": step_id, "title": task["title"], "action": "updated",
                        "fields": fields})
    if changed and not dry_run:
        store.save(data)
    return changed
