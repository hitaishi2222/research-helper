"""research-helper CLI — makes SKILL.md easy for AI agents to adopt.

Storage: everything lives under `.rh/` in a project root (or $RH_HOME /
$XDG_CONFIG_HOME/rh as a global default). .rh/env.json is the single config file
(the SKILL.md config block), .rh/ENVIRONMENT.md holds the phase-2 environment
notes, .rh/tasks.json is the machine-readable task board, and the SKILL.md
artifacts (PROBLEM.md, PLAN.md, ...) are kept at the root or inside .rh/ when
the user asked for a clean workspace.
"""

__version__ = "0.1.7"
__all__ = ["__version__"]
