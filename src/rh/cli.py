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
  rh resume / rh -r       # exec the orchestrator (model + thinking from .rh/ENV.md) here
  rh spawn <role> [prompt] ...   # open another role agent with the ENV.md command
  rh info <FILE.md>       # what that artifact is for, who owns it, its sections
  rh skill install [--dest DIR] [--force]
  rh describe   # AI-friendly map: phases, layout, env schema (decisions you must surface)

Global flags: --root DIR, --json (machine-readable).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from . import __version__, config, paths, ui, workflow
from . import add as add_mod
from . import agents as agents_mod
from . import artifacts as artifacts_mod
from . import checklist as checklist_mod
from . import doctor as doctor_mod
from . import resume as resume_mod
from . import search as search_mod
from . import spawn as spawn_mod
from . import tasks as tasks_mod


def with_root(fn):
    def wrapper(args):
        root = paths.resolve_root(getattr(args, "root", None))
        return fn(args, root)
    wrapper.__name__ = fn.__name__
    return wrapper


@with_root
def cmd_init(args, root: Path):
    """`rh init` — create the .rh/ workspace. Never overwrites what it did not archive.

    Existing files are never clobbered silently: without --force rh refuses and
    names what exists. --force archives ENV.md + tasks.json to
    `.rh/.bak/<timestamp>/` before writing (a copy — it keeps the originals and
    their environment notes). --clean archives the whole `.rh/` tree there
    first, so event logs and notes survive it. --dry-run writes nothing.
    """
    dry = bool(getattr(args, "dry_run", False))
    force = bool(getattr(args, "force", False))
    would_write: list[str] = []
    backups: list[str] = []

    # .rh/ layout is folders-only; ensure_layout never writes file contents
    d = paths.rh_dir(root)
    would_write += [f"create {d}/ (folders: logs/ notes/ tasks/ tmp/)",
                    "create src/ results/ papers/ at root"]

    # Sensitive existing files
    env_file = paths.env_md(root)
    tasks_file = paths.tasks_json(root)
    had_env = env_file.exists()
    for f, what in ((env_file, "ENV.md config block"), (tasks_file, "task board")):
        if f.exists():
            would_write.append(f"{f} exists ({what}) — kept unless --force archives it first")
    if args.clean and d.exists():
        would_write.append(f"--clean: archive {d}/ to .rh/.bak/<timestamp>/ (event logs, notes included), then recreate it")
    plan_file = paths.artifact_path(root, "PLAN.md")
    if plan_file.exists():
        would_write.append(f"PLAN.md already exists at {plan_file} — adopt it, do not overwrite")

    # Existing role files
    role_files = sorted((d / "agents").glob("*.md")) if (d / "agents").is_dir() else []

    # Non-destructive guard: existing files block without --force
    blocking = [str(f) for f in (env_file, tasks_file) if f.exists()]
    if blocking and not force and not args.clean:
        print(ui.colorize("✗ refusing to overwrite existing files without --force:", ui.RED), file=sys.stderr)
        for b in blocking:
            print(f"  - {b}", file=sys.stderr)
        print(ui.colorize("  --force archives a copy to .rh/.bak/<timestamp>/ and keeps the rest; "
                          "--clean archives the whole .rh/ and recreates it", ui.DIM), file=sys.stderr)
        return 1

    # Questionnaire answers (skippable — the Orchestrator asks later if skipped).
    # Defaults are the values already in ENV.md, so Enter never downgrades a
    # configured project.
    answers: dict[str, str] = {}
    skipped: list[str] = []
    if not args.non_interactive and not dry and not getattr(args, "json", False):
        answers, skipped = _init_questionnaire(args, root)

    # Effective slug: flag wins, then questionnaire, then existing
    slug = args.slug or answers.get("slug") or ""

    if dry:
        if getattr(args, "json", False):
            ui.json_out({"root": str(root), "would_write": would_write, "dry_run": True,
                         "slug": slug, "answers": answers, "skipped": skipped})
            return 0
        print(ui.banner("rh init (dry-run)", f"{root}"))
        for w in would_write:
            print(f"  would {w}")
        if role_files:
            for rf in role_files:
                print(f"  would keep role file {rf}")
        if slug:
            print(f"  would set project.slug={slug}")
        if answers:
            print(f"  questionnaire answers: {answers}")
        if skipped:
            print(f"  would leave untouched: {', '.join(skipped)}")
        print(ui.colorize("  nothing written (dry-run)", ui.DIM))
        return 0

    # Archive before anything is overwritten or removed.
    if args.clean and d.exists():
        archived = paths.archive_tree(root, d)  # copy, then remove: nothing is lost
        backups.append(str(archived))
        print(ui.colorize(f"  --clean: archived {d}/ → {archived}", ui.YELLOW))
    else:
        for f in (env_file, tasks_file):
            if f.exists():
                backups.append(str(paths.backup_file(root, f)))

    d = paths.ensure_layout(root)
    tasks_mod.TaskStore(root).load()  # ensure tasks.json shape exists lazily

    # ENV.md: created when missing, updated with the slug/questionnaire answers,
    # otherwise left as it is (environment notes stay put)
    if slug or answers or not env_file.exists():
        env = config.load_env(root)
        if slug:
            env["project"]["slug"] = slug
        for key, val in answers.items():
            if not key.startswith(("agents.", "project.")):
                continue
            try:
                config.set_nested(env, key, config.coerce_value(val, config.schema_for(key)[1]))
            except Exception:
                print(ui.colorize(f"  ⚠ could not write {key}={val!r} — set it later with "
                                  f"`rh env set {key}=...`", ui.YELLOW))
        config.save_env(root, env)

    if not (d / ".gitkeep").exists():
        (d / ".gitkeep").write_text("")
    if getattr(args, "json", False):
        ui.json_out({"root": str(root), "rh_dir": str(d), "initialized": True,
                     "backups": backups, "slug": slug, "answers": answers, "skipped": skipped})
        return 0
    print(ui.banner("rh init", f"{root}"))
    print(f"  {ui.colorize('✓', ui.GREEN)} created {d}/")
    for sub in ("logs/", "notes/", "tasks/", "tmp/"):
        print(f"  {ui.colorize('✓', ui.GREEN)} .rh/{sub}")
    print(f"  {ui.colorize('✓', ui.GREEN)} src/ results/ papers/ at root")
    if not had_env or args.clean:
        print(f"  {ui.colorize('✓', ui.GREEN)} ENV.md at .rh/ENV.md (config + environment notes)")
    elif slug or answers:
        print(f"  {ui.colorize('✓', ui.GREEN)} ENV.md updated at {env_file}")
    else:
        print(f"  {ui.colorize('↷', ui.DIM)} ENV.md kept as-is at {env_file}")
    for b in backups:
        print(f"  {ui.colorize('↷', ui.DIM)} archived (copy) to {b}")
    if role_files:
        for rf in role_files:
            print(f"  {ui.colorize('↷', ui.DIM)} kept role file {rf} (not overwritten)")
    if plan_file.exists():
        print(f"  {ui.colorize('↷', ui.YELLOW)} PLAN.md already exists at {plan_file} — adopt it (rh plan import), do not overwrite")
    if skipped:
        print(ui.colorize(f"  skipped (Orchestrator will ask): {', '.join(skipped)}", ui.DIM))
    print()
    print(f"Next: {ui.colorize('rh env set project.slug=<name>', ui.CYAN)}  "
          f"·  {ui.colorize('rh env show', ui.CYAN)}  ·  {ui.colorize('rh doctor', ui.CYAN)}")
    return 0


