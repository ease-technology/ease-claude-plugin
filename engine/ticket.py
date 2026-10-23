"""The ticket flow: interview -> answer -> interview ... -> approve -> done. It ends with a one-page ticket."""
import json

from engine import jev
from engine.flow import parse_report, spawn
from engine.models import Project, Question, TicketState, Verdict
from engine.workspace import (
    CONTEXT_DIR, EaseError, load_config, load_project, new_ticket_state, project_and_mode, save_state, slugify,
    ticket_runs,
)

MAX_ROUNDS = 5                     # rounds of questions; live mode may add one more
RECOMMENDED = " (Recommended)"     # how AskUserQuestion shows the recommended option
APPROVE_QUESTION = "Write this ticket?"
QUESTIONS_SHAPE = """```json
{"questions": [{"question": "...?", "header": "at most 12 characters", "context": "what the code shows",
  "options": [{"label": "1-5 words", "description": "..."}], "recommended": "<one of the labels>"}]}
```"""
TICKET_SHAPE = """# <title>

When <situation>, I want to <motivation>, so I can <outcome>.

## Why
## What changes
## Acceptance criteria
- AC1: When <situation>, then <observable result>.
## Out of scope
## Where
## Check it end to end
## Assumptions"""


# ---------- start ----------

def start(ws, project_name: str | None, text: str) -> dict:
    """Begin a ticket run from an idea. With no project name, use default_project from config.json."""
    project_name, jev_mode = project_and_mode(ws, project_name)
    idea = text.strip()
    if not idea:
        raise EaseError("no idea given")
    state = new_ticket_state(project_name, idea)
    state.jev_mode = jev_mode  # the run keeps this mode, even if config.json changes later
    save_state(ws, state)
    return {"run_id": state.run_id}


def open_runs(ws) -> dict:
    """The ticket runs that aren't done, for resuming one."""
    return {"runs": [
        {"run_id": run.run_id, "project": run.project, "title": run.idea.splitlines()[0][:80], "step": run.step}
        for run in ticket_runs(ws) if run.step != "done"
    ]}


# ---------- next ----------

def next_action(ws, state: TicketState) -> dict:
    """Tell the skill what to do now."""
    if state.step == "answer":
        return ask_round(state)
    if state.step == "approve":
        return ask_approval(state)
    if state.step == "done":
        return {"type": "done", "summary": summary(state)}
    return spawn(ws, state, "interviewer", interviewer_prompt(state, load_project(ws, state.project)))


def ask_round(state: TicketState) -> dict:
    """This round's open questions, ready for AskUserQuestion, and the ones Jev settled."""
    this_round = [q for q in state.questions if q.round == state.rounds]
    settled = [q for q in this_round if q.decided_by == "jev"]
    open_questions = [q for q in this_round if not q.answer]
    lines = []
    if settled:
        lines.append("Jev agreed with the recommendation on these, so they are settled:")
        lines += [f"- {q.question} {q.answer}" for q in settled]
        lines.append("")
    lines += [f"- {q.header}: {q.context}" for q in open_questions if q.context]
    return {
        "type": "ask_user",
        "message": "\n".join(lines).strip(),
        "questions": [for_user(q) for q in open_questions],
    }


def for_user(q: Question) -> dict:
    """One question as AskUserQuestion takes it: the recommended option first, and Jev's pick marked."""
    labels = [q.recommended] + [label for label in q.options if label != q.recommended]
    options = []
    for label in labels:
        description = q.options[label]
        if label == q.jev and label != q.recommended:
            sure = f" ({q.jev_confidence:.2f})" if q.jev_confidence is not None else ""
            description = f"Jev would pick this{sure}. {description}"
        name = label + RECOMMENDED if label == q.recommended else label
        options.append({"label": name, "description": description})
    return {"question": q.question, "header": q.header, "multiSelect": False, "options": options}


def ask_approval(state: TicketState) -> dict:
    """The draft and its readiness, with one question: write it or not. Changes go in "Other"."""
    return {
        "type": "ask_user",
        "message": f"{state.draft}\n{readiness_line(state)}",
        "questions": [{
            "question": APPROVE_QUESTION, "header": "Ticket", "multiSelect": False,
            "options": [
                {"label": "Approve", "description": "Write the ticket file."},
                {"label": "Cancel", "description": "Stop without writing anything."},
            ],
        }],
    }


# ---------- reply ----------

def reply(ws, state: TicketState, text: str) -> dict:
    """Handle what came back (the interviewer's message or your answers), then save."""
    if state.step == "done":
        raise EaseError("this ticket run is done")
    if not text.strip():
        raise EaseError("empty reply")

    if state.step == "interview":
        result = reply_interview(ws, state, text)
    elif state.step == "answer":
        result = reply_answers(state, text)
    else:
        result = reply_approve(ws, state, text)

    save_state(ws, state)
    return result


def reply_interview(ws, state: TicketState, text: str) -> dict:
    """The interviewer sent either a round of questions (a JSON block) or the ticket."""
    key = load_config(ws).get("typesafe_api_key")
    raw = questions_in(text)
    if raw is not None:
        return take_round(key, state, raw)
    return take_draft(ws, key, state, text)


