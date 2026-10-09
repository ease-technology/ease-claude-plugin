"""The data model: what a project, a run, a task and a decision look like."""
import json
from dataclasses import asdict, dataclass, field


@dataclass
class Repo:
    path: str            # absolute path of the repo folder
    checks: str          # shell command: lint, build, tests...


@dataclass
class Project:
    name: str
    repos: dict[str, Repo]
    context: str = ""    # notes for the planner (context.md)


@dataclass
class Task:
    title: str
    repo: str            # one of the project's repo names
    steps: list[str]
    done_when: str


@dataclass
class Decision:          # one line of the shadow log: the code rule vs Jev
    task: int            # task number, from 1
    attempt: int
    checks_ok: bool
    review_ok: bool
    code: str            # what the code rule decided: accept | fix | escalate
    jev: str | None = None             # what Jev would do: accept | fix | replan | escalate
    jev_confidence: float | None = None


@dataclass
class State:
    run_id: str
    project: str
    ticket_title: str
    ticket_body: str
    branch: str                        # ease/<slug>
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


def state_to_json(state: State) -> str:
    """The state as JSON text, for state.json."""
    return json.dumps(asdict(state), indent=2)


def state_from_json(text: str) -> State:
    """Read state.json text back into a State (with its Tasks and Decisions)."""
    data = json.loads(text)
    data["tasks"] = [Task(**t) for t in data["tasks"]]
    data["log"] = [Decision(**d) for d in data["log"]]
    return State(**data)
