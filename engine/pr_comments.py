"""The PR comments flow: one pass over a PR's open review threads. So far it starts a run and refuses unsafe states."""
import re
from pathlib import Path

from engine.models import Project, PrState, Thread
from engine.shell import capture, current_branch, git, head, is_dirty, pr_view, repo_name, review_threads, run
from engine.workspace import (
    EaseError, build_runs, load_project, new_pr_state, pr_runs, project_and_mode, save_state, state_dir,
)

PR_LINK = re.compile(r"https?://(?:www\.)?github\.com/([^/\s]+/[^/\s]+)/pull/([0-9]+)(?:[/?#]\S*)?")
HIDDEN = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)  # an opening marker with no end hides the rest
CODE_LINES = 5                     # how many lines to show on each side of a thread's line


# ---------- start ----------

def start(ws, project_name: str | None, text: str, repo: str | None = None) -> dict:
    """Begin a run on a PR: `text` is its number, its link, or empty for the PR of the current branch.
    With no project name, use default_project from config.json. Nothing is saved until every check passes,
    and no check changes the repo."""
    project_name, jev_mode = project_and_mode(ws, project_name)
    project = load_project(ws, project_name)
    ref, link_repo = parse_pr_ref(text)
    repo = choose_repo(project, repo)
    path = project.repos[repo].path

    if not (Path(path) / ".git").exists():
        raise EaseError(f"{path} is not the top folder of a git repo")
    pr = pr_view(path, ref)
    full_name = repo_name(path)
    check_pr(ws, path, pr, link_repo, full_name)

    owner, name = full_name.split("/")
    viewer, nodes = review_threads(path, owner, name, pr["number"])
    threads = [build_thread(path, node) for node in nodes if not node["isResolved"]]

    title = f"PR {pr['number']}: {pr['title']}"
    body = f"Open review threads on {pr['url']} ({pr['title']}), branch {pr['headRefName']}."
    state = new_pr_state(
        project_name, title, body, pr["headRefName"],
        repo, pr["number"], pr["url"], pr["headRefOid"], viewer, threads,
    )
    state.jev_mode = jev_mode  # the run keeps this mode, even if config.json changes later
    if not threads:
        state.step = "done"
        state.outcome = "no open threads"
    save_state(ws, state)
    return {"run_id": state.run_id}


def parse_pr_ref(text: str) -> tuple[str, str | None]:
    """What to give `gh pr view`, and the owner/name of a link (None for a number or empty text)."""
    text = text.strip()
    if not text or re.fullmatch("[0-9]+", text):
        return text, None
    link = PR_LINK.fullmatch(text)
    if not link:
        raise EaseError(f"not a PR number or a github.com pull link: {text}")
    full_name, number = link.groups()
    return f"https://github.com/{full_name}/pull/{number}", full_name


def choose_repo(project: Project, repo: str | None) -> str:
    """The repo to work in. It may go unnamed only when the project has just one."""
    names = ", ".join(project.repos)
    if repo is None and len(project.repos) > 1:
        raise EaseError(f"this project has several repos, so name one with --repo: {names}")
    if repo is None:
        return next(iter(project.repos))
    if repo not in project.repos:
        raise EaseError(f"unknown repo: {repo}. This project's repos are: {names}")
    return repo


def check_pr(ws, path: str, pr: dict, link_repo: str | None, full_name: str) -> None:
    """Refuse a PR this run can't safely work on. The busy check comes before the branch, dirty and HEAD checks,
    so the leftovers of a stopped run name that run."""
    number, branch, pr_head = pr["number"], pr["headRefName"], pr["headRefOid"]
    # GitHub ignores case in names, so a link may differ from the repo's real spelling
    if link_repo is not None and link_repo.lower() != full_name.lower():
        raise EaseError(f"that link is a PR on {link_repo}, but {path} is {full_name}")
    if pr["state"] != "OPEN":
        raise EaseError(f"PR #{number} is {pr['state'].lower()}, not open")
    if pr["isCrossRepository"]:
        raise EaseError(f"PR #{number} comes from a fork, and a run pushes only to origin")

    for other in [*build_runs(ws), *pr_runs(ws)]:
        if other.step != "done" and other.branch == branch:
            raise EaseError(
                f"branch {branch} is busy with run {other.run_id} ({other.ticket_title}). Start again once that "
                f"run is done, or, if you dropped it, delete its folder {state_dir(ws, other)}."
            )

    checked_out = current_branch(path)
    if checked_out != branch:
        where = "a detached HEAD" if checked_out == "HEAD" else checked_out
        raise EaseError(f"{path} is on {where}, not the PR's branch {branch}. Check it out, then start again.")
    if is_dirty(path):
        raise EaseError(f"{path} has uncommitted changes. Commit or stash them, then start again.")
    local = head(path)
    if local != pr_head:
        raise EaseError(head_mismatch(path, local, pr_head))