def questions_in(text: str):
    """The questions from the message's last ```json block, or None when it has none (then it's the ticket)."""
    try:
        report = parse_report(text)
    except (EaseError, ValueError):  # no JSON block, or not valid JSON
        return None
    return report.get("questions") if isinstance(report, dict) else None


def take_round(key, state: TicketState, raw) -> dict:
    """Check the round, ask Jev, and settle what live mode lets Jev settle."""
    limit = round_limit(state)
    if state.rounds >= limit:
        raise EaseError(f"interviewer reply: no questions after {limit} rounds; write the ticket")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4:
        raise EaseError("interviewer reply: a round has 1 to 4 questions")
    round_questions = [to_question(state.rounds + 1, item) for item in raw]
    if len({q.question for q in round_questions}) < len(round_questions):
        raise EaseError("interviewer reply: the questions in a round must differ")

    picks = jev.judge_questions(key, state, round_questions)
    for q, (pick, confidence) in zip(round_questions, picks):
        q.jev, q.jev_confidence = pick, confidence
        if question_rule(state.jev_mode, q.recommended, pick, confidence) == "jev":
            q.answer, q.decided_by = q.recommended, "jev"
    state.questions += round_questions
    state.rounds += 1
    state.step = "answer" if any(not q.answer for q in round_questions) else "interview"
    settled = len([q for q in round_questions if q.decided_by == "jev"])
    return {"ok": True, "round": state.rounds, "settled_by_jev": settled}


def to_question(round_number: int, item: dict) -> Question:
    """Check one question from the interviewer. A missing key raises KeyError."""
    options = {option["label"]: option.get("description", "") for option in item["options"]}
    question = Question(
        round=round_number, question=item["question"], header=item["header"],
        context=item.get("context", ""), options=options, recommended=item["recommended"],
    )
    if not 2 <= len(options) <= 4:
        raise EaseError("interviewer reply: each question needs 2 to 4 options")
    if question.recommended not in options:
        raise EaseError("interviewer reply: recommended must be one of the option labels")
    if len(question.header) > 12:
        raise EaseError("interviewer reply: a header must be at most 12 characters")
    return question


def round_limit(state: TicketState) -> int:
    """How many rounds of questions this run may have."""
    return MAX_ROUNDS + (1 if state.extra_round else 0)


def question_rule(mode, recommended, jev_pick, confidence) -> str:
    """Who answers a question: "jev" (live mode, Jev picks the recommendation and is sure enough) or "you"."""
    if mode == "live" and jev_pick == recommended and confidence is not None and confidence >= 0.5:
        return "jev"
    return "you"


def reply_answers(state: TicketState, text: str) -> dict:
    """Your answers to this round's open questions, keyed by the question text."""
    answers = read_answers(text)
    open_questions = [q for q in state.questions if q.round == state.rounds and not q.answer]
    missing = [q.question for q in open_questions if not answers.get(q.question)]
    if missing:
        raise EaseError("no answer for: " + " | ".join(missing))
    for q in open_questions:
        q.answer, q.decided_by = answers[q.question], "you"
    state.step = "interview"
    return {"ok": True}


def read_answers(text: str) -> dict[str, str]:
    """{"answers": {question: answer}} -> {question: answer}, without AskUserQuestion's " (Recommended)"."""
    try:
        data = parse_report(text) if "```json" in text else json.loads(text)
        answers = data["answers"].items()
    except (EaseError, ValueError, KeyError, TypeError, AttributeError):
        raise EaseError('answers must be JSON like {"answers": {"<question>": "<answer>"}}') from None
    return {question: str(answer).strip().removesuffix(RECOMMENDED) for question, answer in answers}


def take_draft(ws, key, state: TicketState, text: str) -> dict:
    """The interviewer sent the ticket. Jev scores it, and the ready rule says what happens next."""
    state.draft = ticket_in(text)
    state.notes = ""  # the draft now has your changes in it
    state.readiness, state.readiness_confidence = jev.score_ticket(key, state)
    decision = ready_rule(state.jev_mode, state.readiness, state.readiness_confidence, state.extra_round)
    if decision == "write":
        write_ticket(ws, state)
    elif decision == "ask_more":
        state.extra_round = True
        state.step = "interview"
    else:
        state.step = "approve"
    return {
        "ok": True, "decision": decision,
        "readiness": state.readiness, "readiness_confidence": state.readiness_confidence,
    }


def ticket_in(text: str) -> str:
    """The ticket inside the interviewer's message: everything from its first "# " line."""
    lines = text.strip().splitlines()
    starts = [number for number, line in enumerate(lines) if line.startswith("# ")]
    if not starts:
        raise EaseError(
            "interviewer reply: send a round of questions as a ```json block, "
            "or the ticket starting at its # title line"
        )
    ticket = "\n".join(lines[starts[0]:]).strip() + "\n"
    if "## Acceptance criteria" not in ticket:
        raise EaseError("interviewer reply: the ticket needs an ## Acceptance criteria section")
    return ticket


