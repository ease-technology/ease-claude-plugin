"""The step machine: plan -> approve -> build -> review -> (next task | fix | done)."""
import json
from pathlib import Path

from engine import jev
from engine.models import Decision, Project, Repo, State, Task
from engine.shell import (
    commit_all, commits_ahead, current_branch, has_remote, head,
    is_dirty, open_pr, run_checks, switch_to_branch,
)
from engine.workspace import EaseError, load_config, load_project, new_state, run_dir, save_state

PLAN_SHAPE = """```json
{"summary": "...", "tasks": [{"title": "...", "repo": "<one of the repo names above>", "steps": ["..."], "done_when": "..."}]}
```"""
REVIEW_SHAPE = """```json
{"verdict": "pass or fail", "findings": ["file: what's wrong, what to do"]}
```"""


# ---------- start ----------

def start(ws, project_name: str | None, text: str) -> dict:
    """Begin a run. With no project name, use default_project from config.json."""
    config = load_config(ws)
    project_name = project_name or config.get("default_project")
    if not project_name:
        raise EaseError("no project given and no default_project in config.json")
    load_project(ws, project_name)  # fails early if the project is unknown or bad
    jev_mode = config.get("jev_mode", "shadow")
    if jev_mode not in ("shadow", "live"):
        raise EaseError('jev_mode must be "shadow" or "live"')

    text = text.strip()
    if not text:
        raise EaseError("no ticket given")
    title = text.splitlines()[0][:80]  # the ticket's first line

    state = new_state(project_name, title, text)
    state.jev_mode = jev_mode  # the run keeps this mode, even if config.json changes later
    save_state(ws, state)
    return {"run_id": state.run_id}


# ---------- next ----------

def next_action(ws, state: State) -> dict:
    """Tell the skill what to do now."""
    if state.step == "approve":
        return {"type": "ask_user", "message": plan_text(state)}
    if state.step == "done":
        return {"type": "done", "summary": summary(state)}

    project = load_project(ws, state.project)
    if state.step == "plan":
        return spawn(ws, state, "planner", planner_prompt(state, project))
    if state.step == "build":
        return spawn(ws, state, "worker", worker_prompt(state, project))
    return spawn(ws, state, "reviewer", reviewer_prompt(state, project))


def spawn(ws, state: State, agent: str, prompt: str) -> dict:
    """Save the prompt as prompts/NN-<agent>.md and ask the skill to start the agent."""
    folder = run_dir(ws, state.run_id) / "prompts"
    folder.mkdir(parents=True, exist_ok=True)
    number = len(list(folder.glob("*.md"))) + 1
    path = folder / f"{number:02d}-{agent}.md"
    path.write_text(prompt)
    return {
        "type": "spawn",
        "agent": f"ease:{agent}",
        "prompt": f"Your instructions are in {path}. Read that file first and follow it.",
    }


# ---------- reply ----------

def reply(ws, state: State, text: str) -> dict:
    """Handle what came back (an agent's report or the user's words), then save."""
    if state.step == "done":
        raise EaseError("this run is done")
    if not text.strip():
        raise EaseError("empty reply")

    project = load_project(ws, state.project)
    if state.step == "plan":
        result = reply_plan(ws, state, project, text)
    elif state.step == "approve":
        result = reply_approve(ws, state, project, text)
    elif state.step == "build":
        result = reply_build(state, project)
    else:
        result = reply_review(ws, state, project, text)

    save_state(ws, state)
    return result


def reply_plan(ws, state: State, project: Project, text: str) -> dict:
    """Save the planner's tasks, and Jev's score of them."""
    report = parse_report(text)
    tasks = [Task(**task) for task in report["tasks"]]  # a missing or extra key raises TypeError
    # A bad plan saved here would leave the run stuck at approve, so check it now.
    if not tasks:
        raise EaseError("planner report: tasks must be a non-empty list")
    for task in tasks:
        if task.repo not in project.repos:
            raise EaseError(f"planner report: repo must be one of: {', '.join(project.repos)}")

    state.tasks = tasks
    state.plan_summary = str(report.get("summary", ""))
    key = load_config(ws).get("typesafe_api_key")
    state.plan_score, state.plan_confidence = jev.score_plan(key, state)
    state.step = "approve"
    return {"ok": True}


