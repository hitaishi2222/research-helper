"""Config surfaces and search: the pieces of `rh` a project really leans on.

The PLAN.md parser is gone (`rh plan import` was removed on 2026-11-07 — the plan is
prose, tasks are created explicitly with `rh add task`), so nothing here parses a plan.
"""
import json

from rh import cli, tasks


def run(argv):
    return cli.main(argv)


# --- planners = none means the user plans -------------------------------------

def test_planners_none_coerces_to_empty_list():
    from rh import config
    assert config.coerce_value("none", "list", "agents.planners.models") == []
    assert config.coerce_value("0", "list", "agents.planners.models") == []
    assert config.coerce_value("[]", "list", "agents.planners.models") == []
    assert config.coerce_value("a,b", "list", "agents.planners.models") == ["a", "b"]


def test_user_plans_and_phase4_gate_text():
    from rh import config, tasks
    empty = {"agents": {"planners": {"models": []}}}
    two = {"agents": {"planners": {"models": [{"model": "a"}, {"model": "b"}]}}}
    assert config.user_plans(empty) is True
    assert config.user_plans(two) is False
    assert "written by the user" in tasks.phase_exit(4, user_plans=True)
    assert "planners agreed" in tasks.phase_exit(4, user_plans=False)
    assert tasks.phase_exit(6, user_plans=True) == tasks.phase_exit(6)


def test_env_set_planners_none_round_trip(tmp_path, capsys):
    run(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "env", "set", "agents.planners.models=none"]) == 0
    env = json.loads((tmp_path / ".rh" / "env.json").read_text())
    assert env["agents"]["planners"]["models"] == []
    run(["--root", str(tmp_path), "doctor"])  # exit code is about other checks in a bare project
    out = capsys.readouterr().out
    assert "planners: none — the user plans" in out
    assert "no agents.commands" not in out.split("planners")[0]


# --- project.environment: the software list ------------------------------------

def test_environment_entries_keep_their_objects():
    from rh import config
    raw = '[{"name": "numpy", "version": "2.3.5", "note": "arrays"}]'
    assert config.coerce_value(raw, "list", "project.environment") == [
        {"name": "numpy", "version": "2.3.5", "note": "arrays"}
    ]
    assert config.coerce_value("a,b", "list", "project.environment") == ["a", "b"]


def test_environment_validation_names_the_shape():
    from rh import config
    base = {"agents": {"count": 1, "backend": "none", "skills": [], "split": "",
                       "planners": {"models": []}},
            "project": {"name": "p", "environment": [{"version": "1"}]},
            "literature": {"ref_manager": "zot", "reading": "lit", "search": "crw",
                           "paywall": "ask_user"}}
    problems = config.validate(base)
    assert any("project.environment[0] must be an object with a name" in p for p in problems)


def test_env_show_prints_the_environment_table(tmp_path, capsys):
    run(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "env", "set",
                'project.environment=[{"name": "numpy", "version": "2.3.5", "note": "arrays"}]']) == 0
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "env", "show"]) == 0
    out = capsys.readouterr().out
    assert "Project environment" in out
    assert "numpy" in out and "2.3.5" in out and "arrays" in out


def test_search_skips_archives_and_reads_live_artifacts(tmp_path):
    from rh import search
    rh = tmp_path / ".rh"
    rh.mkdir()
    (rh / "STATUS.md").write_text("live: numpy 2.3.5 recorded here\n", encoding="utf-8")
    bak = rh / ".bak" / "20260101-000000"
    bak.mkdir(parents=True)
    (bak / "STATUS.md").write_text("stale: numpy 1.0.0 from the archive\n", encoding="utf-8")
    (rh / "tmp").mkdir()
    (rh / "tmp" / "note.md").write_text("transient numpy render\n", encoding="utf-8")

    names = {str(p.relative_to(tmp_path)) for p in search.candidate_files(tmp_path)}
    assert ".rh/STATUS.md" in names
    assert not any(n.startswith(".rh/.bak") for n in names)
    assert not any(n.startswith(".rh/tmp") for n in names)


# --- the replacement: tasks are created explicitly ------------------------------

def test_add_task_with_subtasks_then_set_them(tmp_path, capsys):
    run(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "add", "task", "Dispersion screen",
                "--id", "S01", "--phase", "6", "--owner", "researcher",
                "--deliverable", "results/S01.json", "--verify", "pytest -q",
                "--subtask", "build the sweep", "--subtask", "profile one cell"]) == 0
    board = {t["id"]: t for t in tasks.TaskStore(tmp_path).list()}
    task = board["S01"]
    assert task["title"] == "Dispersion screen"
    assert task["verify"] == "pytest -q"
    assert [st["id"] for st in task["subtasks"]] == ["S01.1", "S01.2"]
    assert run(["--root", str(tmp_path), "tasks", "set", "S01.2", "complete"]) == 0
    assert tasks.TaskStore(tmp_path).get("S01.2")["state"] == "complete"
    assert tasks.TaskStore(tmp_path).get("S01.1")["state"] == "idle"
