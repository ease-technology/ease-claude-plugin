import io
import json

from engine.cli import main
from engine.workspace import CONTEXT_DIR, load_state
from test_pr_comments import (
    BRANCH, PASSED, RESOLVED, checkout, cli, comment, gh_says, git_out, report, resolves, thread, threads_answer,
)

REPORT = """```json
{"summary": "A plan", "tasks": [{"title": "Do it", "repo": "app", "steps": ["x"], "done_when": "y"}]}
```"""


def output(capsys):
    """Everything printed so far must be exactly one JSON object."""
    return json.loads(capsys.readouterr().out)


def test_start_next_reply(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)

    monkeypatch.setattr("sys.stdin", io.StringIO("Add a `thing` for $USD\n"))  # the ticket
    assert main(["start", "demo"]) == 0
    run_id = output(capsys)["run_id"]
    assert load_state(ws, run_id).ticket_title == "Add a `thing` for $USD"

    assert main(["next", run_id]) == 0
    result = output(capsys)
    assert result["type"] == "spawn"
    assert result["agent"] == "ease:planner"

    monkeypatch.setattr("sys.stdin", io.StringIO(REPORT))
    assert main(["reply", run_id]) == 0
    assert output(capsys) == {"ok": True}

    assert main(["next", run_id]) == 0
    assert output(capsys)["type"] == "ask_user"

    assert main(["runs"]) == 0
    assert output(capsys) == {"runs": [
        {"run_id": run_id, "project": "demo", "title": "Add a `thing` for $USD", "step": "approve"}
    ]}


def test_start_with_a_branch(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    monkeypatch.setattr("sys.stdin", io.StringIO("Add a thing\n"))
    assert main(["start", "--branch", "juan/joi-7-add-a-thing"]) == 0
    run_id = output(capsys)["run_id"]
    assert load_state(ws, run_id).branch == "juan/joi-7-add-a-thing"


def test_errors_are_printed_as_json(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    assert main(["next", "nope"]) == 1
    assert output(capsys) == {"error": "unknown run: nope"}

    assert main(["next"]) == 1  # the run id is required
    assert output(capsys)["error"].startswith("usage: ")

    assert main(["start", "demo", "extra"]) == 1
    assert output(capsys)["error"].startswith("usage: ")


def test_ticket_commands(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    assert main(["ticket", "runs"]) == 0
    assert output(capsys) == {"runs": []}

    monkeypatch.setattr("sys.stdin", io.StringIO("Improve the sync\n"))  # the idea
    assert main(["ticket", "start"]) == 0
    run_id = output(capsys)["run_id"]

    assert main(["ticket", "next", run_id]) == 0
    assert output(capsys)["agent"] == "ease:interviewer"

    ticket_text = "# Improve the sync\n\n## Acceptance criteria\n- AC1: When it syncs, then it is fast.\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(ticket_text))
    assert main(["ticket", "reply", run_id]) == 0
    assert output(capsys)["decision"] == "ask_you"

    assert main(["ticket", "next", run_id]) == 0
    assert output(capsys)["type"] == "ask_user"

    assert main(["ticket", "runs"]) == 0
    assert output(capsys)["runs"][0]["title"] == "Improve the sync"

    assert main(["next", run_id]) == 1  # build runs are separate
    assert output(capsys) == {"error": f"unknown run: {run_id}"}

    assert main(["ticket", "bogus"]) == 1
    assert output(capsys)["error"].startswith("usage: ")

    assert main(["ticket", "start", "--branch", "x"]) == 1  # ticket runs have no branch
    assert output(capsys)["error"].startswith("usage: ")


def test_a_stopped_pr_comments_run_continues_from_its_saved_step(ws, checkout, scripted_gh, monkeypatch, capsys):  # AC5
    monkeypatch.chdir(ws)
    threads = [{**thread(f"T{n}", [comment(f"C{n}")]), "line": n} for n in range(1, 6)]
    gh_says(scripted_gh, checkout, RESOLVED, threads_answer(*threads))
    pr_head = git_out(checkout, "rev-parse", "HEAD")

    def pr(*args, stdin=""):
        """One call of the command, which reads the run from disk: nothing else is kept between calls."""
        code, result = cli(capsys, monkeypatch, ["pr-comments", *args], stdin)
        assert code == 0, result
        return result

    def answers(*pairs):
        return json.dumps({"answers": dict(pairs)})

    def worker_prompts(task):
        prompts = ws / CONTEXT_DIR / "pr-runs" / run_id / "prompts"
        return [file for file in prompts.glob("*-worker.md") if f"Task {task}/2:" in file.read_text()]

    def build_and_review(*files):
        for name in files:
            (checkout / name).write_text(name)
        assert pr("reply", run_id, stdin="Built it.") == {"ok": True}
        assert pr("next", run_id)["agent"] == "ease:reviewer"
        return pr("reply", run_id, stdin=PASSED)

    def listed(step):
        return {"runs": [{"run_id": run_id, "project": "demo", "title": "PR 7: Add a thing", "step": step}]}

    run_id = pr("start", stdin="7\n")["run_id"]
    assert pr("runs") == listed("judge")
    assert pr("next", run_id)["agent"] == "ease:thread-judge"
    assert pr("reply", run_id, stdin=report(*[(f"T{n}", "fix") for n in range(1, 6)])) == {"ok": True}

    # The first screen holds four of the five threads. The session stops once they are answered.
    first = pr("next", run_id)["questions"]
    assert [question["header"] for question in first] == ["Thread 1", "Thread 2", "Thread 3", "Thread 4"]
    words = ["Fix (Recommended)", "Skip not needed", "Skip not needed", "Skip not needed"]
    sent = answers(*[(question["question"], word) for question, word in zip(first, words)])
    assert pr("reply", run_id, stdin=sent) == {"ok": True, "rejected": []}

    # A new session asks only about the thread left.
    assert pr("runs") == listed("answer")
    second = pr("next", run_id)
    assert [question["header"] for question in second["questions"]] == ["Thread 5"]
    assert not any(f"Thread {n}:" in second["message"] for n in range(1, 5))
    sent = answers((second["questions"][0]["question"], "Fix (Recommended)"))
    assert pr("reply", run_id, stdin=sent) == {"ok": True, "rejected": []}

    # The first fix finishes, and the session stops.
    assert pr("runs") == listed("build")
    assert pr("next", run_id)["agent"] == "ease:worker"
    assert len(worker_prompts(1)) == 1
    assert build_and_review("ok.txt", "first.txt")["decision"] == "accept"

    # A new session goes on to the second fix: no new prompt for the first, and nothing is asked again.
    assert pr("runs") == listed("build")
    assert pr("next", run_id)["agent"] == "ease:worker"
    assert len(worker_prompts(1)) == 1
    assert len(worker_prompts(2)) == 1
    assert build_and_review("second.txt")["decision"] == "accept"

    # The run is done, with each fix committed once and resolved once.
    assert pr("runs") == {"runs": []}
    action = pr("next", run_id)
    assert action["type"] == "done"
    assert "Outcome: pushed" in action["summary"]
    assert resolves(scripted_gh) == ["T1", "T5"]
    subjects = git_out(ws / "origin.git", "log", "--format=%s", f"{pr_head}..{BRANCH}").splitlines()
    assert subjects == ["Fix a.py line 5", "Fix a.py line 1"]
