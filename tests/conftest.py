"""Shared fixtures. Tests use real git inside tmp_path and never touch the network."""
import json
import os
import subprocess
import sys

import pytest

from engine import jev

SCRIPTED_GH = """#!{python}
import json, pathlib, sys

folder = pathlib.Path(__file__).parent
argv = sys.argv[1:]
with open(folder / "calls.jsonl", "a") as log:
    log.write(json.dumps(argv) + "\\n")
call = " ".join(argv)
for answer in json.loads((folder / "answers.json").read_text()):
    if answer["match"] in call:
        out = answer.get("stdout", "")
        sys.stdout.write(out if isinstance(out, str) else json.dumps(out))
        sys.stderr.write(answer.get("stderr", ""))
        sys.exit(answer.get("code", 0))
sys.exit("no scripted answer for: " + call)
"""


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


class ScriptedGh:
    """What the fake `gh` answers, and the calls it got."""

    def __init__(self, folder):
        self.folder = folder
        self.answer()

    def answer(self, *answers):
        """Each answer is {"match", "stdout", "stderr", "code"}; all but match are optional and stdout may be JSON.
        A call gets the first answer whose match is in its joined argv. A call with no answer fails."""
        (self.folder / "answers.json").write_text(json.dumps(answers))

    def calls(self):
        """The argv of every call so far."""
        log = self.folder / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture
def scripted_gh(tmp_path_factory, monkeypatch):
    """Put a fake `gh` first on PATH. It answers from a JSON file and logs every argv to a file."""
    folder = tmp_path_factory.mktemp("scripted-gh")
    script = folder / "gh"
    script.write_text(SCRIPTED_GH.format(python=sys.executable))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    return ScriptedGh(folder)
