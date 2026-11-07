import json
from datetime import datetime
from pathlib import Path

from rh import checklist, cli, config, paths, spawn, tasks, workflow


def run(argv):
    return cli.main(argv)


def payload(out, opener):
    return json.loads(out[out.index(opener):])


def test_init_and_status(tmp_path, capsys):
    root = str(tmp_path)
    assert run(["--root", root, "init"]) == 0
    assert (tmp_path / ".rh").is_dir()
    capsys.readouterr()
    assert run(["--root", root, "status", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["name"] == tmp_path.name
    assert data["initialized"] is True
    assert "agents" not in data  # agent config is not status


def test_env_set_and_show(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    assert run(["--root", root, "env", "set", "literature.search=mytool"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "env", "show", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["literature"]["search"] == "mytool"


def test_config_lives_in_env_json(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init"])
    assert (root / ".rh" / "env.json").exists()
    assert not (root / ".rh" / "ENV.md").exists()
    assert not (root / "ENV.md").exists()


def test_env_set_never_touches_environment_notes(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init"])
    notes = root / ".rh" / "ENVIRONMENT.md"
    notes.write_text("## Environment\n\n- custom tool 1.0\n")
    run(["--root", str(root), "env", "set", "project.git=true"])
    assert notes.read_text() == "## Environment\n\n- custom tool 1.0\n"
    assert json.loads((root / ".rh" / "env.json").read_text())["project"]["git"] is True


def test_agents_skills_key(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    assert run(["--root", root, "env", "set", "agents.skills=research-helper,crw"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "env", "show", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["agents"]["skills"] == ["research-helper", "crw"]


def test_add_task_and_list(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
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
    run(["--root", str(root), "init"])
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
    run(["--root", str(root), "init"])
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
    run(["--root", str(root), "init"])
    monkey = workflow.ascii_tools
    workflow.ascii_tools = list
    try:
        art, tool = workflow.render_ascii(root, src)
    finally:
        workflow.ascii_tools = monkey
    assert art and tool == "built-in"


def test_status_shows_one_progress_bar(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
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
    run(["--root", root, "init"])
    assert run(["--root", root, "env", "set",
                'agents.roles.orchestrator={"provider":"pi","model":"glm-5","thinking":"high"}',
                "agents.skills=research-helper,crw",
                ("agents.commands.orchestrator=pi --model {model} --thinking {thinking} "
                 "--skill {skills} --system-prompt-file {agent_file} --prompt-file {prompt_file}")]) == 0
    # also write the role file so {agent_file} resolves to a real path
    run(["--root", root, "agents", "orchestrator", "--write"])
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["model"] == "glm-5" and data["thinking"] == "high"
    assert data["source"] == "agents.commands.orchestrator"
    assert data["argv"][:5] == ["pi", "--model", "glm-5", "--thinking", "high"]
    assert data["argv"][5:7] == ["--skill", "research-helper,crw"]
    agent_arg = data["argv"].index("--system-prompt-file") + 1
    assert data["argv"][agent_arg].endswith(".rh/agents/orchestrator.md")
    # the template takes the prompt file, so the prompt must not be appended twice
    assert data["argv"][-1].endswith("resume-prompt.md")
    assert data["skills"] == ["research-helper", "crw"]
    assert data["notes"] == []
    # the first message is the skill read, nothing else
    assert "Load the `research-helper` skill" in data["prompt"]
    assert "pi/glm-5" not in data["prompt"]
    # {agent_file} is wired through the template, so the role file is not duplicated
    assert "ORCHESTRATOR agent" not in data["prompt"]


def test_resume_notes_when_env_does_not_pass_the_model(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    run(["--root", root, "env", "set",
         'agents.roles.orchestrator={"provider":"pi","model":"glm-5"}',
         "agents.commands.orchestrator=pi --system-prompt-file {agent_file} --prompt-file {prompt_file}"])
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][0] == "pi" and "--prompt-file" in data["argv"]
    assert any("model glm-5 is NOT passed" in n for n in data["notes"])


def test_skill_note_is_suppressed_for_the_orchestrator():
    """The orchestrator must see every skill, so a missing {skills} is not a warning."""
    env = config.deep_merge(config.DEFAULT_ENV, {"agents": {
        "commands": {"default": "pi --model {model} {prompt}"},
        "skills": ["research-helper"],
    }})
    root = Path("/tmp/x")
    worker = spawn.launch_plan(root, env, "researcher", "hi", root / "p.md")
    chair = spawn.launch_plan(root, env, "orchestrator", "hi", root / "p.md")
    assert any("not restricted at the CLI" in n for n in worker["notes"])
    assert not any("not restricted at the CLI" in n for n in chair["notes"])


def test_spawn_uses_role_command_and_role_tasks(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
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
    # --dry-run writes nothing, not even the prompt file
    assert data["prompt_file"].endswith("spawn-researcher-prompt.md")
    assert not Path(data["prompt_file"]).exists()
    assert data["spawned"] is False


def test_spawn_unknown_role_and_missing_command(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "coder", "hi"]) == 2
    assert "unknown role" in capsys.readouterr().err
    # a known role with no command template anywhere is a clear error, not a crash
    assert run(["--root", root, "spawn", "reviewer", "hi"]) == 1
    assert "no launch command" in capsys.readouterr().err


def test_custom_role_command_is_settable(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    assert run(["--root", root, "env", "set", "agents.commands.coder=pi --model {model}"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "spawn", "coder", "write it", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][0] == "pi"
    assert data["source"] == "agents.commands.coder"


def test_info_lists_and_describes_artifacts(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    assert run(["--root", root, "info", "--json"]) == 0
    listed = payload(capsys.readouterr().out, "[")
    assert [a["file"] for a in listed][:2] == ["ENVIRONMENT.md", "PROBLEM.md"]
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

def test_spawn_terminal_detects_shell_and_split(tmp_path, capsys, monkeypatch):
    root = str(tmp_path)
    run(["--root", root, "init"])
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    run(["--root", root, "env", "set", "agents.split=vertical"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "terminal", "echo hi", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["terminal"] is True
    assert data["shell"] == "fish"
    assert data["split"] == "vertical"
    assert data["argv"] == ["fish", "-c", "echo hi"]
    assert data["mode"] in ("pane", "background")
    assert data["spawned"] is False


def test_spawn_terminal_and_missing_split_note(tmp_path, capsys, monkeypatch):
    root = str(tmp_path)
    run(["--root", root, "init"])
    monkeypatch.setenv("SHELL", "/bin/zsh")
    capsys.readouterr()
    assert run(["--root", root, "spawn", "terminal", "ls", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["shell"] == "zsh"
    assert any("agents.split is not set" in n for n in data["notes"])


def test_agents_write_list_and_spawn_uses_role_file(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    run(["--root", root, "env", "set", "agents.commands.researcher=pi --model {model} {prompt}"])
    capsys.readouterr()
    assert run(["--root", root, "agents", "--write"]) == 0
    capsys.readouterr()
    assert (tmp_path / ".rh" / "agents" / "researcher.md").exists()
    assert run(["--root", root, "agents", "researcher"]) == 0
    assert "RESEARCHER agent" in capsys.readouterr().out
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do S01", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert "Role file (.rh/agents/<role>.md)" in data["prompt"]
    assert "Owns:" in data["prompt"] and "# RESEARCHER agent" in data["prompt"]
    assert "agents.commands.<role>" in data["prompt"]


def test_checklist_reports_live_items(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    data = checklist.build_checklist(tmp_path)
    ids = {i["id"] for i in data["items"]}
    assert {"setup-config", "phase-0", "rule-9", "rule-10", "rule-11", "rule-12",
            "rule-13", "rule-14", "plan-approved", "critique-veto"} <= ids
    assert data["phase_name"] == "0 CONFIG"
    assert data["pending"] >= 1
    assert "STATUS.md" in (tmp_path / ".rh" / "CHECKLIST.md").read_text()


def test_doctor_reports_shell_and_templates(tmp_path, capsys):
    # `sh` exists on every CI runner; fish/pi do not
    root = str(tmp_path)
    run(["--root", root, "init"])
    run(["--root", root, "env", "set", "agents.shell=sh", "agents.split=vertical",
         "agents.commands.researcher=sh --model {model} --system-prompt-file {agent_file} --prompt-file {prompt_file}"])
    run(["--root", root, "agents", "researcher", "--write"])
    capsys.readouterr()
    assert run(["--root", root, "doctor", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    ids = {c["id"]: c for c in data["checks"]}
    assert ids["shell"]["ok"] is True
    assert ids["split"]["ok"] is True
    assert ids["commands.researcher.placeholders"]["ok"] is True
    assert ids["role-file.researcher"]["ok"] is True


def test_doctor_fails_when_no_command_template(tmp_path, capsys):
    """A fresh project has no launch command — doctor must say so, not pass."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    capsys.readouterr()
    assert run(["--root", root, "doctor", "--json"]) == 1
    data = payload(capsys.readouterr().out, "{")
    assert {c["id"]: c for c in data["checks"]}["commands"]["ok"] is False


def test_env_set_warns_when_agent_file_missing(tmp_path, capsys):
    """A command template without {agent_file}/{prompt} is reported at `env set` time."""
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    assert run(["--root", root, "env", "set", "agents.commands.researcher=pi --model {model} {prompt}"]) == 0
    assert "missing {agent_file}" in capsys.readouterr().out


def test_skills_list_expansion(tmp_path):
    from rh import config, spawn
    env = config.deep_merge(config.DEFAULT_ENV, {"agents": {
        "commands": {"default": "pi --skill {skills:list} --prompt-file {prompt_file}"},
        "skills": ["a", "b"]}})
    plan = spawn.launch_plan(tmp_path, env, "writer", "hi", tmp_path / "p.md")
    assert plan["argv"] == ["pi", "--skill", "a", "b", "--prompt-file", str(tmp_path / "p.md")]


def test_agent_file_contents_placeholder(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    run(["--root", root, "agents", "researcher", "--write"])
    run(["--root", root, "env", "set",
         "agents.commands.researcher=pi --system {agent_file_contents} --prompt-file {prompt_file}"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do S01", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert "# RESEARCHER agent" in " ".join(data["argv"])


def test_checklist_v2_content_items(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    data = checklist.build_checklist(tmp_path)
    ids = {i["id"] for i in data["items"]}
    assert {"content-status-header", "content-plan-verify", "content-lit-doi", "content-one-layout"} <= ids


def test_gate_check_and_log_tail_and_handoff(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    assert run(["--root", root, "gate", "check", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert "phase" in data and "ok" in data
    assert run(["--root", root, "log", "tail", "--json"]) == 0
    assert run(["--root", root, "handoff", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert (tmp_path / ".rh" / "HANDOFF.md").exists()


def test_agent_status_empty(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    capsys.readouterr()
    assert run(["--root", root, "agent", "status", "--json"]) == 0
    assert payload(capsys.readouterr().out, "[") == []


def test_budget_enforcement(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init"])
    run(["--root", root, "env", "set", "agents.count=1",
         "agents.commands.researcher=pi --model {model} --system-prompt-file {agent_file} --prompt-file {prompt_file}"])
    # pre-seed one alive entry
    import json as _json
    import os
    f = tmp_path / ".rh" / "logs" / "spawns.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_json.dumps({"role": "researcher", "pid": os.getpid(), "mode": "background", "model": "m", "source": "x", "ts": "t"}) + "\n")
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do S01", "--dry-run"]) == 1
    assert "agents.count" in capsys.readouterr().err
    assert run(["--root", root, "spawn", "researcher", "do S01", "--dry-run", "--force"]) == 0


def test_background_spawn_is_recorded_and_budgeted(tmp_path, capsys):
    """A real spawn must land in spawns.jsonl, or `rh agent status` and the
    agents.count budget are dead weight."""
    import json as _json
    import os
    import signal
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "agents", "researcher", "--write"])
    run(["--root", root, "env", "set", "agents.count=1", "agents.commands.researcher=/bin/sleep 30"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do S01"]) == 0
    recs = [_json.loads(l) for l in (tmp_path / ".rh" / "logs" / "spawns.jsonl").read_text().splitlines()]
    assert recs and recs[-1]["role"] == "researcher" and recs[-1]["mode"] == "background"
    pid = recs[-1]["pid"]
    try:
        assert spawn.running_count(tmp_path) == 1
        capsys.readouterr()
        assert run(["--root", root, "spawn", "researcher", "do S02"]) == 1
        assert "agents.count" in capsys.readouterr().err
        assert run(["--root", root, "agent", "status", "--json"]) == 0
        assert payload(capsys.readouterr().out, "[")[-1]["pid"] == pid
    finally:
        os.kill(pid, signal.SIGTERM)


def test_init_is_non_destructive_without_force(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "env.json").write_text("sentinel")
    capsys.readouterr()
    assert run(["--root", root, "init", "--non-interactive"]) == 1
    assert "refusing to overwrite" in capsys.readouterr().err
    assert (tmp_path / ".rh" / "env.json").read_text() == "sentinel"


def test_init_force_archives_to_bak(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "env.json").write_text("sentinel")
    capsys.readouterr()
    assert run(["--root", root, "init", "--non-interactive", "--force"]) == 0
    baks = list((tmp_path / ".rh" / ".bak").rglob("env.json"))
    assert baks and baks[0].read_text() == "sentinel"


def test_init_dry_run_writes_nothing(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--dry-run", "--json"])
    data = payload(capsys.readouterr().out, "{")
    assert data["dry_run"] is True
    assert not (tmp_path / ".rh").exists()


def test_init_never_touches_existing_plan(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    plan = tmp_path / "PLAN.md"
    plan.write_text("### S01 — user plan\n")
    capsys.readouterr()
    assert run(["--root", root, "init", "--non-interactive", "--force"]) == 0
    assert plan.read_text() == "### S01 — user plan\n"
    out = capsys.readouterr().out
    assert "PLAN.md already exists" in out


def test_init_questionnaire_skips_are_orchestrator_job(tmp_path):
    # stdin not a tty (pytest) → the questionnaire is skipped without asking
    root = str(tmp_path)
    assert run(["--root", root, "init"]) == 0
    assert (tmp_path / ".rh").is_dir()


def test_init_questionnaire_skip_writes_nothing(tmp_path, capsys, monkeypatch):
    """`s` means skip: the key is left alone, not written as the string "s"."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "env", "set", "agents.backend=tuios", "agents.cli=pi",
         "agents.skills=research-helper,tuios"])
    before = config.load_env(tmp_path)
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: "s")
    assert run(["--root", root, "init", "--force"]) == 0
    after = config.load_env(tmp_path)
    assert after["project"]["name"] == tmp_path.name
    assert after["agents"]["backend"] == "tuios"
    assert after["agents"]["cli"] == "pi"
    assert after["agents"]["skills"] == before["agents"]["skills"]
    assert after["agents"]["skills"] != ["s"]
    assert after["agents"]["backend"] != "s" and after["agents"]["split"] != "s"
    assert not config.validate(after)


def test_init_questionnaire_enter_keeps_existing_config(tmp_path, capsys, monkeypatch):
    """Defaults come from ENV.md, so Enter never downgrades a configured project."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "env", "set", "agents.count=3", "agents.backend=tuios",
         "agents.cli=pi", "agents.skills=research-helper,tuios", "agents.split=vertical"])
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert run(["--root", root, "init", "--force"]) == 0
    env = config.load_env(tmp_path)
    assert env["project"]["name"] == tmp_path.name
    assert env["agents"]["count"] == 3
    assert env["agents"]["backend"] == "tuios"
    assert env["agents"]["cli"] == "pi"
    assert env["agents"]["skills"] == ["research-helper", "tuios"]
    assert env["agents"]["split"] == "vertical"


def test_init_questionnaire_ctrl_c_stops_asking(tmp_path, capsys, monkeypatch):
    calls = {"n": 0}

    def fake_input(*a):
        calls["n"] += 1
        if calls["n"] == 1:
            return "demo"
        raise KeyboardInterrupt

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", fake_input)
    assert run(["--root", str(tmp_path), "init"]) == 0
    assert config.load_env(tmp_path)["project"]["name"] == "demo"
    assert calls["n"] == 2  # Ctrl-C ends the questionnaire, it does not continue it


def test_old_project_slug_key_is_read_as_name(tmp_path, capsys):
    """env.json written before the rename still reports its project name."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "env.json").write_text('{"project": {"slug": "old-name"}}\n')
    capsys.readouterr()
    assert run(["--root", root, "status", "--json"]) == 0
    assert payload(capsys.readouterr().out, "{")["name"] == "old-name"
    # a write migrates the key in place
    run(["--root", root, "env", "set", "agents.count=2"])
    text = (tmp_path / ".rh" / "env.json").read_text()
    assert "project.slug" not in text
    assert "old-name" in text


def test_init_clean_archives_the_whole_rh_dir_first(tmp_path, capsys):
    """--clean must never delete what it could not archive (logs, notes, config)."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "logs" / "2026-01-01-x.md").write_text("# event log\n")
    (tmp_path / ".rh" / "env.json").write_text('{"project": {"name": "keep"}}\n')
    (tmp_path / ".rh" / "ENVIRONMENT.md").write_text("## Environment\n\n- keep 1.0\n")
    capsys.readouterr()
    assert run(["--root", root, "init", "--clean", "--non-interactive"]) == 0
    baks = list((tmp_path / ".rh" / ".bak").glob("*/env.json"))
    assert baks and "keep" in baks[0].read_text()
    assert list((tmp_path / ".rh" / ".bak").glob("*/logs/2026-01-01-x.md"))
    assert (tmp_path / ".rh" / "env.json").exists()  # recreated, not missing


def test_init_clean_force_archives_too(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "logs" / "keep.md").write_text("log\n")
    capsys.readouterr()
    assert run(["--root", root, "init", "--clean", "--force", "--non-interactive"]) == 0
    assert list((tmp_path / ".rh" / ".bak").glob("*/logs/keep.md"))


def test_repeated_clean_keeps_earlier_archives(tmp_path, capsys):
    """Each --clean re-creates .rh/; the archives of earlier cleans must survive."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "logs" / "one.md").write_text("1\n")
    capsys.readouterr()
    assert run(["--root", root, "init", "--clean", "--non-interactive"]) == 0
    (tmp_path / ".rh" / "logs" / "two.md").write_text("2\n")
    assert run(["--root", root, "init", "--clean", "--non-interactive"]) == 0
    logs = sorted(p.name for p in (tmp_path / ".rh" / ".bak").glob("*/logs/*.md"))
    assert "one.md" in logs and "two.md" in logs


def test_backups_in_the_same_second_do_not_overwrite(tmp_path, monkeypatch):
    class FixedDT:
        @staticmethod
        def now():
            return datetime(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(paths, "datetime", FixedDT)
    f = tmp_path / "ENV.md"
    f.write_text("one")
    first = paths.backup_file(tmp_path, f)
    f.write_text("two")
    second = paths.backup_file(tmp_path, f)
    assert first != second
    assert first.read_text() == "one" and second.read_text() == "two"


def test_deep_merge_does_not_mutate_defaults(tmp_path):
    before = json.dumps(config.DEFAULT_ENV, sort_keys=True)
    env = config.load_env(tmp_path)  # no ENV.md → defaults
    config.set_nested(env, "agents.commands.coder", "pi {prompt}")
    assert json.dumps(config.DEFAULT_ENV, sort_keys=True) == before


def test_doctor_flags_missing_role_file_for_configured_role(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "env", "set",
         'agents.roles.coder={"provider":"pi","model":"m1"}',
         "agents.commands.coder=sh --system-prompt-file {agent_file} --prompt-file {prompt_file}"])
    capsys.readouterr()
    assert run(["--root", root, "doctor", "--json"]) == 1
    ids = {c["id"]: c for c in payload(capsys.readouterr().out, "{")["checks"]}
    assert ids["role-file.coder"]["ok"] is False
    run(["--root", root, "agents", "coder", "--write"])
    capsys.readouterr()
    assert run(["--root", root, "doctor", "--json"]) == 0


def test_checklist_future_phases_are_not_pending(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    capsys.readouterr()
    data = checklist.build_checklist(tmp_path)
    by_id = {i["id"]: i for i in data["items"]}
    assert by_id["phase-9"]["status"] == "later"
    assert data["pending"] == len([i for i in data["items"] if i["status"] == "pending"])


def test_checklist_accepts_bold_status_header(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    paths.artifact_path(tmp_path, "STATUS.md").write_text(
        "phase: **6 IMPLEMENT** | step: S05 | updated: 2026-11-06T06:40\n")
    capsys.readouterr()
    by_id = {i["id"]: i for i in checklist.build_checklist(tmp_path)["items"]}
    assert by_id["content-status-header"]["status"] == "ok"


def test_checklist_reports_the_missing_header_part(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    # the header is a phase-5 artifact, so the project must have got there
    (tmp_path / ".rh" / "tasks.json").write_text(
        json.dumps({"version": 1, "project_name": "", "current_phase": 6, "tasks": []}))
    paths.artifact_path(tmp_path, "STATUS.md").write_text("phase: 6 IMPLEMENT | step: S05\n")
    capsys.readouterr()
    by_id = {i["id"]: i for i in checklist.build_checklist(tmp_path)["items"]}
    item = by_id["content-status-header"]
    assert item["status"] == "pending" and "updated" in item["detail"]


def test_dry_run_writes_no_prompt_files(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "agents", "researcher", "--write"])
    run(["--root", root, "env", "set",
         "agents.commands.researcher=pi --system-prompt-file {agent_file} --prompt-file {prompt_file}",
         "agents.commands.orchestrator=pi --system-prompt-file {agent_file} --prompt-file {prompt_file}"])
    capsys.readouterr()
    assert run(["--root", root, "spawn", "researcher", "do it", "--dry-run"]) == 0
    assert run(["--root", root, "resume", "--dry-run"]) == 0
    assert not (tmp_path / ".rh" / "resume-prompt.md").exists()
    assert not list((tmp_path / ".rh" / "tmp").glob("spawn-*-prompt.md"))


def test_plan_import_is_read_only_for_plan(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--non-interactive"])
    plan = root / ".rh" / "PLAN.md"
    plan.write_text("### S01 — steps\nowner: researcher | deliverable: `x`\n", encoding="utf-8")
    before = plan.read_text()
    tasks.import_plan_md(root)
    assert plan.read_text() == before


def test_init_creates_role_files_and_orchestrator_checklist(tmp_path, capsys):
    """`rh init` leaves the orchestrator with a job description and a to-do list."""
    root = str(tmp_path)
    assert run(["--root", root, "init", "--non-interactive"]) == 0
    agents_dir = tmp_path / ".rh" / "agents"
    assert (agents_dir / "orchestrator.md").exists()
    assert {"orchestrator", "researcher", "critique", "reviewer"} <= {p.stem for p in agents_dir.glob("*.md")}
    text = (agents_dir / "orchestrator.md").read_text()
    assert "ORCHESTRATOR agent" in text and "May not: implement" in text

    checklist = tmp_path / ".rh" / "CHECKLIST.md"
    assert checklist.exists()
    body = checklist.read_text()
    assert "## Setup tasks" in body
    assert ".rh/ENVIRONMENT.md" in body           # ask the user for the environment
    assert "agents.commands" in body              # wire the launch commands
    assert "workflow.mmd" in body                 # author it after the plan
    assert "[ ]" in body                          # pending work is visible


def test_init_applies_the_chosen_harness_template(tmp_path, capsys, monkeypatch):
    """The harness answer from the questionnaire fills the launch commands."""
    answers = iter(["", "", "", "", "", "", "pi"])  # ..., harness = pi
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    root = str(tmp_path)
    capsys.readouterr()
    assert run(["--root", root, "init"]) == 0
    env = config.load_env(tmp_path)
    assert env["agents"]["cli"] == "pi"
    cmd = env["agents"]["commands"]["orchestrator"]
    assert cmd.startswith("pi ") and "{agent_file}" in cmd and "{prompt}" in cmd
    assert "--append-system-prompt" in cmd          # append, never replace
    assert "--skill" not in cmd                     # orchestrator needs every skill
    assert "--prompt-file" not in cmd and "--prompt-template" not in cmd
    # and the file is on disk for the next session
    assert (tmp_path / ".rh" / "agents" / "orchestrator.md").exists()
    # the orchestrator gets no skill restriction, so rh must not nag about it
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][-1].startswith("Load the `research-helper` skill")
    assert not any("not restricted" in n for n in data["notes"])


def test_legacy_env_md_is_migrated_not_leaked(tmp_path, capsys):
    """An old .rh/ENV.md becomes env.json + ENVIRONMENT.md, and is archived."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    (tmp_path / ".rh" / "env.json").unlink()
    (tmp_path / ".rh" / "ENV.md").write_text(
        '```json\n{"project": {"name": "legacy"}, "agents": {"count": 3}}\n```\n\n'
        "## Environment\n\n- meep 1.29.0\n")
    capsys.readouterr()
    assert run(["--root", root, "status", "--json"]) == 0
    assert payload(capsys.readouterr().out, "{")["name"] == "legacy"
    assert json.loads((tmp_path / ".rh" / "env.json").read_text())["agents"]["count"] == 3
    assert "meep 1.29.0" in (tmp_path / ".rh" / "ENVIRONMENT.md").read_text()
    assert not (tmp_path / ".rh" / "ENV.md").exists()
    assert list((tmp_path / ".rh" / ".bak").rglob("ENV.md"))  # archived, never deleted


def test_checklist_write_refreshes_the_file(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    paths.artifact_path(tmp_path, "STATUS.md").write_text("phase: 0 CONFIG | step: S01 | updated: now\n")
    capsys.readouterr()
    dest, data = checklist.write_checklist(tmp_path)
    assert str(dest).endswith(".rh/CHECKLIST.md")
    assert "- [x]" in dest.read_text()


def test_resume_falls_back_to_the_role_file_when_no_template(tmp_path, capsys):
    """With only agents.cli set, the role file still reaches the harness."""
    root = str(tmp_path)
    run(["--root", root, "init", "--non-interactive"])
    run(["--root", root, "env", "set", "agents.cli=sh",
         'agents.roles.orchestrator={"provider":"x","model":"m"}'])
    capsys.readouterr()
    assert run(["--root", root, "resume", "--dry-run", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["argv"][0] == "sh"
    assert "ORCHESTRATOR agent" in data["prompt"]
    assert "Load the `research-helper` skill" in data["prompt"]


def test_init_questionnaire_renders_shortcuts_and_q_finishes(tmp_path, capsys, monkeypatch):
    """The wizard shows the keys; `q` finishes with the answers collected so far."""
    answers = iter(["demo", "q"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    root = str(tmp_path)
    capsys.readouterr()
    assert run(["--root", root, "init"]) == 0
    out = capsys.readouterr().out
    assert "keys" in out and "tab" in out and "ctrl-c" in out
    assert "1/7" in out
    env = config.load_env(tmp_path)
    assert env["project"]["name"] == "demo"
    assert env["agents"]["count"] == 1  # never asked: q stopped the cycle


def test_init_questionnaire_other_accepts_a_custom_binary(tmp_path, capsys, monkeypatch):
    """Choosing `other` opens a free-text prompt for a binary that is not detected."""
    answers = iter(["", "", "", "other", "mycli", "", "", ""])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    root = str(tmp_path)
    capsys.readouterr()
    assert run(["--root", root, "init"]) == 0
    out = capsys.readouterr().out
    assert "1)" in out and "other — type it" in out  # numbered options, not free text only
    assert config.load_env(tmp_path)["agents"]["cli"] == "mycli"


def test_bad_usage_falls_back_to_full_help(capsys):
    """A wrong command/flag shows the same text as `--help`, not just a usage line."""
    assert run(["nope"]) == 2
    out = capsys.readouterr()
    assert out.err == ""  # no "error: invalid choice" line
    assert "usage: rh" in out.out and "init" in out.out and "handoff" in out.out


def test_help_and_version_exit_zero(capsys):
    assert run(["--help"]) == 0
    assert "init" in capsys.readouterr().out
    assert run(["--version"]) == 0
    assert "rh " in capsys.readouterr().out


def test_no_command_shows_help(capsys):
    assert run([]) == 2
    assert "usage: rh" in capsys.readouterr().out
