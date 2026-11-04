import json

from rh import cli, tasks, workflow


def run(argv):
    return cli.main(argv)


def payload(out, opener):
    return json.loads(out[out.index(opener):])


def test_init_and_status(tmp_path, capsys):
    root = str(tmp_path)
    assert run(["--root", root, "init", "--slug", "demo"]) == 0
    assert (tmp_path / ".rh").is_dir()
    capsys.readouterr()
    assert run(["--root", root, "status", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["slug"] == "demo"
    assert data["initialized"] is True
    assert "agents" not in data  # agent config is not status


def test_env_set_and_show(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "env", "set", "literature.search=mytool"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "env", "show", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["literature"]["search"] == "mytool"


def test_env_md_lives_in_rh_dir(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    assert (root / ".rh" / "ENV.md").exists()
    assert not (root / "ENV.md").exists()


def test_env_notes_preserved(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    env_md = root / ".rh" / "ENV.md"
    env_md.write_text(env_md.read_text() + "\n## Environment\n\n- custom tool 1.0\n")
    run(["--root", str(root), "env", "set", "project.git=true"])
    text = env_md.read_text()
    assert "## Environment" in text
    assert "custom tool 1.0" in text


def test_agents_skills_key(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "env", "set", "agents.skills=research-helper,crw"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "env", "show", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["agents"]["skills"] == ["research-helper", "crw"]


def test_add_task_and_list(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "add", "task", "do it", "--id", "S01", "--subtask", "step a"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "tasks", "set", "S01.1", "working"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "tasks", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["tasks"][0]["id"] == "S01"
    assert data["tasks"][0]["subtasks"][0]["state"] == "working"


def test_plan_import_updates_titles_and_accepts_suffixed_ids(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    plan = root / ".rh" / "PLAN.md"
    plan.write_text(
        "### S03 — retired title\n"
        "owner: researcher | deliverable: `results/a.json`\n"
        "depends on: none | kind: build\n\n"
        "### S04b — audit the valid cell\n"
        "owner: researcher | deliverable: `results/b.json`\n"
        "depends on: S03 | kind: audit\n",
        encoding="utf-8",
    )
    assert [t["id"] for t in tasks.import_plan_md(root)] == ["S03", "S04b"]

    plan.write_text(plan.read_text().replace("retired title", "current title"), encoding="utf-8")
    changed = tasks.import_plan_md(root)
    assert changed == [{"id": "S03", "title": "current title", "action": "updated",
                        "fields": ["title"]}]
    board = {t["id"]: t for t in tasks.TaskStore(root).list()}
    assert board["S03"]["title"] == "current title"
    assert board["S04b"]["kind"] == "audit"
    assert board["S04b"]["depends_on"] == ["S03"]
    # nothing changed -> no churn
    assert tasks.import_plan_md(root) == []


def test_papers_stay_at_root(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    assert (root / "papers").is_dir()
    assert not (root / ".rh" / "papers").exists()


def test_workflow_builtin_text_view(tmp_path, capsys):
    src = workflow.mermaid_for_tasks([
        {"id": "S01", "title": "probe", "state": "complete", "depends_on": []},
        {"id": "S02", "title": "build", "state": "working", "depends_on": ["S01"]},
    ])
    art = workflow.render_text_graph(src)
    assert "S01" in art and "S02" in art
    assert "S01 → S02" in art
    # render_ascii must never end empty when the source has nodes, even with no
    # external ascii renderer installed
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    monkey = workflow.ascii_tools
    workflow.ascii_tools = lambda: []
    try:
        art, tool = workflow.render_ascii(root, src)
    finally:
        workflow.ascii_tools = monkey
    assert art and tool == "built-in"


def test_skill_install(tmp_path):
    dest = tmp_path / "skills" / "research-helper"
    assert run(["skill", "install", "--dest", str(dest)]) == 0
    skill = dest / "SKILL.md"
    assert skill.exists()
    assert "research-helper" in skill.read_text(encoding="utf-8")[:2000]
