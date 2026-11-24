import json
import subprocess
import sys
from pathlib import Path

OUTBOX = Path(__file__).resolve().parent.parent / "pilot" / "outbox.py"


def outbox(folder, *args):
    return subprocess.run(
        [sys.executable, str(OUTBOX), "--dir", str(folder), *args], capture_output=True, text=True
    )


def add(folder, kind, ref, text):
    result = outbox(folder, "add", "--kind", kind, "--ref", ref, *text.split())
    assert result.returncode == 0, result.stderr
    return result


def states(folder):
    return {item["ref"]: item["state"] for item in json.loads((folder / "outbox.json").read_text())["items"]}


def test_add_takes_14_words_and_refuses_15_leaving_the_file_unchanged(tmp_path):
    assert add(tmp_path, "decision", "a.md#1", " ".join(["word"] * 14)).stdout == "added\n"
    before = (tmp_path / "outbox.json").read_bytes()
    result = outbox(tmp_path, "add", "--kind", "decision", "--ref", "a.md#2", *["word"] * 15)
    assert result.returncode != 0
    assert result.stderr == "outbox: item has 15 words; the limit is 14\n"
    assert (tmp_path / "outbox.json").read_bytes() == before


def test_add_refuses_an_empty_item(tmp_path):
    result = outbox(tmp_path, "add", "--kind", "result", "--ref", "a.md#1")
    assert result.returncode == 1
    assert result.stderr == "outbox: item has 0 words; the limit is 14\n"
    assert not (tmp_path / "outbox.json").exists()


def test_add_joins_words_with_single_spaces(tmp_path):
    outbox(tmp_path, "add", "--kind", "decision", "--ref", "a.md#1", "Merge  PR 3?", "yes")
    assert outbox(tmp_path, "compose").stdout == "1 need you\n1. Merge PR 3? yes\n"


def test_duplicate_ref_is_a_no_op(tmp_path):
    add(tmp_path, "decision", "a.md#1", "Merge PR 3?")
    outbox(tmp_path, "close", "1")
    before = (tmp_path / "outbox.json").read_bytes()
    result = add(tmp_path, "decision", "a.md#1", "Something else")
    assert result.stdout == "already in the outbox\n"
    assert (tmp_path / "outbox.json").read_bytes() == before


def test_compose_lists_decisions_before_results_numbered_from_1(tmp_path):
    add(tmp_path, "result", "r1", "Login PR is ready")
    add(tmp_path, "decision", "d1", "Merge PR 3?")
    add(tmp_path, "result", "r2", "Deploy finished")
    add(tmp_path, "decision", "d2", "Drop the old table?")
    result = outbox(tmp_path, "compose")
    assert result.stdout == (
        "4 need you\n1. Merge PR 3?\n2. Drop the old table?\n3. Login PR is ready\n4. Deploy finished\n"
    )


def test_compose_leaves_out_closed_items_and_prints_nothing_when_none_is_open(tmp_path):
    assert outbox(tmp_path, "compose").stdout == ""
    add(tmp_path, "decision", "d1", "Merge PR 3?")
    add(tmp_path, "decision", "d2", "Drop the old table?")
    outbox(tmp_path, "drop", "d1")
    assert outbox(tmp_path, "compose").stdout == "1 need you\n1. Drop the old table?\n"
    outbox(tmp_path, "drop", "d2")
    assert outbox(tmp_path, "compose").stdout == ""


def write_pushed(folder, last_push):
    """An outbox whose last push numbered the refs as given, which differs from the current compose order."""
    items = [
        {"ref": "d1", "kind": "decision", "text": "Merge PR 3?", "state": "sent"},
        {"ref": "d2", "kind": "decision", "text": "Drop the old table?", "state": "sent"},
        {"ref": "r1", "kind": "result", "text": "Deploy finished", "state": "sent"},
    ]
    (folder / "outbox.json").write_text(json.dumps({"items": items, "last_push": last_push}))


def test_list_prints_the_numbering_of_the_last_push(tmp_path):
    write_pushed(tmp_path, ["d2", "d1"])
    assert outbox(tmp_path, "list").stdout == (
        "1. [decision] d2 Drop the old table? (sent)\n2. [decision] d1 Merge PR 3? (sent)\n"
    )


def test_close_by_number_uses_the_stored_numbering(tmp_path):
    write_pushed(tmp_path, ["d2", "r1", "d1"])
    result = outbox(tmp_path, "close", "1", "2")
    assert result.returncode == 0, result.stderr
    assert states(tmp_path) == {"d1": "sent", "d2": "closed", "r1": "closed"}


def test_close_with_an_unknown_number_changes_nothing(tmp_path):
    write_pushed(tmp_path, ["d1", "d2"])
    before = (tmp_path / "outbox.json").read_bytes()
    result = outbox(tmp_path, "close", "1", "3")
    assert result.returncode == 1
    assert result.stderr == "outbox: no item 3 in the last push\n"
    assert (tmp_path / "outbox.json").read_bytes() == before


def test_drop_by_ref(tmp_path):
    add(tmp_path, "decision", "/w/a-decisions.md#7", "Merge PR 3?")
    add(tmp_path, "decision", "/w/a-decisions.md#8", "Drop the old table?")
    result = outbox(tmp_path, "drop", "/w/a-decisions.md#7")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert states(tmp_path) == {"/w/a-decisions.md#7": "closed", "/w/a-decisions.md#8": "new"}