def _init_questionnaire(args, root: Path) -> tuple[dict[str, str], list[str]]:
    """Ask the few questions that let ENV.md be born with answers.

    Defaults are read from the ENV.md already on disk, so pressing Enter keeps
    the project's current settings instead of resetting them. `s` (or Ctrl-C)
    **skips**: the key is not written at all and is returned in `skipped` so the
    Orchestrator can ask later. Non-interactive callers never reach here
    (--non-interactive, --json, --dry-run skip it entirely).
    """
    if not sys.stdin.isatty():
        return {}, []
    env = config.load_env(root)
    agents = env.get("agents") or {}
    answers: dict[str, str] = {}
    skipped: list[str] = []
    stopped = False  # Ctrl-C skips this and every later question

    def ask(key: str, title: str, default: str, choices: str = "") -> None:
        nonlocal stopped
        if stopped:
            skipped.append(key)
            return
        print(ui.colorize(f"? {title}", ui.BOLD))
        if choices:
            print(ui.colorize(f"  {choices}", ui.DIM))
        print(ui.colorize(f"  enter=keep {default!r} · s=skip (Orchestrator asks later) · Ctrl-C=skip the rest", ui.DIM))
        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            stopped = True
            skipped.append(key)
            return
        if raw.lower() == "s":
            skipped.append(key)
        elif raw == "":
            answers[key] = default
        else:
            answers[key] = raw

    ask("slug", "Project slug (kebab-case, e.g. my-project)",
        args.slug or str((env.get("project") or {}).get("slug") or "demo"))
    ask("agents.count", "How many parallel agents for planning and research? (1..4)",
        str(agents.get("count") or 1), "1 | 2 | 3 | 4")
    ask("agents.backend", "Backend for parallel agents?",
        str(agents.get("backend") or "none"), "tmux | herdr | tuios | none")
    ask("agents.cli", "Agent CLI binary?",
        str(agents.get("cli") or ""), "e.g. pi, claude, codex — blank = harness default")
    ask("agents.shell", "Your shell?",
        str(agents.get("shell") or ""), "e.g. fish, zsh, bash — blank = $SHELL")
    ask("agents.split", "Pane layout for rh spawn?",
        str(agents.get("split") or ""), "vertical | horizontal | window — blank = ask at first spawn")
    skills = agents.get("skills") or []
    ask("agents.skills", "Skills every agent must load?",
        ",".join(str(s) for s in skills) if isinstance(skills, list) else str(skills),
        "comma-separated, e.g. research-helper,crw")

    # harness snippet: copy-paste only, never executed here
    if stopped:
        skipped.append("snippet")
        return answers, skipped
    print(ui.colorize("? Harness snippet (examples/envs/*.sh) — copy-paste, s=skip", ui.BOLD))
    print(ui.colorize("  pi | claude | codex | custom (type the file path, or s to skip)", ui.DIM))
    try:
        raw = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        raw = "s"
    if raw in ("pi", "claude", "codex"):
        answers["snippet"] = f"examples/envs/{raw}.sh"
    elif raw and raw != "s":
        answers["snippet"] = raw
    else:
        skipped.append("snippet")
    return answers, skipped


