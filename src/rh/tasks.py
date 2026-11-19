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
        # Set by the permissive load when a bad file had to be discarded.
        self.corrupt = False

    def load(self, *, strict: bool = False) -> dict:
        """Read the board. `strict` refuses a bad file instead of guessing empty.

        Writes use the strict path: a hand edit with a typo must never be saved
        back as an empty board. Display keeps the permissive path and flags
        `self.corrupt` so the caller can warn.
        """
        self.corrupt = False
        empty = {"version": 1, "project_name": "", "current_phase": 0, "tasks": []}
        if not self.file.exists():
            return empty
        problem = ""
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # JSONDecodeError subclasses ValueError
            problem, data = f"is not valid JSON ({exc})", None
        if not isinstance(data, dict):
            problem = problem or "is not a JSON object"
        else:
            tasks = data.get("tasks", [])
            if not isinstance(tasks, list):
                problem = "has a `tasks` value that is not a list"
            elif any(not isinstance(t, dict) or not str(t.get("id") or "") for t in tasks):
                problem = "has a task without an `id`"
            elif len({t["id"] for t in tasks}) != len(tasks):
                problem = "has two tasks with the same `id`"
        if problem:
            if strict:
                raise ValueError(
                    f"{self.file} {problem} — fix it or restore a copy from "
                    ".rh/.bak/; nothing was written"
                )
            self.corrupt = True
            return empty
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
        data = self.load(strict=True)
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

    @staticmethod
    def _refuse_removal(tasks, task_id, removed_ids, state, force) -> None:
        if force:
            return
        if state == "working":
            raise ValueError(f"{task_id} is working — finish it or pass --force")
        dependents = [
            t["id"]
            for t in tasks
            if t["id"] not in removed_ids
            and removed_ids & set(t.get("depends_on") or [])
        ]
        if dependents:
            raise ValueError(
                f"{task_id} is a dependency of {', '.join(dependents)} — pass --force"
            )

    def remove(self, task_id: str, *, force: bool = False) -> dict:
        """Drop a task (with its subtasks) or one subtask; ids are never renumbered."""
        data = self.load(strict=True)
        tasks = data["tasks"]
        for t in tasks:
            if t["id"] == task_id:
                removed = {t["id"]} | {s["id"] for s in t.get("subtasks", [])}
                self._refuse_removal(tasks, t["id"], removed, t.get("state"), force)
                tasks.remove(t)
                self.save(data)
                return t
            for st in t.get("subtasks", []):
                if st["id"] == task_id:
                    self._refuse_removal(tasks, task_id, {task_id}, st.get("state"), force)
                    t["subtasks"].remove(st)
                    self.save(data)
                    return {**st, "parent": t["id"], "subtask": True}
        raise KeyError(f"no task {task_id}")

    def reorder(
        self,
        task_id: str,
        *,
        before: str | None = None,
        after: str | None = None,
    ) -> dict:
        """Move a task relative to another in the same phase; list order is display order."""
        if bool(before) == bool(after):
            raise ValueError("pass exactly one of --before or --after")
        target_id = before or after
        if target_id == task_id:
            raise ValueError("cannot move a task relative to itself")
        data = self.load(strict=True)
        tasks = data["tasks"]
        moving = next((t for t in tasks if t["id"] == task_id), None)
        target = next((t for t in tasks if t["id"] == target_id), None)
        if moving is None:
            raise KeyError(f"no task {task_id}")
        if target is None:
            raise KeyError(f"no task {target_id}")
        if moving["phase"] != target["phase"]:
            raise ValueError(
                f"{task_id} is in {phase_name(moving['phase'])}, {target_id} in "
                f"{phase_name(target['phase'])} — a reorder stays inside one phase"
            )
        tasks.remove(moving)
        pos = tasks.index(target)
        tasks.insert(pos if before else pos + 1, moving)
        self.save(data)
        return moving

    def set_state(self, task_id: str, state: str) -> dict:
        if state not in TASK_STATES:
            raise ValueError(f"state must be one of {TASK_STATES}, got {state!r}")
        data = self.load(strict=True)
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
        data = self.load(strict=True)
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


# Exit gate text per phase (SKILL.md §3) — shown by `rh tasks phase`, never enforced alone.
PHASE_EXIT = {
    0: ".rh/env.json parses and the user confirmed it",
    1: "PROBLEM.md has all seven sections (purpose first), user approved",
    2: ".rh/ENVIRONMENT.md notes the tools/versions the user named",
    3: "LITERATURE.md (+ OUTPUT_LAYOUT.md when the output is a paper/report), or a user-agreed skip",
    4: "PLAN.md: both planners agreed + the user approved it",
    5: "STATUS.md describes reality (phase, step, blockers, history)",
    6: "plan steps checked, tests green, results/ reproduces from a clean run",
    7: "zero open blocking questions from Critique",
    8: "every claim has an evidence line and `rh verify --strict` passes, Critique signed off",
    9: "all steps checked, close log written, handoff written, push question answered",
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
