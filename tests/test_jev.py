import json

from engine import jev
from engine.models import Decision, Question, Task
from engine.workspace import new_state, new_ticket_state


def make_state():
    """A run with one planned task."""
    state = new_state("demo", "Add a thing", "details")
    state.tasks = [Task(title="Do it", repo="app", steps=["x"], done_when="y")]
    return state


def fake_post(answers, calls):
    """A stand-in for jev.post that records the request body and returns `answers`."""

    def post(key, body):
        calls.append(body)
        return {"answers": answers}

    return post


def test_no_key_means_no_call(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(jev, "post", fake_post({}, calls))
    assert jev.score_plan(None, make_state()) == (None, None)
    assert calls == []
    assert capsys.readouterr().err == ""


def test_post_error_is_printed_and_gives_none(monkeypatch, capsys):
    def broken(key, body):
        raise TimeoutError("too slow")

    monkeypatch.setattr(jev, "post", broken)
    assert jev.score_plan("key", make_state()) == (None, None)
    assert capsys.readouterr().err == "jev: too slow\n"


def test_missing_answer_gives_none(monkeypatch):
    monkeypatch.setattr(jev, "post", fake_post({"something_else": {"score": 3}}, []))
    assert jev.score_plan("key", make_state()) == (None, None)


def test_score_plan(monkeypatch):
    calls = []
    answers = {"plan_coverage": {"score": 4.2, "confidence": 0.81}}
    monkeypatch.setattr(jev, "post", fake_post(answers, calls))
    assert jev.score_plan("key", make_state()) == (4.2, 0.81)
    question = calls[0]["questions"]["plan_coverage"]
    assert question["type"] == "score"
    assert "each acceptance criterion" in question["instructions"]
    assert calls[0]["state"]["plan"]["tasks"][0]["title"] == "Do it"
    assert calls[0]["model"] == "jev-latest"


def test_judge_task_rotates_by_decisions_so_far(monkeypatch):
    calls = []
    answers = {"next_action": {"choice": "fix", "confidence": 0.7}}
    monkeypatch.setattr(jev, "post", fake_post(answers, calls))
    state = make_state()

    assert jev.judge_task("key", state, True, [], "") == ("fix", 0.7)
    state.log.append(Decision(task=1, attempt=1, checks_ok=True, review_ok=True, code="accept", final="accept"))
    jev.judge_task("key", state, True, [], "")

    first = list(calls[0]["questions"]["next_action"]["criteria"])
    second = list(calls[1]["questions"]["next_action"]["criteria"])
    assert first == ["accept", "fix", "escalate"]
    assert second == ["fix", "escalate", "accept"]


def test_judge_task_sends_the_review_and_a_cut_diff(monkeypatch):
    calls = []
    monkeypatch.setattr(jev, "post", fake_post({}, calls))
    jev.judge_task("key", make_state(), False, ["a.py: broken"], "x" * (jev.DIFF_LIMIT + 5))

    sent = calls[0]["state"]
    assert sent["review"] == {"ok": False, "findings": ["a.py: broken"]}
    assert sent["diff"] == "x" * jev.DIFF_LIMIT + "\n[diff cut here]"


def make_ticket_state():
    """A ticket run with one question already answered."""
    state = new_ticket_state("demo", "Improve the sync")
    state.questions.append(Question(
        round=1, question="Old?", header="Old", context="", options={"A": "a", "B": "b"},
        recommended="A", answer="B", decided_by="you",
    ))
    return state


def a_question(text, labels=("Yes", "No", "Later")):
    return Question(
        round=2, question=text, header="Q", context="the code shows x",
        options={label: f"means {label}" for label in labels}, recommended=labels[0],
    )


def test_judge_questions_asks_once_and_never_shows_the_recommendation(monkeypatch):
    calls = []
    answers = {"q1": {"choice": "No", "confidence": 0.8}, "q2": {"choice": ["No"], "confidence": 0.9}}
    monkeypatch.setattr(jev, "post", fake_post(answers, calls))

    picks = jev.judge_questions("key", make_ticket_state(), [a_question("First?"), a_question("Second?")])

    assert picks == [("No", 0.8), (None, None)]  # a choice that isn't one of the options (here not even a string) counts as no answer
    assert len(calls) == 1
    sent = calls[0]
    assert sent["state"]["decisions"] == [{"question": "Old?", "answer": "B"}]
    assert "First?" in sent["questions"]["q1"]["instructions"]
    assert "the code shows x" in sent["questions"]["q1"]["instructions"]
    assert "recommend" not in json.dumps(sent).lower()
    # One question was asked before, so the first new one turns by 1 and the second by 2.
    assert list(sent["questions"]["q1"]["criteria"]) == ["No", "Later", "Yes"]
    assert list(sent["questions"]["q2"]["criteria"]) == ["Later", "Yes", "No"]