def _env_value(value) -> str:
    """One-line display for a config value (dicts become provider/model)."""
    if isinstance(value, dict):
        if not value:
            return "—"
        if set(value) <= {"provider", "model", "thinking"}:
            model = value.get("model") or ""
            if not model:
                return "—"
            text = f"{value.get('provider')}/{model}" if value.get("provider") else str(model)
            if value.get("thinking"):
                text += f" (thinking: {value['thinking']})"
            return text
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
    print()
    print(ui.colorize("Also settable (any role name):", ui.DIM))
    for _pattern, kind, label, help_text in config.ENV_PATTERNS:
        print(f"  {ui.colorize(label, ui.CYAN)} ({kind}) — {help_text}")
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
        for _pattern, kind, label, help_text in config.ENV_PATTERNS:
            print(f"  {label} ({kind}) — {help_text}")
        return 2
    for pair in args.pairs:
        if "=" not in pair:
            print(f"⚠ skipping {pair!r}: missing '='", file=sys.stderr)
            continue
        key, raw = pair.split("=", 1)
        key = key.strip()
        spec = config.schema_for(key)
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
        # PLAN.md guard: warn when appending to a pre-existing plan
        if args.target == "plan":
            pf = paths.artifact_path(root, "PLAN.md")
            if pf.exists() and pf.stat().st_size > 0:
                print(ui.colorize(f"↷ PLAN.md already exists at {pf} — appended a step; read it first (rh info PLAN.md) and mirror with `rh plan import`", ui.YELLOW))
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
    print(ui.phase_rail(current, done=gate["done"]))
    print()
    # one bar for the board — subtask counts show inline on each task row
    print(f"{ui.bar(summary['pct'])}  {summary['complete']}/{summary['total']} tasks complete · "
          f"{summary['working']} working · {summary['idle']} idle")
    if summary["subtasks_total"]:
        sc = summary["subtasks_complete"]
        st = summary["subtasks_total"]
        print(ui.colorize(f"Subtasks: {sc}/{st} complete", ui.DIM))
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
    print(f"Project: {slug} · Phase: {tasks_mod.phase_name(summary['current_phase'])}")
    print()
    if gate["problems"]:
        for p in gate["problems"]:
            print(ui.colorize(f"⚠ {p}", ui.YELLOW))
        print(ui.colorize("  (SKILL.md §3 hard gates: resolve these or ask the user to waive.)", ui.DIM))
        print()
    print(ui.phase_rail(summary["current_phase"], done=gate["done"]))
    print()
    # ONE overall progress line — the phase rail above already shows position,
    # and the per-phase bars below show the breakdown, so no repeats here.
    print(f"{ui.bar(summary['pct'], width=24)}  {summary['complete']}/{summary['total']} tasks · "
          f"{summary['working']} working · {summary['idle']} idle")
    print()
    # per-phase progress only — the task/subtask detail lives in `rh tasks`
    by_phase: dict[int, list[dict]] = {}
    for t in store.list():
        by_phase.setdefault(t["phase"], []).append(t)
    if not by_phase:
        print(ui.colorize("No tasks — `rh plan import` will mirror PLAN.md steps here.", ui.DIM))
    elif len(by_phase) == 1:
        # one phase means a per-phase bar would just repeat the line above
        only = next(iter(by_phase))
        working = [t["id"] for t in by_phase[only] if t["state"] == "working"]
        now = f" · working: {', '.join(working)}" if working else ""
        print(ui.colorize(f"all {len(by_phase[only])} tasks are in "
                          f"{tasks_mod.phase_name(only)}{now} · detail: `rh tasks`", ui.DIM))
    else:
        for phase in sorted(by_phase):
            phase_tasks = by_phase[phase]
            done = sum(1 for t in phase_tasks if t["state"] == "complete")
            working = [t["id"] for t in phase_tasks if t["state"] == "working"]
            bar_pct = round(100 * done / len(phase_tasks)) if phase_tasks else 0
            now = f" · working: {', '.join(working)}" if working else ""
            print(f"{ui.colorize(tasks_mod.phase_name(phase), ui.BOLD)}  "
                  f"{ui.bar(bar_pct, width=14)}  ({done}/{len(phase_tasks)}){now}")
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
        "artifacts": [{"file": n, "phase": artifacts_mod.ARTIFACTS[n]["phase"],
                       "owner": artifacts_mod.ARTIFACTS[n]["owner"],
                       "purpose": artifacts_mod.ARTIFACTS[n]["purpose"]}
                      for n in artifacts_mod.names()],
        "info": {
            "command": "rh info <FILE.md>",
            "note": "one clean description per artifact (owner, phase, sections, template, "
                    "rules) — read it before writing the file",
        },
        "spawn": {
            "command": "rh spawn <role> \"<instructions>\" [--inline] [--dry-run]",
            "roles": agents_mod.list_roles(root),
            "launch_template": "agents.commands.<role> (falls back to agents.commands.default)",
            "window_template": "agents.spawn — how a parallel agent is opened; blank = "
                               "detached process with a log in .rh/logs/",
            "placeholders": list(spawn_mod.PLACEHOLDERS),
            "spawn_placeholders": list(spawn_mod.SPAWN_PLACEHOLDERS),
            "note": "rh never hardcodes a CLI flag: the commands live in .rh/ENV.md",
        },
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
    print(f"\n{ui.colorize('Artifacts (rh info <FILE>):', ui.BOLD)}")
    for a in info["artifacts"]:
        name = ui.colorize(f"{a['file']:17}", ui.CYAN)
        print(f"  {name} {a['phase']:22} {a['owner']}")
    print(f"\n{ui.colorize('Spawning (commands come from .rh/ENV.md):', ui.BOLD)}")
    print("  rh resume / rh -r       orchestrator here, model+thinking from "
          "agents.roles.orchestrator")
    print(f"  rh spawn <role> \"...\"   {', '.join(info['spawn']['roles'])}")
    print(f"  placeholders: {', '.join('{' + p + '}' for p in info['spawn']['placeholders'])}"
          f" (+ {{command}} in agents.spawn)")
    print(f"\n{ui.colorize('Agent budget:', ui.BOLD)}")
    for k, v in info["agent_budget"].items():
        print(f"  count={k} → {v}")
    return 0


