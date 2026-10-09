import json
import os
import subprocess

import pytest

from conftest import git_repo, write_project
from engine import flow, jev
from engine.workspace import CONTEXT_DIR, EaseError, load_state

PASS = '```json\n{"verdict": "pass", "findings": []}\n```'


def plan_report(*repos):
    """A planner report with one task per repo name."""
    tasks = [
        {"title": f"Task in {repo}", "repo": repo, "steps": ["do it"], "done_when": "it works"}
        for repo in repos
    ]
    return "Here is the plan.\n```json\n" + json.dumps({"summary": "A plan", "tasks": tasks}) + "\n```"


def send(ws, text):
    """Reply to the newest run, loading its state from disk like the CLI does."""
    return flow.reply(ws, load_state(ws), text)


def ask(ws):
    """Ask the newest run what to do next."""
    return flow.next_action(ws, load_state(ws))


def last_prompt(ws):
    prompts = sorted((ws / CONTEXT_DIR / "runs").glob("*/prompts/*.md"))
    return prompts[-1].read_text()


def start_run(ws, repos=("app",)):
    """Start a run and get it planned. It stops at the approve step."""
    flow.start(ws, None, "Add a thing")
    send(ws, plan_report(*repos))


def start_building(ws, repos=("app",)):
    """Start a run, plan it and approve it. It stops at the first build step."""
    start_run(ws, repos)
    send(ws, "approve")


