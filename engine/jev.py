"""Ask Jev (the TypeSafe API) about a plan, a task, or a ticket. Jev never breaks a run: any problem gives None."""
import json
import sys
import urllib.request
from dataclasses import asdict

from engine.models import Question, State, TicketState

API_URL = "https://api.typesafe.ai/v1/systemone"
ACTIONS = {  # what can happen after a review, and what each one means
    "accept": "the task is done and working",
    "fix": "right approach, concrete problems to fix in another attempt",
    "escalate": "a human is needed",
}
PLAN_LEVELS = [
    "misses what the ticket asks",
    "covers part of it",
    "covers most of it",
    "covers all of it",
    "covers all of it, with a check for each criterion",
]
TICKET_LEVELS = [
    "not a ticket yet",
    "the goal is unclear",
    "clear goal, but the criteria are vague or untestable",
    "testable criteria, but gaps in scope or edge cases",
    "ready: testable criteria, clear scope, nothing open",
]
DIFF_LIMIT = 20_000  # characters of the task's diff that Jev sees


def post(key: str, body: dict) -> dict:
    """Send one request to Jev. May raise anything. Tests replace this function."""
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def ask(key: str | None, state: dict, questions: dict) -> dict:
    """Ask Jev some questions in one call. Returns {name: answer}; empty with no key or if anything went wrong."""
    if not key:
        return {}
    try:
        answers = post(key, {"state": state, "model": "jev-latest", "questions": questions})["answers"]
    except Exception as error:
        print(f"jev: {error}", file=sys.stderr)  # stdout stays one JSON object
        return {}
    if not isinstance(answers, dict):
        return {}
    return {name: answer for name, answer in answers.items() if isinstance(answer, dict)}


def number_or_none(value) -> float | None:
    """`value` if it is a number, else None. type() is exact, so True/False (bools) don't count."""
    return value if type(value) in (int, float) else None


def score_plan(key: str | None, state: State) -> tuple[float | None, float | None]:
    """How fully the plan covers the ticket, 1-5. Returns (score, confidence), or (None, None)."""
    question = {
        "type": "score",
        "instructions": (
            "How fully does the `plan` cover what the `ticket` asks, including each acceptance "
            "criterion? A good plan has small ordered tasks, each with one repo, concrete steps "
            "and a checkable 'done when'."
        ),
        "criteria": PLAN_LEVELS,
    }
    jev_state = {
        "ticket": {"title": state.ticket_title, "body": state.ticket_body},
        "plan": {"summary": state.plan_summary, "tasks": [asdict(task) for task in state.tasks]},
    }
    answer = ask(key, jev_state, {"plan_coverage": question}).get("plan_coverage", {})
    score = number_or_none(answer.get("score"))
    if score is None:
        return None, None
    return score, number_or_none(answer.get("confidence"))


def judge_task(
    key: str | None, state: State, review_ok: bool, findings: list[str], diff: str
) -> tuple[str | None, float | None]:
    """What Jev would do next with the current task. Returns (choice, confidence), or (None, None)."""
    # Jev slightly favors the first option, so the order turns by one with each decision.
    names = list(ACTIONS)
    turn = len(state.log) % len(names)
    order = names[turn:] + names[:turn]
    question = {
        "type": "choice",
        "instructions": (
            "Given the `ticket`, the `task`, its `diff`, the `checks` and the `review`, "
            "what should happen next with this task?"
        ),
        "criteria": {action: ACTIONS[action] for action in order},
    }
    if len(diff) > DIFF_LIMIT:
        diff = diff[:DIFF_LIMIT] + "\n[diff cut here]"
    jev_state = {
        "ticket": {"title": state.ticket_title, "body": state.ticket_body},
        "task": asdict(state.tasks[state.task]),
        "attempt": state.attempt,
        "diff": diff,
        "checks": {"ok": state.checks_ok, "output": state.checks_output},
        "review": {"ok": review_ok, "findings": findings},
    }
    answer = ask(key, jev_state, {"next_action": question}).get("next_action", {})
    if answer.get("choice") not in order:
        return None, None
    return answer["choice"], number_or_none(answer.get("confidence"))


def decisions(state: TicketState) -> list[dict]:
    """The interview so far, as Jev sees it: each answered question and its answer."""
    return [{"question": q.question, "answer": q.answer} for q in state.questions if q.answer]


def judge_questions(
    key: str | None, state: TicketState, round_questions: list[Question]
) -> list[tuple[str | None, float | None]]:
    """Jev's pick for each question of a new round, in one call. Jev never sees the recommendation."""
    asked = {}
    for number, q in enumerate(round_questions):
        # The interviewer lists its recommendation first, so the order turns by one with each question.
        labels = list(q.options)
        turn = (len(state.questions) + number) % len(labels)
        order = labels[turn:] + labels[:turn]
        asked[f"q{number + 1}"] = {
            "type": "choice",
            "instructions": (
                f"For the `idea`, given the `decisions` so far: {q.question}\n\n"
                f"What the code shows: {q.context}"
            ),
            "criteria": {label: q.options[label] for label in order},
        }
    answers = ask(key, {"idea": state.idea, "decisions": decisions(state)}, asked)

    picks = []
    for number, q in enumerate(round_questions):
        answer = answers.get(f"q{number + 1}", {})
        choice = answer.get("choice")
        if isinstance(choice, str) and choice in q.options:
            picks.append((choice, number_or_none(answer.get("confidence"))))
        else:
            picks.append((None, None))
    return picks


def score_ticket(key: str | None, state: TicketState) -> tuple[float | None, float | None]:
    """Is the draft ready to build, 1-5, compared with the interview? Returns (score, confidence), or (None, None)."""
    question = {
        "type": "score",
        "instructions": (
            "Is the `ticket` ready to build? Compare it with the `idea` and the `decisions` from the "
            "interview: does it capture every decision, with testable acceptance criteria, a clear "
            "scope and nothing left open?"
        ),
        "criteria": TICKET_LEVELS,
    }
    jev_state = {"idea": state.idea, "decisions": decisions(state), "ticket": state.draft}
    answer = ask(key, jev_state, {"ticket_readiness": question}).get("ticket_readiness", {})
    score = number_or_none(answer.get("score"))
    if score is None:
        return None, None
    return score, number_or_none(answer.get("confidence"))
