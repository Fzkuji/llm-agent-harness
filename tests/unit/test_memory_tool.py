from pathlib import Path

from openprogram.tools.memory import memory


def test_memory_defaults_to_profile_global_store(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".openprogram").mkdir(parents=True)
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENPROGRAM_MEMORY_FILE", raising=False)
    monkeypatch.delenv("OPENPROGRAM_MEMORY_SCOPE", raising=False)
    monkeypatch.delenv("OPENPROGRAM_PROFILE", raising=False)
    monkeypatch.chdir(project)

    out = memory.execute(action="set", key="k", value="v")

    global_path = home / ".agentic" / "memory" / "memory.json"
    project_path = project / ".openprogram" / "memory.json"
    assert str(global_path) in out
    assert global_path.exists()
    assert not project_path.exists()


def test_memory_project_scope_is_explicit(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENPROGRAM_MEMORY_SCOPE", "project")
    monkeypatch.delenv("OPENPROGRAM_MEMORY_FILE", raising=False)
    monkeypatch.delenv("OPENPROGRAM_PROFILE", raising=False)
    monkeypatch.chdir(project)

    out = memory.execute(action="set", key="k", value="v")

    project_path = project / ".openprogram" / "memory.json"
    global_path = home / ".agentic" / "memory" / "memory.json"
    assert str(project_path) in out
    assert project_path.exists()
    assert not global_path.exists()


def test_memory_file_override_wins(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    override = tmp_path / "custom" / "memory.json"
    home.mkdir()
    project.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENPROGRAM_MEMORY_FILE", str(override))
    monkeypatch.setenv("OPENPROGRAM_MEMORY_SCOPE", "project")
    monkeypatch.delenv("OPENPROGRAM_PROFILE", raising=False)
    monkeypatch.chdir(project)

    out = memory.execute(action="set", key="k", value="v")

    assert str(override) in out
    assert override.exists()
    assert not (project / ".openprogram" / "memory.json").exists()

