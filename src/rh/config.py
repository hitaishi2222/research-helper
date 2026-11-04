"""Config + storage model — maps SKILL.md §2 onto .rh/.

ENV.md holds the config block (human-readable, SKILL.md truth). .rh/env.json
mirrors it for machines. Anything below the config block (the Orchestrator's
environment notes) is preserved verbatim across `rh env set`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths
from .tasks import TaskStore

DEFAULT_ENV: dict = {
    "agents": {
        "count": 1,
        "backend": "none",  # tmux | herdr | tuios | none — how the Orchestrator spawns parallel agents
        "cli": "",  # agent binary rh resume spawns (user-named)
        "skills": ["research-helper"],  # skills every spawned agent must read first
        "roles": {
            "orchestrator": {},
            "literature": {},
            "researcher": {},
            "reviewer": {},
            "critique": {},
            "writer": {},
        },
        "planners": {"models": [{}, {}], "max_rounds": 0},
    },
    "literature": {
        "ref_manager": "none",  # zot | bibtex | none
        "reading": "pdftotext",  # lit | pdftotext | images
        "paywall": "ask_user",  # ask_user | skip
        "search": "crw",  # crw | agent-browser | obscura | <binary>
    },
    "project": {"slug": "", "git": False},
    "gates": {"user_approves_plan": True, "critique_veto": True},
}

AGENT_BACKENDS = ("tmux", "herdr", "tuios", "none")
PAYWALL_POLICIES = ("ask_user", "skip")

# dotted key -> (type, choices, help) — drives `rh env set` and docs
ENV_SCHEMA: list[tuple[str, str, tuple, str]] = [
    ("agents.count", "int", (1, 2, 3, 4), "how many agents may run at once, 1..4"),
    ("agents.backend", "str", AGENT_BACKENDS, "tmux | herdr | tuios | none — how the Orchestrator spawns parallel agents (rh resume always runs inline)"),
    ("agents.cli", "str", (), "agent binary the harness spawns, e.g. opencode (rh resume)"),
    ("agents.skills", "list", (), "skills every spawned agent must read first, comma-separated"),
    ("agents.roles.orchestrator", "dict", (), "provider+model, must be the model running this session"),
    ("agents.roles.literature", "dict", (), "provider+model for the Literature role"),
    ("agents.roles.researcher", "dict", (), "provider+model for the Researcher role"),
    ("agents.roles.reviewer", "dict", (), "provider+model for the Reviewer role"),
    ("agents.roles.critique", "dict", (), "provider+model for the Critique role"),
    ("agents.roles.writer", "dict", (), "provider+model for the Writer role"),
    ("agents.planners.models.0", "dict", (), "planner 1 model (must differ from planner 2)"),
    ("agents.planners.models.1", "dict", (), "planner 2 model"),
    ("agents.planners.max_rounds", "int", (0, 1, 2, 3, 5), "0 = cap at 3 rounds, then escalate"),
    ("literature.ref_manager", "str", (), "reference manager the user names (e.g. zot, bibtex, none)"),
    ("literature.reading", "str", (), "reader the user names (e.g. lit, pdftotext, images)"),
    ("literature.paywall", "str", PAYWALL_POLICIES, "ask_user | skip (proceed without paper)"),
    ("literature.search", "str", (), "search tool the user names (e.g. crw, agent-browser, any binary)"),
    ("project.slug", "str", (), "short kebab-case name"),
    ("project.git", "bool", (True, False), "true only if the project is already a repo"),
    ("gates.user_approves_plan", "bool", (True, False), "user approves PLAN.md before implementation"),
    ("gates.critique_veto", "bool", (True, False), "Critique can veto the critique gate"),
]


class ConfigError(RuntimeError):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_nested(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def set_nested(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            nxt = cur.get(part)
            if not isinstance(nxt, (dict, list)):
                nxt = []
                cur[part] = nxt
            cur = nxt
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def coerce_value(raw: str, kind: str):
    raw = raw.strip()
    if kind == "int":
        return int(raw)
    if kind == "list":
        if raw.startswith("["):
            v = json.loads(raw)
            if not isinstance(v, list):
                raise ValueError(f"expected JSON list, got {raw!r}")
            return [str(x).strip() for x in v if str(x).strip()]
        return [x.strip() for x in raw.split(",") if x.strip()]
    if kind == "bool":
        if raw.lower() in ("true", "yes", "1", "on"):
            return True
        if raw.lower() in ("false", "no", "0", "off"):
            return False
        raise ValueError(f"expected true/false, got {raw!r}")
    if kind == "dict":
        try:
            v = json.loads(raw)
        except json.JSONDecodeError:
            # allow "provider/model" shorthand
            if "/" in raw:
                provider, model = raw.split("/", 1)
                return {"provider": provider, "model": model}
            raise ValueError(f"expected JSON object or provider/model, got {raw!r}")
        if not isinstance(v, dict):
            raise ValueError(f"expected JSON object, got {raw!r}")
        return v
    return raw


def validate(env: dict) -> list[str]:
    """Return list of problems (empty = valid)."""
    problems = []
    try:
        count = env["agents"]["count"]
        if count not in (1, 2, 3, 4):
            problems.append(f"agents.count must be 1..4, got {count!r}")
    except KeyError:
        problems.append("agents.count is missing")
    backend = env.get("agents", {}).get("backend")
    if backend not in AGENT_BACKENDS:
        problems.append(f"agents.backend must be one of {AGENT_BACKENDS}, got {backend!r}")
    planners = env.get("agents", {}).get("planners", {}).get("models", [])
    if len(planners) >= 2 and planners[0] and planners[1] and planners[0] == planners[1]:
        problems.append("agents.planners.models must be two different models")
    slug = env.get("project", {}).get("slug", "")
    if slug and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        problems.append(f"project.slug must be kebab-case, got {slug!r}")
    lit = env.get("literature", {})
    # tool names are whatever the user names — never restricted to a known list
    for key in ("ref_manager", "reading", "search"):
        val = lit.get(key)
        if not isinstance(val, str) or not val.strip():
            problems.append(f"literature.{key} must be a non-empty tool/method name, got {val!r}")
    paywall = lit.get("paywall")
    if paywall not in PAYWALL_POLICIES:
        problems.append(f"literature.paywall must be one of {PAYWALL_POLICIES}, got {paywall!r}")
    orch = env.get("agents", {}).get("roles", {}).get("orchestrator", {})
    if orch:
        if not isinstance(orch, dict) or not orch:
            problems.append("agents.roles.orchestrator must be a model object")
    skills = env.get("agents", {}).get("skills")
    if not isinstance(skills, list) or not all(isinstance(s, str) and s.strip() for s in skills):
        problems.append("agents.skills must be a list of skill names, e.g. [\"research-helper\"]")
    return problems


# --- ENV.md rendering/parsing -------------------------------------------------

ENV_FENCE = re.compile(r"```jsonc?\n(.*?)```", re.DOTALL)


def render_env_md(env: dict, tail: str = "") -> str:
    """Render ENV.md: config block (json) + whatever the Orchestrator wrote below it."""
    block = json.dumps(env, indent=2, sort_keys=True)
    lines = [
        "# ENV — research-helper config",
        "",
        "```json",
        block,
        "```",
    ]
    if tail.strip():
        lines += ["", tail.strip()]
    return "\n".join(lines) + "\n"


def _block_and_tail(path: Path) -> tuple[dict | None, str]:
    """Return (config block, text below it) from ENV.md."""
    if not path.exists():
        return None, ""
    text = path.read_text(encoding="utf-8")
    m = ENV_FENCE.search(text)
    if not m:
        return None, ""
    try:
        env = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, ""
    return env, text[m.end():].strip("\n")


def parse_env_md(path: Path) -> dict | None:
    """Extract the json config block from ENV.md. Returns None if absent."""
    return _block_and_tail(path)[0]


def load_tail(root: Path) -> str:
    """The Orchestrator's environment notes below the config block."""
    return _block_and_tail(ensure_env_location(root))[1]


