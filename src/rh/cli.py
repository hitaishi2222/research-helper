"""`rh` entry point.

Commands:
  rh init [--root DIR] [--force] [--clean] [--dry-run]
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
  rh resume / rh -r       # exec the orchestrator (model + thinking from .rh/env.json) here
  rh spawn <role> [prompt] ...   # open another role agent with the env.json command
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
import shutil
import sys
from pathlib import Path

from rich.prompt import Prompt

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
    names what exists. --force archives env.json + tasks.json to
    `.rh/.bak/<timestamp>/` before writing (a copy — it keeps the originals). --clean archives the whole `.rh/` tree there
    first, so event logs and notes survive it. --dry-run writes nothing.
    """
    dry = bool(getattr(args, "dry_run", False))
    force = bool(getattr(args, "force", False))
    would_write: list[str] = []
    backups: list[str] = []

    # .rh/ layout is folders-only; ensure_layout never writes file contents
    d = paths.rh_dir(root)
    would_write += [
        f"create {d}/ (folders: logs/ notes/ tasks/ tmp/)",
        "create src/ results/ papers/ at root",
        "create .rh/env.json (config), .rh/agents/*.md (role files), .rh/CHECKLIST.md",
        "create .rh/HANDOFF.md (empty — the next session's to-do is written at session end)",
    ]

    # Sensitive existing files
    env_file = paths.env_json(root)
    tasks_file = paths.tasks_json(root)
    legacy_env = paths.env_md(root)
    had_env = env_file.exists()
    for f, what in ((env_file, "config"), (tasks_file, "task board")):
        if f.exists():
            would_write.append(
                f"{f} exists ({what}) — kept unless --force archives it first"
            )
    if legacy_env.exists():
        would_write.append(
            f"migrate legacy {legacy_env} → {env_file} + .rh/ENVIRONMENT.md "
            "(the markdown is archived, not deleted)"
        )
    if args.clean and d.exists():
        would_write.append(
            f"--clean: archive {d}/ to .rh/.bak/<timestamp>/ (event logs, notes included), then recreate it"
        )
    plan_file = paths.artifact_path(root, "PLAN.md")
    if plan_file.exists():
        would_write.append(
            f"PLAN.md already exists at {plan_file} — adopt it, do not overwrite"
        )

    # Existing role files
    role_files = sorted((d / "agents").glob("*.md")) if (d / "agents").is_dir() else []

    # The project name is the directory — no naming flag, no extra argument.
    # Change it later with `rh env set project.name=...`; the questionnaire may override.
    default_name = root.name

    # Non-destructive guard: existing files block without --force
    blocking = [str(f) for f in (env_file, tasks_file) if f.exists()]
    if blocking and not force and not args.clean:
        print(
            ui.colorize(
                "✗ refusing to overwrite existing files without --force:", ui.RED
            ),
            file=sys.stderr,
        )
        for b in blocking:
            print(f"  - {b}", file=sys.stderr)
        print(
            ui.colorize(
                "  --force archives a copy to .rh/.bak/<timestamp>/ and keeps the rest; "
                "--clean archives the whole .rh/ and recreates it",
                ui.DIM,
            ),
            file=sys.stderr,
        )
        return 1

    # Questionnaire answers (skippable — the Orchestrator asks later if skipped).
    # Defaults are the values already in env.json, so Enter never downgrades a
    # configured project.
    answers: dict[str, str] = {}
    skipped: list[str] = []
    if not args.non_interactive and not dry and not getattr(args, "json", False):
        answers, skipped = _init_questionnaire(args, root)

    # Effective name: questionnaire answer, else whatever env.json already has,
    # else the directory name
    name = answers.get("project.name") or ""

    if dry:
        if getattr(args, "json", False):
            ui.json_out(
                {
                    "root": str(root),
                    "would_write": would_write,
                    "dry_run": True,
                    "name": name,
                    "answers": answers,
                    "skipped": skipped,
                }
            )
            return 0
        print(ui.banner("rh init (dry-run)", f"{root}"))
        for w in would_write:
            print(f"  would {w}")
        if role_files:
            for rf in role_files:
                print(f"  would keep role file {rf}")
        existing_name = ""
        if env_file.exists():
            try:
                block = json.loads(env_file.read_text(encoding="utf-8"))
                project = (
                    (block.get("project") or {}) if isinstance(block, dict) else {}
                )
                existing_name = str(project.get("name") or "")
            except (OSError, json.JSONDecodeError):
                existing_name = ""
        print(f"  would set project.name={name or existing_name or default_name}")
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
    migrated = config.migrate_legacy_env_md(root)
    if migrated:
        backups.append(str(migrated))
        print(
            ui.colorize(
                f"  migrated {legacy_env} → .rh/env.json + .rh/ENVIRONMENT.md "
                f"(archived {migrated})",
                ui.YELLOW,
            )
        )
    tasks_mod.TaskStore(root).load()  # ensure tasks.json shape exists lazily

    # env.json: created when missing, updated with the name/questionnaire answers,
    # otherwise left as it is
    env = config.load_env(root)
    if name:
        env.setdefault("project", {})["name"] = name
    elif not (env.get("project") or {}).get("name"):
        env.setdefault("project", {})["name"] = default_name
    for key, val in answers.items():
        if key == "harness":  # applied separately, below
            continue
        try:
            config.set_nested(
                env, key, config.coerce_value(val, config.schema_for(key)[1])
            )
        except (KeyError, TypeError, IndexError, ValueError):
            print(
                ui.colorize(
                    f"  ⚠ could not write {key}={val!r} — set it later with "
                    f"`rh env set {key}=...`",
                    ui.YELLOW,
                )
            )
    if answers.get("harness") and not config.apply_harness(env, answers["harness"]):
        print(
            ui.colorize(
                f"  ⚠ unknown harness {answers['harness']!r} — set the launch command "
                f"later with `rh env set agents.commands.orchestrator=...`",
                ui.YELLOW,
            )
        )
    config.save_env(root, env)

    # Default role files: every role gets a scaffold to tailor with the user
    # (existing files are never overwritten).
    agents_written = agents_mod.write_all(root)

    if not (d / ".gitkeep").exists():
        (d / ".gitkeep").write_text("")
    # The Orchestrator's to-do list, checked against the state we just wrote.
    checklist_file, checklist_data = checklist_mod.write_checklist(root, env)
    # Empty at init: the handoff is written only when a session ends, never
    # generated from STATUS/PLAN (rule 14).
    handoff_file = d / "HANDOFF.md"
    if not handoff_file.exists():
        handoff_file.write_text("", encoding="utf-8")
    if getattr(args, "json", False):
        ui.json_out(
            {
                "root": str(root),
                "rh_dir": str(d),
                "initialized": True,
                "backups": backups,
                "name": name,
                "answers": answers,
                "skipped": skipped,
                "env_json": str(env_file),
                "agents_written": [str(p) for p in agents_written],
                "checklist": str(checklist_file),
                "handoff": str(handoff_file),
                "pending": checklist_data["pending"],
            }
        )
        return 0
    print(ui.banner("rh init", f"{root}"))
    print(f"  {ui.colorize('✓', ui.GREEN)} created {d}/")
    for sub in ("logs/", "notes/", "tasks/", "tmp/"):
        print(f"  {ui.colorize('✓', ui.GREEN)} .rh/{sub}")
    print(f"  {ui.colorize('✓', ui.GREEN)} src/ results/ papers/ at root")
    if not had_env or args.clean:
        print(
            f"  {ui.colorize('✓', ui.GREEN)} .rh/env.json (config — `rh env show`, `rh env set KEY=VALUE`)"
        )
    else:
        print(f"  {ui.colorize('✓', ui.GREEN)} .rh/env.json updated")
    if agents_written:
        print(
            f"  {ui.colorize('✓', ui.GREEN)} .rh/agents/*.md ({len(agents_written)} role files — edit with the user)"
        )
    else:
        print(f"  {ui.colorize('↷', ui.DIM)} kept existing role files in .rh/agents/")
    print(
        f"  {ui.colorize('✓', ui.GREEN)} .rh/CHECKLIST.md ({checklist_data['pending']} pending "
        f"— the Orchestrator's to-do list, read from its system prompt)"
    )
    print(
        f"  {ui.colorize('✓', ui.GREEN)} .rh/HANDOFF.md (empty until a session hands work to the next)"
    )
    print(
        f"  {ui.colorize('·', ui.DIM)} .rh/ENVIRONMENT.md is written in phase 2, after the environment interview"
    )
    for b in backups:
        print(f"  {ui.colorize('↷', ui.DIM)} archived (copy) to {b}")
    if plan_file.exists():
        print(
            f"  {ui.colorize('↷', ui.YELLOW)} PLAN.md already exists at {plan_file} — read it (rh info PLAN.md); its steps become tasks with `rh add task`, never by overwrite"
        )
    if skipped:
        print(
            ui.colorize(
                f"  skipped (Orchestrator will ask): {', '.join(skipped)}", ui.DIM
            )
        )
    print()
    print(
        f"Next: {ui.colorize('rh doctor', ui.CYAN)}  ·  {ui.colorize('rh resume', ui.CYAN)}"
    )
    return 0


