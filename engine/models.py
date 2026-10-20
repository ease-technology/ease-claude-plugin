"""The data model: what a project, a run, a task, a decision and a ticket run look like."""
import json
from dataclasses import asdict, dataclass, field


@dataclass
class Repo:
    path: str            # absolute path of the repo folder
    checks: str          # shell command: lint, build, tests...


@dataclass
class Project:
    repos: dict[str, Repo]
    context: str = ""    # notes for the planner (context.md)


@dataclass
class Task:
    title: str
    repo: str            # one of the project's repo names
    steps: list[str]
    done_when: str


@dataclass
class Decision:          # one line of the Jev log: the code rule, Jev, and what really happened
    task: int            # task number, from 1
    attempt: int
    checks_ok: bool
    review_ok: bool
    code: str            # what the code rule decided: accept | fix | escalate
    final: str           # what really happened: accept | fix | escalate (same as code in shadow mode)
    jev: str | None = None             # what Jev would do: accept | fix | escalate
    jev_confidence: float | None = None


@dataclass
class State:
    run_id: str
    project: str
    ticket_title: str
    ticket_body: str
    branch: str                        # the name given at start, else ease-feature/<slug>
    jev_mode: str = "shadow"           # shadow | live, copied from config.json when the run starts
    step: str = "plan"                 # plan | approve | build | review | done
    notes: str = ""                    # your change notes for the planner
    plan_summary: str = ""
    tasks: list[Task] = field(default_factory=list)
    plan_score: float | None = None    # Jev's score of the plan, 1-5
    plan_confidence: float | None = None
    bases: dict[str, str] = field(default_factory=dict)  # repo -> the branch we started from (the PR base)
    task: int = 0                      # index of the current task
    attempt: int = 1
    task_start: str = ""               # commit where the current task started
    checks_ok: bool = False
    checks_output: str = ""
    problems: list[str] = field(default_factory=list)    # for the next attempt, or for you if escalated
    log: list[Decision] = field(default_factory=list)
    prs: list[str] = field(default_factory=list)
    outcome: str = ""                  # done | escalated | cancelled


@dataclass
class Question:          # one interview question, and how it was answered
    round: int           # which round it was asked in, from 1
    question: str
    header: str          # short label for AskUserQuestion, at most 12 characters
    context: str         # what the interviewer found in the code that makes this a question
    options: dict[str, str]            # label -> description, 2 to 4 of them
    recommended: str                   # one of the labels
    jev: str | None = None             # Jev's pick, one of the labels
    jev_confidence: float | None = None
    answer: str = ""                   # a label, or your own words
    decided_by: str = ""               # you | jev


@dataclass
class TicketState:
    run_id: str
    project: str
    idea: str                          # your idea, as Claude wrote it down
    jev_mode: str = "shadow"           # shadow | live, copied from config.json when the run starts
    step: str = "interview"            # interview | answer | approve | done
    questions: list[Question] = field(default_factory=list)
    rounds: int = 0                    # rounds of questions asked so far
    draft: str = ""                    # the last ticket the interviewer wrote
    readiness: float | None = None     # Jev's score of the draft, 1-5
    readiness_confidence: float | None = None
    extra_round: bool = False          # live mode: Jev already sent a draft back once
    notes: str = ""                    # your changes to the last draft
    path: str = ""                     # where the ticket was written
    outcome: str = ""                  # written | cancelled


def state_to_json(state: State | TicketState) -> str:
    """The state as JSON text, for state.json."""
    return json.dumps(asdict(state), indent=2)


def state_from_json(text: str) -> State:
    """Read state.json text back into a State (with its Tasks and Decisions)."""
    data = json.loads(text)
    data["tasks"] = [Task(**t) for t in data["tasks"]]
    data["log"] = [Decision(**d) for d in data["log"]]
    return State(**data)


def ticket_state_from_json(text: str) -> TicketState:
    """Read a ticket run's state.json back into a TicketState (with its Questions)."""
    data = json.loads(text)
    data["questions"] = [Question(**q) for q in data["questions"]]
    return TicketState(**data)