def ensure_env_location(root: Path) -> Path:
    """ENV.md lives in .rh/. Migrate a ROOT ENV.md (or a symlink to it) once."""
    target = paths.env_md(root)
    if target.is_symlink():
        content = target.read_text(encoding="utf-8")
        target.unlink()
        target.write_text(content, encoding="utf-8")
    elif not target.exists():
        legacy = root / "ENV.md"
        if legacy.exists() and paths.rh_dir(root).exists():
            legacy.replace(target)
    return target


def load_env(root: Path) -> dict:
    """Load effective config: .rh/ENV.md block (truth) or .rh/env.json mirror or defaults."""
    env_md = ensure_env_location(root)
    if env_md.exists():
        parsed = parse_env_md(env_md)
        if parsed is not None:
            return deep_merge(DEFAULT_ENV, parsed)
    mirror = paths.env_json(root)
    if mirror.exists():
        try:
            return deep_merge(DEFAULT_ENV, json.loads(mirror.read_text()))
        except json.JSONDecodeError:
            pass
    return deep_merge(DEFAULT_ENV, {})


def save_env(root: Path, env: dict) -> None:
    """Write .rh/ENV.md config block (preserving the notes below it) + .rh/env.json mirror."""
    env_path = ensure_env_location(root)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    _, tail = _block_and_tail(env_path)
    env_path.write_text(render_env_md(env, tail), encoding="utf-8")
    mirror = paths.env_json(root)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def config_complete(env: dict) -> bool:
    """Phase-0 exit gate (SKILL.md §3): the block parses and no validate() problems.

    Never use this alone — defaults pass validation with no ENV.md on disk.
    Gate on config_written() for "did the user actually configure the project".
    """
    return not validate(env)


