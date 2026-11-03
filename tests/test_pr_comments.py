import pytest

from engine.models import Decision, Task, Thread, Verdict
from engine.workspace import (
    CONTEXT_DIR, EaseError, build_runs, load_pr_state, new_pr_state, new_state, new_ticket_state, pr_runs, save_state,
    state_dir, ticket_runs,
)


def pr_run():
    """A PR comments run partway through: one thread decided by you, one settled by Jev, one not yet judged."""
    state = new_pr_state(
        "demo", "PR 7: Add a thing", "Review threads on the PR.", "juan/add-a-thing",
        "app", 7, "https://github.com/acme/app/pull/7", "abc123", "juan",
        [
            Thread(
                "T1", "a.py", 3, False, [{"id": "C1", "author": "sam", "body": "Off by one."}], code="x = y + 1",
                proposal="fix", fix_note="Drop the + 1.", jev="skip", jev_confidence=0.7,
                verdict="fix", instruction="Drop the + 1.", decided_by="you", commit="def456", resolved=True,
            ),
            Thread(
                "T2", "b.py", None, True, [{"id": "C2", "author": "ghost", "body": "Rename this."}],
                proposal="skip", skip_reason="Already renamed.", jev="skip", jev_confidence=0.9,
                verdict="skip", reason="Already renamed.", decided_by="jev",
                earlier_verdict="skip", earlier_reason="Not needed.", draft="Skipped because Already renamed.",
            ),
            Thread("T3", "c.py", 9, False, [{"id": "C3", "author": "sam", "body": "Why?"}]),
        ],
    )
    state.tasks = [Task("Fix a.py line 3", "app", ["Drop the + 1."], "The line is right.")]
    state.log = [Decision(1, 1, True, True, "accept", "accept", "accept", 0.8)]
    state.plan_log = [Verdict(4.0, 0.6, "approve")]
    return state


def test_a_new_run_starts_at_judge():
    assert pr_run().step == "judge"


def test_a_run_loads_back_equal(ws):  # AC5: a stopped run continues from what was saved
    state = pr_run()
    state.step = "review"
    state.attempt_start = "abc123"
    state.pushed = True
    state.push_error = "rejected"
    save_state(ws, state)

    assert load_pr_state(ws, state.run_id) == state


def test_a_thread_keeps_how_it_was_decided(ws):  # AC12
    state = pr_run()
    save_state(ws, state)

    thread = load_pr_state(ws, state.run_id).threads[0]
    assert isinstance(thread, Thread)
    assert (thread.proposal, thread.jev, thread.jev_confidence) == ("fix", "skip", 0.7)
    assert (thread.verdict, thread.decided_by) == ("fix", "you")


def test_a_run_is_only_listed_with_pr_runs(ws):
    state = pr_run()
    save_state(ws, state)

    assert state_dir(ws, state) == ws / CONTEXT_DIR / "pr-runs" / state.run_id
    assert (ws / CONTEXT_DIR / "pr-runs" / state.run_id / "state.json").is_file()
    assert pr_runs(ws) == [state]
    assert build_runs(ws) == []
    assert ticket_runs(ws) == []


def test_other_runs_stay_in_their_folders(ws):
    build = new_state("demo", "Add a thing", "details")
    ticket = new_ticket_state("demo", "An idea")
    save_state(ws, build)
    save_state(ws, ticket)

    assert state_dir(ws, build) == ws / CONTEXT_DIR / "runs" / build.run_id
    assert state_dir(ws, ticket) == ws / CONTEXT_DIR / "ticket-runs" / ticket.run_id
    assert pr_runs(ws) == []


def test_an_unknown_run_is_an_error(ws):
    with pytest.raises(EaseError, match="unknown run: nope"):
        load_pr_state(ws, "nope")
