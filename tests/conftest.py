"""Shared fixtures. Tests use real git inside tmp_path and never touch the network."""
import json
import subprocess

import pytest

from engine import jev


def git_repo(path):
    """Make a git repo at `path` with one commit, on branch main."""
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-b", "main"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.com"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=path, check=True, capture_output=True)


def write_project(ws, name, repos):
    """Write .ease-context/projects/<name>/project.json. `repos` is {repo: {"path", "checks"}}."""
    folder = ws / ".ease-context" / "projects" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.json").write_text(json.dumps({"repos": repos}))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """If any test reaches the real Jev call, it fails (ask() turns that into None)."""

    def refuse(key, body):
        raise AssertionError("tests must not call the network")

    monkeypatch.setattr(jev, "post", refuse)


@pytest.fixture
def ws(tmp_path):
    """A workspace with project `demo` (one repo, `app`) and `app/` as a git repo."""
    context = tmp_path / ".ease-context"
    context.mkdir()
    (context / "config.json").write_text(json.dumps({"default_project": "demo"}))
    write_project(tmp_path, "demo", {"app": {"path": "app", "checks": "test -f ok.txt"}})
    git_repo(tmp_path / "app")
    return tmp_path
