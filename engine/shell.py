"""Run commands, plus small git and gh helpers."""
import os
import subprocess

from engine.workspace import EaseError

TIMEOUT_S = 540  # just under the skill's 600 s Bash limit, so we answer with JSON first


def run(cmd: list[str], cwd) -> tuple[int, str]:
    """Run a command. Returns (exit code, stdout + stderr). Never raises."""
    try:
        done = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S
        )
    except FileNotFoundError as error:  # a missing program or a missing cwd folder; the message names it
        return 127, str(error)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {TIMEOUT_S}s"
    return done.returncode, done.stdout + done.stderr


def must(cmd: list[str], cwd) -> str:
    """Like run, but a failing command raises EaseError. Returns the output."""
    code, out = run(cmd, cwd)
    if code != 0:
        raise EaseError(f"`{' '.join(cmd)}` failed: {out.strip()[-500:]}")
    return out.strip()


def git(cwd, *args: str) -> str:
    return must(["git", *args], cwd)


def is_dirty(cwd) -> bool:
    return git(cwd, "status", "--porcelain") != ""


def head(cwd) -> str:
    return git(cwd, "rev-parse", "HEAD")


def current_branch(cwd) -> str:
    """The branch we are on. A detached HEAD gives "HEAD"."""
    return git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def switch_to_branch(cwd, branch: str) -> str:
    """Create `branch` and switch to it (fails if it exists). Returns the branch we were on."""
    base = current_branch(cwd)
    git(cwd, "switch", "-c", branch)
    return base


def commit_all(cwd, message: str) -> None:
    """Commit every change. Does nothing if there is nothing to commit."""
    git(cwd, "add", "-A")
    code, _ = run(["git", "diff", "--cached", "--quiet"], cwd)
    if code == 0:
        return
    git(cwd, "commit", "-m", message)


def run_checks(cwd, command: str) -> tuple[bool, str]:
    """Run the repo's checks in a login shell (so npm/nvm are on PATH)."""
    code, out = run([os.environ.get("SHELL", "/bin/sh"), "-lc", command], cwd)
    last_lines = "\n".join(out.strip().splitlines()[-40:])
    return code == 0, last_lines


def has_remote(cwd) -> bool:
    code, _ = run(["git", "remote", "get-url", "origin"], cwd)
    return code == 0


def commits_ahead(cwd, base: str, branch: str) -> int:
    return int(git(cwd, "rev-list", "--count", f"{base}..{branch}"))


def open_pr(cwd, branch: str, base: str, title: str, body: str) -> str:
    """Push the branch and open a pull request. Returns the PR URL."""
    git(cwd, "push", "-u", "origin", branch)
    out = must(
        ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
        cwd,
    )
    lines = out.splitlines()
    urls = [line for line in lines if line.startswith("https://")]  # gh may add warnings after the URL
    return (urls or lines)[-1]

