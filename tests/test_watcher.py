import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

WATCHER = Path(__file__).resolve().parent.parent / "pilot" / "watcher.py"
PILOT = "99999999-9999-9999-9999-999999999999"
WORKER = "11111111-1111-1111-1111-111111111111"
HANDED = "22222222-2222-2222-2222-222222222222"
OLD = "33333333-3333-3333-3333-333333333333"
OWN = "44444444-4444-4444-4444-444444444444"
FAKE_CLAUDE = """#!{python}
import os, pathlib, sys
sys.stdout.write((pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "agents.json").read_text())
"""


class Setup:
    """A pilot folder, one workspace and its config folder, read by a fake `claude`."""

    def __init__(self, root):
        self.dir = root / "pilot"
        self.ws = root / "ws"
        self.config = root / "config"
        for folder in (self.dir, self.ws / ".ease-context" / "handoffs", self.config):
            folder.mkdir(parents=True)
        workspace = {"name": "ws", "path": str(self.ws), "config_dir": str(self.config)}
        (self.dir / "workspaces.json").write_text(json.dumps({"workspaces": [workspace]}))
        (self.dir / "pilot.session").write_text(PILOT + "\n")
        self.orders()
        self.agents()

    def orders(self, text="# Orders\n"):
        (self.dir / "orders.md").write_text(text)

    def agents(self, *sessions):
        """Each session is (sessionId, name, state)."""
        listed = [{"id": i[:8], "sessionId": i, "name": n, "state": s} for i, n, s in sessions]
        (self.config / "agents.json").write_text(json.dumps(listed))

    def decisions(self, name, title_id, *lines):
        path = self.ws / ".ease-context" / "handoffs" / f"{name}-decisions.md"
        path.write_text(f"# Autopilot: goal (session {title_id})\n" + "".join(line + "\n" for line in lines))
        return path

    def start(self, *args):
        return subprocess.Popen(
            [sys.executable, str(WATCHER), "--dir", str(self.dir), "--interval", "0.05", *args],
            env={**os.environ, "CLAUDE_CODE_SESSION_ID": PILOT},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def baseline(self, *args):
        """Start a watcher and wait until it saved its first snapshot."""
        (self.dir / "watcher-state.json").unlink(missing_ok=True)
        watcher = self.start(*args)
        deadline = time.time() + 10
        while not (self.dir / "watcher-state.json").exists():
            assert time.time() < deadline, "no snapshot saved"
            time.sleep(0.02)
        return watcher


def append(path, line):
    with open(path, "a") as file:
        file.write(line + "\n")


def still_running(watcher):
    time.sleep(0.6)
    return watcher.poll() is None


def finish(watcher):
    out, err = watcher.communicate(timeout=10)
    assert watcher.returncode == 0, err
    return out


def stop(watcher):
    watcher.kill()
    watcher.communicate()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Put a fake `claude` first on PATH that prints $CLAUDE_CONFIG_DIR/agents.json."""
    bin_folder = tmp_path / "bin"
    bin_folder.mkdir()
    script = bin_folder / "claude"
    script.write_text(FAKE_CLAUDE.format(python=sys.executable))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_folder}:{os.environ['PATH']}")
    return Setup(tmp_path)


def test_heavy_stopped_is_not_news_and_heavy_started_is(setup):
    setup.agents((WORKER, "pilot-login", "busy"))
    path = setup.decisions("login", WORKER, "1. **Started.** login page")
    watcher = setup.baseline()
    assert int((setup.dir / "watcher.pid").read_text()) == watcher.pid
    append(path, "2. **heavy: stopped** tests done")
    assert still_running(watcher)
    append(path, "3. **heavy: started** jest with 8 workers")
    assert finish(watcher) == f"new entry {path}:3. **heavy: started** jest with 8 workers\n"


def test_ask_juan_in_a_file_not_driven_is_not_news(setup):
    setup.agents((WORKER, "pilot-login", "busy"), (OWN, "Juan's own", "busy"))
    own = setup.decisions("own", OWN)
    driven = setup.decisions("login", WORKER)
    watcher = setup.baseline()
    append(own, "1. **ASK JUAN: merge PR 3?** Run: gh pr merge 3")
    assert still_running(watcher)
    append(driven, "1. **answered: ASK JUAN 4.** yes")
    assert finish(watcher) == f"new entry {driven}:1. **answered: ASK JUAN 4.** yes\n"


def test_paused_session_moving_to_stopped_is_not_reported(setup):
    setup.orders(f"- [fix] ws: fix it (session {HANDED})\n")
    setup.agents((WORKER, "pilot-login", "busy"), (HANDED, "Fixing", "busy"))
    watcher = setup.baseline()
    pause = setup.dir / "watcher.pause"
    pause.write_text(HANDED + "\n")
    setup.agents((WORKER, "pilot-login", "busy"), (HANDED, "Fixing", "stopped"))
    assert still_running(watcher)
    pause.unlink()
    assert still_running(watcher)
    setup.agents((WORKER, "pilot-login", "failed"), (HANDED, "Fixing", "stopped"))
    assert finish(watcher) == f"session pilot-login ({WORKER}) is failed\n"


def test_stale_pause_file_is_ignored(setup):
    setup.agents((WORKER, "pilot-login", "busy"))
    watcher = setup.baseline()
    pause = setup.dir / "watcher.pause"
    pause.write_text(WORKER + "\n")
    old = time.time() - 600
    os.utime(pause, (old, old))
    setup.agents((WORKER, "pilot-login", "stopped"))
    assert finish(watcher) == f"session pilot-login ({WORKER}) is stopped\n"


def test_corrupt_snapshot_is_treated_as_missing(setup):
    setup.agents((WORKER, "pilot-login", "busy"))
    path = setup.decisions("login", WORKER, "1. **ASK JUAN: merge PR 3?** Run: gh pr merge 3")
    (setup.dir / "watcher-state.json").write_text("{not json")
    watcher = setup.start()
    deadline = time.time() + 10
    while (setup.dir / "watcher-state.json").read_text() == "{not json":
        assert time.time() < deadline, "no snapshot saved"
        time.sleep(0.02)
    assert still_running(watcher)
    append(path, "2. **ASK JUAN: merge PR 4?** Run: gh pr merge 4")
    assert finish(watcher) == f"new entry {path}:2. **ASK JUAN: merge PR 4?** Run: gh pr merge 4\n"


def test_order_session_counts_as_driven_when_claude_agents_fails(setup):
    setup.orders(f"- [fix] ws: fix it (session {HANDED})\n")
    (setup.config / "agents.json").write_text("not json")
    path = setup.decisions("fix", HANDED, "1. **ASK JUAN: old ask?** Run: gh pr merge 1")
    watcher = setup.baseline()
    setup.agents((HANDED, "Fixing", "busy"))
    assert still_running(watcher)
    append(path, "2. **ASK JUAN: new ask?** Run: gh pr merge 2")
    assert finish(watcher) == f"new entry {path}:2. **ASK JUAN: new ask?** Run: gh pr merge 2\n"


def test_event_while_no_watcher_runs_is_reported_on_the_next_first_poll(setup):
    setup.agents((WORKER, "pilot-login", "busy"))
    path = setup.decisions("login", WORKER)
    watcher = setup.baseline()
    (setup.dir / "pilot.session").write_text(OWN + "\n")
    assert finish(watcher) == ""
    (setup.dir / "pilot.session").write_text(PILOT + "\n")
    append(path, "1. **ASK JUAN: drop the old table?** Run: psql -c 'drop table old'")
    line = f"new entry {path}:1. **ASK JUAN: drop the old table?** Run: psql -c 'drop table old'"
    assert finish(setup.start()) == line + "\n"
    assert (setup.dir / "inbox.txt").read_text() == line + "\n"
    assert finish(setup.start()) == line + "\n"


def test_commented_order_session_is_ignored(setup):
    setup.orders(
        "# Orders\n"
        f"- [live] ws: goal (session {HANDED})\n"
        f"# done 2026-11-14: [old] ws: goal (session {OLD})\n"
    )
    setup.agents((HANDED, "Live", "busy"), (OLD, "Old", "busy"))
    watcher = setup.baseline()
    setup.agents((HANDED, "Live", "busy"), (OLD, "Old", "stopped"))
    assert still_running(watcher)
    setup.agents((HANDED, "Live", "waiting"), (OLD, "Old", "stopped"))
    assert finish(watcher) == f"session Live ({HANDED}) is waiting\n"
