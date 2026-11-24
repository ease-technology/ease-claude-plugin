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
