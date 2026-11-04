"""Terminal UI on top of `rich` — tables, progress bars, banners, phase rail.

rich is a hard dependency (see pyproject). Its Console runs with `markup=False`
so user data (titles, paths, prompts) is never parsed as markup; inline colour
stays plain ANSI and is dropped automatically when stdout is not a TTY.
Use --json on any command for machine-readable output.
"""
from __future__ import annotations

import json
import sys

from rich import box
from rich.console import Console
from rich.rule import Rule
from rich.table import Table as RichTable
from rich.text import Text

# --- ANSI (inline text only) --------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

_TTY = sys.stdout.isatty()


def colorize(text: str, color: str) -> str:
    if not _TTY:
        return text
    return f"{color}{text}{RESET}"


def _render(renderable, *, width: int | None = None) -> str:
    """Render a rich object to a string so it composes inside f-strings."""
    console = Console(force_terminal=_TTY, no_color=not _TTY, highlight=False,
                      emoji=False, markup=False, width=width)
    with console.capture() as cap:
        console.print(renderable)
    return cap.get().rstrip("\n")


def bar(pct: int, width: int = 20) -> str:
    # distinct glyphs so the bar still reads when piped (rich's ProgressBar
    # relies on colour alone and drops its empty track without a colour system)
    pct = max(0, min(100, int(pct)))
    filled = width * pct // 100
    t = Text()
    t.append("█" * filled, style="cyan")
    t.append("░" * (width - filled), style="dim")
    return f"{_render(t)} {pct}%"


def table(headers: list[str], rows: list[list[str]]) -> str:
    rt = RichTable(
        box=box.SIMPLE_HEAVY,  # thick rule under the header only
        header_style="bold cyan",
        pad_edge=False,
        padding=(0, 1),
        show_header=True,
        show_edge=False,
    )
    for h in headers:
        rt.add_column(h, overflow="fold")
    for row in rows:
        rt.add_row(*[str(c) for c in row])
    # piped output has no terminal width to fold against: render wide instead
    return _render(rt, width=None if _TTY else 160)


def state_color(state: str) -> str:
    return {"complete": GREEN, "working": CYAN, "idle": DIM}.get(state, "")


def state_label(state: str) -> str:
    dot = {"complete": "●", "working": "◐", "idle": "○"}.get(state, "?")
    return colorize(f"{dot} {state}", state_color(state))


def phase_rail(current: int, *, done: list[bool] | None = None) -> str:
    """Rail where ✓ means *verified by an artifact/gate*, never just position.

    done[i] is computed by config.phase_gate(). Phases claimed past but unmet
    render as `⚠x` in yellow, so a jumped-to phase can never look earned.
    """
    names = ["C", "I", "E", "L", "P", "S", "M", "K", "W", "✕"]
    rail = Text()
    for i, label in enumerate(names):
        if i:
            rail.append(" → ", style="dim")
        if done is not None:
            if done[i] and i != current:
                rail.append(f"✓{label}", style="green")
            elif i == current:
                rail.append(f"[{label}]", style="bold cyan")
            elif i < current:
                rail.append(f"⚠{label}", style="yellow")
            else:
                rail.append(label, style="dim")
        else:
            # no gate data: never fake ✓ — show position only
            if i == current:
                rail.append(f"[{label}]", style="bold cyan")
            elif i < current:
                rail.append(f"?{label}", style="yellow")
            else:
                rail.append(label, style="dim")
    legend = ("0 CONFIG → 1 INTAKE → 2 ENVIRONMENT → 3 LITERATURE → 4 PLAN → "
              "5 STATE → 6 IMPLEMENT → 7 CRITIQUE → 8 MANUSCRIPT → 9 CLOSE")
    head = Text("FLOW", style="bold")
    # legend stays a plain line: rich would wrap it on narrow terminals
    return f"{_render(head)}\n{_render(rail)}\n{colorize(legend, DIM)}"


def banner(title: str, subtitle: str = "") -> str:
    out = [_render(Rule(Text(title, style="bold"), align="left", style="grey37"))]
    if subtitle:
        out.append(colorize(subtitle, DIM))
    return "\n".join(out)


def json_out(obj) -> None:
    print(json.dumps(obj, indent=2))
