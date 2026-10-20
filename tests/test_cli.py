import io
import json

from engine.cli import main
from engine.workspace import load_state

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
    assert "run_id" in output(capsys)
    assert load_state(ws).ticket_title == "Add a `thing` for $USD"

    assert main(["next"]) == 0
    result = output(capsys)
    assert result["type"] == "spawn"
    assert result["agent"] == "ease:planner"

    monkeypatch.setattr("sys.stdin", io.StringIO(REPORT))
    assert main(["reply"]) == 0
    assert output(capsys) == {"ok": True}

    assert main(["next"]) == 0
    assert output(capsys)["type"] == "ask_user"


def test_start_with_a_branch(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    monkeypatch.setattr("sys.stdin", io.StringIO("Add a thing\n"))
    assert main(["start", "--branch", "juan/joi-7-add-a-thing"]) == 0
    assert "run_id" in output(capsys)
    assert load_state(ws).branch == "juan/joi-7-add-a-thing"


def test_errors_are_printed_as_json(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    assert main(["next"]) == 1  # no runs yet
    assert output(capsys) == {"error": "no runs yet"}

    assert main(["start", "demo", "extra"]) == 1
    assert output(capsys)["error"].startswith("usage: ")


def test_ticket_commands(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    assert main(["ticket", "next"]) == 1
    assert output(capsys) == {"error": "no ticket runs yet"}

    monkeypatch.setattr("sys.stdin", io.StringIO("Improve the sync\n"))  # the idea
    assert main(["ticket", "start"]) == 0
    assert "run_id" in output(capsys)

    assert main(["ticket", "next"]) == 0
    assert output(capsys)["agent"] == "ease:interviewer"

    ticket_text = "# Improve the sync\n\n## Acceptance criteria\n- AC1: When it syncs, then it is fast.\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(ticket_text))
    assert main(["ticket", "reply"]) == 0
    assert output(capsys)["decision"] == "ask_you"

    assert main(["ticket", "next"]) == 0
    assert output(capsys)["type"] == "ask_user"

    assert main(["next"]) == 1  # build runs are separate
    assert output(capsys) == {"error": "no runs yet"}

    assert main(["ticket", "bogus"]) == 1
    assert output(capsys)["error"].startswith("usage: ")

    assert main(["ticket", "start", "--branch", "x"]) == 1  # ticket runs have no branch
    assert output(capsys)["error"].startswith("usage: ")
