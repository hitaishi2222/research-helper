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
            return {"version": 1, "project_slug": "", "current_phase": 0, "tasks": []}
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "project_slug": "", "current_phase": 0, "tasks": []}
        data.setdefault("tasks", [])
        data.setdefault("current_phase", 0)
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

PLAN_STEP = re.compile(r"^###\s+(S\d+|T-\S+)\s*[—\-]\s*(.+)$", re.MULTILINE)


def import_plan_md(root: Path, dry_run: bool = False) -> list[dict]:
    """Parse PLAN.md steps (SKILL.md §8 template) into tasks."""
    plan = paths.artifact_path(root, "PLAN.md")
    if not plan.exists():
        return []
    text = plan.read_text(encoding="utf-8")
    store = TaskStore(root)
    existing = {t["id"] for t in store.load()["tasks"]}
    added = []
    for m in PLAN_STEP.finditer(text):
        step_id, title = m.group(1), m.group(2).strip()
        if step_id in existing:
            continue
        owner, deliverable, verify, kind, timebox = "researcher", "", "", "build", ""
        owner_m = re.search(rf"###\s+{re.escape(step_id)}.*?owner:\s*(\w+)", text, re.DOTALL)
        if owner_m:
            owner = owner_m.group(1)
        del_m = re.search(rf"###\s+{re.escape(step_id)}.*?deliverable:\s*(.+)", text)
        if del_m:
            deliverable = del_m.group(1).strip()
        ver_m = re.search(rf"###\s+{re.escape(step_id)}.*?verify:\s*`([^`]+)`", text)
        if ver_m:
            verify = ver_m.group(1)
        kind_m = re.search(rf"###\s+{re.escape(step_id)}.*?\|\s*(build|spike)", text)
        if kind_m:
            kind = kind_m.group(1)
        tb_m = re.search(rf"###\s+{re.escape(step_id)}.*?timebox:\s*(\S+)", text)
        if tb_m:
            timebox = tb_m.group(1)
        if dry_run:
            added.append({"id": step_id, "title": title, "owner": owner})
        else:
            added.append(
                store.add(
                    title,
                    task_id=step_id,
                    owner=owner,
                    deliverable=deliverable,
                    verify=verify,
                    kind=kind,
                    timebox=timebox,
                )
            )
    return added
