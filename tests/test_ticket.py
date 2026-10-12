import json

import pytest

from engine import jev, ticket
from engine.workspace import CONTEXT_DIR, EaseError, load_state, load_ticket_state

TICKET = (
    "# Add a thing\n\n"
    "When I use the app, I want a thing, so I can do more.\n\n"
    "## Acceptance criteria\n"
    "- AC1: When I ask for the thing, then it appears.\n"
)


def q(text, recommended="A", labels=("A", "B"), header="Pick"):
    """One question, as the interviewer writes it."""
    return {
        "question": text, "header": header, "context": f"the code shows {text}",
        "options": [{"label": label, "description": f"means {label}"} for label in labels],
        "recommended": recommended,
    }


def round_of(*questions):
    """An interviewer message with a round of questions."""
    return "A few questions.\n```json\n" + json.dumps({"questions": list(questions)}) + "\n```"


def answers(by_question):
    """Your answers, as the skill sends them."""
    return json.dumps({"answers": by_question})


def send(ws, text):
    """Reply to the newest ticket run, loading its state from disk like the CLI does."""
    return ticket.reply(ws, load_ticket_state(ws), text)


def ask(ws):
    """Ask the newest ticket run what to do next."""
    return ticket.next_action(ws, load_ticket_state(ws))


def last_prompt(ws):
    prompts = sorted((ws / CONTEXT_DIR / "ticket-runs").glob("*/prompts/*.md"))
    return prompts[-1].read_text()


def use_jev(ws, monkeypatch, mode="shadow", picks=(), readiness=None):
    """Give config.json a key and `mode`. Jev picks picks[i] = (label, confidence) for the i-th
    question of every round, and scores each draft `readiness` = (score, confidence)."""
    (ws / CONTEXT_DIR / "config.json").write_text(json.dumps(
        {"default_project": "demo", "typesafe_api_key": "secret", "jev_mode": mode}
    ))

    def post(key, body):
        found = {}
        for number, name in enumerate(body["questions"]):
            if name == "ticket_readiness":
                if readiness:
                    found[name] = {"score": readiness[0], "confidence": readiness[1]}
            elif number < len(picks):
                found[name] = {"choice": picks[number][0], "confidence": picks[number][1]}
        return {"answers": found}

    monkeypatch.setattr(jev, "post", post)


def test_shadow_run(ws, monkeypatch):
    use_jev(ws, monkeypatch, picks=[("B", 0.7), ("A", 0.9), ("A", 0.9)], readiness=(4.2, 0.8))
    ticket.start(ws, None, "  Add a thing\n\nIt helps.  ")
    assert load_ticket_state(ws).idea == "Add a thing\n\nIt helps."
    with pytest.raises(EaseError, match="no runs yet"):  # build runs are separate
        load_state(ws)

    assert ask(ws)["agent"] == "ease:interviewer"
    assert "This is round 1 of at most 5." in last_prompt(ws)

    result = send(ws, round_of(q("First?"), q("Second?"), q("Third?")))
    assert result == {"ok": True, "round": 1, "settled_by_jev": 0}  # shadow: Jev never settles
    action = ask(ws)
    first, second, _ = action["questions"]
    assert [option["label"] for option in first["options"]] == ["A (Recommended)", "B"]
    assert first["options"][1]["description"] == "Jev would pick this (0.70). means B"
    assert second["options"][1]["description"] == "means B"  # Jev agreed: nothing to mark
    assert "- Pick: the code shows First?" in action["message"]

    send(ws, answers({"First?": "A (Recommended)", "Second?": "Something else", "Third?": "A"}))
    ask(ws)
    assert "- First? Answer: A (decided by the user)" in last_prompt(ws)

    folder = ws / CONTEXT_DIR / "projects" / "demo" / "tickets"
    folder.mkdir(parents=True)
    (folder / "add-a-thing.md").write_text("mine")
    assert send(ws, "Here is the ticket.\n\n" + TICKET)["decision"] == "ask_you"  # shadow: you approve
    action = ask(ws)
    assert action["message"].startswith("# Add a thing")  # the text before the title is dropped
    assert "Jev (shadow): readiness 4.2/5 (confidence 0.80)" in action["message"]
    assert action["questions"][0]["question"] == ticket.APPROVE_QUESTION
    send(ws, answers({ticket.APPROVE_QUESTION: "Approve"}))

    assert (folder / "add-a-thing.md").read_text() == "mine"  # never overwritten
    path = folder / "add-a-thing-2.md"
    assert path.read_text() == TICKET
    summary = ask(ws)["summary"]
    assert f"Build it: /ease:build {path}" in summary
    assert "Questions: 3 in 1 rounds (3 answered by you, 0 settled by Jev)" in summary
    assert "Jev agreed with you on 1 of 3 questions" in summary
    assert "On the 2 where Jev agreed with the recommendation, you agreed too 1 times" in summary


