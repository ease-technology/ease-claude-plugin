"""Find the workspace and read or write its files (config, projects, build and ticket runs)."""
import json
import os
import re
import time
from pathlib import Path

from engine.models import (
    Project, Repo, State, TicketState, state_from_json, state_to_json, ticket_state_from_json,
)

CONTEXT_DIR = ".ease-context"


class EaseError(Exception):
    """A problem to show the user. The CLI prints it as {"error": ...}."""


def find_workspace(start: Path | None = None) -> Path:
    """Walk up from `start` to the first folder that contains .ease-context/."""
    folder = (start or Path.cwd()).resolve()
    for candidate in [folder, *folder.parents]:
        if (candidate / CONTEXT_DIR).is_dir():
            return candidate
    raise EaseError("no .ease-context/ folder found here or above")


def load_config(ws: Path) -> dict:
    """Read config.json. A missing file means an empty config."""
    path = ws / CONTEXT_DIR / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_project(ws: Path, name: str) -> Project:
    """Read a project. A missing or extra key in a repo raises TypeError. Repo paths become absolute."""
    folder = ws / CONTEXT_DIR / "projects" / name
    file = folder / "project.json"
    if not file.exists():
        raise EaseError(f"unknown project: {name}")

    repos = {repo: Repo(**info) for repo, info in json.loads(file.read_text())["repos"].items()}
    if not repos:
        raise EaseError(f"bad project.json for {name}: repos is empty")
    for repo in repos.values():
        repo.path = str(ws / repo.path)  # project.json paths are relative to the workspace

    context_file = folder / "context.md"
    context = context_file.read_text() if context_file.exists() else ""
    return Project(repos, context)


def project_and_mode(ws: Path, project_name: str | None) -> tuple[str, str]:
    """The project for a new run (the given one, else default_project) and the jev_mode, both checked."""
    config = load_config(ws)
    project_name = project_name or config.get("default_project")
    if not project_name:
        raise EaseError("no project given and no default_project in config.json")
    load_project(ws, project_name)  # fails early if the project is unknown or bad
    jev_mode = config.get("jev_mode", "shadow")
    if jev_mode not in ("shadow", "live"):
        raise EaseError('jev_mode must be "shadow" or "live"')
    return project_name, jev_mode


def slugify(text: str) -> str:
    """'Add a Login Page!' -> 'add-a-login-page'. Empty text gives 'run'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:40].strip("-")
    return slug or "run"


def new_state(project: str, title: str, body: str, branch: str | None = None) -> State:
    """A fresh run for a ticket. With no branch name, the work goes on ease-feature/<slug>."""
    slug = slugify(title)
    return State(
        run_id=time.strftime("%Y%m%d-%H%M%S") + "-" + slug,
        project=project,
        ticket_title=title,
        ticket_body=body,
        branch=branch or "ease-feature/" + slug,
    )


def new_ticket_state(project: str, idea: str) -> TicketState:
    """A fresh ticket run for an idea."""
    return TicketState(
        run_id=time.strftime("%Y%m%d-%H%M%S") + "-" + slugify(idea.splitlines()[0]),
        project=project,
        idea=idea,
    )


def state_dir(ws: Path, state: State | TicketState) -> Path:
    """A run's folder: runs/<run_id> for build runs, ticket-runs/<run_id> for ticket runs."""
    kind = "ticket-runs" if isinstance(state, TicketState) else "runs"
    return ws / CONTEXT_DIR / kind / state.run_id


def save_state(ws: Path, state: State | TicketState) -> None:
    """Write state.json through a temp file, so a crash never leaves half a file."""
    folder = state_dir(ws, state)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "state.json.tmp"
    temp.write_text(state_to_json(state))
    os.replace(temp, folder / "state.json")


def state_text(folder: Path, run_id: str) -> str:
    """state.json of one run in `folder`."""
    file = folder / run_id / "state.json"
    if not file.exists():
        raise EaseError(f"unknown run: {run_id}")
    return file.read_text()


def state_texts(folder: Path) -> list[str]:
    """state.json of every run in `folder`, oldest first (run ids start with the time)."""
    return [file.read_text() for file in sorted(folder.glob("*/state.json"))]


def load_state(ws: Path, run_id: str) -> State:
    """Load a build run by its id."""
    return state_from_json(state_text(ws / CONTEXT_DIR / "runs", run_id))


def load_ticket_state(ws: Path, run_id: str) -> TicketState:
    """Load a ticket run by its id."""
    return ticket_state_from_json(state_text(ws / CONTEXT_DIR / "ticket-runs", run_id))


def build_runs(ws: Path) -> list[State]:
    """Every build run, oldest first."""
    return [state_from_json(text) for text in state_texts(ws / CONTEXT_DIR / "runs")]


def ticket_runs(ws: Path) -> list[TicketState]:
    """Every ticket run, oldest first."""
    return [ticket_state_from_json(text) for text in state_texts(ws / CONTEXT_DIR / "ticket-runs")]
