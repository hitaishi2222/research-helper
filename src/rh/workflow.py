"""Workflow diagram — mermaid source + CLI rendering.

Uses `mmdr` / `beautiful-mermaid` when installed; otherwise renders an
ASCII rail and tells the user how to get diagrams. Shows current phase.
"""
from __future__ import annotations

import re
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


# Renderer priority is the declaration order below — `bm` (beautiful-mermaid
# CLI) first, then the other ASCII-native tools, then the built-in text view.
# ONLY binaries already installed are used: rh never downloads anything, not
# even via `npx` (the install hints are suggestions for the user).
ASCII_TOOLS: dict[str, dict] = {
    "bm": {"bins": ("bm", "beautiful-mermaid"), "argv": ["{bin}", "ascii", "{file}"]},
    # AlexanderGrooff/mermaid-ascii (Go)
    "mermaid-ascii": {"bins": ("mermaid-ascii",), "argv": ["{bin}", "-f", "{file}", "-y", "2"]},
    "mermansi": {"bins": ("mermansi",), "argv": ["{bin}", "--file", "{file}", "--concise"]},
    "mermaid2term": {"bins": ("mermaid2term",), "argv": ["{bin}", "{file}"]},
    "merx": {"bins": ("merx",), "argv": ["{bin}", "render", "{file}", "--ascii"]},
    "ma": {"bins": ("ma",), "argv": ["{bin}", "{file}"]},
}

