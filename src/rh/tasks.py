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

# `### S04b — title` / `### S12 - title` / `### T-abc — title`
PLAN_STEP = re.compile(r"^###\s+((?:S\d+[a-zA-Z]?|T-\S+))\s*[—–-]\s*(.+)$", re.MULTILINE)

# Exit gate text per phase (SKILL.md §3) — shown by `rh phase`, never enforced alone.
PHASE_EXIT = {
    0: "ENV.md config block parses and the user confirmed it",
    1: "PROBLEM.md has all six sections, user approved",
    2: "ENV.md `## Environment` notes the tools/versions the user named",
    3: "LITERATURE.md (+ OUTPUT_LAYOUT.md when the output is a paper/report), or a user-agreed skip",
    4: "PLAN.md: both planners agreed + the user approved it",
    5: "STATUS.md describes reality (phase, step, blockers, history)",
    6: "plan steps checked, tests green, results/ reproduces from a clean run",
    7: "zero open blocking questions from Critique",
    8: "every claim has an evidence line, Critique signed off",
    9: "all steps checked, close log written, push question answered",
}


def _step_blocks(text: str) -> list[tuple[str, str, str]]:
    """[(step_id, title, body)] — a step's body ends at the next heading."""
    starts = [(m.group(1), m.group(2).strip(), m.start(), m.end())
              for m in PLAN_STEP.finditer(text)]
    blocks = []
    for i, (step_id, title, _start, body_start) in enumerate(starts):
        end = starts[i + 1][2] if i + 1 < len(starts) else len(text)
        nxt = re.search(r"^##\s", text[body_start:end], re.MULTILINE)
        if nxt:
            end = body_start + nxt.start()
        blocks.append((step_id, title, text[body_start:end]))
    return blocks


def _field(body: str, pattern: str) -> str:
    m = re.search(pattern, body)
    return (m.group(1).strip().strip("`") if m else "")


def parse_plan_steps(text: str, default_phase: int = 4) -> list[dict]:
    """Parse PLAN.md steps (SKILL.md §8 template) into task dicts."""
    out = []
    for step_id, title, body in _step_blocks(text):
        deps = _field(body, r"depends on:\s*([^|\n]+)")
        out.append({
            "id": step_id,
            "title": title,
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


def import_plan_md(root: Path, dry_run: bool = False) -> list[dict]:
    """Parse PLAN.md steps into tasks; existing ids get their fields refreshed.
    Read-only for PLAN.md: this function never writes PLAN.md (user file stays put).

    PLAN.md is the truth (SKILL.md §10 contract 3): a retired title must not
    survive on the board. Task state/subtasks are never touched here.
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
        task = existing.get(step_id)
        if task is None:
            if dry_run:
                changed.append({"id": step_id, "title": step["title"], "action": "added"})
            else:
                task = store.add(step["title"], task_id=step_id, phase=step["phase"],
                                 owner=step["owner"] or "researcher",
                                 deliverable=step["deliverable"], verify=step["verify"],
                                 kind=step["kind"] or "build", timebox=step["timebox"],
                                 risk=step["risk"], depends_on=step["depends_on"])
                existing[step_id] = task
                data["tasks"].append(task)  # keep the snapshot we save at the end consistent
                changed.append({"id": step_id, "title": task["title"], "action": "added"})
            continue
        updates = {k: v for k, v in step.items() if k != "phase" and v and task.get(k) != v}
        if not updates:
            continue
        if not dry_run:
            for k, v in updates.items():
                task[k] = v
            task["updated_at"] = now_iso()
        changed.append({"id": step_id, "title": task["title"], "action": "updated",
                        "fields": sorted(updates)})
    if changed and not dry_run:
        store.save(data)
    return changed