def _path_options(
    candidates: list[str], current: str, other: bool = True
) -> list[tuple]:
    """(value, label) options for a binary question, marking what is installed."""
    options: list[tuple] = []
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        options.append(
            (name, f"{name}  " + ("✓ on PATH" if shutil.which(name) else "— not found"))
        )
    if current and current not in seen:
        options.append((current, f"{current}  (current, not on PATH)"))
    if other:
        options.append((None, "other — type it"))
    return options


def _rich_ask(console, *, default: str, choices: list[str] | None = None) -> str:
    """`rich.prompt.Prompt` with a compact `›` prompt (no `: ` suffix)."""
    ask = Prompt(
        "  [bold cyan]›[/]",
        console=console,
        choices=choices,
        show_choices=False,
        show_default=False,
    )
    ask.prompt_suffix = " "
    return ask(default=default)


def _ask_question(console, wizard, question: dict) -> str:
    """One answer via rich.prompt; numeric options map to their value.

    `s`, `q` and `other` stay commands, not values. Free-text questions accept
    anything; option questions also accept the value typed out.
    """
    options = question.get("options")
    default = question["default"]
    if not options:
        return _rich_ask(console, default=default).strip()
    values = [value for value, _label in options if value]
    choices = (
        [str(i) for i in range(1, len(options) + 1)] + values + ["other", "s", "q"]
    )
    raw = _rich_ask(console, choices=choices, default=default).strip()
    low = raw.lower()
    if low in ("s", "q"):
        return low
    if low == "other":
        wizard.extra_line()
        return _rich_ask(console, default="").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        value = options[int(raw) - 1][0]
        if value is None:
            wizard.extra_line()
            return _rich_ask(console, default="").strip()
        return value
    return raw