def config_written(root: Path) -> bool:
    """True only if .rh/ENV.md exists and holds a parseable config block.

    This is the phase-0 exit gate: the block was written (rh env set / init),
    so it is user-confirmed config, not silent defaults.
    """
    return parse_env_md(paths.env_md(root)) is not None


def phase_gate(root: Path, env: dict | None = None) -> dict:
    """Hard-gate check per SKILL.md §3 — warns when the pipeline was skipped.

    Returns {phase, ok, problems[], done[]}. done[i] is True only when phase i
    is *verified* by an artifact (or the phase after it was entered). The rail
    renders ✓ from done[], never from position alone.
    """
    env = env if env is not None else load_env(root)
    problems: list[str] = []
    current = TaskStore(root).current_phase() if (paths.tasks_json(root)).exists() else 0

    written = config_written(root)
    if not written:
        problems.append(
            "phase 0 CONFIG unfinished — no ENV.md with a parseable config block "
            "(run `rh env set KEY=VALUE ...`, then have the user confirm)"
        )
    elif not config_complete(env):
        problems.append(f"phase 0 CONFIG invalid: {validate(env)}")

    done = [False] * 10
    done[0] = written and not validate(env)
    problem = paths.artifact_path(root, "PROBLEM.md")
    done[1] = problem.exists() and problem.stat().st_size > 0
    if current >= 6 and not done[1]:
        problems.append("phase 1 INTAKE artifact missing: PROBLEM.md")
    done[2] = bool(load_tail(root).strip())
    if current >= 6 and not done[2]:
        problems.append("phase 2 ENVIRONMENT artifact missing: have the Orchestrator "
                        "interview the user and write the environment section in ENV.md")
    lit = paths.artifact_path(root, "LITERATURE.md")
    gaps = paths.artifact_path(root, "GAPS.md")
    done[3] = (lit.exists() and lit.stat().st_size > 0) or (gaps.exists() and gaps.stat().st_size > 0)
    if current >= 6 and not done[3]:
        problems.append("phase 3 LITERATURE artifact missing: LITERATURE.md or GAPS.md (or user-agreed skip)")
    plan = paths.artifact_path(root, "PLAN.md")
    done[4] = plan.exists() and plan.stat().st_size > 0
    if current >= 6 and not done[4]:
        problems.append("phase 4 PLAN artifact missing: PLAN.md (two planners + user approval)")
    status = paths.artifact_path(root, "STATUS.md")
    done[5] = status.exists() and status.stat().st_size > 0
    if current >= 6 and not done[5]:
        problems.append("phase 5 STATE artifact missing: STATUS.md")
    for i in range(6, 10):
        done[i] = current > i
    # later phases may mark earlier ones done only via artifacts (already handled)
    return {"phase": current, "ok": not problems, "problems": problems, "done": done}