@with_root
def cmd_resume(args, root: Path):
    """Run the Orchestrator in THIS terminal, using the command written in ENV.md."""
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
    store = tasks_mod.TaskStore(root)
    extra = getattr(args, "prompt", None) or ""
    if getattr(args, "prompt_file", None):
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(ui.colorize(f"✗ cannot read {args.prompt_file}: {exc}", ui.RED), file=sys.stderr)
            return 1
        extra = f"{extra}\n{text}".strip() if extra else text
    prompt = resume_mod.build_prompt(root, env, gate, store, extra=extra)
    prompt_file = paths.rh_dir(root) / "resume-prompt.md"
    if not dry:  # --dry-run writes nothing, not even the prompt file
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
    slug = env.get("project", {}).get("slug") or "untitled"

    # The launch command (model + thinking level included) is written in ENV.md's
    # agents.commands.orchestrator. Only when no command template exists at all do
    # we fall back to picking a bare binary — and then we persist it.
    plan = spawn_mod.launch_plan(root, env, "orchestrator", prompt, prompt_file)
    if plan["argv"] is None and not dry:
        agent_cli, cli_changed = resume_mod.resolve_agent_cli(
            getattr(args, "cli", None), env, interactive=resume_mod.is_interactive())
        if not agent_cli:
            if plan.get("error"):
                print(ui.colorize(f"✗ {plan['error']}", ui.RED), file=sys.stderr)
            print(ui.colorize("✗ no agent CLI found — nothing to spawn", ui.RED), file=sys.stderr)
            print(ui.colorize("  add the launch command to ENV.md: rh env set "
                              "agents.commands.orchestrator='pi --model {model} --thinking {thinking}'",
                              ui.DIM), file=sys.stderr)
            return 1
        if cli_changed:
            env.setdefault("agents", {})["cli"] = agent_cli
            config.save_env(root, env)
            print(ui.colorize(f"✓ saved to {paths.env_md(root)}: agents.cli={agent_cli}", ui.GREEN))
        plan = spawn_mod.launch_plan(root, env, "orchestrator", prompt, prompt_file)
    if plan["argv"] is None:
        if plan.get("error"):
            print(ui.colorize(f"✗ {plan['error']}", ui.RED), file=sys.stderr)
        for note in plan["notes"]:
            print(ui.colorize(f"⚠ {note}", ui.YELLOW), file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        ui.json_out({
            "root": str(root), "role": "orchestrator", "argv": plan["argv"],
            "command": shlex.join(plan["argv"]), "source": plan["source"],
            "prompt_file": str(prompt_file), "prompt": prompt,
            "model": plan["model"], "provider": plan["provider"],
            "thinking": plan["thinking"], "skills": plan["skills"],
            "notes": plan["notes"], "error": plan.get("error", ""),
            "gate": gate,
            "spawned": False, "inline": True,
        })
        return 0
    model = (f"{plan['provider']}/{plan['model']}" if plan["provider"] and plan["model"]
             else plan["model"]) or "ENV.md default"
    if plan["thinking"]:
        model += f" · thinking {plan['thinking']}"
    print(ui.banner(f"rh resume — {slug}", f"project: {root} · this terminal"))
    print(f"{ui.colorize('model:', ui.DIM)} {model}"
          f"  {ui.colorize('skills:', ui.DIM)} {', '.join(plan['skills']) or '—'}")
    print(f"{ui.colorize('command:', ui.DIM)} {shlex.join(plan['argv'])}")
    for note in plan["notes"]:
        print(ui.colorize(f"⚠ {note}", ui.YELLOW))
    print()
    print(prompt)
    if dry:
        return 0
    print()
    _started, detail = spawn_mod.exec_argv(root, plan["argv"])
    # exec replaces this process; reaching here means it could not start
    print(ui.colorize(f"✗ {detail}", ui.RED), file=sys.stderr)
    print(ui.colorize(f"  prompt ready at {prompt_file}", ui.DIM), file=sys.stderr)
    return 1


@with_root
def cmd_doctor(args, root: Path):
    """`rh doctor` — verify what ENV.md names actually exists on this machine."""
    data = doctor_mod.check(root)
    if getattr(args, "json", False):
        ui.json_out(data)
        return 0 if data["ok"] else 1
    print(ui.banner("Doctor", f"root: {root}"))
    for item in data["checks"]:
        mark = ui.colorize("[✓]", ui.GREEN) if item["ok"] else ui.colorize("[✗]", ui.RED)
        print(f"  {mark} {item['id']:28} {item['detail']}")
    print()
    print(ui.colorize("✓ all named tools present" if data["ok"] else f"✗ {data['failures']} check(s) failed — fix ENV.md or create the named file/binary",
                      ui.GREEN if data["ok"] else ui.YELLOW))
    return 0 if data["ok"] else 1


@with_root
def cmd_checklist(args, root: Path):
    """`rh checklist` — the Orchestrator's live checklist (SKILL.md §0 + phase exits)."""
    data = checklist_mod.build_checklist(root)
    if getattr(args, "json", False):
        ui.json_out(data)
        return 0
    print(ui.banner(f"Checklist — {data['phase_name']}", f"root: {root}"))
    for item in data["items"]:
        st = item["status"]
        if st == "ok":
            mark = ui.colorize("[✓]", ui.GREEN)
        elif st == "current":
            mark = ui.colorize("[~]", ui.CYAN)
        elif st == "later":
            mark = ui.colorize("[·]", ui.DIM)
        else:
            mark = ui.colorize("[ ]", ui.YELLOW)
        print(f"  {mark} {item['label']}")
        if item.get("detail"):
            print(ui.colorize(f"      {item['detail']}", ui.DIM))
    print()
    if data["ok"]:
        print(ui.colorize("✓ all checks satisfied", ui.GREEN))
    else:
        print(ui.colorize(f"⚠ {data['pending']} pending — resolve or record a waiver in STATUS.md (rule 11)", ui.YELLOW))
    return 0


@with_root
def cmd_agents(args, root: Path):
    """`rh agents [ROLE]` — list or show the per-role agent files (.rh/agents/<role>.md)."""
    role = (getattr(args, "role", None) or "").strip().lower()
    if getattr(args, "write", False):
        if role:
            p = agents_mod.write_one(root, role)
            if getattr(args, "json", False):
                ui.json_out({"written": str(p)})
                return 0
            print(ui.colorize(f"✓ wrote {p}", ui.GREEN))
            return 0
        written = agents_mod.write_all(root)
        if getattr(args, "json", False):
            ui.json_out({"written": [str(x) for x in written]})
            return 0
        if not written:
            print(ui.colorize("✓ all role files already exist in .rh/agents/", ui.GREEN))
        for pth in written:
            print(ui.colorize(f"✓ wrote {pth}", ui.GREEN))
        return 0
    if role:
        info = agents_mod.role_file_info(root, role)
        content = agents_mod.read_role(root, role)
        if getattr(args, "json", False):
            ui.json_out({**info, "content": content or ""})
            return 0
        if content is None:
            print(ui.colorize(f"⏳ no .rh/agents/{role}.md yet — `rh agents {role} --write` scaffolds it; the Orchestrator fills it in with the user.", ui.YELLOW))
            return 0
        print(content)
        return 0
    # list
    roles = agents_mod.list_roles(root)
    if getattr(args, "json", False):
        ui.json_out([agents_mod.role_file_info(root, r) for r in roles])
        return 0
    print(ui.banner("Agents", ".rh/agents/<role>.md — tailored role files (no role info is hardcoded in rh)"))
    for r in roles:
        info = agents_mod.role_file_info(root, r)
        mark = "✓" if info["exists"] else "·"
        print(f"  {mark} {ui.colorize(r, ui.CYAN):12} {info['file']} ({'exists' if info['exists'] else 'missing — run `rh agents --write`'})")
    print(ui.colorize("  Edit the .md files with user approval; ENV.md holds agents.commands.<role> per role.", ui.DIM))
    return 0


@with_root
def cmd_spawn_terminal(args, root: Path):
    """`rh spawn terminal <command>` — open a plain shell terminal in a new pane."""
    if not paths.rh_dir(root).exists():
        # Still allow --dry-run outside a project for shell/split detection demo
        if not getattr(args, "dry_run", False):
            print(ui.colorize(f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED), file=sys.stderr)
            return 1
    env = config.load_env(root) if paths.rh_dir(root).exists() else config.deep_merge(config.DEFAULT_ENV, {})
    command = " ".join(getattr(args, "text", None) or []).strip()
    if not command:
        print("✗ which command? e.g. rh spawn terminal 'pytest -q' or rh spawn terminal -- python3 -m http.server", file=sys.stderr)
        return 2
    plan = spawn_mod.terminal_plan(root, env, command, split=getattr(args, "split", None))
    preview = spawn_mod.terminal_preview(root, env, plan)
    if getattr(args, "json", False):
        ui.json_out({
            "root": str(root), "terminal": True, "argv": plan["argv"],
            "command": preview["command"], "mode": preview["mode"], "log": preview["log"],
            "shell": plan["shell"], "split": plan["split"],
            "notes": plan["notes"], "spawned": False,
        })
        return 0
    print(ui.banner("rh spawn terminal", f"project: {root}"))
    print(f"{ui.colorize('shell:', ui.DIM)} {plan['shell']}"
          f"  {ui.colorize('split:', ui.DIM)} {plan['split'] or '(not set — ask the user)'}"
          f"  {ui.colorize('mode:', ui.DIM)} {preview['mode']}")
    print(f"{ui.colorize('command:', ui.DIM)} {preview['command']}")
    if preview.get("log"):
        print(f"{ui.colorize('log:', ui.DIM)} {preview['log']}")
    for note in plan["notes"] + preview.get("notes", []):
        print(ui.colorize(f"⚠ {note}", ui.YELLOW))
    if getattr(args, "dry_run", False):
        return 0
    result = spawn_mod.spawn_terminal_now(root, env, plan, preview)
    if result.get("mode") == "pane":
        ok = result.get("returncode", 0) == 0
        print(ui.colorize(("✓ opened terminal pane via agents.spawn" if ok else "⚠ agents.spawn failed") + f" ({result['command']})", ui.GREEN if ok else ui.YELLOW))
    else:
        print(ui.colorize(f"✓ started terminal pid {result.get('pid')} → {result.get('log','')}", ui.GREEN))
    return 0


@with_root
def cmd_agent_status(args, root: Path):
    """`rh agent status` — who is running, on which model, from .rh/logs/spawns.jsonl."""
    f = paths.logs_dir(root) / "spawns.jsonl"
    rows: list[dict] = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if getattr(args, "json", False):
        ui.json_out(rows)
        return 0
    print(ui.banner("Agent status", f"root: {root}"))
    if not rows:
        print(ui.colorize("No spawns recorded yet — `rh spawn <role>` writes .rh/logs/spawns.jsonl from here on.", ui.DIM))
        print(ui.colorize("  pane spawns record no pid, so they never count against agents.count; "
                          "the panes are visible to the user instead.", ui.DIM))
        return 0
    for r in rows:
        alive = ""
        pid = r.get("pid")
        if pid:
            try:
                os.kill(pid, 0); alive = "alive"
            except OSError:
                alive = "dead"
        print(f"  {r.get('role','?'):12} pid={pid} ({alive}) model={r.get('model') or '—'} mode={r.get('mode')} ts={r.get('ts','')}")
    return 0


@with_root
def cmd_gate_check(args, root: Path):
    """`rh gate check [--json]` — machine-readable gate report (same as phase_gate)."""
    env = config.load_env(root)
    gate = config.phase_gate(root, env)
    if getattr(args, "json", False):
        ui.json_out(gate)
        return 0 if gate["ok"] else 1
    print(ui.banner("Gate check", f"root: {root}"))
    print(f"  phase: {gate['phase']}  ok: {gate['ok']}")
    for p in gate["problems"]:
        print(ui.colorize(f"  - {p}", ui.YELLOW))
    return 0 if gate["ok"] else 1


@with_root
def cmd_log_tail(args, root: Path):
    """`rh log tail [N]` — read the newest §7 event log without opening files."""
    logs_dir = paths.logs_dir(root)
    n = int(getattr(args, "n", None) or 20)
    files = sorted(logs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime) if logs_dir.is_dir() else []
    if getattr(args, "json", False):
        out = []
        for f in files[-n:]:
            out.append({"file": str(f), "text": f.read_text(encoding="utf-8")[:4000]})
        ui.json_out(out)
        return 0
    if not files:
        print(ui.colorize("No event logs yet in .rh/logs/ (use `rh add log` per SKILL.md §7).", ui.DIM))
        return 0
    for f in files[-n:]:
        print(ui.colorize(f"=== {f.name} ===", ui.BOLD))
        print(f.read_text(encoding="utf-8")[:2000])
        print()
    return 0


@with_root
def cmd_handoff(args, root: Path):
    """`rh handoff [--file NAME]` — pack STATUS.md + PLAN.md + checklist for a fresh session."""
    data = checklist_mod.build_checklist(root)
    lines = [
        f"# Handoff — {data['phase_name']} (rule 14)",
        f"root: {root}",
        "",
        "## Checklist",
    ]
    for item in data["items"]:
        lines.append(f"- [{item['status']}] {item['label']} ({item['ref']})")
    lines += ["", "## ENV tail (environment notes)"]
    lines.append(config.load_tail(root) or "(none)")
    for name in ("STATUS.md", "PLAN.md"):
        if paths.rh_dir(root).exists():
            try:
                text = paths.artifact_path(root, name).read_text(encoding="utf-8")
            except OSError:
                text = "(missing)"
        else:
            text = "(missing)"
        lines += ["", f"## {name}", text or "(empty)"]
    out = "\n".join(lines) + "\n"
    fname = getattr(args, "file", None) or ".rh/HANDOFF.md"
    dest = root / fname if not fname.startswith("/") else Path(fname)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    if getattr(args, "json", False):
        ui.json_out({"file": str(dest), "phase": data["phase_name"], "pending": data["pending"]})
        return 0
    print(ui.colorize(f"✓ wrote {dest} — start a fresh session and read it first (rule 14)", ui.GREEN))
    return 0


@with_root
def cmd_spawn(args, root: Path):
    """`rh spawn <role> [instructions]` — open another role agent with the ENV.md command."""
    if not paths.rh_dir(root).exists():
        print(ui.colorize(f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED), file=sys.stderr)
        return 1
    env = config.load_env(root)
    role = (args.agent or "").strip().lower()
    if not role:
        known_roles = agents_mod.list_roles(root)
        print("✗ which role? " + " | ".join(known_roles), file=sys.stderr)
        return 2
    commands = (env.get("agents") or {}).get("commands") or {}
    known = set(agents_mod.list_roles(root)) | ({str(k).lower() for k in commands} if isinstance(commands, dict) else set())
    if role not in known:
        print(ui.colorize(f"✗ unknown role {role!r} — roles come from .rh/agents/<role>.md and agents.commands.<role>", ui.RED),
              file=sys.stderr)
        print(ui.colorize(f"  define your own: rh env set agents.commands.{role}='pi --model {{model}} --system-prompt-file {{agent_file}}' "
                          f"and write .rh/agents/{role}.md (rh agents {role} --write scaffolds it)",
                          ui.DIM), file=sys.stderr)
        return 2
    extra = " ".join(getattr(args, "text", None) or []).strip()
    if getattr(args, "prompt", None):
        extra = f"{extra}\n{args.prompt}".strip() if extra else args.prompt
    if getattr(args, "prompt_file", None):
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(ui.colorize(f"✗ cannot read {args.prompt_file}: {exc}", ui.RED), file=sys.stderr)
            return 1
        extra = f"{extra}\n{text}".strip() if extra else text
    slug = env.get("project", {}).get("slug") or "untitled"
    store = tasks_mod.TaskStore(root)
    prompt = spawn_mod.build_role_prompt(root, env, role, store, extra=extra)
    prompt_file = paths.rh_dir(root) / "tmp" / f"spawn-{add_mod.slugify(role)}-prompt.md"
    if not getattr(args, "dry_run", False):  # --dry-run writes nothing
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
    plan = spawn_mod.launch_plan(root, env, role, prompt, prompt_file)
    if plan["argv"] is None:
        if plan.get("error"):
            print(ui.colorize(f"✗ {plan['error']}", ui.RED), file=sys.stderr)
        for note in plan["notes"]:
            print(ui.colorize(f"⚠ {note}", ui.YELLOW), file=sys.stderr)
        return 1
    # Budget: agents.count is a ceiling on concurrent agents (SKILL.md §5).
    budget = int((env.get("agents") or {}).get("count") or 1)
    running = spawn_mod.running_count(root)
    if running >= budget and not getattr(args, "force", False):
        print(ui.colorize(f"✗ agents.count={budget} reached ({running} running) — close one (rule 13) or pass --force", ui.RED), file=sys.stderr)
        return 1
    preview = spawn_mod.spawn_preview(root, env, role, plan)
    notes = plan["notes"] + preview["notes"]
    if getattr(args, "json", False):
        ui.json_out({
            "root": str(root), "role": role, "argv": plan["argv"],
            "command": preview["command"], "mode": preview["mode"],
            "log": preview["log"], "source": plan["source"],
            "prompt_file": str(prompt_file), "prompt": prompt,
            "model": plan["model"], "provider": plan["provider"],
            "thinking": plan["thinking"], "skills": plan["skills"],
            "agents_count": (env.get("agents") or {}).get("count"),
            "notes": notes, "error": plan.get("error", ""), "spawned": False,
        })
        return 0
    model = (f"{plan['provider']}/{plan['model']}" if plan["provider"] and plan["model"]
             else plan["model"]) or "ENV.md default"
    if plan["thinking"]:
        model += f" · thinking {plan['thinking']}"
    print(ui.banner(f"rh spawn — {role}", f"project: {root} · {slug}"))
    print(f"{ui.colorize('model:', ui.DIM)} {model}"
          f"  {ui.colorize('skills:', ui.DIM)} {', '.join(plan['skills']) or '—'}"
          f"  {ui.colorize('agents.count:', ui.DIM)} {(env.get('agents') or {}).get('count')}")
    print(f"{ui.colorize('mode:', ui.DIM)} {preview['mode']}"
          f"  {ui.colorize('via', ui.DIM)} {plan['source'] or 'agents.cli'}")
    print(f"{ui.colorize('command:', ui.DIM)} {preview['command']}")
    if preview["log"]:
        print(f"{ui.colorize('log:', ui.DIM)} {preview['log']}")
    for note in notes:
        print(ui.colorize(f"⚠ {note}", ui.YELLOW))
    print(f"{ui.colorize('prompt:', ui.DIM)} {prompt_file}")
    if getattr(args, "dry_run", False):
        print()
        print(prompt)
        return 0
    print()
    if getattr(args, "inline", False):
        _started, detail = spawn_mod.exec_argv(root, plan["argv"])
        print(ui.colorize(f"✗ {detail}", ui.RED), file=sys.stderr)
        print(ui.colorize(f"  prompt ready at {prompt_file}", ui.DIM), file=sys.stderr)
        return 1
    result = spawn_mod.spawn_now(root, env, role, plan)
    if result["mode"] == "pane":
        ok = result.get("returncode", 0) == 0
        print(ui.colorize(("✓ opened pane via agents.spawn" if ok
                           else "⚠ the agents.spawn command failed") +
                          f" ({result['command']})", ui.GREEN if ok else ui.YELLOW))
    else:
        print(ui.colorize(f"✓ started pid {result.get('pid')} → {result['log']}", ui.GREEN))
    print(ui.colorize("  record the spawn in STATUS.md; close it when the job is done (rules 12–13).", ui.DIM))
    return 0


def _short(text: str, limit: int = 88) -> str:
    """First sentence of a purpose, trimmed — for one-line tables."""
    sentence = text.split(". ")[0].rstrip(".")
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


@with_root
def cmd_info(args, root: Path):
    """`rh info [FILE]` — what that artifact is for, who owns it, its sections."""
    names = artifacts_mod.names()
    if not args.name:
        if getattr(args, "json", False):
            ui.json_out([{"file": n, "phase": artifacts_mod.ARTIFACTS[n]["phase"],
                          "owner": artifacts_mod.ARTIFACTS[n]["owner"],
                          "purpose": artifacts_mod.ARTIFACTS[n]["purpose"]} for n in names])
            return 0
        print(ui.banner("Artifacts", "rh info <FILE.md> for the full description"))
        rows = [[n, artifacts_mod.ARTIFACTS[n]["phase"], artifacts_mod.ARTIFACTS[n]["owner"],
                 _short(artifacts_mod.ARTIFACTS[n]["purpose"])] for n in names]
        print(ui.table(["file", "phase", "owner", "what it is"], rows))
        return 0
    key = artifacts_mod.resolve(args.name)
    if key is None:
        print(ui.colorize(f"✗ unknown artifact {args.name!r} — known: {', '.join(names)}", ui.RED),
              file=sys.stderr)
        return 1
    spec = artifacts_mod.ARTIFACTS[key]
    path = paths.artifact_path(root, key)
    exists = path.exists()
    if getattr(args, "json", False):
        ui.json_out({"file": key, "path": str(path), "exists": exists, **spec})
        return 0
    if getattr(args, "template", False):
        print(spec["template"])
        return 0
    print(ui.banner(key, f"{spec['phase']} · owner: {spec['owner']}"))
    print(spec["purpose"])
    print()
    print(f"{ui.colorize('location:', ui.DIM)} {spec['location']}"
          f"  {ui.colorize('now:', ui.DIM)} {path} ({'exists' if exists else 'not created yet'})")
    print(f"{ui.colorize('consumers:', ui.DIM)} {spec['consumers']}")
    print()
    print(ui.colorize("Sections it must have:", ui.BOLD))
    for section in spec["sections"]:
        print(f"  - {section}")
    print()
    print(ui.colorize("Rules that bite here:", ui.BOLD))
    for rule in spec["rules"]:
        print(f"  - {rule}")
    print()
    print(ui.colorize(f"Template (`rh info {key} --template`):", ui.BOLD))
    print(spec["template"])
    return 0


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

    s = sub.add_parser("init", help="create .rh/ layout (non-destructive; --force/--clean archive first, --dry-run previews)",
                       parents=[common])
    s.add_argument("--slug", default=None)
    s.add_argument("--clean", action="store_true",
                   help="archive .rh/ (event logs, notes, ENV.md, tasks.json) to .rh/.bak/<timestamp>/ then recreate it")
    s.add_argument("--force", action="store_true",
                   help="archive a copy of ENV.md/tasks.json to .rh/.bak/<timestamp>/ before init writes")
    s.add_argument("--dry-run", action="store_true", help="preview what would be written without writing")
    s.add_argument("--non-interactive", action="store_true", help="skip the questionnaire (agents/CI)")
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

    s = sub.add_parser("resume", help="run the orchestrator here (model + thinking from .rh/ENV.md)", parents=[common])
    s.add_argument("--cli", dest="cli", default=None, help="fallback agent binary when ENV.md has no agents.commands (default: config agents.cli, else ask)")
    s.add_argument("--prompt", default=None, help="extra user instructions appended to the go-forward prompt")
    s.add_argument("--prompt-file", dest="prompt_file", default=None,
                   help="read the extra instructions from a markdown file (examples/prompts/orchestrator.md)")
    s.add_argument("--dry-run", action="store_true", help="show the resolved command + prompt without spawning")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("spawn", help="open another role agent with the launch command from .rh/ENV.md",
                       parents=[common])
    s.add_argument("agent", help="role (a .rh/agents/<role>.md file and/or agents.commands.<role> key), "
                                "e.g. researcher; 'terminal' means `rh spawn terminal <cmd>` for a shell pane")
    s.add_argument("text", nargs="*", help="instructions for that agent (joined into one prompt)")
    s.add_argument("--prompt", default=None, help="instructions instead of the positional form")
    s.add_argument("--prompt-file", dest="prompt_file", default=None,
                   help="read the instructions from a markdown file (examples/prompts/*.md)")
    s.add_argument("--inline", action="store_true", help="run the agent in this terminal instead of a new pane/process")
    s.add_argument("--dry-run", action="store_true", help="print the command + role prompt without starting anything")
    s.add_argument("--split", default=None, choices=["vertical", "horizontal", "window"], help="pane layout override for this spawn (default: agents.split)")
    s.add_argument("--force", action="store_true", help="ignore agents.count budget (waiver → STATUS.md)")
    s.set_defaults(func=cmd_spawn)

    s = sub.add_parser("spawn-terminal", help="open a plain shell terminal in a new pane (shell from agents.shell/$SHELL, layout from agents.split)",
                       parents=[common])
    s.add_argument("text", nargs="*", help="command to run in the new terminal")
    s.add_argument("--split", default=None, choices=["vertical", "horizontal", "window"], help="pane layout override (default: agents.split)")
    s.add_argument("--dry-run", action="store_true", help="print the shell + split + command without starting anything")
    s.set_defaults(func=cmd_spawn_terminal)
    # alias handled in main(): `rh spawn terminal <cmd>` → spawn-terminal

    s = sub.add_parser("checklist", help="live Orchestrator checklist: SKILL.md §0 rules + phase exit gates",
                       parents=[common])
    s.set_defaults(func=cmd_checklist)

    s = sub.add_parser("doctor", help="verify the binaries, shells, templates and role files ENV.md names",
                       parents=[common])
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("agent", help="agent helpers: `rh agent status`", parents=[common])
    asub = s.add_subparsers(dest="a", required=True)
    ast = asub.add_parser("status", parents=[common]); ast.set_defaults(func=cmd_agent_status)

    s = sub.add_parser("gate", help="`rh gate check` — machine-readable gate report", parents=[common])
    gsub = s.add_subparsers(dest="g", required=True)
    gc = gsub.add_parser("check", parents=[common]); gc.set_defaults(func=cmd_gate_check)

    s = sub.add_parser("log", help="`rh log tail [N]` — newest §7 event logs", parents=[common])
    lsub = s.add_subparsers(dest="l", required=True)
    lt = lsub.add_parser("tail", parents=[common])
    lt.add_argument("n", nargs="?", default=None, help="how many logs (default 20)")
    lt.set_defaults(func=cmd_log_tail)

    s = sub.add_parser("handoff", help="pack STATUS + PLAN + checklist for a fresh session (rule 14)",
                       parents=[common])
    s.add_argument("--file", default=None, help="output file (default: .rh/HANDOFF.md)")
    s.set_defaults(func=cmd_handoff)

    s = sub.add_parser("agents", help="list / show / write the per-role agent files (.rh/agents/<role>.md)",
                       parents=[common])
    s.add_argument("role", nargs="?", default=None, help="one role to show (e.g. researcher)")
    s.add_argument("--write", action="store_true", help="write default role files (all roles, or just ROLE when given)")
    s.set_defaults(func=cmd_agents)

    s = sub.add_parser("info", help="describe an artifact: what it is for, owner, sections, template",
                       parents=[common])
    s.add_argument("name", nargs="?", default=None, help="file name, e.g. PLAN.md | status | .rh/GAPS.md")
    s.add_argument("--template", action="store_true", help="print only the template block")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("skill", help="install the bundled agent skill", parents=[common])
    ssub = s.add_subparsers(dest="sk", required=True)
    si = ssub.add_parser("install", parents=[common])
    si.add_argument("--dest", default=None, help="destination dir (default: ~/.agents/skills/research-helper)")
    si.add_argument("--force", action="store_true", help="overwrite an existing skill dir")
    si.set_defaults(func=cmd_skill_install)

    return p


KNOWN_CMDS = {"init", "env", "add", "search", "tasks", "status", "workflow", "phase", "plan",
              "describe", "resume", "spawn", "spawn-terminal", "info", "skill", "agents", "checklist", "doctor", "agent", "gate", "log", "handoff"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `rh [--root DIR] spawn terminal <cmd>` → `rh [--root DIR] spawn-terminal <cmd>`
    # (root flags may precede the subcommand, so only the adjacent pair matches)
    for _i in range(len(argv) - 1):
        if argv[_i] == "spawn" and argv[_i + 1] == "terminal":
            argv = argv[:_i] + ["spawn-terminal"] + argv[_i + 2:]
            break
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