def _init_questionnaire(args, root: Path) -> tuple[dict[str, str], list[str]]:
    """Ask the few questions that let env.json be born with answers.

    A compact rich wizard: the keys are printed once, then one question frame
    is redrawn in place. Enter keeps the shown default, Tab submits the line and
    moves on, `s` skips the key (the Orchestrator asks later), `q` finishes with
    the answers so far, Ctrl-C skips the rest. Options are numbered and include
    what is actually installed (agent CLIs, shells, backends).
    Non-interactive callers never reach here (--non-interactive, --json,
    --dry-run skip it entirely).
    """
    if not sys.stdin.isatty():
        return {}, []
    env = config.load_env(root)
    agents = env.get("agents") or {}
    harnesses = config.harness_names()
    current_cli = str(agents.get("cli") or "").strip().lower()
    default_harness = current_cli if current_cli in harnesses else ""
    shell_name = (
        str(agents.get("shell") or "") or Path(os.environ.get("SHELL", "")).name
    )
    shell_candidates = [
        s
        for s in ("fish", "zsh", "bash", "sh", "nushell", "tcsh")
        if shutil.which(s) or s == shell_name
    ]

    questions: list[dict] = [
        {
            "key": "project.name",
            "title": "Project name",
            "help": "only a label — the directory is the workspace",
            "options": None,
            "default": str((env.get("project") or {}).get("name") or root.name),
        },
        {
            "key": "agents.count",
            "title": "How many parallel agents for planning and research?",
            "help": "how many agents may run at once",
            "default": str(agents.get("count") or 1),
            "options": [
                ("1", "1 — one agent wears all hats"),
                ("2", "2 — + researcher"),
                ("3", "3 — + critique"),
                ("4", "4 — + reviewer"),
            ],
        },
        {
            "key": "agents.backend",
            "title": "Backend for parallel agents?",
            "help": "how agents open in panes",
            "default": str(agents.get("backend") or "none"),
            "options": [
                (
                    name,
                    f"{name}  "
                    + ("✓ on PATH" if shutil.which(name) else "— not found"),
                )
                for name in ("tmux", "herdr", "tuios")
            ]
            + [("none", "none — no panes (serial)")],
        },
        {
            "key": "agents.cli",
            "title": "Agent CLI binary?",
            "help": "detected on PATH; other lets you type one",
            "default": current_cli,
            "options": _path_options(resume_mod.detect_agent_clis(), current_cli),
        },
        {
            "key": "agents.shell",
            "title": "Your shell?",
            "help": "blank keeps $SHELL",
            "default": str(agents.get("shell") or ""),
            "options": [("", f"keep $SHELL ({shell_name or 'sh'})")]
            + _path_options(shell_candidates, str(agents.get("shell") or "")),
        },
        {
            "key": "agents.split",
            "title": "Pane layout for rh spawn?",
            "help": "blank asks at the first spawn",
            "default": str(agents.get("split") or ""),
            "options": [
                ("", "ask at the first spawn"),
                ("vertical", "vertical split"),
                ("horizontal", "horizontal split"),
                ("window", "new window / workspace"),
            ],
        },
        {
            "key": "harness",
            "title": "Harness start template?",
            "help": "fills agents.cli + agents.commands.*; existing commands are kept",
            "default": default_harness,
            "options": [("", "skip — set the commands later")]
            + [
                (
                    name,
                    f"{name}  "
                    + (
                        "✓ on PATH"
                        if shutil.which(
                            str(
                                (config.load_harnesses().get(name) or {}).get(
                                    "cli", name
                                )
                            )
                        )
                        else "— not found"
                    ),
                )
                for name in harnesses
            ],
        },
        {
            "key": "literature.library",
            "title": "PDF library / arXiv downloads?",
            "help": "papr manages papers and writes the manuscript from the same TUI",
            "default": str((env.get("literature") or {}).get("library") or "none"),
            "options": [
                (
                    name,
                    f"{name}  "
                    + ("✓ on PATH" if shutil.which(name) else "— not found")
                    + f" · {what}",
                )
                for name, what in (
                    ("papr", "TUI: paper library, arXiv download, manuscript"),
                    ("zot", "Zotero CLI"),
                    ("lit", "liteparse: PDF text out"),
                )
            ]
            + [("none", "none — keep papers/ by hand"), (None, "other — type it")],
        },
    ]

    answers: dict[str, str] = {}
    skipped: list[str] = []
    stopped = False  # q or Ctrl-C: finish with what we have
    console = ui.init_console()
    wizard = ui.InitWizard(console)
    ui.enable_tab_to_advance()
    wizard.header()

    for step, question in enumerate(questions, 1):
        key = question["key"]
        if stopped:
            skipped.append(key)
            continue
        wizard.question(
            step=step,
            total=len(questions),
            title=question["title"],
            help_text=question["help"],
            options=question["options"],
            default=question["default"],
            answered=len(answers),
            skipped=len(skipped),
        )
        try:
            answer = _ask_question(console, wizard, question)
        except (EOFError, KeyboardInterrupt):
            print()
            stopped = True
            skipped.append(key)
            continue
        low = answer.lower()
        if low == "s":
            skipped.append(key)
        elif low == "q":
            stopped = True
            skipped.append(key)
        elif key == "harness":
            if low in harnesses:
                answers[key] = low
            elif not answer and question["default"]:
                answers[key] = question["default"]
            else:
                skipped.append(key)
        else:
            answers[key] = answer
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
            text = (
                f"{value.get('provider')}/{model}"
                if value.get("provider")
                else str(model)
            )
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
    rows = [
        [key, _env_value(_safe_nested(env, key))]
        for key, _kind, _choices, _help in config.ENV_SCHEMA
    ]
    print(ui.table(["key", "value"], rows))
    tools = (env.get("project") or {}).get("environment") or []
    tools = [t for t in tools if isinstance(t, dict) and str(t.get("name", "")).strip()]
    if tools:
        print()
        print(ui.colorize("Project environment (the software this project runs)", ui.DIM))
        print(ui.table(
            ["software", "version", "what it is for"],
            [[str(t.get("name", "")), str(t.get("version") or "—"),
              str(t.get("note") or "")] for t in tools],
        ))
    if config.user_plans(env):
        print()
        print(ui.colorize(
            "planners: none — the user is the planner "
            "(phase 4 gate: user-authored PLAN.md + user approval)",
            ui.DIM,
        ))
    tail = config.environment_notes(root)
    if tail.strip():
        print()
        print(ui.colorize("Environment notes (.rh/ENVIRONMENT.md)", ui.DIM))
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
            ui.json_out(
                {"key": key, "kind": kind, "choices": list(choices), "help": help_text}
            )
        return 0
    rows = [
        [key, kind, " ".join(str(c) for c in choices) or "—", help_text]
        for key, kind, choices, help_text in config.ENV_SCHEMA
    ]
    print(ui.table(["key", "kind", "choices", "help"], rows))
    print()
    print(ui.colorize("Also settable (any role name):", ui.DIM))
    for _pattern, kind, label, help_text in config.ENV_PATTERNS:
        print(f"  {ui.colorize(label, ui.CYAN)} ({kind}) — {help_text}")
    print(
        f"\n{ui.colorize('Set:', ui.DIM)} rh env set agents.count=2 agents.backend=tmux ..."
    )
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
        current = config.resolve_key(key)
        if current != key:
            print(ui.colorize(f"↷ {key} was renamed — writing {current}", ui.DIM))
            key = current
        spec = config.schema_for(key)
        if spec is None:
            print(f"⚠ unknown key {key!r} — see `rh env list`", file=sys.stderr)
            continue
        kind = spec[1]
        try:
            value = config.coerce_value(raw, kind, key)
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
    print(ui.colorize(f"✓ wrote {paths.env_json(root)}", ui.GREEN))
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
            args.heading,
            task_id=args.id,
            phase=phase,
            owner=args.owner,
            state=args.state,
            deliverable=args.deliverable,
            verify=args.verify,
            depends_on=deps,
            kind=args.kind,
            subtasks=args.subtask,
        )
        print(
            ui.colorize(
                f"✓ task {task['id']} ({task['state']}, {tasks_mod.phase_name(phase)})",
                ui.GREEN,
            )
        )
        return 0
    else:
        # PLAN.md guard: warn when appending to a pre-existing plan
        if args.target == "plan":
            pf = paths.artifact_path(root, "PLAN.md")
            if pf.exists() and pf.stat().st_size > 0:
                print(
                    ui.colorize(
                        f"↷ PLAN.md already exists at {pf} — appended a step; read it first (rh info PLAN.md), then create the matching task with `rh add task --id <id>`",
                        ui.YELLOW,
                    )
                )
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
        ui.json_out(
            [
                {
                    "path": str(h.path.relative_to(root))
                    if h.path.is_relative_to(root)
                    else str(h.path),
                    "line": h.line_no,
                    "text": h.line.strip(),
                }
                for h in hits
            ]
        )
        return 0
    print(
        ui.banner(
            f"Search: {args.query}",
            f"engine: {engine} · {len(hits)} hits · root: {root}",
        )
    )
    if not hits:
        print(
            ui.colorize(
                "No matches. Try `rh search <different term>` or check .rh/ exists.",
                ui.YELLOW,
            )
        )
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
    draft = [
        t
        for t in tasks
        if t["state"] == "idle"
        and not any(s["state"] != "idle" for s in t.get("subtasks", []))
    ]
    active = [t for t in tasks if t["state"] == "working"]
    complete = [t for t in tasks if t["state"] == "complete"]
    cancelled = [t for t in tasks if t["state"] == "cancelled"]
    remaining = [
        t
        for t in tasks
        if t not in draft and t not in active and t not in complete and t not in cancelled
    ]
    return {
        "draft": draft,
        "active": active,
        "complete": complete,
        "cancelled": cancelled,
        "remaining": remaining,
    }


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
        ui.json_out(
            {
                "summary": summary,
                "tasks": tasks,
                "groups": {k: [t["id"] for t in v] for k, v in groups.items()},
                "gate": gate,
            }
        )
        return 0
    print(ui.banner("Tasks"))
    print(ui.phase_rail(current, done=gate["done"]))
    print()
    # one bar for the board — subtask counts show inline on each task row
    print(
        f"{ui.bar(summary['pct'])}  {summary['complete']}/{summary['total']} tasks complete · "
        f"{summary['working']} working · {summary['idle']} idle"
        + (f" · {summary['cancelled']} cancelled" if summary["cancelled"] else "")
    )
    if summary["subtasks_total"]:
        sc = summary["subtasks_complete"]
        st = summary["subtasks_total"]
        print(ui.colorize(f"Subtasks: {sc}/{st} complete", ui.DIM))
    print()
    if gate["problems"]:
        for p in gate["problems"]:
            print(ui.colorize(f"⚠ {p}", ui.YELLOW))
        print(
            ui.colorize(
                "  (SKILL.md §3 hard gates: resolve these or ask the user to waive.)",
                ui.DIM,
            )
        )
        print()
    if not tasks:
        print(
            ui.colorize(
                'No tasks yet — `rh add task "..."` (repeatable `--subtask`).', ui.DIM
            )
        )
        return 0
    # one flat table — the state column replaces the old Draft/Active/Complete lanes
    rows = [
        [
            t["id"],
            ui.state_label(t["state"]),
            tasks_mod.phase_name(t["phase"]),
            (t["title"] or "")[:42],
        ]
        for t in tasks
    ]
    print(ui.table(["id", "state", "phase", "title"], rows))
    return 0