def test_live_run(ws, monkeypatch):
    use_jev(ws, monkeypatch, mode="live", picks=[("A", 0.9), ("B", 0.9)], readiness=(4.5, 0.8))
    ticket.start(ws, None, "Add a thing")
    assert send(ws, round_of(q("First?"), q("Second?")))["settled_by_jev"] == 1
    action = ask(ws)
    assert [x["question"] for x in action["questions"]] == ["Second?"]  # Jev disagreed, so it's yours
    assert "- First? A" in action["message"]
    send(ws, answers({"Second?": "B"}))

    send(ws, round_of(q("Third?")))  # Jev agrees with the recommendation, so nothing comes to you
    assert ask(ws)["type"] == "spawn"

    assert send(ws, TICKET)["decision"] == "write"  # ready, so it's written without you
    state = load_ticket_state(ws)
    assert state.outcome == "written"
    assert [x.decided_by for x in state.questions] == ["jev", "you", "jev"]
    assert "Jev (live): readiness 4.5/5 (confidence 0.80)" in ask(ws)["summary"]


def test_live_low_score_gets_one_extra_round(ws, monkeypatch):
    use_jev(ws, monkeypatch, mode="live", readiness=(2, 0.9))
    ticket.start(ws, None, "Add a thing")
    assert send(ws, TICKET)["decision"] == "ask_more"
    ask(ws)
    prompt = last_prompt(ws)
    assert "Jev scored this draft 2.0/5" in prompt
    assert "of at most 6" in prompt
    assert send(ws, TICKET)["decision"] == "ask_you"  # only once
    assert load_ticket_state(ws).step == "approve"


def test_changes_go_back_then_cancel_writes_nothing(ws):
    ticket.start(ws, None, "Add a thing")
    send(ws, TICKET)
    send(ws, answers({ticket.APPROVE_QUESTION: "Also handle errors"}))
    ask(ws)
    prompt = last_prompt(ws)
    assert "## Your last draft" in prompt
    assert "The user asked for these changes: Also handle errors" in prompt

    send(ws, TICKET)  # the revised draft
    assert load_ticket_state(ws).notes == ""
    send(ws, answers({ticket.APPROVE_QUESTION: "Cancel"}))
    assert not (ws / CONTEXT_DIR / "projects" / "demo" / "tickets").exists()
    assert "Cancelled: no ticket written" in ask(ws)["summary"]
    with pytest.raises(EaseError, match="this ticket run is done"):
        send(ws, "again")


@pytest.mark.parametrize("mode, pick, confidence, expected", [
    ("live", "A", 0.5, "jev"),      # Jev picks the recommendation, sure enough
    ("live", "A", 0.49, "you"),     # Jev isn't sure
    ("live", "B", 0.9, "you"),      # Jev disagrees with the recommendation
    ("shadow", "A", 0.9, "you"),    # shadow: you answer everything
])
def test_question_rule(mode, pick, confidence, expected):
    assert ticket.question_rule(mode, "A", pick, confidence) == expected


@pytest.mark.parametrize("mode, score, confidence, extra_used, expected", [
    ("live", 4, 0.5, False, "write"),
    ("live", 3.9, 0.9, False, "ask_more"),
    ("live", 3.9, 0.9, True, "ask_you"),     # the extra round is used up
    ("live", 5, 0.4, False, "ask_you"),      # Jev isn't sure
    ("shadow", 5, 0.9, False, "ask_you"),    # shadow: you always approve
])
def test_ready_rule(mode, score, confidence, extra_used, expected):
    assert ticket.ready_rule(mode, score, confidence, extra_used) == expected


@pytest.mark.parametrize("bad, message", [
    (round_of(*[q(f"Q{n}?") for n in range(5)]), "1 to 4 questions"),
    (round_of(q("Odd pick?", recommended="C")), "one of the option labels"),
    (round_of(q("Long?", header="Much too long")), "at most 12 characters"),
    ("# Add a thing\n\nNo criteria here.\n", "Acceptance criteria"),
])
def test_bad_interviewer_replies_change_nothing(ws, bad, message):
    ticket.start(ws, None, "Add a thing")
    with pytest.raises(EaseError, match=message):
        send(ws, bad)
    state = load_ticket_state(ws)
    assert (state.questions, state.draft, state.step) == ([], "", "interview")


def test_rounds_run_out(ws):
    ticket.start(ws, None, "Improve the sync")
    for number in range(5):
        send(ws, round_of(q(f"Q{number}?")))
        send(ws, answers({f"Q{number}?": "A"}))
    ask(ws)
    assert "You have used all 5 rounds" in last_prompt(ws)
    with pytest.raises(EaseError, match="no questions after 5 rounds"):
        send(ws, round_of(q("One more?")))


def test_every_open_question_needs_an_answer(ws):
    ticket.start(ws, None, "Improve the sync")
    send(ws, round_of(q("First?"), q("Second?")))
    with pytest.raises(EaseError, match="no answer for: Second"):
        send(ws, answers({"First?": "A"}))
