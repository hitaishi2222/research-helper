"""Workflow diagram — mermaid source + CLI rendering.

Uses `mmdr` / `beautiful-mermaid` when installed; otherwise renders an
ASCII rail and tells the user how to get diagrams. Shows current phase.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import ui

FLIP = {0: "CONFIG", 1: "INTAKE", 2: "ENVIRONMENT", 3: "LITERATURE", 4: "PLAN",
        5: "STATE", 6: "IMPLEMENT", 7: "CRITIQUE", 8: "MANUSCRIPT", 9: "CLOSE"}

MERMAID_TEMPLATE = """%%{init: {'theme': 'dark', 'background': 'transparent'}}%%
flowchart LR
    C["0 CONFIG<br/>ENV.md"]:::done
    I["1 INTAKE<br/>PROBLEM.md"]:::done
    E["2 ENVIRONMENT<br/>ENV.md tools"]:::done
    L["3 LITERATURE<br/>papers/ GAPS.md"]:::done
    P["4 PLAN<br/>PLAN.md"]:::done
    S["5 STATE<br/>STATUS.md"]:::done
    M["6 IMPLEMENT<br/>src/ results/"]:::done
    K["7 CRITIQUE"]:::done
    W["8 MANUSCRIPT"]:::done
    X["9 CLOSE"]:::done
    C --> I --> E --> L --> P --> S --> M --> K --> W --> X
    K -. "blocking → replan" .-> P
    K -. "fix" .-> M
    classDef done fill:#151923,stroke:#3b82f6,color:#e5e7eb;
    classDef current fill:#1d4ed8,stroke:#93c5fd,color:#fff,stroke-width:3px;
    classDef todo fill:#0b0f17,stroke:#374151,color:#6b7280;
