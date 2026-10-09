"""Ask Jev (the TypeSafe API) about a plan or a task. Jev never breaks a run: any problem gives None."""
import json
import sys
import urllib.request
from dataclasses import asdict

from engine.models import State

API_URL = "https://api.typesafe.ai/v1/systemone"
ACTIONS = {  # what can happen after a review, and what each one means
    "accept": "the task is done and working",
    "fix": "right approach, concrete problems to fix in another attempt",
    "replan": "the plan itself is wrong",
    "escalate": "a human is needed",
}
PLAN_LEVELS = ["unusable", "vague", "workable with gaps", "clear", "clear and complete"]


def post(key: str, body: dict) -> dict:
    """Send one request to Jev. May raise anything. Tests replace this function."""
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def ask(key: str | None, state: dict, name: str, question: dict) -> dict | None:
    """Ask Jev one question. Returns its answer, or None (no key, or anything went wrong)."""
    if not key:
        return None
    try:
        body = {"state": state, "model": "jev-latest", "questions": {name: question}}
        answer = post(key, body)["answers"][name]
    except Exception as error:
        print(f"jev: {error}", file=sys.stderr)  # stdout stays one JSON object
        return None
    return answer if isinstance(answer, dict) else None


def number_or_none(value) -> float | None:
    """`value` if it is a number, else None. type() is exact, so True/False (bools) don't count."""
    return value if type(value) in (int, float) else None


def score_plan(key: str | None, state: State) -> tuple[float | None, float | None]:
    """Jev's score of the plan, 1-5. Returns (score, confidence), or (None, None)."""
    question = {
        "type": "score",
        "instructions": (
            "How clear and complete is the `plan` for the `ticket`? A good plan has "
            "small ordered tasks, each with one repo, concrete steps and a checkable "
            "'done when'."
        ),
        "criteria": PLAN_LEVELS,
    }
    jev_state = {
        "ticket": {"title": state.ticket_title, "body": state.ticket_body},
        "plan": {"summary": state.plan_summary, "tasks": [asdict(task) for task in state.tasks]},
    }
    answer = ask(key, jev_state, "plan_quality", question) or {}
    score = number_or_none(answer.get("score"))
    if score is None:
        return None, None
    return score, number_or_none(answer.get("confidence"))


def judge_task(key: str | None, state: State, findings: list[str]) -> tuple[str | None, float | None]:
    """What Jev would do next with the current task. Returns (choice, confidence), or (None, None)."""
    # Jev slightly favors the first option, so the order turns by one with each decision.
    names = list(ACTIONS)
    turn = len(state.log) % len(names)
    order = names[turn:] + names[:turn]
    question = {
        "type": "choice",
        "instructions": (
            "Given the `ticket`, the `task`, the `checks` and the `review_findings`, "
            "what should happen next with this task?"
        ),
        "criteria": {action: ACTIONS[action] for action in order},
    }
    jev_state = {
        "ticket": {"title": state.ticket_title, "body": state.ticket_body},
        "task": asdict(state.tasks[state.task]),
        "attempt": state.attempt,
        "checks": {"ok": state.checks_ok, "output": state.checks_output},
        "review_findings": findings,
    }
    answer = ask(key, jev_state, "next_action", question) or {}
    if answer.get("choice") not in order:
        return None, None
    return answer["choice"], number_or_none(answer.get("confidence"))
