"""The data model: what a project, a run, a task, a decision, a ticket run and a PR comments run look like."""
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
class Verdict:           # Jev's score of a plan or a ticket draft, and your answer to it
    score: float | None
    confidence: float | None
    answer: str          # approve | change | cancel
    decided_by: str = ""  # you | autopilot; empty in runs from before


@dataclass
class State:
    run_id: str
    project: str
    ticket_title: str
    ticket_body: str
    branch: str                        # the name given at start, else the slug
    jev_mode: str = "shadow"           # shadow | live, copied from config.json when the run starts
    step: str = "plan"                 # plan | approve | build | review | done
    notes: str = ""                    # your change notes for the planner
    plan_summary: str = ""
    tasks: list[Task] = field(default_factory=list)
    plan_score: float | None = None    # Jev's score of the plan, 1-5
    plan_confidence: float | None = None
    plan_log: list[Verdict] = field(default_factory=list)  # every plan you answered
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
    draft_log: list[Verdict] = field(default_factory=list)  # every draft you answered
    extra_round: bool = False          # live mode: Jev already sent a draft back once
    notes: str = ""                    # your changes to the last draft
    path: str = ""                     # where the ticket was written
    outcome: str = ""                  # written | cancelled


@dataclass
class Thread:            # one open review thread on a PR, and what happened to it
    id: str
    path: str
    line: int | None
    outdated: bool
    comments: list[dict]               # each has id, author and body
    code: str = ""                     # the code at the thread's line
    proposal: str | None = None        # the agent's view: fix | skip, None when it has no view
    skip_reason: str = ""
    fix_note: str = ""
    jev: str | None = None             # Jev's pick: fix | skip
    jev_confidence: float | None = None
    verdict: str = ""                  # fix | skip, empty until decided
    reason: str = ""                   # why it was skipped
    instruction: str = ""              # what to fix
    decided_by: str = ""               # you | jev | earlier
    earlier_verdict: str = ""          # the verdict an earlier run gave this thread
    earlier_reason: str = ""
    new_comments: list[str] = field(default_factory=list)  # ids of the comments that earlier run's skip didn't see
    draft: str = ""                    # the reply you can paste on the thread
    commit: str = ""                   # the last commit of its fix
    resolved: bool = False
    resolve_error: str = ""


@dataclass
class PrState(State):
    step: str = "judge"                # judge | answer | build | review | push | done
    repo: str = ""                     # one of the project's repo names
    pr_number: int = 0
    pr_url: str = ""
    pr_head: str = ""                  # the PR's head commit when the run started
    viewer: str = ""                   # the GitHub login running this
    threads: list[Thread] = field(default_factory=list)
    attempt_start: str = ""            # commit where the current attempt started
    pushed: bool = False
    push_error: str = ""
    unpushed: str = ""                 # git log --oneline pr_head..HEAD, when the push was rejected


def state_to_json(state: State | TicketState) -> str:
    """The state as JSON text, for state.json."""
    return json.dumps(asdict(state), indent=2)


def build_fields(data: dict) -> dict:
    """Turn the Tasks, Decisions and Verdicts of a build or PR comments run back into objects."""
    data["tasks"] = [Task(**t) for t in data["tasks"]]
    data["log"] = [Decision(**d) for d in data["log"]]
    data["plan_log"] = [Verdict(**v) for v in data.get("plan_log", [])]  # older runs have none
    return data


def state_from_json(text: str) -> State:
    """Read state.json text back into a State (with its Tasks and Decisions)."""
    return State(**build_fields(json.loads(text)))


def pr_state_from_json(text: str) -> PrState:
    """Read a PR comments run's state.json back into a PrState (with its Tasks, Decisions and Threads)."""
    data = build_fields(json.loads(text))
    data["threads"] = [Thread(**t) for t in data["threads"]]
    return PrState(**data)


def ticket_state_from_json(text: str) -> TicketState:
    """Read a ticket run's state.json back into a TicketState (with its Questions)."""
    data = json.loads(text)
    data["questions"] = [Question(**q) for q in data["questions"]]
    data["draft_log"] = [Verdict(**v) for v in data.get("draft_log", [])]  # older runs have none
    return TicketState(**data)
