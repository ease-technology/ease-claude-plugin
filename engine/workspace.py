"""Find the workspace and read or write its files (config, projects, run state)."""
import json
import os
import re
import time
from pathlib import Path

from engine.models import Project, Repo, State, state_from_json, state_to_json

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
    return Project(name, repos, context)


def slugify(text: str) -> str:
    """'Add a Login Page!' -> 'add-a-login-page'. Empty text gives 'run'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:40].strip("-")
    return slug or "run"


def new_state(project: str, title: str, body: str) -> State:
    """A fresh run for a ticket."""
    slug = slugify(title)
    return State(
        run_id=time.strftime("%Y%m%d-%H%M%S") + "-" + slug,
        project=project,
        ticket_title=title,
        ticket_body=body,
        branch="ease/" + slug,
    )


def run_dir(ws: Path, run_id: str) -> Path:
    return ws / CONTEXT_DIR / "runs" / run_id


def save_state(ws: Path, state: State) -> None:
    """Write state.json through a temp file, so a crash never leaves half a file."""
    folder = run_dir(ws, state.run_id)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "state.json.tmp"
    temp.write_text(state_to_json(state))
    os.replace(temp, folder / "state.json")


def load_state(ws: Path) -> State:
    """Load the newest run (run ids start with the time, so the newest sorts last)."""
    runs = ws / CONTEXT_DIR / "runs"
    names = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    if not names:
        raise EaseError("no runs yet")
    return state_from_json((runs / names[-1] / "state.json").read_text())
