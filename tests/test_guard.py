import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import git_repo

GUARD = Path(__file__).resolve().parent.parent / "pilot" / "guard.py"


@pytest.fixture
def repo(tmp_path):
    """A git repo on `main`, with `main` and `dev` listed as shared branches in the config."""
    path = tmp_path / "work" / "app"
    git_repo(path)
    config = {
        "shared_branches": {str(path): ["main", "dev"]},
        "prod_markers": ["asado-prod", "prod-db.example.com"],
        "blocked_tools": ["mcp__slack__*"],
    }
    (tmp_path / "workspaces.json").write_text(json.dumps(config))
    return path


def switch(repo, branch):
    subprocess.run(["git", "switch", "-c", branch], cwd=repo, check=True, capture_output=True)


def run_guard(repo, event, *extra):
    args = [sys.executable, str(GUARD), "--config", str(repo.parent.parent / "workspaces.json"), *extra]
    return subprocess.run(args, input=json.dumps(event), capture_output=True, text=True)


def guard(repo, command, cwd=None, own_prefix=None, approvals=None):
    extra = []
    if own_prefix:
        extra += ["--own-prefix", own_prefix]
    if approvals:
        extra += ["--approvals", str(approvals)]
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or repo)}
    return run_guard(repo, event, *extra)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 3",
        "gh pr comment 3 --body hi",
        "gh pr review 3 --approve",
        "gh issue comment 7 --body hi",
        "gh api -X POST repos/o/r/issues/1/comments -f body=hi",
        "gh api -XPATCH repos/o/r/pulls/comments/5 -f body=hi",
        "gh api --method PUT repos/o/r/pulls/1/merge",
        "gh api --method=DELETE repos/o/r/pulls/1/reviews/2",
        "gh api repos/o/r/issues/1/comments -f body=hi",
        "gh api repos/o/r/issues/1/comments -F body=@x",
        "gh api repos/o/r/issues/1/comments --input file.json",
        "git merge feature",
        "git push origin -f",
        "git push --force origin feature",
        "git push --force-with-lease origin feature",
        "git push --force-with-lease=feature:abc origin feature",
        "git push origin +feature",
        "git push --delete origin feature",
        "git push -d origin feature",
        "git push origin :feature",
        "git push origin feature:main",
        "git push origin dev",
        "git push",
        "git push origin",
        "git branch -D feature",
        "git branch --delete --force feature",
        "psql -h asado-prod -U me",
        "pg_dump postgresql://me@prod-db.example.com/db",
        "mysql --host=prod-db.example.com",
        "mongosh mongodb://asado-prod/db",
        "cloud-sql-proxy proper-base:us-west1:asado-prod",
        "cd app && git push -f",
        "GH_TOKEN=x gh pr merge 3",
        "env GH_TOKEN=x gh pr merge 3",
        'git push origin "main"',
        "echo ok; git push origin main",
        "git status | gh pr merge 3",
    ],
)
def test_blocks_ask_juan_actions(repo, command):
    cwd = repo.parent if command.startswith("cd app") else repo
    result = guard(repo, command, cwd=cwd)
    assert result.returncode == 2, result.stderr
    assert result.stderr.startswith("ASK JUAN:")
    assert result.stderr.count("\n") == 1
    assert "Log the exact action as an ASK JUAN entry in your decisions file and do not retry it." in result.stderr


def test_blocks_branch_delete_outside_own_prefix(repo):
    result = guard(repo, "git branch -D someone-else", own_prefix="ease/run-1")
    assert result.returncode == 2
    assert result.stderr.startswith("ASK JUAN:")


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin my-branch",
        "gh pr create --title x --body y",
        "gh pr view 3",
        "gh api repos/o/r/pulls/1/comments",
        "gh api repos/o/r/pulls/1",
        "psql -h localhost -U me",
        "git status && git log --oneline",
    ],
)
def test_allows_other_commands(repo, command):
    result = guard(repo, command)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.parametrize("command", ["git push", "git merge main", "git push origin HEAD"])
def test_allows_push_and_merge_on_a_non_shared_branch(repo, command):
    switch(repo, "my-branch")
    result = guard(repo, command)
    assert result.returncode == 0, result.stderr


def test_allows_branch_delete_with_own_prefix(repo):
    result = guard(repo, "git branch -D ease/run-1-task", own_prefix="ease/run-1")
    assert result.returncode == 0, result.stderr


def test_allows_push_outside_a_git_repo(repo, tmp_path):
    result = guard(repo, "git push", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_lets_unparseable_command_through_with_a_note(repo):
    result = guard(repo, 'git push origin "main')
    assert result.returncode == 0
    assert result.stderr.startswith("guard:")


def test_missing_config_asks_juan(repo, tmp_path):
    args = [sys.executable, str(GUARD), "--config", str(tmp_path / "missing.json")]
    event = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(repo)}
    result = subprocess.run(args, input=json.dumps(event), capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stderr.startswith("ASK JUAN: guard error")
    assert result.stderr.count("\n") == 1


def test_error_inside_a_check_asks_juan_and_never_exits_1(repo):
    config = repo.parent.parent / "workspaces.json"
    config.write_text(json.dumps({**json.loads(config.read_text()), "prod_markers": 5}))
    result = guard(repo, "psql -h asado-prod")
    assert result.returncode != 1
    assert result.returncode == 2
    assert result.stderr.startswith("ASK JUAN: guard error")


def test_ignores_other_tools(repo):
    result = run_guard(repo, {"tool_name": "Read", "tool_input": {"file_path": "/x"}, "cwd": str(repo)})
    assert result.returncode == 0


def test_blocks_tools_matching_blocked_tools(repo):
    result = run_guard(repo, {"tool_name": "mcp__slack__send_message", "tool_input": {}, "cwd": str(repo)})
    assert result.returncode == 2
    assert result.stderr.startswith("ASK JUAN: mcp__slack__send_message")
    assert result.stderr.count("\n") == 1


def test_allows_tools_not_in_blocked_tools(repo):
    result = run_guard(repo, {"tool_name": "mcp__jira__get_issue", "tool_input": {}, "cwd": str(repo)})
    assert result.returncode == 0, result.stderr


def test_approval_lets_the_exact_command_through_once(repo, tmp_path):
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps(["gh pr merge 3", "gh pr merge 4"]))
    assert guard(repo, "gh pr merge 3", approvals=approvals).returncode == 0
    assert json.loads(approvals.read_text()) == ["gh pr merge 4"]
    assert guard(repo, "gh pr merge 3", approvals=approvals).returncode == 2


def test_approval_does_not_cover_a_different_command(repo, tmp_path):
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps(["gh pr merge 3"]))
    result = guard(repo, "gh pr merge 5", approvals=approvals)
    assert result.returncode == 2
    assert json.loads(approvals.read_text()) == ["gh pr merge 3"]


@pytest.mark.parametrize("content", [None, ""])
def test_missing_or_empty_approvals_file_approves_nothing(repo, tmp_path, content):
    approvals = tmp_path / "approvals.json"
    if content is not None:
        approvals.write_text(content)
    assert guard(repo, "gh pr merge 3", approvals=approvals).returncode == 2
