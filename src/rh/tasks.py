"""Task board — openspec-inspired but single-file (.rh/tasks.json).

Avoids spec bloat: one JSON file, phases + steps + subtasks, states
idle | working | complete | cancelled. PLAN.md steps are mirrored here so
`rh tasks` and `rh status` have a machine-readable source.

`cancelled` is the research-death state: a later step proved the plan wrong, so
the task is deliberately dropped. It counts as *resolved* (progress bar) but
never as done.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import paths

TASK_STATES = ("idle", "working", "complete", "cancelled")
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
        cancelled = sum(1 for t in tasks if t["state"] == "cancelled")
        subtasks_total = sum(len(t.get("subtasks", [])) for t in tasks)
        subtasks_complete = sum(
            1 for t in tasks for s in t.get("subtasks", []) if s["state"] == "complete"
        )
        return {
            "total": total,
            "complete": complete,
            "working": working,
            "cancelled": cancelled,
            "idle": total - complete - working - cancelled,
            "subtasks_total": subtasks_total,
            "subtasks_complete": subtasks_complete,
            "current_phase": int(data.get("current_phase", 0)),
            # cancelled tasks are resolved (decided against), so they unblock the bar
            "pct": round(100 * (complete + cancelled) / total) if total else 0,
        }


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