def ready_rule(mode, score, confidence, extra_round_used) -> str:
    """What happens to a draft: "write" it, "ask_more" (one more round of questions), or "ask_you"."""
    if mode != "live" or score is None or confidence is None or confidence < 0.5:
        return "ask_you"
    if score >= 4:
        return "write"
    return "ask_you" if extra_round_used else "ask_more"


def reply_approve(ws, state: TicketState, text: str) -> dict:
    """Your answer to the draft: Approve, Cancel, or the changes you want. It is logged next to Jev's score."""
    answer = read_answers(text).get(APPROVE_QUESTION, "")
    if not answer:
        raise EaseError(f"no answer for: {APPROVE_QUESTION}")
    if answer.lower() == "cancel":
        state.step = "done"
        state.outcome = "cancelled"
    elif answer.lower() == "approve":
        write_ticket(ws, state)
    else:  # your changes: the next interviewer gets the draft and these notes
        state.notes = answer
        state.step = "interview"
    verdict = answer.lower() if answer.lower() in ("approve", "cancel") else "change"
    state.draft_log.append(Verdict(state.readiness, state.readiness_confidence, verdict))
    return {"ok": True}


def write_ticket(ws, state: TicketState) -> None:
    """Write the draft to projects/<project>/tickets/<slug>.md, never over an existing file."""
    folder = ws / CONTEXT_DIR / "projects" / state.project / "tickets"
    folder.mkdir(parents=True, exist_ok=True)
    slug = slugify(state.draft.splitlines()[0])
    path, number = folder / f"{slug}.md", 2
    while path.exists():
        path, number = folder / f"{slug}-{number}.md", number + 1
    path.write_text(state.draft)
    state.path = str(path)
    state.step = "done"
    state.outcome = "written"


# ---------- text for the user ----------

def readiness_line(state: TicketState) -> str:
    """Jev's readiness score of the draft, as one line."""
    label = f"Jev ({state.jev_mode})"
    if state.readiness is None:
        return f"{label}: no readiness score (no key or no answer)"
    line = f"{label}: readiness {state.readiness:.1f}/{len(jev.TICKET_LEVELS)}"
    if state.readiness_confidence is not None:
        line += f" (confidence {state.readiness_confidence:.2f})"
    return line


def summary(state: TicketState) -> str:
    """How the ticket run ended, and how Jev's picks compare with yours."""
    yours = [q for q in state.questions if q.decided_by == "you"]
    judged = [q for q in yours if q.jev is not None]
    agreed = [q for q in judged if q.jev == q.answer]
    paired = [q for q in judged if q.jev == q.recommended]  # Jev and the recommendation agreed
    you_too = [q for q in paired if q.answer == q.recommended]
    settled = len([q for q in state.questions if q.decided_by == "jev"])

    if state.outcome == "written":
        lines = [f"Ticket: {state.path}", f"Build it: /ease:build {state.path}"]
    else:
        lines = ["Cancelled: no ticket written"]
    lines += [
        f"Questions: {len(state.questions)} in {state.rounds} rounds "
        f"({len(yours)} answered by you, {settled} settled by Jev)",
        f"Jev agreed with you on {len(agreed)} of {len(judged)} questions",
        f"On the {len(paired)} where Jev agreed with the recommendation, you agreed too {len(you_too)} times",
        readiness_line(state),
        f"Jev mode: {state.jev_mode}",
    ]
    return "\n".join(lines)


# ---------- the interviewer's prompt (agents/interviewer.md holds the general rules) ----------

def interviewer_prompt(state: TicketState, project: Project) -> str:
    repos = [f"- {name}: {repo.path}" for name, repo in project.repos.items()]
    lines = [
        "# Turn this idea into a ticket", "",
        "## The idea", "", state.idea, "",
        "## Project context", "", project.context or "(none)", "",
        "## Repos", "", *repos, "",
    ]
    if state.questions:
        lines += ["## Questions so far", ""]
        for q in state.questions:
            who = "Jev" if q.decided_by == "jev" else "the user"
            lines.append(f"- {q.question} Answer: {q.answer} (decided by {who})")
        lines.append("")
    if state.draft:
        lines += ["## Your last draft", "", state.draft, ""]
        if state.notes:
            lines += [f"The user asked for these changes: {state.notes}", ""]
        elif state.readiness is not None:  # live mode sent it back
            lines += [
                f"Jev scored this draft {state.readiness:.1f}/{len(jev.TICKET_LEVELS)} for readiness to build. "
                "Find what is missing or unclear: ask about it, or fix it.", "",
            ]

    limit = round_limit(state)
    if state.rounds >= limit:
        lines += [
            f"You have used all {limit} rounds of questions. Write the ticket now, "
            "and list anything still open under Assumptions.", "",
        ]
    else:
        lines += [
            f"This is round {state.rounds + 1} of at most {limit}. If something important is still open, "
            "end your reply with up to 4 questions in a JSON block of this shape:",
            QUESTIONS_SHAPE, "",
        ]
    lines += ["To finish, reply with only the ticket, starting at its # title line, in this shape:", "", TICKET_SHAPE]
    return "\n".join(lines)
