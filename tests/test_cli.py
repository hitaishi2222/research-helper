import json
from pathlib import Path

from rh import cli, config, spawn, tasks, workflow


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
    workflow.ascii_tools = list
    try:
        art, tool = workflow.render_ascii(root, src)
    finally:
        workflow.ascii_tools = monkey
    assert art and tool == "built-in"


def test_status_shows_one_progress_bar(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    run(["--root", root, "add", "task", "build it", "--id", "S01", "--owner", "researcher"])
    run(["--root", root, "add", "task", "read it", "--id", "S02"])
    capsys.readouterr()
    assert run(["--root", root, "status"]) == 0
    out = capsys.readouterr().out
    # the openspec-style duplicate ("Progress: …" + task lanes) is gone
    assert "Progress:" not in out
    assert "Changes (task lanes)" not in out
    # exactly one overall completion line ("N/M tasks · W working · I idle")
    assert out.count("working ·") == 1
    assert "0/2 tasks" in out


def test_resume_uses_env_command_model_thinking_and_skills(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "env", "set",
                'agents.roles.orchestrator={"provider":"pi","model":"glm-5","thinking":"high"}',
                "agents.skills=research-helper,crw",
                ("agents.commands.orchestrator=pi --model {model} --thinking {thinking} "
                 "--skill {skills} --prompt-file {prompt_file}")]) == 0
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["model"] == "glm-5" and data["thinking"] == "high"
    assert data["source"] == "agents.commands.orchestrator"
    assert data["argv"][:5] == ["pi", "--model", "glm-5", "--thinking", "high"]
    assert data["argv"][5:7] == ["--skill", "research-helper,crw"]
    # the template takes the prompt file, so the prompt must not be appended twice
    assert data["argv"][-1].endswith("resume-prompt.md")
    assert data["skills"] == ["research-helper", "crw"]
    assert data["notes"] == []
    assert "pi/glm-5 · thinking: high" in data["prompt"]
    assert "Load exactly these skills" in data["prompt"]


def test_resume_notes_when_env_does_not_pass_the_model(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    run(["--root", root, "env", "set",
         'agents.roles.orchestrator={"provider":"pi","model":"glm-5"}',
         "agents.commands.orchestrator=pi --prompt-file {prompt_file}"])
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][0] == "pi" and data["argv"][1] == "--prompt-file"
    assert any("model glm-5 is NOT passed" in n for n in data["notes"])
    assert any("not restricted at the CLI" in n for n in data["notes"])


def test_spawn_uses_role_command_and_role_tasks(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    run(["--root", root, "add", "task", "kernel", "--id", "S01", "--owner", "researcher",
         "--deliverable", "results/S01.csv", "--verify", "pytest -q"])
    run(["--root", root, "env", "set", "agents.roles.researcher.model=gpt-5",
         "agents.commands.researcher=pi --model {model} {prompt}"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do S01", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["role"] == "researcher"
    assert data["argv"][0] == "pi" and "gpt-5" in data["argv"]
    assert data["source"] == "agents.commands.researcher"
    assert data["model"] == "gpt-5"
    assert "owner=researcher" in data["prompt"]
    assert "[idle] S01 kernel" in data["prompt"]
    assert "deliverable: results/S01.csv" in data["prompt"]
    assert "do S01" in data["prompt"]
    assert "rh info" in data["prompt"]
    assert data["mode"] in ("pane", "background")
    assert Path(data["prompt_file"]).exists()
    assert data["spawned"] is False


def test_spawn_unknown_role_and_missing_command(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "coder", "hi"]) == 2
    assert "unknown role" in capsys.readouterr().err
    # a known role with no command template anywhere is a clear error, not a crash
    assert run(["--root", root, "spawn", "reviewer", "hi"]) == 1
    assert "no launch command" in capsys.readouterr().err


def test_custom_role_command_is_settable(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "env", "set", "agents.commands.coder=pi --model {model}"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "spawn", "coder", "write it", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][0] == "pi"
    assert data["source"] == "agents.commands.coder"


def test_info_lists_and_describes_artifacts(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    capsys.readouterr()
    assert run(["--root", root, "info", "--json"]) == 0
    listed = payload(capsys.readouterr().out, "[")
    assert [a["file"] for a in listed][:2] == ["ENV.md", "PROBLEM.md"]
    assert {a["file"] for a in listed} >= {"PLAN.md", "STATUS.md", "MANUSCRIPT.md"}

    assert run(["--root", root, "info", "plan"]) == 0
    out = capsys.readouterr().out
    assert "PLAN.md" in out and "verify:" in out and "owner:" in out

    assert run(["--root", root, "info", ".rh/STATUS.md", "--template"]) == 0
    assert "phase:" in capsys.readouterr().out

    assert run(["--root", root, "info", "nope"]) == 1
    assert "unknown artifact" in capsys.readouterr().err


def test_launch_plan_template_engine():
    env = config.deep_merge(config.DEFAULT_ENV, {"agents": {
        "commands": {"default": "pi --model {model} --thinking {thinking} {prompt}"},
        "skills": ["research-helper"],
    }})
    root = Path("/tmp/x")
    plan = spawn.launch_plan(root, env, "writer", "hi", root / "p.md")
    # an unset model/thinking drops the flag instead of passing an empty value
    assert plan["argv"] == ["pi", "hi"]
    assert any("model is empty" in n for n in plan["notes"])

    env["agents"]["roles"]["writer"] = {"provider": "pi", "model": "glm-4", "thinking": "low"}
    plan = spawn.launch_plan(root, env, "writer", "hi", root / "p.md")
    assert plan["argv"] == ["pi", "--model", "glm-4", "--thinking", "low", "hi"]
    # shell variables in a template survive (only {placeholders} are substituted)
    assert spawn.substitute("cd ${HOME} && pi {prompt}", {"prompt": "x"}) == "cd ${HOME} && pi x"


def test_skill_install(tmp_path):
    dest = tmp_path / "skills" / "research-helper"
    assert run(["skill", "install", "--dest", str(dest)]) == 0
    skill = dest / "SKILL.md"
    assert skill.exists()
    assert "research-helper" in skill.read_text(encoding="utf-8")[:2000]