def branch_of(path):
    done = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def fake_gh(tmp_path_factory, monkeypatch):
    """Put a fake `gh` first on PATH. It answers `gh issue view` and `gh pr create`."""
    folder = tmp_path_factory.mktemp("bin")
    script = folder / "gh"
    script.write_text(
        "#!/bin/sh\n"
        """if [ "$1" = issue ]; then echo '{"title": "Fix login", "body": "It breaks"}'; fi\n"""
        """if [ "$1" = pr ]; then echo "https://github.com/me/app/pull/7"; echo "Warning: 1 uncommitted change" >&2; fi\n"""
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")


def test_start_with_default_project(ws):
    flow.start(ws, None, "Add a login page\n\nWith a form.\n")
    state = load_state(ws)
    assert state.project == "demo"
    assert state.ticket_title == "Add a login page"
    assert state.ticket_body == "Add a login page\n\nWith a form."
    assert state.branch == "ease/add-a-login-page"
    assert state.step == "plan"


def test_start_with_project_name(ws):
    write_project(ws, "other", {"app": {"path": "app", "checks": "true"}})
    flow.start(ws, "other", "Fix the bug")
    state = load_state(ws)
    assert state.project == "other"
    assert state.ticket_title == "Fix the bug"


def test_start_from_issue_number(ws, fake_gh):
    flow.start(ws, None, "12")
    state = load_state(ws)
    assert state.ticket_title == "#12 Fix login"
    assert state.ticket_body == "It breaks"


def test_happy_path(ws):
    start_run(ws)
    assert load_state(ws).step == "approve"
    assert "Task in app" in ask(ws)["message"]
    assert "no score" in ask(ws)["message"]

    send(ws, "Approve.")  # the words are compared without case and end punctuation
    state = load_state(ws)
    assert branch_of(ws / "app") == "ease/add-a-thing"
    assert state.bases == {"app": "main"}
    assert ask(ws)["agent"] == "ease:worker"

    (ws / "app" / "ok.txt").write_text("done")  # what the worker does
    send(ws, "Built it.")
    assert load_state(ws).checks_ok is True

    result = send(ws, PASS)
    assert result["decision"] == "accept"
    state = load_state(ws)
    assert state.step == "done"
    assert state.outcome == "done"
    assert state.prs == ["app: branch ease/add-a-thing (no GitHub remote, no PR)"]
    assert "Outcome: done" in ask(ws)["summary"]


def test_failed_checks_lead_to_fix(ws):
    start_building(ws)  # the worker writes nothing, so the checks fail
    send(ws, "Built it.")
    assert load_state(ws).checks_ok is False

    assert send(ws, PASS)["decision"] == "fix"
    state = load_state(ws)
    assert state.step == "build"
    assert state.attempt == 2
    assert state.problems[0].startswith("Checks failed")

    ask(ws)
    assert "Checks failed" in last_prompt(ws)


def test_three_failed_attempts_escalate(ws):
    start_building(ws)
    decisions = []
    for _ in range(3):
        send(ws, "Built it.")
        decisions.append(send(ws, PASS)["decision"])
    assert decisions == ["fix", "fix", "escalate"]
    assert load_state(ws).outcome == "escalated"
    assert "Checks failed" in ask(ws)["summary"]  # the summary lists the problems


def test_change_notes_keep_the_plan(ws):
    start_run(ws)
    send(ws, "split task 1")
    state = load_state(ws)
    assert state.step == "plan"
    assert state.tasks[0].title == "Task in app"

    ask(ws)
    prompt = last_prompt(ws)
    assert "Task in app" in prompt  # the planner sees the plan the notes change
    assert "split task 1" in prompt


def test_cancel(ws):
    start_run(ws)
    send(ws, "cancel")
    state = load_state(ws)
    assert state.step == "done"
    assert state.outcome == "cancelled"


def test_empty_reply_is_an_error(ws):
    start_run(ws)
    with pytest.raises(EaseError, match="empty reply"):
        send(ws, "  \n")
    assert load_state(ws).step == "approve"


def test_bad_planner_report_leaves_state_unchanged(ws):
    flow.start(ws, None, "Add a thing")
    before = load_state(ws)

    with pytest.raises(EaseError, match="```json"):
        send(ws, "I made a plan but forgot the JSON.")
    with pytest.raises(EaseError, match="repo must be one of"):
        send(ws, plan_report("nonexistent"))

    assert load_state(ws) == before


def test_repo_must_be_a_git_top_folder(ws):
    (ws / "app" / "sub").mkdir()
    write_project(ws, "demo", {"app": {"path": "app/sub", "checks": "true"}})
    start_run(ws)

    with pytest.raises(EaseError, match="not the top folder of a git repo"):
        send(ws, "approve")
    assert load_state(ws).step == "approve"


def test_dirty_repo_blocks_approve(ws):
    start_run(ws)
    (ws / "app" / "unsaved.txt").write_text("work in progress")

    with pytest.raises(EaseError, match="uncommitted changes"):
        send(ws, "approve")

    assert load_state(ws).step == "approve"
    assert branch_of(ws / "app") == "main"


def test_existing_branch_blocks_approve(ws):
    subprocess.run(["git", "branch", "ease/add-a-thing"], cwd=ws / "app", check=True)
    start_run(ws)

    with pytest.raises(EaseError, match="already exists"):
        send(ws, "approve")
    assert load_state(ws).step == "approve"


def test_reviewer_fail_needs_a_finding(ws):
    start_building(ws)
    send(ws, "Built it.")

    with pytest.raises(EaseError, match="at least one finding"):
        send(ws, '```json\n{"verdict": "fail", "findings": []}\n```')
    assert load_state(ws).step == "review"


def test_jev_is_shadow_only(ws, monkeypatch):
    (ws / CONTEXT_DIR / "config.json").write_text(
        json.dumps({"default_project": "demo", "typesafe_api_key": "secret"})
    )

    def fake_post(key, body):
        if "plan_quality" in body["questions"]:
            return {"answers": {"plan_quality": {"score": 4.2, "confidence": 0.81}}}
        return {"answers": {"next_action": {"choice": "fix", "confidence": 0.7}}}

    monkeypatch.setattr(jev, "post", fake_post)

    start_run(ws)
    assert "Jev: plan score 4.2/5 (confidence 0.81)" in ask(ws)["message"]
    send(ws, "approve")
    (ws / "app" / "ok.txt").write_text("done")
    send(ws, "Built it.")
    send(ws, PASS)

    state = load_state(ws)
    assert state.outcome == "done"  # Jev said fix, but the code rule decided
    decision = state.log[-1]
    assert decision.code == "accept"
    assert decision.jev == "fix"
    assert "agreed with the code rule on 0 of 1" in ask(ws)["summary"]


def test_two_tasks_in_two_repos(ws):
    git_repo(ws / "api")
    write_project(ws, "demo", {
        "app": {"path": "app", "checks": "test -f ok.txt"},
        "api": {"path": "api", "checks": "true"},
    })
    start_building(ws, repos=("app", "api"))
    assert load_state(ws).bases == {"app": "main", "api": "main"}

    (ws / "app" / "ok.txt").write_text("done")
    send(ws, "Built task 1.")
    assert send(ws, PASS)["decision"] == "accept"

    state = load_state(ws)
    api_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ws / "api", capture_output=True, text=True
    ).stdout.strip()
    assert state.step == "build"
    assert state.task == 1
    assert state.task_start == api_head

    ask(ws)
    assert str(ws / "api") in last_prompt(ws)


def test_pr_is_opened_when_there_is_a_remote(ws, tmp_path_factory, fake_gh):
    remote = tmp_path_factory.mktemp("remote")
    subprocess.run(["git", "init", "--bare"], cwd=remote, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)], cwd=ws / "app", check=True, capture_output=True
    )

    start_building(ws)
    (ws / "app" / "ok.txt").write_text("done")
    send(ws, "Built it.")
    send(ws, PASS)

    # gh prints a warning after the URL; the URL is still what we keep
    assert load_state(ws).prs == ["app: https://github.com/me/app/pull/7"]