def test_drop_by_file_closes_every_ref_of_that_file(tmp_path):
    add(tmp_path, "decision", "/w/a-decisions.md#7", "Merge PR 3?")
    add(tmp_path, "decision", "/w/a-decisions.md#8", "Drop the old table?")
    add(tmp_path, "decision", "/w/a-decisions.md.bak#1", "Keep the backup?")
    add(tmp_path, "decision", "/w/b-decisions.md#1", "Rename the repo?")
    result = outbox(tmp_path, "drop", "--file", "/w/a-decisions.md")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert states(tmp_path) == {
        "/w/a-decisions.md#7": "closed",
        "/w/a-decisions.md#8": "closed",
        "/w/a-decisions.md.bak#1": "new",
        "/w/b-decisions.md#1": "new",
    }


PILOT = "pilot-session-1"


def hook(folder, command, payload):
    return subprocess.run(
        [sys.executable, str(OUTBOX), "--dir", str(folder), command],
        input=json.dumps(payload), capture_output=True, text=True,
    )


def push(folder, message, session_id=PILOT, tool_name="PushNotification"):
    payload = {"session_id": session_id, "hook_event_name": "PreToolUse", "tool_name": tool_name,
               "tool_input": {"message": message}}
    return hook(folder, "push-check", payload)


def stop(folder, session_id=PILOT, stop_hook_active=False):
    payload = {"session_id": session_id, "hook_event_name": "Stop", "stop_hook_active": stop_hook_active}
    return hook(folder, "stop-check", payload)


def pilot_outbox(folder):
    """A pilot folder with one new decision and one new result."""
    (folder / "pilot.session").write_text(PILOT + "\n")
    add(folder, "result", "r1", "Login PR is ready")
    add(folder, "decision", "d1", "Merge PR 3?")
    return "2 need you\n1. Merge PR 3?\n2. Login PR is ready"


def test_push_with_wrong_text_is_refused_with_the_composed_push(tmp_path):
    composed = pilot_outbox(tmp_path)
    before = (tmp_path / "outbox.json").read_bytes()
    result = push(tmp_path, "Hey, PR 3 is waiting for you to merge it")
    assert result.returncode == 2
    assert result.stderr == f"Push refused: send exactly the composed push:\n{composed}\n"
    assert (tmp_path / "outbox.json").read_bytes() == before


def test_exact_push_passes_and_is_recorded_as_sent(tmp_path):
    composed = pilot_outbox(tmp_path)
    result = push(tmp_path, composed)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""
    state = json.loads((tmp_path / "outbox.json").read_text())
    assert states(tmp_path) == {"r1": "closed", "d1": "sent"}
    assert state["last_push"] == ["d1", "r1"]
    assert [entry["text"] for entry in state["sent"]] == [composed]
    assert state["sent"][0]["at"]


def test_every_push_is_refused_while_no_item_is_new(tmp_path):
    composed = pilot_outbox(tmp_path)
    assert push(tmp_path, composed).returncode == 0
    for message in [composed, "1 need you\n1. Merge PR 3?", "Worker started"]:
        result = push(tmp_path, message)
        assert result.returncode == 2
        assert result.stderr == "Push refused: no new item in the outbox, so send no push.\n"


def test_push_is_refused_with_an_empty_outbox(tmp_path):
    (tmp_path / "pilot.session").write_text(PILOT)
    result = push(tmp_path, "Worker restarted")
    assert result.returncode == 2
    assert result.stderr == "Push refused: no new item in the outbox, so send no push.\n"


def test_push_check_lets_other_tools_through(tmp_path):
    pilot_outbox(tmp_path)
    result = push(tmp_path, "anything", tool_name="Bash")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_push_check_error_is_one_refusal_line(tmp_path):
    (tmp_path / "pilot.session").write_text(PILOT)
    (tmp_path / "outbox.json").write_text("{not json")
    result = push(tmp_path, "anything")
    assert result.returncode == 2
    assert result.stderr.startswith("Push refused: outbox error (")
    assert result.stderr.count("\n") == 1


def test_stop_is_blocked_while_a_new_item_exists_and_passes_once_sent(tmp_path):
    composed = pilot_outbox(tmp_path)
    for active in [False, True]:
        result = stop(tmp_path, stop_hook_active=active)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "decision": "block",
            "reason": "The outbox has an unsent new item. Call PushNotification with exactly this message:\n"
            + composed,
        }
    assert push(tmp_path, composed).returncode == 0
    result = stop(tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_stop_check_error_lets_the_stop_through(tmp_path):
    (tmp_path / "pilot.session").write_text(PILOT)
    (tmp_path / "outbox.json").write_text("{not json")
    result = stop(tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr


def test_hooks_allow_everything_outside_the_pilot_session(tmp_path):
    pilot_outbox(tmp_path)
    before = (tmp_path / "outbox.json").read_bytes()
    for result in [push(tmp_path, "anything", session_id="other"), stop(tmp_path, session_id="other")]:
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (tmp_path / "pilot.session").unlink()
    for result in [push(tmp_path, "anything"), stop(tmp_path)]:
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert (tmp_path / "outbox.json").read_bytes() == before