def reply_approve(ws, state: State, project: Project, text: str) -> dict:
    """The user's answer to the plan: approve, cancel, or change notes."""
    answer = text.strip().strip(".!").lower()

    if answer == "cancel":
        state.step = "done"
        state.outcome = "cancelled"
    elif answer != "approve":  # anything else is change notes; the plan stays, so the planner sees it
        state.notes = text.strip()
        state.step = "plan"
    else:
        repos = list(dict.fromkeys(task.repo for task in state.tasks))  # no duplicates, in order
        for repo in repos:
            path = project.repos[repo].path
            if not (Path(path) / ".git").exists():
                raise EaseError(f"{path} is not the top folder of a git repo")
            if is_dirty(path):
                raise EaseError(f"{path} has uncommitted changes. Commit or stash them, then approve again.")
            branch = current_branch(path)
            if branch == "HEAD" or branch.startswith("ease-feature/"):  # an old run's branch, or no branch at all
                where = "a detached HEAD" if branch == "HEAD" else branch
                raise EaseError(
                    f"{path} is on {where}. Check out the branch you want the work based on (like develop), "
                    "then approve again."
                )
        for repo in repos:
            if repo not in state.bases:
                state.bases[repo] = switch_to_branch(project.repos[repo].path, state.branch)
                save_state(ws, state)  # remember the base now, in case a later repo fails
        state.task = 0
        state.attempt = 1
        state.task_start = head(project.repos[state.tasks[0].repo].path)
        state.step = "build"
    return {"ok": True}


def reply_build(state: State, project: Project) -> dict:
    """The worker's message is free text. Run the checks, then commit everything (even if they fail)."""
    task, repo = current_task(state, project)
    state.checks_ok, state.checks_output = run_checks(repo.path, repo.checks)
    commit_all(repo.path, f"ease: {task.title}")  # after the checks, so it has what they changed
    state.step = "review"
    return {"ok": True}


def reply_review(ws, state: State, project: Project, text: str) -> dict:
    """Decide with the code rule and ask Jev too. In live mode Jev's answer counts, inside guardrails."""
    report = parse_report(text)
    if report.get("verdict") not in ("pass", "fail"):
        raise EaseError('reviewer report: verdict must be "pass" or "fail"')
    review_ok = report["verdict"] == "pass"
    findings = report.get("findings", [])
    if not review_ok and not findings:
        raise EaseError("reviewer report: a fail needs at least one finding")

    code = code_rule(state.checks_ok, review_ok, state.attempt)
    key = load_config(ws).get("typesafe_api_key")
    jev_choice, jev_confidence = jev.judge_task(key, state, findings)
    # What went wrong: for the worker's next attempt (fix), or for you (escalate).
    checks_problem = [] if state.checks_ok else ["Checks failed:\n" + state.checks_output]
    state.problems = checks_problem + findings

    final = code  # shadow: Jev is only logged
    if state.jev_mode == "live":
        final = live_rule(code, jev_choice, jev_confidence, state.attempt, state.problems)
        if final == "escalate" and code != "escalate":  # the summary would have no reason otherwise
            state.problems.insert(0, f"Jev chose to escalate (confidence {jev_confidence:.2f}).")
    reviewed = state.task + 1
    state.log.append(Decision(
        task=reviewed, attempt=state.attempt, checks_ok=state.checks_ok, review_ok=review_ok,
        code=code, final=final, jev=jev_choice, jev_confidence=jev_confidence,
    ))

    if final == "accept":
        if reviewed < len(state.tasks):
            state.task = reviewed
            state.attempt = 1
            state.problems = []
            state.task_start = head(project.repos[state.tasks[reviewed].repo].path)
            state.step = "build"
        else:
            finish(state, project)
    elif final == "fix":
        state.attempt += 1
        state.step = "build"
    else:  # escalate
        state.step = "done"
        state.outcome = "escalated"

    return {
        "ok": True, "task": reviewed, "decision": final, "code": code,
        "jev": jev_choice, "jev_confidence": jev_confidence,
    }


def code_rule(checks_ok: bool, review_ok: bool, attempt: int) -> str:
    """The decision rule: accept, fix, or (after 3 attempts) escalate."""
    if checks_ok and review_ok:
        return "accept"
    if attempt >= 3:
        return "escalate"
    return "fix"


def live_rule(code, jev, confidence, attempt, problems):
    """Live mode: Jev decides, inside guardrails. Otherwise the code rule's decision stands."""
    if jev is None or confidence is None or confidence < 0.5:
        return code                     # no answer, or Jev isn't sure
    if jev == "accept" and code != "accept":
        return code                     # failing work is never accepted
    if jev == "fix" and (not problems or attempt >= 3):
        return code                     # nothing to fix, or out of attempts
    return jev


