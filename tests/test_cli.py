import json

from rh import cli


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


def test_env_set_and_show(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "env", "set", "literature.search=mytool"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "env", "show", "--json"]) == 0
    data = payload(capsys.readouterr().out, "{")
    assert data["literature"]["search"] == "mytool"


def test_env_notes_preserved(tmp_path):
    root = tmp_path
    run(["--root", str(root), "init", "--slug", "demo"])
    env_md = root / "ENV.md"
    env_md.write_text(env_md.read_text() + "\n## Environment\n\n- custom tool 1.0\n")
    run(["--root", str(root), "env", "set", "project.git=true"])
    text = env_md.read_text()
    assert "## Environment" in text
    assert "custom tool 1.0" in text


def test_add_task_and_list(tmp_path, capsys):
    root = str(tmp_path)
    run(["--root", root, "init", "--slug", "demo"])
    assert run(["--root", root, "add", "task", "do it", "--id", "S01"]) == 0
    capsys.readouterr()
    assert run(["--root", root, "task", "list", "--json"]) == 0
    data = payload(capsys.readouterr().out, "[")
    assert data[0]["id"] == "S01"


def test_skill_install(tmp_path):
    dest = tmp_path / "skills" / "research-helper"
    assert run(["skill", "install", "--dest", str(dest)]) == 0
    skill = dest / "SKILL.md"
    assert skill.exists()
    assert "research-helper" in skill.read_text(encoding="utf-8")[:2000]