@with_root
def cmd_status(args, root: Path):
    env = config.load_env(root)
    store = tasks_mod.TaskStore(root)
    summary = store.summary()
    gate = config.phase_gate(root, env)
    if getattr(args, "json", False):
        ui.json_out(
            {
                "root": str(root),
                "name": env.get("project", {}).get("name", ""),
                "phase": summary["current_phase"],
                "phase_name": tasks_mod.phase_name(summary["current_phase"]),
                "summary": summary,
                "gate": gate,
                "initialized": (root / ".rh").exists(),
            }
        )
        return 0
    name = env.get("project", {}).get("name") or "untitled"
    print(ui.banner(f"{name} — status", str(root)))
    print(f"Project: {name} · Phase: {tasks_mod.phase_name(summary['current_phase'])}")
    print()
    if gate["problems"]:
        for p in gate["problems"]:
            print(ui.colorize(f"⚠ {p}", ui.YELLOW))
        print(
            ui.colorize(
                "  (SKILL.md §3 hard gates: resolve these or ask the user to waive.)",
                ui.DIM,
            )
        )
        print()
    print(ui.phase_rail(summary["current_phase"], done=gate["done"]))
    print()
    # ONE overall progress line — the phase rail above already shows position,
    # and the per-phase bars below show the breakdown, so no repeats here.
    print(
        f"{ui.bar(summary['pct'], width=24)}  {summary['complete']}/{summary['total']} tasks · "
        f"{summary['working']} working · {summary['idle']} idle"
        + (f" · {summary['cancelled']} cancelled" if summary["cancelled"] else "")
    )
    print()
    # per-phase progress only — the task/subtask detail lives in `rh tasks`
    by_phase: dict[int, list[dict]] = {}
    for t in store.list():
        by_phase.setdefault(t["phase"], []).append(t)
    if not by_phase:
        print(
            ui.colorize(
                "No tasks — create them from PLAN.md with `rh add task` (see `rh info PLAN.md`).", ui.DIM
            )
        )
    elif len(by_phase) == 1:
        # one phase means a per-phase bar would just repeat the line above
        only = next(iter(by_phase))
        working = [t["id"] for t in by_phase[only] if t["state"] == "working"]
        now = f" · working: {', '.join(working)}" if working else ""
        print(
            ui.colorize(
                f"all {len(by_phase[only])} tasks are in "
                f"{tasks_mod.phase_name(only)}{now} · detail: `rh tasks`",
                ui.DIM,
            )
        )
    else:
        for phase in sorted(by_phase):
            phase_tasks = by_phase[phase]
            # cancelled counts as resolved here, same as the overall bar
            done = sum(
                1 for t in phase_tasks if t["state"] in ("complete", "cancelled")
            )
            working = [t["id"] for t in phase_tasks if t["state"] == "working"]
            bar_pct = round(100 * done / len(phase_tasks)) if phase_tasks else 0
            now = f" · working: {', '.join(working)}" if working else ""
            print(
                f"{ui.colorize(tasks_mod.phase_name(phase), ui.BOLD)}  "
                f"{ui.bar(bar_pct, width=14)}  ({done}/{len(phase_tasks)}){now}"
            )
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
            ui.json_out(
                {
                    "ascii_tools": workflow.ascii_tools(),
                    "diagram_tools": workflow.diagram_tools(),
                }
            )
            return 0
        if getattr(args, "example", False):
            src = (
                workflow.mermaid_for_phase(current, done=gate["done"])
                if args.phases
                else workflow.mermaid_for_tasks(store.list())
            )
            ui.json_out({"example": src})
            return 0
        if not src_file.exists():
            ui.json_out(
                {
                    "has_workflow": False,
                    "workflow_file": str(src_file),
                    "ascii_tools": workflow.ascii_tools(),
                    "diagram_tools": workflow.diagram_tools(),
                }
            )
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
        ui.json_out(
            {
                "has_workflow": True,
                "workflow_file": str(src_file),
                "current_phase": current,
                "gate": gate,
                "ascii_tool": tool,
                "ascii_ok": art is not None,
                "rendered": rendered,
            }
        )
        return 0

    # pure-output modes first: everything below adds UI chrome around them
    if args.tools:
        print(
            ui.banner(
                "Renderers",
                "rh workflow: external tools are optional — the built-in text view always works",
            )
        )
        rows = [["built-in text", "always", "compact node/edge view from the .mmd"]]
        for tool, spec in workflow.ASCII_TOOLS.items():
            rows.append(
                [
                    f"{tool} (ascii)",
                    "✓ installed" if workflow.tool_installed(tool) else "—",
                    f"{' | '.join(spec['bins'])} — {workflow.ASCII_TOOL_INSTALL.get(tool, '')}",
                ]
            )
        for tool, spec in workflow.DIAGRAM_TOOLS.items():
            rows.append(
                [
                    f"{tool} (svg/png)",
                    "✓ installed" if workflow.tool_installed(tool) else "—",
                    f"{' | '.join(spec['bins'])} — writes .rh/workflow.svg|png",
                ]
            )
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
        print(
            ui.colorize(
                "  The Orchestrator or Researcher authors .rh/workflow.mmd (the PLAN.md step DAG,",
                ui.DIM,
            )
        )
        print(
            ui.colorize(
                "  adapted to the installed renderers) — rh only displays it, it never creates it.",
                ui.DIM,
            )
        )
        return 0
    src = src_file.read_text(encoding="utf-8")

    art, tool = (None, None)
    if not args.no_render:
        art, tool = workflow.render_ascii(root, src)
    if art:
        print(
            f"{ui.colorize('Diagram', ui.BOLD)} {ui.colorize(f'(via {tool})', ui.DIM)}"
        )
        print(art)
        print()
    elif not args.no_render:
        installed = workflow.ascii_tools()
        if installed:
            print(
                ui.colorize(
                    f"⚠ ascii render failed via {installed[0]} — check the .mmd syntax",
                    ui.YELLOW,
                )
            )
        else:
            print(
                ui.colorize(
                    "No ASCII renderer installed — nothing downloaded without your say-so.",
                    ui.YELLOW,
                )
            )
            print(
                ui.colorize(
                    "  Options (install one, or run the npx form yourself — it fetches into the npm cache):",
                    ui.DIM,
                )
            )
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
    plans = config.user_plans(config.load_env(root))

    def exit_gate(phase: int) -> str:
        return tasks_mod.phase_exit(phase, plans)

    if args.phase is None or args.phase == current:
        # `rh phase` — the phase is a gate, not a badge: show what it costs to leave it
        if getattr(args, "json", False):
            ui.json_out(
                {
                    "phase": current,
                    "phase_name": tasks_mod.phase_name(current),
                    "exit_gate": exit_gate(current),
                    "met": gate["done"][current],
                    "gate": gate,
                }
            )
            return 0
        print(ui.banner(f"Phase {tasks_mod.phase_name(current)}"))
        status = (
            ui.colorize("met", ui.GREEN)
            if gate["done"][current]
            else ui.colorize("unmet", ui.YELLOW)
        )
        print(f"  exit gate ({status}): {exit_gate(current)}")
        if args.phase is None:
            nxt = min(current + 1, 9)
            if nxt != current:
                print(
                    f"  next   → {tasks_mod.phase_name(nxt)}: {exit_gate(nxt)}"
                )
            print(
                ui.colorize(
                    "  set it with `rh phase N` (gated; --force records a waiver)",
                    ui.DIM,
                )
            )
        return 0

    if args.phase > current and not args.force:
        # hard gate (SKILL.md §3): do not enter the next phase with an unmet gate
        unmet = [i for i in REQUIRED_BEFORE.get(args.phase, ()) if not gate["done"][i]]
        if unmet:
            names = ", ".join(tasks_mod.phase_name(i) for i in unmet)
            print(
                ui.colorize(
                    f"✗ refusing to enter {tasks_mod.phase_name(args.phase)} — unmet exit gates: {names}",
                    ui.RED,
                ),
                file=sys.stderr,
            )
            for i in unmet:
                print(
                    f"  - {tasks_mod.phase_name(i)}: {exit_gate(i)}",
                    file=sys.stderr,
                )
            print(
                ui.colorize(
                    "  or re-run with --force and record the waiver in STATUS.md (SKILL.md §0 rule 11)",
                    ui.DIM,
                ),
                file=sys.stderr,
            )
            return 1
    store.set_phase(args.phase)
    # soft warnings: gates that may be user-agreed skips
    soft = [
        i
        for i in range(args.phase)
        if i not in REQUIRED_BEFORE.get(args.phase, ())
        and not gate["done"][i]
        and i >= current
    ]
    if soft and not args.force:
        names = ", ".join(tasks_mod.phase_name(i) for i in soft)
        print(
            ui.colorize(
                f"⚠ skipping ahead past {names} without artifacts — if user-agreed, note the waiver in STATUS.md (§0 rule 11)",
                ui.YELLOW,
            ),
            file=sys.stderr,
        )
    if getattr(args, "json", False):
        ui.json_out(
            {
                "phase": args.phase,
                "phase_name": tasks_mod.phase_name(args.phase),
                "exit_gate": exit_gate(args.phase),
                "forced": args.force,
                "gate": gate,
            }
        )
        return 0
    print(ui.colorize(f"✓ phase → {tasks_mod.phase_name(args.phase)}", ui.GREEN))
    print(f"  exit gate: {exit_gate(args.phase)}")
    return 0