def finish(state: State, project: Project) -> None:
    """All tasks are accepted. Open a PR in each repo that has a GitHub remote."""
    titles = "\n".join(f"- {task.title}" for task in state.tasks)
    pr_body = f"{state.plan_summary}\n\nTasks:\n{titles}"
    for repo, base in state.bases.items():
        path = project.repos[repo].path
        if commits_ahead(path, base, state.branch) == 0:
            continue
        if not has_remote(path):
            state.prs.append(f"{repo}: branch {state.branch} (no GitHub remote, no PR)")
            continue
        try:
            url = open_pr(path, state.branch, base, state.ticket_title, pr_body)
            state.prs.append(f"{repo}: {url}")
        except EaseError as error:
            state.prs.append(f"{repo}: PR failed: {error}")
    state.step = "done"
    state.outcome = "done"


def parse_report(text: str) -> dict:
    """Read the JSON from the last ```json block of an agent's message."""
    parts = text.split("```json")
    if len(parts) < 2:
        raise EaseError("report must end with a ```json block")
    return json.loads(parts[-1].split("```")[0])


def current_task(state: State, project: Project) -> tuple[Task, Repo]:
    """The task being worked on, and its repo."""
    task = state.tasks[state.task]
    return task, project.repos[task.repo]


# ---------- text for the user ----------

def plan_text(state: State) -> str:
    """The plan as Markdown, with Jev's score at the end."""
    jev_label = f"Jev ({state.jev_mode})"
    lines = [state.plan_summary, ""]
    for number, task in enumerate(state.tasks, 1):
        lines.append(f"{number}. {task.title} (repo: {task.repo})")
        lines += [f"   - {step}" for step in task.steps]
        lines.append(f"   Done when: {task.done_when}")
    lines.append("")

    if state.plan_score is None:
        lines.append(f"{jev_label}: no score (no key or no answer)")
    else:
        line = f"{jev_label}: plan score {state.plan_score:.1f}/{len(jev.PLAN_LEVELS)}"
        if state.plan_confidence is not None:
            line += f" (confidence {state.plan_confidence:.2f})"
        lines.append(line)
    return "\n".join(lines)


def summary(state: State) -> str:
    """How the run ended."""
    done = len(state.tasks) if state.outcome == "done" else state.task
    decisions = [d for d in state.log if d.jev is not None]
    agreed = len([d for d in decisions if d.jev == d.code])

    lines = [f"Outcome: {state.outcome}"]
    if state.bases:  # the branch exists only once the plan was approved
        lines.append(f"Branch: {state.branch}")
    lines += state.prs
    if state.outcome == "escalated":
        lines += ["Problems:", *[f"- {p}" for p in state.problems]]
    lines.append(f"Tasks done: {done}/{len(state.tasks)}")
    lines.append(f"Jev mode: {state.jev_mode}")
    lines.append(f"Jev agreed with the code rule on {agreed} of {len(decisions)} decisions")
    return "\n".join(lines)


# ---------- prompts for the agents (the agent files hold the general rules) ----------

def planner_prompt(state: State, project: Project) -> str:
    repos = [f"- {name}: {repo.path} (checks: `{repo.checks}`)" for name, repo in project.repos.items()]
    lines = [
        "# Plan this ticket", "",
        f"## Ticket: {state.ticket_title}", "", state.ticket_body, "",
        "## Project context", "", project.context or "(none)", "",
        "## Repos", "", *repos, "",
    ]
    if state.notes:
        lines += [
            "## The last plan", "", plan_text(state), "",
            f"The user asked for these changes: {state.notes}", "",
        ]
    lines += ["End your reply with a JSON block of this shape:", PLAN_SHAPE]
    return "\n".join(lines)


def worker_prompt(state: State, project: Project) -> str:
    task, repo = current_task(state, project)
    lines = [
        "# Build one task", "",
        f"Ticket: {state.ticket_title}",
        f"Task {state.task + 1}/{len(state.tasks)}: {task.title}", "",
        f"Repo: {repo.path}", "",
        "Steps:", *[f"- {step}" for step in task.steps], "",
        f"Done when: {task.done_when}", "",
    ]
    if state.problems:
        lines += ["Problems from the last attempt (fix these):", *[f"- {p}" for p in state.problems], ""]
    lines.append(f"Before you finish, run the checks: `{repo.checks}`")
    return "\n".join(lines)


def reviewer_prompt(state: State, project: Project) -> str:
    task, repo = current_task(state, project)
    lines = [
        "# Review one task", "",
        f"Ticket: {state.ticket_title}", "",
        f"Task: {task.title}",
        "Steps:", *[f"- {step}" for step in task.steps],
        f"Done when: {task.done_when}", "",
        f"Repo: {repo.path}",
        f"See the changes with: `git -C {repo.path} diff {state.task_start} HEAD`", "",
        f"Checks {'passed' if state.checks_ok else 'FAILED'}:",
        "```", state.checks_output, "```", "",
        "End your reply with a JSON block of this shape:",
        REVIEW_SHAPE,
    ]
    return "\n".join(lines)