def head_mismatch(path: str, local: str, pr_head: str) -> str:
    """Why HEAD isn't the PR's head: the commits that differ, or both SHAs when the PR's head isn't here.
    It never fetches, so an unknown commit stays unknown."""
    code, _ = run(["git", "cat-file", "-e", f"{pr_head}^{{commit}}"], path)
    if code != 0:
        return (
            f"{path} is at {local}, but the PR's head is {pr_head}, which is not in this repo. "
            "Bring the two together yourself, then start again."
        )
    only_here = git(path, "log", "--oneline", f"{pr_head}..HEAD") or "(none)"
    only_on_pr = git(path, "log", "--oneline", f"HEAD..{pr_head}") or "(none)"
    return (
        f"{path} differs from the PR's head {pr_head}.\n"
        f"Commits only here:\n{only_here}\n"
        f"Commits only on the PR:\n{only_on_pr}\n"
        "Push, pull or reset them yourself, then start again."
    )


def build_thread(path: str, node: dict) -> Thread:
    """A Thread from a fetched node. Comments keep only their id, author and body with its hidden text removed."""
    comments = node["comments"]
    line = node["line"] or node["originalLine"]  # an outdated thread only has its original line
    return Thread(
        id=node["id"],
        path=node["path"],
        line=line,
        outdated=node["isOutdated"],
        comments=[{"id": c["id"], "author": c["author"], "body": strip_hidden(c["body"])} for c in comments],
        code=code_at(path, node["path"], line, comments[0]["diffHunk"] if comments else ""),
    )


def strip_hidden(body: str) -> str:
    """Remove HTML comments, repeating because removing one can form another out of the text around it."""
    while True:
        stripped = HIDDEN.sub("", body)
        if stripped == body:
            return body
        body = stripped


def code_at(path: str, file: str, line: int | None, hunk: str) -> str:
    """The numbered lines around `line` at HEAD, or the comment's diff hunk with no line or no such file or line."""
    if line is None:
        return hunk
    code, out, _ = capture(["git", "show", f"HEAD:{file}"], path)
    lines = out.removesuffix("\n").split("\n")
    if code != 0 or not 1 <= line <= len(lines):
        return hunk
    first = max(line - CODE_LINES, 1)
    return "\n".join(f"{number}: {text}" for number, text in enumerate(lines[first - 1:line + CODE_LINES], first))


def open_runs(ws) -> dict:
    """The PR comments runs that aren't done, for resuming one."""
    return {"runs": [
        {"run_id": pr_run.run_id, "project": pr_run.project, "title": pr_run.ticket_title, "step": pr_run.step}
        for pr_run in pr_runs(ws) if pr_run.step != "done"
    ]}


# ---------- next ----------

def next_action(ws, state: PrState) -> dict:
    """Tell the skill what to do now."""
    if state.step == "done":
        return {"type": "done", "summary": summary(state)}
    raise EaseError(f"step {state.step} of a PR comments run is not built yet")


# ---------- reply ----------

def reply(ws, state: PrState, text: str) -> dict:
    """Handle what came back (an agent's report or the user's words), then save."""
    if state.step == "done":
        raise EaseError("this run is done")
    raise EaseError(f"step {state.step} of a PR comments run is not built yet")


# ---------- text for the user ----------

def summary(state: PrState) -> str:
    """How the run ended."""
    return "\n".join([f"Outcome: {state.outcome}", f"Branch: {state.branch}", f"PR: {state.pr_url}"])