@with_root
def cmd_describe(args, root: Path):
    from . import tasks as task_mod

    info = {
        "version": __version__,
        "root": str(root),
        "layout": {
            ".rh/env.json": "the config (phase 0) — read with `rh env show`, written with `rh env set` (§2)",
            ".rh/ENVIRONMENT.md": "Orchestrator-written environment notes (§3 phase 2)",
            ".rh/CHECKLIST.md": "generated orchestrator to-do list (written by rh init)",
            ".rh/logs/": "SKILL.md §7 event logs",
            ".rh/notes/": "rh add note files (heading-structured)",
            ".rh/tasks.json": "machine-readable board (idle|working|complete)",
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
        "artifacts": [
            {
                "file": n,
                "phase": artifacts_mod.ARTIFACTS[n]["phase"],
                "owner": artifacts_mod.ARTIFACTS[n]["owner"],
                "purpose": artifacts_mod.ARTIFACTS[n]["purpose"],
            }
            for n in artifacts_mod.names()
        ],
        "info": {
            "command": "rh info <FILE.md>",
            "note": "one clean description per artifact (owner, phase, sections, template, "
            "rules) — read it before writing the file",
        },
        "spawn": {
            "command": 'rh spawn <role> "<instructions>" [--inline] [--dry-run]',
            "roles": agents_mod.list_roles(root),
            "launch_template": "agents.commands.<role> (falls back to agents.commands.default)",
            "window_template": "agents.spawn — how a parallel agent is opened; blank = "
            "detached process with a log in .rh/logs/",
            "placeholders": list(spawn_mod.PLACEHOLDERS),
            "spawn_placeholders": list(spawn_mod.SPAWN_PLACEHOLDERS),
            "note": "rh never hardcodes a CLI flag: the commands live in .rh/env.json",
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
    print(f"\n{ui.colorize('Spawning (commands come from .rh/env.json):', ui.BOLD)}")
    print(
        "  rh resume / rh -r       orchestrator here, model+thinking from "
        "agents.roles.orchestrator"
    )
    print(f'  rh spawn <role> "..."   {", ".join(info["spawn"]["roles"])}')
    print(
        f"  placeholders: {', '.join('{' + p + '}' for p in info['spawn']['placeholders'])}"
        f" (+ {{command}} in agents.spawn)"
    )
    print(f"\n{ui.colorize('Agent budget:', ui.BOLD)}")
    for k, v in info["agent_budget"].items():
        print(f"  count={k} → {v}")
    return 0


@with_root
def cmd_resume(args, root: Path):
    """Run the Orchestrator in THIS terminal, using the command in .rh/env.json."""
    # Cheap path check first: an agent must never be opened against the wrong project.
    if not paths.rh_dir(root).exists():
        print(
            ui.colorize(
                f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED
            ),
            file=sys.stderr,
        )
        return 1
    env = config.load_env(root)
    gate = config.phase_gate(root, env)
    if not gate["done"][0]:
        print(
            ui.colorize(
                f"✗ phase 0 CONFIG unfinished — {paths.env_json(root)}:", ui.RED
            ),
            file=sys.stderr,
        )
        for problem in gate["problems"]:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "  fix with `rh env set KEY=VALUE ...` (see `rh env list`), then confirm the config",
            file=sys.stderr,
        )
        return 1
    dry = getattr(args, "dry_run", False)
    store = tasks_mod.TaskStore(root)
    # The role file must exist before {agent_file} points at it (init writes it;
    # older projects get the scaffold here). --dry-run writes nothing.
    if not dry:
        agents_mod.write_one(root, "orchestrator")
    extra = getattr(args, "prompt", None) or ""
    if getattr(args, "prompt_file", None):
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                ui.colorize(f"✗ cannot read {args.prompt_file}: {exc}", ui.RED),
                file=sys.stderr,
            )
            return 1
        extra = f"{extra}\n{text}".strip() if extra else text
    # When the launch template wires the role file into the harness system
    # prompt, the first message stays a pure skill-read; otherwise the role file
    # is prepended to it so the Orchestrator knows its job from the get go.
    template, _source = spawn_mod.find_template(env, "orchestrator")
    include_role_file = "{agent_file" not in template
    prompt = resume_mod.build_prompt(
        root, env, gate, store, extra=extra, include_role_file=include_role_file
    )
    prompt_file = paths.rh_dir(root) / "resume-prompt.md"
    if not dry:  # --dry-run writes nothing, not even the prompt file
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
    name = env.get("project", {}).get("name") or "untitled"

    # The launch command (model + thinking level included) is written in env.json
    # as agents.commands.orchestrator. Only when no command template exists at all do
    # we fall back to picking a bare binary — and then we persist it.
    plan = spawn_mod.launch_plan(root, env, "orchestrator", prompt, prompt_file)
    if plan["argv"] is None and not dry:
        agent_cli, cli_changed = resume_mod.resolve_agent_cli(
            getattr(args, "cli", None), env, interactive=resume_mod.is_interactive()
        )
        if not agent_cli:
            if plan.get("error"):
                print(ui.colorize(f"✗ {plan['error']}", ui.RED), file=sys.stderr)
            print(
                ui.colorize("✗ no agent CLI found — nothing to spawn", ui.RED),
                file=sys.stderr,
            )
            print(
                ui.colorize(
                    "  add the launch command: rh env set "
                    "agents.commands.orchestrator='pi --model {model} --thinking {thinking}'",
                    ui.DIM,
                ),
                file=sys.stderr,
            )
            return 1
        if cli_changed:
            env.setdefault("agents", {})["cli"] = agent_cli
            config.save_env(root, env)
            print(
                ui.colorize(
                    f"✓ saved to {paths.env_json(root)}: agents.cli={agent_cli}",
                    ui.GREEN,
                )
            )
        plan = spawn_mod.launch_plan(root, env, "orchestrator", prompt, prompt_file)
    if plan["argv"] is None:
        if plan.get("error"):
            print(ui.colorize(f"✗ {plan['error']}", ui.RED), file=sys.stderr)
        for note in plan["notes"]:
            print(ui.colorize(f"⚠ {note}", ui.YELLOW), file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        ui.json_out(
            {
                "root": str(root),
                "role": "orchestrator",
                "argv": plan["argv"],
                "command": shlex.join(plan["argv"]),
                "source": plan["source"],
                "prompt_file": str(prompt_file),
                "prompt": prompt,
                "model": plan["model"],
                "provider": plan["provider"],
                "thinking": plan["thinking"],
                "skills": plan["skills"],
                "notes": plan["notes"],
                "error": plan.get("error", ""),
                "gate": gate,
                "spawned": False,
                "inline": True,
            }
        )
        return 0
    model = (
        f"{plan['provider']}/{plan['model']}"
        if plan["provider"] and plan["model"]
        else plan["model"]
    ) or "env.json default"
    if plan["thinking"]:
        model += f" · thinking {plan['thinking']}"
    print(ui.banner(f"rh resume — {name}", f"project: {root} · this terminal"))
    print(
        f"{ui.colorize('model:', ui.DIM)} {model}"
        f"  {ui.colorize('skills:', ui.DIM)} {', '.join(plan['skills']) or '—'}"
    )
    print(f"{ui.colorize('command:', ui.DIM)} {shlex.join(plan['argv'])}")
    for note in plan["notes"]:
        print(ui.colorize(f"⚠ {note}", ui.YELLOW))
    if dry:
        print()
        print(prompt)
        return 0
    # No prompt echo here: the harness opens with the skill read as its first message.
    print(
        ui.colorize(
            f"  opening the harness (first message: load the skill · prompt: {prompt_file})",
            ui.DIM,
        )
    )
    _started, detail = spawn_mod.exec_argv(root, plan["argv"])
    # exec replaces this process; reaching here means it could not start
    print(ui.colorize(f"✗ {detail}", ui.RED), file=sys.stderr)
    print(ui.colorize(f"  prompt ready at {prompt_file}", ui.DIM), file=sys.stderr)
    return 1


@with_root
def cmd_doctor(args, root: Path):
    """`rh doctor` — verify what env.json names actually exists on this machine."""
    data = doctor_mod.check(root)
    if getattr(args, "json", False):
        ui.json_out(data)
        return 0 if data["ok"] else 1
    print(ui.banner("Doctor", f"root: {root}"))
    for item in data["checks"]:
        mark = (
            ui.colorize("[✓]", ui.GREEN) if item["ok"] else ui.colorize("[✗]", ui.RED)
        )
        print(f"  {mark} {item['id']:28} {item['detail']}")
    print()
    print(
        ui.colorize(
            "✓ all named tools present"
            if data["ok"]
            else f"✗ {data['failures']} check(s) failed — fix .rh/env.json or create the named file/binary",
            ui.GREEN if data["ok"] else ui.YELLOW,
        )
    )
    return 0 if data["ok"] else 1


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
            print(
                ui.colorize("✓ all role files already exist in .rh/agents/", ui.GREEN)
            )
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
            print(
                ui.colorize(
                    f"⏳ no .rh/agents/{role}.md yet — `rh agents {role} --write` scaffolds it; the Orchestrator fills it in with the user.",
                    ui.YELLOW,
                )
            )
            return 0
        print(content)
        return 0
    # list
    roles = agents_mod.list_roles(root)
    if getattr(args, "json", False):
        ui.json_out([agents_mod.role_file_info(root, r) for r in roles])
        return 0
    print(
        ui.banner(
            "Agents",
            ".rh/agents/<role>.md — tailored role files (no role info is hardcoded in rh)",
        )
    )
    for r in roles:
        info = agents_mod.role_file_info(root, r)
        mark = "✓" if info["exists"] else "·"
        print(
            f"  {mark} {ui.colorize(r, ui.CYAN):12} {info['file']} ({'exists' if info['exists'] else 'missing — run `rh agents --write`'})"
        )
    print(
        ui.colorize(
            "  Edit the .md files with user approval; env.json holds agents.commands.<role> per role.",
            ui.DIM,
        )
    )
    return 0


def _spawn_terminal(args, root: Path):
    """`rh spawn terminal <command>` — open a plain shell terminal in a new pane."""
    # Still allow --dry-run outside a project for shell/split detection demo
    if not paths.rh_dir(root).exists() and not getattr(args, "dry_run", False):
        print(
            ui.colorize(
                f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED
            ),
            file=sys.stderr,
        )
        return 1
    env = (
        config.load_env(root)
        if paths.rh_dir(root).exists()
        else config.deep_merge(config.DEFAULT_ENV, {})
    )
    command = " ".join(getattr(args, "text", None) or []).strip()
    if not command:
        print(
            "✗ which command? e.g. rh spawn terminal 'pytest -q' or rh spawn terminal -- python3 -m http.server",
            file=sys.stderr,
        )
        return 2
    plan = spawn_mod.terminal_plan(
        root, env, command, split=getattr(args, "split", None)
    )
    preview = spawn_mod.terminal_preview(root, env, plan)
    if getattr(args, "json", False):
        ui.json_out(
            {
                "root": str(root),
                "terminal": True,
                "argv": plan["argv"],
                "command": preview["command"],
                "mode": preview["mode"],
                "log": preview["log"],
                "shell": plan["shell"],
                "split": plan["split"],
                "notes": plan["notes"],
                "spawned": False,
            }
        )
        return 0
    print(ui.banner("rh spawn terminal", f"project: {root}"))
    print(
        f"{ui.colorize('shell:', ui.DIM)} {plan['shell']}"
        f"  {ui.colorize('split:', ui.DIM)} {plan['split'] or '(not set — ask the user)'}"
        f"  {ui.colorize('mode:', ui.DIM)} {preview['mode']}"
    )
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
        print(
            ui.colorize(
                (
                    "✓ opened terminal pane via agents.spawn"
                    if ok
                    else "⚠ agents.spawn failed"
                )
                + f" ({result['command']})",
                ui.GREEN if ok else ui.YELLOW,
            )
        )
    else:
        print(
            ui.colorize(
                f"✓ started terminal pid {result.get('pid')} → {result.get('log', '')}",
                ui.GREEN,
            )
        )
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
            except json.JSONDecodeError:
                continue  # a torn line at the tail of an append-only file
    if getattr(args, "json", False):
        ui.json_out(rows)
        return 0
    print(ui.banner("Agent status", f"root: {root}"))
    if not rows:
        print(
            ui.colorize(
                "No spawns recorded yet — `rh spawn <role>` writes .rh/logs/spawns.jsonl from here on.",
                ui.DIM,
            )
        )
        print(
            ui.colorize(
                "  pane spawns record no pid, so they never count against agents.count; "
                "the panes are visible to the user instead.",
                ui.DIM,
            )
        )
        return 0
    for r in rows:
        alive = ""
        pid = r.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                alive = "alive"
            except OSError:
                alive = "dead"
        print(
            f"  {r.get('role', '?'):12} pid={pid} ({alive}) model={r.get('model') or '—'} mode={r.get('mode')} ts={r.get('ts', '')}"
        )
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
    files = (
        sorted(logs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        if logs_dir.is_dir()
        else []
    )
    if getattr(args, "json", False):
        out = []
        for f in files[-n:]:
            out.append({"file": str(f), "text": f.read_text(encoding="utf-8")[:4000]})
        ui.json_out(out)
        return 0
    if not files:
        print(
            ui.colorize(
                "No event logs yet in .rh/logs/ (use `rh add log` per SKILL.md §7).",
                ui.DIM,
            )
        )
        return 0
    for f in files[-n:]:
        print(ui.colorize(f"=== {f.name} ===", ui.BOLD))
        print(f.read_text(encoding="utf-8")[:2000])
        print()
    return 0


@with_root
def cmd_handoff(args, root: Path):
    """`rh handoff [--clear]` — show (or empty) the next-session handoff.

    The Orchestrator writes `.rh/HANDOFF.md` at the end of a session: what the
    next session must do first. rh never generates it from STATUS/PLAN — a
    handoff is a decision, not a dump. `--clear` empties it after it was read.
    """
    dest = paths.rh_dir(root) / "HANDOFF.md"
    if not paths.rh_dir(root).exists():
        print(
            ui.colorize(
                f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED
            ),
            file=sys.stderr,
        )
        return 1
    if getattr(args, "clear", False) and not getattr(args, "dry_run", False):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("", encoding="utf-8")
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError:
        text = ""
    pending = bool(text.strip())
    if getattr(args, "json", False):
        ui.json_out(
            {
                "file": str(dest),
                "pending": pending,
                "text": text if pending else "",
                "cleared": bool(getattr(args, "clear", False)),
            }
        )
        return 0
    if getattr(args, "clear", False):
        print(ui.colorize(f"✓ cleared {dest} — read it first next time", ui.GREEN))
        return 0
    if not pending:
        print(
            ui.colorize(
                f"{dest} is empty — nothing handed to the next session.",
                ui.DIM,
            )
        )
        return 0
    print(ui.colorize(f"=== {dest} (next session) ===", ui.BOLD))
    print(text.rstrip())
    return 0


@with_root
def cmd_spawn(args, root: Path):
    """`rh spawn <role|terminal> [instructions]` — open a role agent or a shell terminal."""
    if (args.agent or "").strip().lower() == "terminal":
        return _spawn_terminal(args, root)
    if not paths.rh_dir(root).exists():
        print(
            ui.colorize(
                f"✗ not initialized: {root} has no .rh/ — run `rh init` first", ui.RED
            ),
            file=sys.stderr,
        )
        return 1
    env = config.load_env(root)
    role = (args.agent or "").strip().lower()
    if not role:
        known_roles = agents_mod.list_roles(root)
        print("✗ which role? " + " | ".join(known_roles), file=sys.stderr)
        return 2
    commands = (env.get("agents") or {}).get("commands") or {}
    known = set(agents_mod.list_roles(root)) | (
        {str(k).lower() for k in commands} if isinstance(commands, dict) else set()
    )
    if role not in known:
        print(
            ui.colorize(
                f"✗ unknown role {role!r} — roles come from .rh/agents/<role>.md and agents.commands.<role>",
                ui.RED,
            ),
            file=sys.stderr,
        )
        print(
            ui.colorize(
                f"  define your own: rh env set agents.commands.{role}='pi --model {{model}} --append-system-prompt {{agent_file}} {{prompt}}' "
                f"and write .rh/agents/{role}.md (rh agents {role} --write scaffolds it)",
                ui.DIM,
            ),
            file=sys.stderr,
        )
        return 2
    extra = " ".join(getattr(args, "text", None) or []).strip()
    if getattr(args, "prompt", None):
        extra = f"{extra}\n{args.prompt}".strip() if extra else args.prompt
    if getattr(args, "prompt_file", None):
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                ui.colorize(f"✗ cannot read {args.prompt_file}: {exc}", ui.RED),
                file=sys.stderr,
            )
            return 1
        extra = f"{extra}\n{text}".strip() if extra else text
    name = env.get("project", {}).get("name") or "untitled"
    store = tasks_mod.TaskStore(root)
    prompt = spawn_mod.build_role_prompt(root, env, role, store, extra=extra)
    prompt_file = (
        paths.rh_dir(root) / "tmp" / f"spawn-{add_mod.slugify(role)}-prompt.md"
    )
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
        print(
            ui.colorize(
                f"✗ agents.count={budget} reached ({running} running) — close one (rule 13) or pass --force",
                ui.RED,
            ),
            file=sys.stderr,
        )
        return 1
    preview = spawn_mod.spawn_preview(root, env, role, plan)
    notes = plan["notes"] + preview["notes"]
    if getattr(args, "json", False):
        ui.json_out(
            {
                "root": str(root),
                "role": role,
                "argv": plan["argv"],
                "command": preview["command"],
                "mode": preview["mode"],
                "log": preview["log"],
                "source": plan["source"],
                "prompt_file": str(prompt_file),
                "prompt": prompt,
                "model": plan["model"],
                "provider": plan["provider"],
                "thinking": plan["thinking"],
                "skills": plan["skills"],
                "agents_count": (env.get("agents") or {}).get("count"),
                "notes": notes,
                "error": plan.get("error", ""),
                "spawned": False,
            }
        )
        return 0
    model = (
        f"{plan['provider']}/{plan['model']}"
        if plan["provider"] and plan["model"]
        else plan["model"]
    ) or "env.json default"
    if plan["thinking"]:
        model += f" · thinking {plan['thinking']}"
    print(ui.banner(f"rh spawn — {role}", f"project: {root} · {name}"))
    print(
        f"{ui.colorize('model:', ui.DIM)} {model}"
        f"  {ui.colorize('skills:', ui.DIM)} {', '.join(plan['skills']) or '—'}"
        f"  {ui.colorize('agents.count:', ui.DIM)} {(env.get('agents') or {}).get('count')}"
    )
    print(
        f"{ui.colorize('mode:', ui.DIM)} {preview['mode']}"
        f"  {ui.colorize('via', ui.DIM)} {plan['source'] or 'agents.cli'}"
    )
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
        print(
            ui.colorize(
                (
                    "✓ opened pane via agents.spawn"
                    if ok
                    else "⚠ the agents.spawn command failed"
                )
                + f" ({result['command']})",
                ui.GREEN if ok else ui.YELLOW,
            )
        )
    else:
        print(
            ui.colorize(
                f"✓ started pid {result.get('pid')} → {result['log']}", ui.GREEN
            )
        )
    print(
        ui.colorize(
            "  record the spawn in STATUS.md; close it when the job is done (rules 12–13).",
            ui.DIM,
        )
    )
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
            ui.json_out(
                [
                    {
                        "file": n,
                        "phase": artifacts_mod.ARTIFACTS[n]["phase"],
                        "owner": artifacts_mod.ARTIFACTS[n]["owner"],
                        "purpose": artifacts_mod.ARTIFACTS[n]["purpose"],
                    }
                    for n in names
                ]
            )
            return 0
        print(ui.banner("Artifacts", "rh info <FILE.md> for the full description"))
        rows = [
            [
                n,
                artifacts_mod.ARTIFACTS[n]["phase"],
                artifacts_mod.ARTIFACTS[n]["owner"],
                _short(artifacts_mod.ARTIFACTS[n]["purpose"]),
            ]
            for n in names
        ]
        print(ui.table(["file", "phase", "owner", "what it is"], rows))
        return 0
    key = artifacts_mod.resolve(args.name)
    if key is None:
        print(
            ui.colorize(
                f"✗ unknown artifact {args.name!r} — known: {', '.join(names)}", ui.RED
            ),
            file=sys.stderr,
        )
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
    print(
        f"{ui.colorize('location:', ui.DIM)} {spec['location']}"
        f"  {ui.colorize('now:', ui.DIM)} {path} ({'exists' if exists else 'not created yet'})"
    )
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

    dest = (
        Path(args.dest).expanduser()
        if args.dest
        else Path.home() / ".agents" / "skills" / "research-helper"
    )
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
    default_dest = Path.home() / ".agents" / "skills" / "research-helper"
    if dest != default_dest:
        print(
            ui.colorize(
                f"  note: pi discovers skills under {default_dest.parent}/", ui.DIM
            )
        )
    return 0


class HelpfulParser(argparse.ArgumentParser):
    """A parser that answers bad usage with the full `--help` text, nothing else."""

    def error(self, message):
        # deliberately no "error: ..." line: bad usage just shows what --help shows
        self.print_help()
        self.exit(2)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=argparse.SUPPRESS,
        help="project root (default: walk up for .rh/, else cwd)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="machine-readable JSON output",
    )
    p = HelpfulParser(
        prog="rh",
        description="research-helper CLI — orchestrate a research project end to end",
        parents=[common],
    )
    p.add_argument("--version", action="version", version=f"rh {__version__}")
    p.add_argument(
        "-r",
        "--resume",
        action="store_true",
        help="shortcut for `rh resume` (spawn harness + go-forward prompt)",
    )
    sub = p.add_subparsers(dest="cmd", required=False)

    s = sub.add_parser(
        "init",
        help="create .rh/ layout (non-destructive; --force/--clean archive first, --dry-run previews)",
        parents=[common],
    )
    s.add_argument(
        "--clean",
        action="store_true",
        help="archive .rh/ (event logs, notes, env.json, tasks.json) to .rh/.bak/<timestamp>/ then recreate it",
    )
    s.add_argument(
        "--force",
        action="store_true",
        help="archive a copy of env.json/tasks.json to .rh/.bak/<timestamp>/ before init writes",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="preview what would be written without writing",
    )
    s.add_argument(
        "--non-interactive",
        action="store_true",
        help="skip the questionnaire (agents/CI)",
    )
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("env", help="environment config", parents=[common])
    esub = s.add_subparsers(dest="e", required=True)
    esub.add_parser("show", parents=[common]).set_defaults(func=cmd_env_show)
    esub.add_parser("list", parents=[common]).set_defaults(func=cmd_env_list)
    sp = esub.add_parser("set", parents=[common])
    sp.add_argument("pairs", nargs="*", metavar="KEY=VALUE")
    sp.set_defaults(func=cmd_env_set)

    s = sub.add_parser("add", help="append under heading/DOI", parents=[common])
    s.add_argument("target", choices=list(add_mod.ADD_TARGETS))
    s.add_argument("heading", help="heading or DOI")
    s.add_argument("-m", "--message", default=None)
    s.add_argument("--file", default=None, help="note filename (md)")
    s.add_argument("--role", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--id", default=None)
    s.add_argument(
        "--phase", type=int, default=None, help="default: current project phase"
    )
    s.add_argument("--owner", default="researcher")
    s.add_argument("--state", default="idle", choices=list(tasks_mod.TASK_STATES))
    s.add_argument("--deliverable", default="")
    s.add_argument("--verify", default="")
    s.add_argument(
        "--depends-on",
        dest="depends_on",
        default="",
        help="comma-separated task ids this depends on",
    )
    s.add_argument("--kind", default="build", choices=["build", "spike"])
    s.add_argument(
        "--subtask",
        action="append",
        default=[],
        metavar="TEXT",
        help="repeatable subtask line",
    )
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("search", help="local search (rg or python)", parents=[common])
    s.add_argument("query")
    s.add_argument("--max", type=int, default=40)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser(
        "tasks",
        help="task board + progress; `rh tasks set <id> <state>`",
        parents=[common],
    )
    s.add_argument("--phase", type=int, default=None)
    s.add_argument("--state", default=None, choices=list(tasks_mod.TASK_STATES))
    tsub = s.add_subparsers(dest="t", required=False)
    ts = tsub.add_parser("set", parents=[common])
    ts.add_argument("id")
    ts.add_argument("state", choices=list(tasks_mod.TASK_STATES))
    ts.set_defaults(func=cmd_task_set)
    s.set_defaults(func=cmd_tasks)

    s = sub.add_parser("status", help="project status", parents=[common])
    s.set_defaults(func=cmd_status)

    s = sub.add_parser(
        "workflow",
        help="display the agent-authored .rh/workflow.mmd (ascii in-terminal)",
        parents=[common],
    )
    s.add_argument(
        "--example",
        action="store_true",
        help="print a starter mermaid source (from the task board) the agent can save as .rh/workflow.mmd",
    )
    s.add_argument(
        "--phases",
        action="store_true",
        help="with --example: use the constant SKILL.md phase pipeline",
    )
    s.add_argument("--tools", action="store_true", help="list installed renderers")
    s.add_argument("--png", action="store_true", help="render png from workflow.mmd")
    s.add_argument("--svg", action="store_true", help="render svg from workflow.mmd")
    s.add_argument("--no-render", action="store_true", help="skip ascii display")
    s.set_defaults(func=cmd_workflow)

    s = sub.add_parser(
        "phase",
        help="show the current phase + exit gate, or set it: rh phase [0-9] (gated)",
    )
    s.add_argument(
        "set",
        nargs="?",
        default=None,
        choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
    )
    s.add_argument(
        "--force",
        action="store_true",
        help="jump despite unmet gates (waiver goes in STATUS.md)",
    )
    s.set_defaults(func=cmd_phase_set)

    s = sub.add_parser("describe", help="AI map of the tool", parents=[common])
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser(
        "resume",
        help="run the orchestrator here (model + thinking from .rh/env.json)",
        parents=[common],
    )
    s.add_argument(
        "--cli",
        dest="cli",
        default=None,
        help="fallback agent binary when env.json has no agents.commands (default: config agents.cli, else ask)",
    )
    s.add_argument(
        "--prompt",
        default=None,
        help="extra user instructions appended to the go-forward prompt",
    )
    s.add_argument(
        "--prompt-file",
        dest="prompt_file",
        default=None,
        help="read the extra instructions from a markdown file (examples/prompts/orchestrator.md)",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="show the resolved command + prompt without spawning",
    )
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser(
        "spawn",
        help="open a role agent with the env.json command, or a shell terminal "
        "(`rh spawn terminal <cmd>`)",
        parents=[common],
    )
    s.add_argument(
        "agent",
        help="role (a .rh/agents/<role>.md file and/or agents.commands.<role> key), "
        "e.g. researcher; 'terminal' means `rh spawn terminal <cmd>` for a shell pane",
    )
    s.add_argument(
        "text",
        nargs="*",
        help="instructions for that agent (joined into one prompt); "
        "for `spawn terminal` it is the command to run",
    )
    s.add_argument(
        "--prompt", default=None, help="instructions instead of the positional form"
    )
    s.add_argument(
        "--prompt-file",
        dest="prompt_file",
        default=None,
        help="read the instructions from a markdown file (examples/prompts/*.md)",
    )
    s.add_argument(
        "--inline",
        action="store_true",
        help="run the agent in this terminal instead of a new pane/process",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the command + role prompt without starting anything",
    )
    s.add_argument(
        "--split",
        default=None,
        choices=["vertical", "horizontal", "window"],
        help="pane layout override for this spawn (default: agents.split)",
    )
    s.add_argument(
        "--force",
        action="store_true",
        help="ignore agents.count budget (waiver → STATUS.md)",
    )
    s.set_defaults(func=cmd_spawn)

    s = sub.add_parser(
        "doctor",
        help="verify the binaries, shells, templates and role files env.json names",
        parents=[common],
    )
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser(
        "agent", help="agent helpers: `rh agent status`", parents=[common]
    )
    asub = s.add_subparsers(dest="a", required=True)
    ast = asub.add_parser("status", parents=[common])
    ast.set_defaults(func=cmd_agent_status)

    s = sub.add_parser(
        "gate", help="`rh gate check` — machine-readable gate report", parents=[common]
    )
    gsub = s.add_subparsers(dest="g", required=True)
    gc = gsub.add_parser("check", parents=[common])
    gc.set_defaults(func=cmd_gate_check)

    s = sub.add_parser(
        "log", help="`rh log tail [N]` — newest §7 event logs", parents=[common]
    )
    lsub = s.add_subparsers(dest="l", required=True)
    lt = lsub.add_parser("tail", parents=[common])
    lt.add_argument("n", nargs="?", default=None, help="how many logs (default 20)")
    lt.set_defaults(func=cmd_log_tail)

    s = sub.add_parser(
        "handoff",
        help="show (or `--clear`) the next-session handoff written by the Orchestrator (rule 14)",
        parents=[common],
    )
    s.add_argument(
        "--clear", action="store_true", help="empty .rh/HANDOFF.md after reading it"
    )
    s.set_defaults(func=cmd_handoff)

    s = sub.add_parser(
        "agents",
        help="list / show / write the per-role agent files (.rh/agents/<role>.md)",
        parents=[common],
    )
    s.add_argument(
        "role", nargs="?", default=None, help="one role to show (e.g. researcher)"
    )
    s.add_argument(
        "--write",
        action="store_true",
        help="write default role files (all roles, or just ROLE when given)",
    )
    s.set_defaults(func=cmd_agents)

    s = sub.add_parser(
        "info",
        help="describe an artifact: what it is for, owner, sections, template",
        parents=[common],
    )
    s.add_argument(
        "name",
        nargs="?",
        default=None,
        help="file name, e.g. PLAN.md | status | .rh/GAPS.md",
    )
    s.add_argument(
        "--template", action="store_true", help="print only the template block"
    )
    s.set_defaults(func=cmd_info)

    s = sub.add_parser(
        "skill", help="install the bundled agent skill", parents=[common]
    )
    ssub = s.add_subparsers(dest="sk", required=True)
    si = ssub.add_parser("install", parents=[common])
    si.add_argument(
        "--dest",
        default=None,
        help="the skill directory itself, e.g. ~/.agents/skills/my-name "
        "(default: ~/.agents/skills/research-helper)",
    )
    si.add_argument(
        "--force", action="store_true", help="overwrite an existing skill dir"
    )
    si.set_defaults(func=cmd_skill_install)

    return p


KNOWN_CMDS = {
    "init",
    "env",
    "add",
    "search",
    "tasks",
    "status",
    "workflow",
    "phase",
    "plan",
    "describe",
    "resume",
    "spawn",
    "info",
    "skill",
    "agents",
    "doctor",
    "agent",
    "gate",
    "log",
    "handoff",
}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not (set(argv) & KNOWN_CMDS) and ("-r" in argv or "--resume" in argv):
        argv = ["resume", *[a for a in argv if a not in ("-r", "--resume")]]
    try:
        args = build_parser().parse_args(argv)
    except (
        SystemExit
    ) as exc:  # --help/--version and HelpfulParser.error already printed
        return int(exc.code or 0)
    if args.cmd is None:
        build_parser().print_help()
        return 2
    # `rh phase N` → phase int
    if args.cmd == "phase":
        args.phase = int(args.set) if args.set is not None else None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