# svg/png renderers, same idea: first installed one wins.
DIAGRAM_TOOLS: dict[str, dict] = {
    "bm": {"bins": ("bm", "beautiful-mermaid"),
           "argv": ["{bin}", "render", "-f", "{fmt}", "-o", "{out}", "{file}"]},
    "mmdr": {"bins": ("mmdr",), "argv": ["{bin}", "-i", "{file}", "-o", "{out}", "-e", "{fmt}", "-t", "dark"]},
    "mmdc": {"bins": ("mmdc",), "argv": ["{bin}", "-i", "{file}", "-o", "{out}", "-t", "dark"]},
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


def find_bin(names) -> str | None:
    """First command from `names` that is on PATH (aliases share one renderer)."""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def ascii_tools() -> list[str]:
    """Installed ASCII renderers, in priority order."""
    return [t for t, spec in ASCII_TOOLS.items() if find_bin(spec["bins"])]


def diagram_tools() -> list[str]:
    """Installed svg/png renderers, in priority order."""
    return [t for t, spec in DIAGRAM_TOOLS.items() if find_bin(spec["bins"])]


def tool_installed(name: str) -> bool:
    spec = ASCII_TOOLS.get(name) or DIAGRAM_TOOLS.get(name) or {}
    return bool(spec and find_bin(spec["bins"]))


def _argv(spec: dict, *, file: Path, out: Path | None = None, fmt: str = "svg") -> list[str]:
    parts = {"bin": find_bin(spec["bins"]) or spec["bins"][0],
             "file": str(file), "out": str(out or ""), "fmt": fmt}
    return [part.format(**parts) for part in spec["argv"]]


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

    Returns (art, tool). Installed renderers win in priority order (`bm` first);
    if none is installed, or its canvas is wider than the terminal, the
    built-in text view is used instead. The transient .mmd lives in .rh/tmp/;
    the caller owns any saved artifact.
    """
    tools = ascii_tools()
    from . import paths
    tmp = paths.rh_dir(root) / "tmp" / "workflow-ascii.mmd"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(mermaid_src, encoding="utf-8")
    limit = max(shutil.get_terminal_size((100, 24)).columns, 100)
    rejects = []
    for tool in tools:
        argv = _argv(ASCII_TOOLS[tool], file=tmp)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if proc.returncode != 0 or not proc.stdout.strip():
            rejects.append(f"{tool} failed")
            continue
        art = proc.stdout.rstrip()
        widest = max((len(line) for line in art.splitlines()), default=0)
        if widest <= limit:
            return art, tool
        # a 300-column canvas is unreadable in a terminal: keep it for --svg,
        # show the compact built-in view here.
        rejects.append(f"{tool} output {widest} cols wide")
    art = render_text_graph(mermaid_src)
    if not art:
        return None, tools[0] if tools else None
    note = f"built-in — {rejects[0]} > {limit} cols" if rejects else "built-in"
    return art, note


def render_via(tool: str, mermaid: str) -> str | None:
    try:
        proc = subprocess.run([tool], input=mermaid, capture_output=True, text=True,
                              timeout=10, check=False)
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
    """Render mermaid source to an svg/png artifact with the best installed tool.

    The transient .mmd goes to .rh/tmp/ — the CLI NEVER writes
    .rh/workflow.mmd, that file belongs to the agent alone.
    Returns (image_path, message).
    """
    from . import paths
    tools = diagram_tools()
    if not tools:
        return None, "no renderer installed (bm / mmdr / mmdc)"
    rh = paths.rh_dir(root)
    mmd = rh / "tmp" / f"{out_name}.mmd"
    mmd.parent.mkdir(parents=True, exist_ok=True)
    mmd.write_text(mermaid_src, encoding="utf-8")
    out = rh / f"{out_name}.{fmt}"
    errors = []
    for tool in tools:
        out.unlink(missing_ok=True)
        try:
            proc = subprocess.run(_argv(DIAGRAM_TOOLS[tool], file=mmd, out=out, fmt=fmt),
                                  capture_output=True, text=True, timeout=60, check=False)
        except (subprocess.TimeoutExpired, OSError) as e:
            errors.append(f"{tool}: {e}")
            continue
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return out, f"rendered with {tool}"
        errors.append(f"{tool}: {(proc.stderr or proc.stdout or 'no output').strip()[:160]}")
    return None, " | ".join(errors)


# --- built-in text view (no external renderer needed) -------------------------
# Deliberately a *reading* of the graph, not a pixel replica: complex mermaid
# syntax (styling, links, nested subgraphs) is ignored rather than guessed at.

_NODE_RE = re.compile(
    r'^\s*(?!subgraph\b|end\b|classDef\b|class\b|flowchart\b|graph\b|direction\b)'
    r'([A-Za-z_][\w-]*)\s*(?:\[\(?|\(\[|\{|\(|\[)\s*"?(.*?)"?\s*(?:\)?\]|\]\)|\}|\)|\])'
    r'\s*(?:[ \t]*:::[ \t]*([\w-]+))?\s*$'
)
_EDGE_RE = re.compile(
    r'^\s*([A-Za-z_][\w-]*)\s*(?:-->|-\.->|==>|---|--)\s*(?:\|[^|]*\|\s*)?([A-Za-z_][\w-]*)\s*$'
)
_SUBGRAPH_RE = re.compile(r'^\s*subgraph\s+([\w-]+)\s*(?:\["?([^"\]]*)"?\])?')
_GLYPH = {"done": "☑", "complete": "☑", "next": "▶", "working": "▶",
          "gate": "◆", "cond": "◇", "todo": "○"}


def _plain(label: str) -> str:
    label = label.replace("<br/>", " · ").replace("<br>", " · ")
    for a, b in (("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&"), ("&quot;", '"')):
        label = label.replace(a, b)
    return label.strip()


def parse_graph(src: str) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[tuple[str, str]] = []
    groups: list[tuple[str, list[str]]] = [("", [])]
    for raw in src.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if m := _SUBGRAPH_RE.match(line):
            groups.append((_plain(m.group(2) or m.group(1)), []))
            continue
        if line == "end":
            if len(groups) > 1:
                groups.append(("", []))
            continue
        if m := _EDGE_RE.match(line):
            edges.append((m.group(1), m.group(2)))
            continue
        if m := _NODE_RE.match(line):
            node_id, label, cls = m.group(1), _plain(m.group(2)), m.group(3) or "todo"
            nodes[node_id] = {"id": node_id, "label": label, "cls": cls}
            groups[-1][1].append(node_id)
    for a, b in edges:  # edges may declare nodes implicitly
        for nid in (a, b):
            nodes.setdefault(nid, {"id": nid, "label": nid, "cls": "todo"})
    return {"nodes": nodes, "edges": edges, "groups": groups}


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def render_text_graph(src: str, width: int = 88) -> str:
    """Built-in ASCII view: groups → nodes (state glyph + label), then edges."""
    g = parse_graph(src)
    nodes, edges = g["nodes"], g["edges"]
    if not nodes:
        return ""
    out = [f"{len(nodes)} nodes · {len(edges)} edges (built-in text view)"]
    for title, ids in g["groups"]:
        ids = [i for i in ids if i in nodes]
        if not ids:
            continue
        if title:
            out.append("")
            out.append(ui.colorize(f"── {title}", ui.BOLD))
        for nid in ids:
            n = nodes[nid]
            head = f"  {_GLYPH.get(n['cls'], '○')} {nid:5} "
            wrapped = _wrap(n["label"], width - len(head))
            out.append(head + wrapped[0])
            out += [" " * len(head) + w for w in wrapped[1:]]
    tails = [(a, b) for a, b in edges if a in nodes and b in nodes]
    if tails:
        out.append("")
        out.append(ui.colorize("── flows", ui.BOLD))
        by_src: dict[str, list[str]] = {}
        for a, b in tails:
            by_src.setdefault(a, []).append(b)
        for a, targets in by_src.items():
            out.append(f"  {a} → {', '.join(targets)}")
    out.append("")
    out.append(ui.colorize("  ☑ done · ▶ current/next · ◆ gate · ◇ conditional · ○ todo", ui.DIM))
    return "\n".join(out)
