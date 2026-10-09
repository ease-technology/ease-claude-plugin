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


def test_errors_are_printed_as_json(ws, monkeypatch, capsys):
    monkeypatch.chdir(ws)
    assert main(["next"]) == 1  # no runs yet
    assert output(capsys) == {"error": "no runs yet"}

    assert main(["start", "demo", "extra"]) == 1
    assert output(capsys)["error"].startswith("usage: ")
