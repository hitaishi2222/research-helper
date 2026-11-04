"""`rh` entry point.

Commands:
  rh init [--root DIR] [--slug NAME] [--clean]
  rh env show | rh env set KEY=VALUE ... | rh env list
  rh add {note|literature|layout|gaps|problem|plan|status|manuscript} <heading|DOI> [-m BODY] [--file NAME]
  rh add log --role ROLE --title TITLE [-m BODY]
  rh add task TITLE [--id ID] [--phase N] [--owner ROLE] [--state S] [--verify CMD] [--deliverable FILE] [--subtask TEXT ...]
  rh search <query> [--max N]
  rh tasks [--phase N] [--state S]      # all tasks + subtasks + status
  rh tasks set <id> {idle|working|complete}
  rh status [--json]
  rh workflow [--mermaid] [--write]
  rh phase [0-9]          # show the current phase + its exit gate, or set it (gated)
  rh plan import [--dry-run]
  rh skill install [--dest DIR] [--force]
  rh describe   # AI-friendly map: phases, layout, env schema (decisions you must surface)

Global flags: --root DIR, --json (machine-readable).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, add as add_mod, config, paths, resume as resume_mod, search as search_mod, tasks as tasks_mod, ui, workflow


def with_root(fn):
    def wrapper(args):
        root = paths.resolve_root(getattr(args, "root", None))
        return fn(args, root)
    wrapper.__name__ = fn.__name__
    return wrapper


@with_root
def cmd_init(args, root: Path):
    if args.clean and root.exists():
        import shutil
        shutil.rmtree(root / ".rh", ignore_errors=True)
    d = paths.ensure_layout(root)
    tasks_mod.TaskStore(root).load()  # ensure tasks.json shape exists lazily
    if args.slug:
        env = config.load_env(root)
        env["project"]["slug"] = args.slug
        config.save_env(root, env)
    (d / ".gitkeep").write_text("") if not (d / ".gitkeep").exists() else None
    if getattr(args, "json", False):
        ui.json_out({"root": str(root), "rh_dir": str(d), "initialized": True})
        return 0
    print(ui.banner("rh init", f"{root}"))
    print(f"  {ui.colorize('✓', ui.GREEN)} created {d}/")
    for sub in ("logs/", "notes/", "tasks/", "tmp/"):
        print(f"  {ui.colorize('✓', ui.GREEN)} .rh/{sub}")
    print(f"  {ui.colorize('✓', ui.GREEN)} src/ results/ papers/ at root")
    print(f"  {ui.colorize('✓', ui.GREEN)} ENV.md at .rh/ENV.md (config + environment notes)")
    print()
    print(f"Next: {ui.colorize('rh env set project.slug=<name>', ui.CYAN)}  "
          f"·  {ui.colorize('rh env show', ui.CYAN)}")
    return 0


def _env_value(value) -> str:
    """One-line display for a config value (dicts become provider/model)."""
    if isinstance(value, dict):
        if not value:
            return "—"
        if set(value) == {"provider", "model"}:
            return f"{value['provider']}/{value['model']}"
        return json.dumps(value, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    return str(value) if value not in ("", None) else "—"


def _safe_nested(env: dict, key: str):
    """Config value by dotted key, or None when the stored shape is malformed."""
    try:
        return config.get_nested(env, key)
    except (KeyError, IndexError, ValueError):
        return None


@with_root
def cmd_env_show(args, root: Path):
    env = config.load_env(root)
    if getattr(args, "json", False):
        ui.json_out(env)
        return 0
    problems = config.validate(env)
    print(ui.banner("ENV — current environment"))
    rows = [[key, _env_value(_safe_nested(env, key))]
            for key, _kind, _choices, _help in config.ENV_SCHEMA]
    print(ui.table(["key", "value"], rows))
    tail = config.load_tail(root)
    if tail.strip():
        print()
        print(ui.colorize("Environment notes (from .rh/ENV.md)", ui.DIM))
        print(tail)
    if problems:
        print()
        print(ui.colorize("⚠ config problems:", ui.YELLOW))
        for p in problems:
            print(f"  - {p}")
    else:
        print()
        print(ui.colorize("✓ config valid", ui.GREEN))
    return 0


@with_root
def cmd_env_list(args, root: Path):
    if getattr(args, "json", False):
        for key, kind, choices, help_text in config.ENV_SCHEMA:
            ui.json_out({"key": key, "kind": kind, "choices": list(choices), "help": help_text})
        return 0
    rows = [[key, kind, " ".join(str(c) for c in choices) or "—", help_text]
            for key, kind, choices, help_text in config.ENV_SCHEMA]
    print(ui.table(["key", "kind", "choices", "help"], rows))
    print(f"\n{ui.colorize('Set:', ui.DIM)} rh env set agents.count=2 agents.backend=tmux ...")
    return 0


@with_root
def cmd_env_set(args, root: Path):
    env = config.load_env(root)
    if not args.pairs:
        # interactive-ish: show what's settable
        print("Usage: rh env set KEY=VALUE [KEY=VALUE ...]")
        print("Keys:")
        for key, kind, choices, _ in config.ENV_SCHEMA:
            print(f"  {key} ({kind}{choices})")
        return 2
    for pair in args.pairs:
        if "=" not in pair:
            print(f"⚠ skipping {pair!r}: missing '='", file=sys.stderr)
            continue
        key, raw = pair.split("=", 1)
        key = key.strip()
        spec = next((s for s in config.ENV_SCHEMA if s[0] == key), None)
        if spec is None:
            print(f"⚠ unknown key {key!r} — see `rh env list`", file=sys.stderr)
            continue
        kind = spec[1]
        try:
            value = config.coerce_value(raw, kind)
        except ValueError as e:
            print(f"⚠ {key}: {e}", file=sys.stderr)
            continue
        try:
            config.set_nested(env, key, value)
        except (KeyError, IndexError, ValueError) as e:
            print(f"⚠ {key}: {e}", file=sys.stderr)
            continue
    problems = config.validate(env)
    if problems:
        print(ui.colorize("Config problems (will still write):", ui.YELLOW))
        for p in problems:
            print(f"  - {p}")
        print()
    config.save_env(root, env)
    if getattr(args, "json", False):
        ui.json_out(env)
        return 0
    print(ui.colorize(f"✓ wrote {paths.env_md(root)} + .rh/env.json", ui.GREEN))
    print(json.dumps(env, indent=2))
    return 0


@with_root
def cmd_add(args, root: Path):
    paths.ensure_layout(root)
    body = args.message or "TODO: fill in"
    if args.target == "note":
        target, result = add_mod.add_note(root, args.heading, body, file=args.file)
    elif args.target == "log":
        if not args.role or not args.title:
            print("rh add log requires --role and --title", file=sys.stderr)
            return 2
        target = add_mod.add_log(root, args.role, args.title, body)
        result = "created"
    elif args.target == "task":
        store = tasks_mod.TaskStore(root)
        phase = args.phase if args.phase is not None else store.current_phase()
        deps = [d.strip() for d in (args.depends_on or "").split(",") if d.strip()]
        task = store.add(
            args.heading, task_id=args.id, phase=phase, owner=args.owner,
            state=args.state, deliverable=args.deliverable, verify=args.verify,
            depends_on=deps, kind=args.kind, subtasks=args.subtask,
        )
        print(ui.colorize(f"✓ task {task['id']} ({task['state']}, {tasks_mod.phase_name(phase)})", ui.GREEN))
        return 0
    else:
        target, result = add_mod.add_text(root, args.target, args.heading, body)
    if getattr(args, "json", False):
        ui.json_out({"target": str(target), "result": result})
        return 0
    print(ui.colorize(f"✓ {result} {target}", ui.GREEN))
    return 0


@with_root
def cmd_search(args, root: Path):
    hits, engine = search_mod.search(root, args.query, max_hits=args.max)
    if getattr(args, "json", False):
        ui.json_out([{"path": str(h.path.relative_to(root)) if h.path.is_relative_to(root) else str(h.path), "line": h.line_no, "text": h.line.strip()} for h in hits])
        return 0
    print(ui.banner(f"Search: {args.query}", f"engine: {engine} · {len(hits)} hits · root: {root}"))
    if not hits:
        print(ui.colorize("No matches. Try `rh search <different term>` or check .rh/ exists.", ui.YELLOW))
    for h in hits:
        print(h.render(root))
        print()
    return 0


@with_root
def cmd_task_set(args, root: Path):
    store = tasks_mod.TaskStore(root)
    try:
        task = store.set_state(args.id, args.state)
    except (KeyError, ValueError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        ui.json_out(task)
        return 0
    print(f"{ui.state_label(args.state)} {task['id']} — {task.get('title', args.id)}")
    return 0


def group_tasks(tasks):
    """openspec-style grouping: Draft (no tasks) / Active / Complete."""
    draft = [t for t in tasks if t["state"] == "idle" and not any(s["state"] != "idle" for s in t.get("subtasks", []))]
    active = [t for t in tasks if t["state"] == "working"]
    complete = [t for t in tasks if t["state"] == "complete"]
    remaining = [t for t in tasks if t not in draft and t not in active and t not in complete]
    return {"draft": draft, "active": active, "complete": complete, "remaining": remaining}


@with_root
def cmd_tasks(args, root: Path):
    store = tasks_mod.TaskStore(root)
    env = config.load_env(root)
    current = store.current_phase()
    summary = store.summary()
    tasks = store.list(phase=args.phase, state=args.state)
    groups = group_tasks(tasks)
    # phase gate (SKILL.md §3): warnings when the pipeline is skipped
    gate = config.phase_gate(root, env)
    if getattr(args, "json", False):
        ui.json_out({
            "summary": summary,
            "tasks": tasks,
            "groups": {k: [t["id"] for t in v] for k, v in groups.items()},
            "gate": gate,
        })
        return 0
    print(ui.banner("Tasks"))
    print(f"{ui.bar(summary['pct'])}  {summary['complete']}/{summary['total']} complete · "
          f"{summary['working']} working · {summary['idle']} idle")
    if summary["subtasks_total"]:
        sc = summary["subtasks_complete"]
        st = summary["subtasks_total"]
        print(f"{ui.colorize('Subtasks:', ui.DIM)} {sc}/{st}  {ui.bar(round(100*sc/st), width=14)}")
    print(ui.phase_rail(current, done=gate["done"]))
    print()
    if gate["problems"]:
        for p in gate["problems"]:
            print(ui.colorize(f"⚠ {p}", ui.YELLOW))
        print(ui.colorize("  (SKILL.md §3 hard gates: resolve these or ask the user to waive.)", ui.DIM))
        print()
    if not tasks:
        print(ui.colorize("No tasks yet — `rh plan import` or `rh add task \"...\"`.", ui.DIM))
        return 0
    # openspec view style: grouped lanes, one row per task, [x]/[ ] checklist
    for label, items in (("Draft", groups["draft"]), ("Active", groups["active"]),
                         ("Complete", groups["complete"]), ("Remaining", groups["remaining"])):
        if not items:
            continue
        print(ui.colorize(f"── {label} ({len(items)}) ──", ui.BOLD))
        for t in items:
            box = "[x]" if t["state"] == "complete" else "[ ]" if t["state"] == "idle" else "[~]"
            box = ui.colorize(box, ui.state_color(t["state"]))
            sub = ""
            if t.get("subtasks"):
                sd = sum(1 for s in t["subtasks"] if s["state"] == "complete")
                stot = len(t["subtasks"])
                sub = f"  [{sd}/{stot} subtasks]"
            print(f"  {box} {ui.colorize(t['id'], ui.CYAN):8} {t['title']}{sub}")
            for st in t.get("subtasks", []):
                sbox = "[x]" if st["state"] == "complete" else "[~]" if st["state"] == "working" else "[ ]"
                print(f"        {ui.colorize(sbox, ui.state_color(st['state']))} "
                      f"{st['id']:9} {st['title']}")
        print()
    # flat table for scripting detail
    rows = [[t["id"], ui.state_label(t["state"]), tasks_mod.phase_name(t["phase"]), (t["title"] or "")[:42]] for t in tasks]
    print(ui.table(["id", "state", "phase", "title"], rows))
    return 0


@with_root
def cmd_status(args, root: Path):
    env = config.load_env(root)
    store = tasks_mod.TaskStore(root)
    summary = store.summary()
    gate = config.phase_gate(root, env)
    if getattr(args, "json", False):
        ui.json_out({
            "root": str(root),
            "slug": env.get("project", {}).get("slug", ""),
            "phase": summary["current_phase"],
            "phase_name": tasks_mod.phase_name(summary["current_phase"]),
            "summary": summary,
            "gate": gate,
            "initialized": (root / ".rh").exists(),
        })
        return 0
    slug = env.get("project", {}).get("slug") or "untitled"
    print(ui.banner(f"{slug} — status", str(root)))
    # openspec status style: header line + progress + artifact checklist
    print(f"Project: {slug} · Phase: {tasks_mod.phase_name(summary['current_phase'])}")
    print(f"Progress: {summary['complete']}/{summary['total']} steps complete  {ui.bar(summary['pct'], width=16)}")
    print("Changes (task lanes):")
    print(f"  [x] Draft (idle)      {len([t for t in store.list() if t['state']=='idle'])}")
    print(f"  [~] Active (working)  {summary['working']}")
    print(f"  [x] Complete          {summary['complete']}")
    print()
    if gate["problems"]:
        for p in gate["problems"]:
            print(ui.colorize(f"⚠ {p}", ui.YELLOW))
        print(ui.colorize("  (SKILL.md §3 hard gates: resolve these or ask the user to waive.)", ui.DIM))
        print()
    print(ui.phase_rail(summary["current_phase"], done=gate["done"]))
    print()
    print(f"{ui.bar(summary['pct'], width=24)}  {summary['complete']}/{summary['total']} steps · "
          f"{summary['working']} working · {summary['idle']} idle")
    print()
    # per-phase progress only — the task/subtask detail lives in `rh tasks`
    by_phase: dict[int, list[dict]] = {}
    for t in store.list():
        by_phase.setdefault(t["phase"], []).append(t)
    if not by_phase:
        print(ui.colorize("No tasks — `rh plan import` will mirror PLAN.md steps here.", ui.DIM))
    for phase in sorted(by_phase):
        tasks = by_phase[phase]
        done = sum(1 for t in tasks if t["state"] == "complete")
        working = [t["id"] for t in tasks if t["state"] == "working"]
        bar_pct = round(100 * done / len(tasks)) if tasks else 0
        now = f" · working: {', '.join(working)}" if working else ""
        print(f"{ui.colorize(tasks_mod.phase_name(phase), ui.BOLD)}  {ui.bar(bar_pct, width=14)}  "
              f"({done}/{len(tasks)}){now}")
    if by_phase:
        print(ui.colorize("  task + subtask detail: `rh tasks`", ui.DIM))
    return 0


@with_root
def cmd_workflow(args, root: Path):
    """View the PROJECT's workflow diagram — agent-authored, CLI-rendered.

    The Orchestrator/Researcher authors .rh/workflow.mmd (the PLAN step DAG,
    adapted to the renderers available: `rh workflow --tools` lists them).
    rh only ever *displays* it: ASCII in the terminal when the file exists,
    nothing invented when it doesn't. `--example` prints a starter the agent
    can save; `--phases` uses the constant SKILL.md pipeline as the starter.
    """
    store = tasks_mod.TaskStore(root)
    current = store.current_phase()
    gate = config.phase_gate(root)
    src_file = paths.rh_dir(root) / "workflow.mmd"

    # --json: machine contract — no UI chrome, only the object
    if getattr(args, "json", False):
        if args.tools:
            ui.json_out({"ascii_tools": workflow.ascii_tools(), "diagram_tools": workflow.diagram_tools()})
            return 0
        if getattr(args, "example", False):
            src = (workflow.mermaid_for_phase(current, done=gate["done"])
                   if args.phases else workflow.mermaid_for_tasks(store.list()))
            ui.json_out({"example": src})
            return 0
        if not src_file.exists():
            ui.json_out({"has_workflow": False, "workflow_file": str(src_file),
                         "ascii_tools": workflow.ascii_tools(), "diagram_tools": workflow.diagram_tools()})
            return 0
        src = src_file.read_text(encoding="utf-8")
        art, tool = (None, None)
        if not args.no_render:
            art, tool = workflow.render_ascii(root, src)
        rendered = None
        fmt = "png" if args.png else "svg"
        if (args.png or args.svg) and workflow.diagram_tools():
            img, _ = workflow.render_image(root, src, fmt=fmt, out_name="workflow")
            rendered = str(img) if img else None
        ui.json_out({
            "has_workflow": True, "workflow_file": str(src_file),
            "current_phase": current, "gate": gate,
            "ascii_tool": tool, "ascii_ok": art is not None, "rendered": rendered,
        })
        return 0

    # pure-output modes first: everything below adds UI chrome around them
    if args.tools:
        print(ui.banner("Renderers", "rh workflow: external tools are optional — the built-in text view always works"))
        rows = [["built-in text", "always", "compact node/edge view from the .mmd"]]
        for tool, spec in workflow.ASCII_TOOLS.items():
            rows.append([f"{tool} (ascii)", "✓ installed" if workflow.tool_installed(tool) else "—",
                         f"{' | '.join(spec['bins'])} — {workflow.ASCII_TOOL_INSTALL.get(tool, '')}"])
        for tool, spec in workflow.DIAGRAM_TOOLS.items():
            rows.append([f"{tool} (svg/png)", "✓ installed" if workflow.tool_installed(tool) else "—",
                         f"{' | '.join(spec['bins'])} — writes .rh/workflow.svg|png"])
        print(ui.table(["renderer", "state", "how"], rows))
        return 0
    if getattr(args, "example", False):
        if args.phases:
            print(workflow.mermaid_for_phase(current, done=gate["done"]))
        else:
            print(workflow.mermaid_for_tasks(store.list()))
        return 0

    print(ui.banner("Workflow"))
    print(ui.colorize("Phase pipeline (SKILL.md §3, constant):", ui.DIM))
    print(ui.phase_rail(current, done=gate["done"]))
    print()

    if not src_file.exists():
        print(ui.colorize("⏳ workflow diagram: still pending.", ui.YELLOW))
        print(ui.colorize("  The Orchestrator or Researcher authors .rh/workflow.mmd (the PLAN.md step DAG,", ui.DIM))
        print(ui.colorize("  adapted to the installed renderers) — rh only displays it, it never creates it.", ui.DIM))
        return 0
    src = src_file.read_text(encoding="utf-8")

    art, tool = (None, None)
    if not args.no_render:
        art, tool = workflow.render_ascii(root, src)
    if art:
        print(f"{ui.colorize('Diagram', ui.BOLD)} {ui.colorize(f'(via {tool})', ui.DIM)}")
        print(art)
        print()
    elif not args.no_render:
        installed = workflow.ascii_tools()
        if installed:
            print(ui.colorize(f"⚠ ascii render failed via {installed[0]} — check the .mmd syntax", ui.YELLOW))
        else:
            print(ui.colorize("No ASCII renderer installed — nothing downloaded without your say-so.", ui.YELLOW))
            print(ui.colorize("  Options (install one, or run the npx form yourself — it fetches into the npm cache):", ui.DIM))
            for line in workflow.ASCII_TOOL_INSTALL.values():
                print(f"  · {line}")
            for line in workflow.ASCII_NO_INSTALL.values():
                print(f"  · {line}")
    fmt = "png" if args.png else "svg"
    if (args.png or args.svg) and workflow.diagram_tools():
        img, msg = workflow.render_image(root, src, fmt=fmt, out_name="workflow")
        if img:
            print(ui.colorize(f"✓ {msg}: {img}", ui.GREEN))
        else:
            print(ui.colorize(f"⚠ {msg}", ui.YELLOW))
    return 0


# Hard prerequisites to ENTER a phase (SKILL.md §3 exit gates). Absent keys =
# no hard requirement (e.g. LITERATURE may be user-agreed skipped).
REQUIRED_BEFORE = {1: (0,), 2: (1,), 3: (2,), 5: (4,), 6: (0, 1, 2, 4)}


@with_root
def cmd_phase_set(args, root: Path):
    store = tasks_mod.TaskStore(root)
    current = store.current_phase()
    gate = config.phase_gate(root)

    if args.phase is None or args.phase == current:
        # `rh phase` — the phase is a gate, not a badge: show what it costs to leave it
        if getattr(args, "json", False):
            ui.json_out({"phase": current, "phase_name": tasks_mod.phase_name(current),
                         "exit_gate": tasks_mod.PHASE_EXIT[current], "met": gate["done"][current],
                         "gate": gate})
            return 0
        print(ui.banner(f"Phase {tasks_mod.phase_name(current)}"))
        status = ui.colorize("met", ui.GREEN) if gate["done"][current] else ui.colorize("unmet", ui.YELLOW)
        print(f"  exit gate ({status}): {tasks_mod.PHASE_EXIT[current]}")
        if args.phase is None:
            nxt = min(current + 1, 9)
            if nxt != current:
                print(f"  next   → {tasks_mod.phase_name(nxt)}: {tasks_mod.PHASE_EXIT[nxt]}")
            print(ui.colorize("  set it with `rh phase N` (gated; --force records a waiver)", ui.DIM))
        return 0

    if args.phase > current and not args.force:
        # hard gate (SKILL.md §3): do not enter the next phase with an unmet gate
        unmet = [i for i in REQUIRED_BEFORE.get(args.phase, ()) if not gate["done"][i]]
        if unmet:
            names = ", ".join(tasks_mod.phase_name(i) for i in unmet)
            print(ui.colorize(f"✗ refusing to enter {tasks_mod.phase_name(args.phase)} — unmet exit gates: {names}", ui.RED), file=sys.stderr)
            for i in unmet:
                print(f"  - {tasks_mod.phase_name(i)}: {tasks_mod.PHASE_EXIT[i]}", file=sys.stderr)
            print(ui.colorize("  or re-run with --force and record the waiver in STATUS.md (SKILL.md §0 rule 11)", ui.DIM), file=sys.stderr)
            return 1
    store.set_phase(args.phase)
    # soft warnings: gates that may be user-agreed skips
    soft = [i for i in range(args.phase) if i not in REQUIRED_BEFORE.get(args.phase, ()) and not gate["done"][i] and i >= current]
    if soft and not args.force:
        names = ", ".join(tasks_mod.phase_name(i) for i in soft)
        print(ui.colorize(f"⚠ skipping ahead past {names} without artifacts — if user-agreed, note the waiver in STATUS.md (§0 rule 11)", ui.YELLOW), file=sys.stderr)
    if getattr(args, "json", False):
        ui.json_out({"phase": args.phase, "phase_name": tasks_mod.phase_name(args.phase),
                     "exit_gate": tasks_mod.PHASE_EXIT[args.phase], "forced": args.force, "gate": gate})
        return 0
    print(ui.colorize(f"✓ phase → {tasks_mod.phase_name(args.phase)}", ui.GREEN))
    print(f"  exit gate: {tasks_mod.PHASE_EXIT[args.phase]}")
    return 0


@with_root
def cmd_plan_import(args, root: Path):
    added = tasks_mod.import_plan_md(root, dry_run=args.dry_run)
    if getattr(args, "json", False):
        ui.json_out(added)
        return 0
    if not added:
        print(ui.colorize("PLAN.md and the board agree (nothing to import or update).", ui.DIM))
    for t in added:
        mark = "+" if t.get("action") == "added" else "~"
        fields = f"  [{', '.join(t['fields'])}]" if t.get("fields") else ""
        print(f"  {ui.colorize(mark, ui.GREEN)} {t['id']} — {t['title']}{fields}")
    return 0


@with_root
def cmd_describe(args, root: Path):
    from . import tasks as task_mod
    info = {
        "version": __version__,
        "root": str(root),
        "layout": {
            ".rh/ENV.md": "config block + Orchestrator-written environment notes (§2)",
            ".rh/logs/": "SKILL.md §7 event logs",
            ".rh/notes/": "rh add note files (heading-structured)",
            ".rh/tasks.json": "machine-readable board (idle|working|complete)",
            ".rh/env.json": "machine mirror of the .rh/ENV.md config block",
            ".rh/workflow.mmd": "agent-authored workflow diagram (rh workflow displays it)",
            "src/": "implementation",
            "results/": "produced numbers + generating script",
            "papers/": "downloaded PDFs — keep them, never deleted by rh",
            "PLAN.md": "approved steps (§4 template)",
            "STATUS.md": "truth (§5)",
            "LITERATURE.md": "paper takes with DOI (§3)",
            "OUTPUT_LAYOUT.md": "output skeleton + comparable-paper patterns (§3)",
        },
        "phases": [{"id": i, "name": n} for i, n in task_mod.PHASES],
        "task_states": list(task_mod.TASK_STATES),
        "env_keys": [
            {"key": k, "kind": kind, "choices": list(choices), "help": h}
            for k, kind, choices, h in config.ENV_SCHEMA
        ],
        "add_targets": list(add_mod.ADD_TARGETS),
        "agent_budget": {
            "1": "Orchestrator wears all hats",
            "2": "Researcher separate",
            "3": "Researcher + Critique separate",
            "4": "Researcher + Critique + Reviewer separate",
        },
    }
    if getattr(args, "json", False):
        ui.json_out(info)
        return 0
    print(ui.banner("rh describe — the map AI agents read"))
    print(f"{ui.colorize('Root:', ui.DIM)} {root}")
    print(f"{ui.colorize('Layout:', ui.BOLD)}")
    for k, v in info["layout"].items():
        print(f"  {ui.colorize(f'{k:24}', ui.CYAN)} {v}")
    print(f"\n{ui.colorize('Phases:', ui.BOLD)}")
    for p in info["phases"]:
        print(f"  {p['id']} {p['name']}")
    print(f"\n{ui.colorize('Env keys (rh env set KEY=VALUE):', ui.BOLD)}")
    for e in info["env_keys"]:
        print(f"  {e['key']} ({e['kind']}{e['choices']}) — {e['help']}")
    print(f"\n{ui.colorize('Add targets:', ui.BOLD)} {info['add_targets']}")
    print(f"\n{ui.colorize('Agent budget:', ui.BOLD)}")
    for k, v in info["agent_budget"].items():
        print(f"  count={k} → {v}")
    return 0


@with_root
def cmd_resume(args, root: Path):
    """Run the agent harness in THIS terminal with a go-forward prompt (rh resume / rh -r)."""
    # Cheap path check first: an agent must never be opened against the wrong project.
    if not paths.rh_dir(root).exists():
        print(ui.colorize(f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED), file=sys.stderr)
        return 1
    env = config.load_env(root)
    gate = config.phase_gate(root, env)
    if not gate["done"][0]:
        print(ui.colorize(f"✗ phase 0 CONFIG unfinished — {paths.env_md(root)} has no parseable config block:", ui.RED), file=sys.stderr)
        print("  `rh env set KEY=VALUE ...` (see `rh env list`), then confirm ENV.md", file=sys.stderr)
        return 1
    dry = getattr(args, "dry_run", False)
    agent_cli, cli_changed = resume_mod.resolve_agent_cli(
        getattr(args, "cli", None), env, interactive=not dry and resume_mod.is_interactive())
    if not agent_cli:
        print(ui.colorize("✗ no agent CLI found — nothing to spawn", ui.RED), file=sys.stderr)
        return 1
    # persist the pick so the next resume is zero-touch
    if cli_changed:
        env.setdefault("agents", {})
        env["agents"]["cli"] = agent_cli
        config.save_env(root, env)
        print(ui.colorize(f"✓ saved to {paths.env_md(root)}: agents.cli={agent_cli}", ui.GREEN))
    store = tasks_mod.TaskStore(root)
    prompt = resume_mod.build_prompt(root, env, gate, store, extra=getattr(args, "prompt", None) or "")
    prompt_file = paths.rh_dir(root) / "resume-prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt + "\n", encoding="utf-8")
    slug = env.get("project", {}).get("slug") or "untitled"
    if getattr(args, "json", False):
        ui.json_out({
            "root": str(root), "agent_cli": agent_cli,
            "prompt_file": str(prompt_file), "prompt": prompt,
            "gate": gate, "spawned": False, "inline": True,
        })
        return 0
    print(ui.banner(f"rh resume — {slug}", f"project: {root} · agent: {agent_cli} (this terminal)"))
    print(prompt)
    if dry:
        return 0
    print()
    _started, detail = resume_mod.exec_inline(root, agent_cli, prompt)
    # exec replaces this process; reaching here means it could not start
    print(ui.colorize(f"✗ {detail}", ui.RED), file=sys.stderr)
    print(ui.colorize(f"  prompt ready at {prompt_file}", ui.DIM), file=sys.stderr)
    return 1


def cmd_skill_install(args):
    """Copy the bundled research-helper skill into a user skills directory."""
    from importlib import resources

    dest = (Path(args.dest).expanduser() if args.dest
            else Path.home() / ".agents" / "skills" / "research-helper")
    src = resources.files("rh").joinpath("skills", "research-helper")
    if not src.is_dir():
        print("✗ this build does not bundle the skill", file=sys.stderr)
        return 1
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print(f"✗ {dest} already exists — pass --force to overwrite", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    files = 0
    for entry in src.iterdir():
        if entry.is_file():
            (dest / entry.name).write_bytes(entry.read_bytes())
            files += 1
    if getattr(args, "json", False):
        ui.json_out({"installed": str(dest), "files": files})
        return 0
    print(ui.colorize(f"✓ installed skill to {dest}", ui.GREEN))
    print(ui.colorize("  pi and other Agent Skills clients discover ~/.agents/skills/", ui.DIM))
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="project root (default: walk up for .rh/ or ENV.md, else cwd)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable JSON output")
    p = argparse.ArgumentParser(prog="rh", description="research-helper CLI — orchestrate a research project end to end", parents=[common])
    p.add_argument("--version", action="version", version=f"rh {__version__}")
    p.add_argument("-r", "--resume", action="store_true", help="shortcut for `rh resume` (spawn harness + go-forward prompt)")
    sub = p.add_subparsers(dest="cmd", required=False)

    s = sub.add_parser("init", help="create .rh/ layout", parents=[common])
    s.add_argument("--slug", default=None)
    s.add_argument("--clean", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("env", help="environment config", parents=[common])
    esub = s.add_subparsers(dest="e", required=True)
    esub.add_parser("show", parents=[common]).set_defaults(func=cmd_env_show)
    esub.add_parser("list", parents=[common]).set_defaults(func=cmd_env_list)
    sp = esub.add_parser("set", parents=[common]); sp.add_argument("pairs", nargs="*", metavar="KEY=VALUE"); sp.set_defaults(func=cmd_env_set)

    s = sub.add_parser("add", help="append under heading/DOI", parents=[common])
    s.add_argument("target", choices=list(add_mod.ADD_TARGETS))
    s.add_argument("heading", help="heading or DOI")
    s.add_argument("-m", "--message", default=None)
    s.add_argument("--file", default=None, help="note filename (md)")
    s.add_argument("--role", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--id", default=None)
    s.add_argument("--phase", type=int, default=None, help="default: current project phase")
    s.add_argument("--owner", default="researcher")
    s.add_argument("--state", default="idle", choices=list(tasks_mod.TASK_STATES))
    s.add_argument("--deliverable", default="")
    s.add_argument("--verify", default="")
    s.add_argument("--depends-on", dest="depends_on", default="", help="comma-separated task ids this depends on")
    s.add_argument("--kind", default="build", choices=["build", "spike"])
    s.add_argument("--subtask", action="append", default=[], metavar="TEXT", help="repeatable subtask line")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("search", help="local search (rg or python)", parents=[common])
    s.add_argument("query")
    s.add_argument("--max", type=int, default=40)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("tasks", help="task board + progress; `rh tasks set <id> <state>`", parents=[common])
    s.add_argument("--phase", type=int, default=None)
    s.add_argument("--state", default=None, choices=list(tasks_mod.TASK_STATES))
    tsub = s.add_subparsers(dest="t", required=False)
    ts = tsub.add_parser("set", parents=[common]); ts.add_argument("id"); ts.add_argument("state", choices=list(tasks_mod.TASK_STATES)); ts.set_defaults(func=cmd_task_set)
    s.set_defaults(func=cmd_tasks)

    s = sub.add_parser("status", help="project status", parents=[common])
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("workflow", help="display the agent-authored .rh/workflow.mmd (ascii in-terminal)", parents=[common])
    s.add_argument("--example", action="store_true", help="print a starter mermaid source (from the task board) the agent can save as .rh/workflow.mmd")
    s.add_argument("--phases", action="store_true", help="with --example: use the constant SKILL.md phase pipeline")
    s.add_argument("--tools", action="store_true", help="list installed renderers")
    s.add_argument("--png", action="store_true", help="render png from workflow.mmd")
    s.add_argument("--svg", action="store_true", help="render svg from workflow.mmd")
    s.add_argument("--no-render", action="store_true", help="skip ascii display")
    s.set_defaults(func=cmd_workflow)

    s = sub.add_parser("phase", help="show the current phase + exit gate, or set it: rh phase [0-9] (gated)")
    s.add_argument("set", nargs="?", default=None, choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
    s.add_argument("--force", action="store_true", help="jump despite unmet gates (waiver goes in STATUS.md)")
    s.set_defaults(func=cmd_phase_set)

    s = sub.add_parser("plan", help="PLAN.md integration", parents=[common])
    psub = s.add_subparsers(dest="pl", required=True)
    pi = psub.add_parser("import", parents=[common]); pi.add_argument("--dry-run", action="store_true"); pi.set_defaults(func=cmd_plan_import)

    s = sub.add_parser("describe", help="AI map of the tool", parents=[common])
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser("resume", help="spawn a configured harness with a go-forward prompt", parents=[common])
    s.add_argument("--cli", dest="cli", default=None, help="agent binary, e.g. opencode (default: config agents.cli, else ask)")
    s.add_argument("--prompt", default=None, help="extra user instructions appended to the go-forward prompt")
    s.add_argument("--dry-run", action="store_true", help="show prompt + choices without spawning")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("skill", help="install the bundled agent skill", parents=[common])
    ssub = s.add_subparsers(dest="sk", required=True)
    si = ssub.add_parser("install", parents=[common])
    si.add_argument("--dest", default=None, help="destination dir (default: ~/.agents/skills/research-helper)")
    si.add_argument("--force", action="store_true", help="overwrite an existing skill dir")
    si.set_defaults(func=cmd_skill_install)

    return p


KNOWN_CMDS = {"init", "env", "add", "search", "tasks", "status", "workflow", "phase", "plan", "describe", "resume", "skill"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `rh -r [flags...]` (no subcommand) → `rh resume [flags...]`
    if not (set(argv) & KNOWN_CMDS) and ("-r" in argv or "--resume" in argv):
        argv = ["resume", *[a for a in argv if a not in ("-r", "--resume")]]
    args = build_parser().parse_args(argv)
    if args.cmd is None:
        build_parser().print_help()
        return 2
    # `rh phase N` → phase int
    if args.cmd == "phase":
        args.phase = int(args.set) if args.set is not None else None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