"""


def mermaid_for_phase(current: int, done: list[bool] | None = None, direction: str = "LR") -> str:
    lines = []
    for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
        if i < current:
            cls = "done"
        elif i == current:
            cls = "current"
        else:
            cls = "todo"
        lines.append(cls)
    # build graph: first mark all todo, then override
    src = MERMAID_TEMPLATE
    if direction != "LR":
        src = src.replace("flowchart LR", f"flowchart {direction}")
    # re-apply per-phase mapping by line surgery
    node_ids = ["C", "I", "E", "L", "P", "S", "M", "K", "W", "X"]
    import re
    out_lines = []
    for line in src.splitlines():
        if line.strip().startswith(("C[", "I[", "E[", "L[", "P[", "S[", "M[", "K[", "W[", "X[")):
            nid = line.strip()[0]
            idx = node_ids.index(nid)
            if done is not None:
                if done[idx] and idx != current:
                    cls = "done"
                elif idx == current:
                    cls = "current"
                elif idx < current:
                    cls = "unmet"
                else:
                    cls = "todo"
            else:
                if idx < current:
                    cls = "done"
                elif idx == current:
                    cls = "current"
                else:
                    cls = "todo"
            line = re.sub(r":::\w+", f":::{cls}", line)
        out_lines.append(line)
    if done is not None and any(i < current and not done[i] for i in range(10)):
        out_lines.append("    classDef unmet fill:#3b2f10,stroke:#f59e0b,color:#fbbf24,stroke-dasharray: 5 5;")
    return "\n".join(out_lines) + "\n"


def render_flow(current: int, done: list[bool] | None = None) -> str:
    """ASCII flow diagram. ✓/☑ only from verified gate state, never position."""
    nodes = []
    for i in range(10):
        label = f"{i} {FLIP[i]}"
        if done is not None:
            if done[i] and i != current:
                nodes.append(ui.colorize(f"☑ {label}", ui.GREEN))
            elif i == current:
                nodes.append(ui.colorize(f"▶ {label}", ui.BOLD))
            elif i < current:
                nodes.append(ui.colorize(f"⚠ {label}", ui.YELLOW))
            else:
                nodes.append(ui.colorize(f"○ {label}", ui.DIM))
        else:
            if i == current:
                nodes.append(ui.colorize(f"▶ {label}", ui.BOLD))
            elif i < current:
                nodes.append(ui.colorize(f"? {label}", ui.YELLOW))
            else:
                nodes.append(ui.colorize(f"○ {label}", ui.DIM))
    lines = [
        "  " + "  ".join(nodes[0:5]),
        "  " + "  ↓".join([""] * 2),
        "  " + "  ".join(nodes[5:10]),
        ui.colorize("  replan: CRITIQUE → PLAN (4) / IMPLEMENT (6)", ui.DIM),
        ui.colorize("  gates: user_approves_plan (4) · critique_veto (7)", ui.DIM),
    ]
    return "\n".join(lines)


def diagram_tools() -> list[str]:
    return [t for t in ("mmdr", "beautiful-mermaid") if shutil.which(t)]


# ASCII-native mermaid renderers, best first. Each entry: binary -> argv prefix.
# All read a .mmd file (or stdin) and print box-drawing/ASCII art.
# ONLY binaries already installed on the machine are used — the CLI never
# downloads or installs anything (npx -y would silently fetch packages;
# that's the user's choice, offered as an install option below, not ours).
ASCII_TOOLS: dict[str, list[str]] = {
    "bm": ["bm", "ascii", None, "--padding-y", "0"],
    "mermaid-ascii": ["mermaid-ascii", "-f", None, "-y", "2"],  # AlexanderGrooff/mermaid-ascii (Go)
    "mermansi": ["mermansi", "--file", None, "--concise"],
    "mermaid2term": ["mermaid2term", None],
    "merx": ["merx", "render", None, "--ascii"],
    "ma": ["ma", None],
}

# Options the CLI merely *suggests* when no renderer is installed — the user
# decides which to run, if any. The npx variants change nothing globally:
# they download to the npm cache on first run. Never executed automatically.
ASCII_TOOL_INSTALL = {
    "bm": "npm i -g beautiful-mermaid-cli",
    "mermaid-ascii": "go install github.com/AlexanderGrooff/mermaid-ascii@latest (or releases page)",
    "mermansi": "cargo install mermansi",
    "mermaid2term": "npm i -g mermaid2term",
    "merx": "npm i -g @wuwe1/merx",
    "ma": "cargo install --git https://github.com/Sixeight/ma",
}
ASCII_NO_INSTALL = {
    "bm": "npx -y beautiful-mermaid-cli ascii workflow.mmd   # no global install; downloads to the npm cache",
    "mermaid2term": "npx -y mermaid2term workflow.mmd       # no global install; downloads to the npm cache",
}


def ascii_tools() -> list[str]:
    found = []
    for t, argv in ASCII_TOOLS.items():
        if shutil.which(argv[0]):
            found.append(t)
    return found


def mermaid_for_tasks(tasks: list[dict], *, direction: str = "TD") -> str:
    """Mermaid DAG of the PROJECT's plan steps (Orchestrator/Researcher's PLAN.md).

    Nodes = board tasks, edges = depends_on. State classes: complete/working/
    idle. Dependencies that are not on the board are skipped (noted in output
    by the caller). The SKILL.md phase pipeline is constant — this is the
    per-project workflow.
    """
    ids = {t["id"] for t in tasks}
    lines = [f"flowchart {direction}", "%%{init: {'theme': 'dark'}}%%" if False else ""]
    lines = [f"flowchart {direction}"]
    for t in tasks:
        cls = {"complete": "done", "working": "working", "idle": "todo"}.get(t["state"], "todo")
        label = (t.get("title") or t["id"]).replace('"', "'").replace("\n", " ")
        extra = []
        if t.get("deliverable"):
            extra.append(t["deliverable"])
        if t.get("kind") == "spike":
            extra.append("spike")
        text = f"{t['id']} {label}" + (f"<br/>{extra[0]}" if extra else "")
        lines.append(f'    {t["id"]}["{text}"]:::{cls}')
    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep in ids:
                lines.append(f'    {dep} --> {t["id"]}')
    lines += [
        "    classDef done fill:#14532d,stroke:#22c55e,color:#dcfce7;",
        "    classDef working fill:#1d4ed8,stroke:#93c5fd,color:#fff,stroke-width:3px;",
        "    classDef todo fill:#0b0f17,stroke:#374151,color:#6b7280;",
    ]
    return "\n".join(lines) + "\n"


def render_ascii(root: Path, mermaid_src: str) -> tuple[str | None, str | None]:
    """Render mermaid source as terminal art via the best installed tool.

    Returns (art, tool). art is None when no tool works. The transient .mmd
    lives in .rh/tmp/; the caller owns any saved artifact.
    """
    tools = ascii_tools()
    if not tools:
        return None, None
    from . import paths
    tmp = paths.rh_dir(root) / "tmp" / "workflow-ascii.mmd"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(mermaid_src, encoding="utf-8")
    for tool in tools:
        argv = [str(tmp) if part is None else part for part in ASCII_TOOLS[tool]]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.rstrip(), tool
    return None, tools[0]


def render_via(tool: str, mermaid: str) -> str | None:
    try:
        proc = subprocess.run([tool], input=mermaid, capture_output=True, text=True, timeout=10)
        return proc.stdout if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def write_mermaid(root: Path, current: int, done: list[bool] | None = None,
                  direction: str = "LR", name: str = "workflow.mmd") -> Path:
    from . import paths
    out = paths.rh_dir(root) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(mermaid_for_phase(current, done, direction), encoding="utf-8")
    return out


def render_image(root: Path, mermaid_src: str, *, fmt: str = "svg",
                 out_name: str = "workflow") -> tuple[Path | None, str]:
    """Render mermaid source to an svg/png artifact with mmdr (file->file).

    The transient .mmd goes to .rh/tmp/ — the CLI NEVER writes
    .rh/workflow.mmd, that file belongs to the agent alone.
    Returns (image_path, message).
    """
    from . import paths
    tools = diagram_tools()
    if not tools:
        return None, "no renderer installed (mmdr / beautiful-mermaid)"
    rh = paths.rh_dir(root)
    mmd = rh / "tmp" / f"{out_name}.mmd"
    mmd.parent.mkdir(parents=True, exist_ok=True)
    mmd.write_text(mermaid_src, encoding="utf-8")
    out = rh / f"{out_name}.{fmt}"
    tool = tools[0]
    try:
        if tool == "mmdr":
            proc = subprocess.run(
                ["mmdr", "-i", str(mmd), "-o", str(out), "-e", fmt, "-t", "dark"],
                capture_output=True, text=True, timeout=30,
            )
        else:  # beautiful-mermaid: pipe source in, binary out
            proc = subprocess.run(
                [tool, "-e", fmt] if fmt != "svg" else [tool],
                input=mermaid_src, capture_output=True, timeout=30,
            )
            if proc.returncode == 0:
                out.write_bytes(proc.stdout if isinstance(proc.stdout, bytes) else proc.stdout.encode())
        if proc.returncode != 0:
            return None, f"{tool} failed: {(proc.stderr or proc.stdout or '')[:200]}".strip()
        if not out.exists() or out.stat().st_size == 0:
            return None, f"{tool} produced no output"
        return out, f"rendered with {tool}"
    except (subprocess.TimeoutExpired, OSError) as e:
        return None, f"{tool} error: {e}"
