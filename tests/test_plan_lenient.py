"""PLAN.md → board: the parser accepts a general Markdown plan, not only the template.

Each test pins one shape or one guarantee the Orchestrator relies on when it mirrors a
user-written plan onto the board.
"""
import json

from rh import cli, tasks


def run(argv):
    return cli.main(argv)


def steps(text):
    return tasks.parse_plan_steps(text)


# --- shapes -------------------------------------------------------------------

def test_explicit_id_heading_with_fields():
    (s,) = steps(
        "### S04b — External validation bench\n"
        "owner: researcher | deliverable: `results/S04b.csv` | risk: bench may not score\n"
        "verify: `pytest tests/test_s04b.py`\n"
        "depends on: S04, S03\n"
    )
    assert s["id"] == "S04b"
    assert s["title"] == "External validation bench"
    assert s["owner"] == "researcher"
    assert s["deliverable"] == "results/S04b.csv"
    assert s["verify"] == "pytest tests/test_s04b.py"
    assert s["depends_on"] == ["S04", "S03"]
    assert s["risk"] == "bench may not score"


def test_plain_level3_headings_get_positional_ids():
    out = steps("### Title one\n\n### Title two\n")
    assert [s["id"] for s in out] == ["S01", "S02"]
    assert [s["title"] for s in out] == ["Title one", "Title two"]


def test_level2_heading_is_a_section_boundary_not_a_step():
    out = steps(
        "## 1. What works\n"
        "prose about prior results\n"
        "### Do the sweep\n"
        "1. first numbered note inside a step\n"
        "## 2. What does not work\n"
        "more prose\n"
    )
    assert [s["title"] for s in out] == ["Do the sweep"]
    assert out[0]["id"] == "S01"


def test_numbered_plan_is_accepted():
    out = steps("1. Build the deck\n2. Run the ladder\n")
    assert [s["id"] for s in out] == ["S01", "S02"]
    assert [s["title"] for s in out] == ["Build the deck", "Run the ladder"]


def test_bullet_plan_is_accepted_and_indented_bullets_are_subtasks():
    out = steps(
        "- Build the deck\n"
        "  - solve the mode\n"
        "  - export the npz\n"
        "- Run the ladder\n"
    )
    assert [s["title"] for s in out] == ["Build the deck", "Run the ladder"]
    assert out[0]["subtasks"] == ["solve the mode", "export the npz"]
    assert out[1]["subtasks"] == []


def test_bullets_inside_a_heading_step_are_subtasks_with_or_without_checkbox():
    out = steps(
        "### Pair the candidates\n"
        "body prose\n"
        "- [ ] keel a2.4 p0.3 h0.9\n"
        "- [x] grade3 a2.0 f0.4 h0.8\n"
        "  - nested detail is a subtask too\n"
    )
    assert out[0]["subtasks"] == [
        "keel a2.4 p0.3 h0.9",
        "grade3 a2.0 f0.4 h0.8",
        "nested detail is a subtask too",
    ]


def test_free_prose_without_steps_yields_nothing():
    assert steps("Just a paragraph about what we might do one day.\n\nAnd another.\n") == []


def test_duplicate_explicit_ids_do_not_collide():
    out = steps("### S07 — first\n### S07 — second\n")
    assert len({s["id"] for s in out}) == 2


# --- import guarantees --------------------------------------------------------

def _project(tmp_path):
    run(["--root", str(tmp_path), "init"])
    return tmp_path


def test_import_creates_steps_and_subtasks(tmp_path, capsys):
    root = _project(tmp_path)
    (tmp_path / ".rh" / "PLAN.md").write_text(
        "## Plan\n\n### Build the deck\nowner: researcher\n- mode solve\n- export npz\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "plan", "import"]) == 0
    board = tasks.TaskStore(tmp_path).load()["tasks"]
    (task,) = [t for t in board if t["id"] == "S01"]
    assert [s["title"] for s in task["subtasks"]] == ["mode solve", "export npz"]
    assert [s["id"] for s in task["subtasks"]] == ["S01.1", "S01.2"]


def test_reimport_appends_new_subtasks_and_keeps_state(tmp_path, capsys):
    root = _project(tmp_path)
    plan = tmp_path / ".rh" / "PLAN.md"
    plan.write_text("### Build the deck\n- mode solve\n", encoding="utf-8")
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "plan", "import"]) == 0
    assert run(["--root", str(tmp_path), "tasks", "set", "S01.1", "complete"]) == 0

    plan.write_text("### Build the deck\n- mode solve\n- export npz\n", encoding="utf-8")
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "plan", "import"]) == 0
    (task,) = [t for t in tasks.TaskStore(tmp_path).load()["tasks"] if t["id"] == "S01"]
    assert [s["title"] for s in task["subtasks"]] == ["mode solve", "export npz"]
    assert task["subtasks"][0]["state"] == "complete"
    assert task["subtasks"][1]["state"] == "idle"
    assert task["subtasks"][1]["id"] == "S01.2"


def test_reimport_is_idempotent(tmp_path, capsys):
    root = _project(tmp_path)
    (tmp_path / ".rh" / "PLAN.md").write_text("### Build the deck\n- mode solve\n", encoding="utf-8")
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "plan", "import"]) == 0
    assert tasks.import_plan_md(tmp_path) == []


def test_unparseable_plan_says_so_instead_of_claiming_agreement(tmp_path, capsys):
    _project(tmp_path)
    (tmp_path / ".rh" / "PLAN.md").write_text(
        "We should probably try a taper at some point.\n", encoding="utf-8"
    )
    capsys.readouterr()
    assert run(["--root", str(tmp_path), "plan", "import"]) == 0
    out = capsys.readouterr().out
    assert "No steps recognised" in out
    assert "board agree" not in out


def test_numbered_level2_headings_are_steps_when_no_level3_exists():
    out = steps(
        "## Why this order\n\nprose\n\n"
        "## 1. Dispersion-first sweep\n\nOwner: researcher.\n"
        "- [ ] widen the stack\n- [ ] score complexity\n\n"
        "## 2. Pair the candidates\n\n- profile one cell\n\n"
        "## 3. What we will not do\n\nMultimode. Out of scope.\n"
    )
    assert [s["title"] for s in out] == [
        "Dispersion-first sweep",
        "Pair the candidates",
        "What we will not do",
    ]
    assert out[0]["subtasks"] == ["widen the stack", "score complexity"]
    assert out[1]["subtasks"] == ["profile one cell"]
    assert out[0]["owner"] == "researcher"


def test_title_keeps_inner_backticks():
    (s,) = steps("### score by complexity as well as `S30`\n")
    assert s["title"] == "score by complexity as well as `S30`"


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
