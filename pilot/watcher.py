#!/usr/bin/env python3
"""The pilot's watcher: polls the managed sessions and the driven decisions files, and exits on news.

Run as `watcher.py --dir <pilot folder> [--interval 60]`. It writes its pid to
<dir>/watcher.pid, polls at once and then every interval, and exits silently once <dir>/pilot.session no
longer holds $CLAUDE_CODE_SESSION_ID. Standard library only.

Managed sessions are the `pilot-*` sessions and the sessions that uncommented `- ... (session <id>)`
lines in <dir>/orders.md name, read with `claude agents --json --all` for each config_dir in
<dir>/workspaces.json. A decisions file (<workspace>/.ease-context/handoffs/*-decisions.md) is driven
when its first line holds the id of a managed session. News is:
  - a managed session whose state moves into done, stopped, blocked, failed or waiting from none of
    those, including a session not seen before;
  - a new ASK JUAN, `heavy: started` or `answered: ASK JUAN` line in a driven decisions file.
A session missing from a poll keeps its last known state. `heavy: stopped` lines are never news.

The snapshot is saved to <dir>/watcher-state.json after every poll, so a restarted watcher still finds
what happened while none ran. With no saved snapshot, or an unreadable one, the first poll only takes a
baseline. The sessions orders.md names count as driven even when `claude agents` cannot list them.

While <dir>/watcher.pause exists and is under 5 minutes old, the watcher does not poll. Each line of it is a
session id whose state the next poll takes as known, without news, so the pilot's own `claude stop` and
wake never wake the pilot. The watcher keeps running through the pause, so no task exit wakes it either.

Each news line is appended to <dir>/inbox.txt before the snapshot is saved, so a kill between the two
writes repeats news rather than losing it. After a poll, if inbox.txt has a line, the watcher
prints its first line and exits 0, so a leftover inbox ends a new watcher on its first poll.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

PAUSE_LIMIT = 300
ENDED = {"done", "stopped", "blocked", "failed", "waiting"}
ORDER = re.compile(r"^- .*\(session ([0-9a-f-]{36})\)", re.M)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ENTRY = re.compile(r"^\d+\. \*\*(ASK JUAN|heavy: started|answered: ASK JUAN)")


def read(path, default=""):
    try:
        with open(path) as file:
            return file.read()
    except FileNotFoundError:
        return default


def save(folder, state):
    with tempfile.NamedTemporaryFile("w", dir=folder, suffix=".tmp", delete=False) as file:
        json.dump(state, file, indent=2)
    os.replace(file.name, os.path.join(folder, "watcher-state.json"))


def listed_sessions(config_dir):
    """The sessions `claude agents --json --all` lists for one config folder, or [] when the read fails."""
    try:
        result = subprocess.run(
            ["claude", "agents", "--json", "--all"],
            env={**os.environ, "CLAUDE_CONFIG_DIR": config_dir},
            capture_output=True, text=True, timeout=60,
        )
        sessions = json.loads(result.stdout) if result.returncode == 0 else []
        return [s for s in sessions if isinstance(s, dict) and s.get("sessionId")]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


def entries(workspaces, managed):
    """Every tracked `<file>:<line>` in the decisions files whose first line names a managed session."""
    found = []
    for workspace in workspaces:
        pattern = os.path.join(os.path.expanduser(workspace["path"]), ".ease-context", "handoffs", "*-decisions.md")
        for path in sorted(glob.glob(pattern)):
            lines = read(path).splitlines()
            if lines and set(UUID.findall(lines[0])) & managed:
                found += [f"{path}:{line}" for line in lines[1:] if ENTRY.match(line)]
    return found


def poll(folder, saved, accept):
    """The news since `saved`, and the new snapshot. `saved` is None when there is no baseline."""
    workspaces = json.loads(read(os.path.join(folder, "workspaces.json")))["workspaces"]
    orders = set(ORDER.findall(read(os.path.join(folder, "orders.md"))))

    def is_managed(session_id, name):
        return (name or "").startswith("pilot-") or session_id in orders

    known = (saved or {}).get("sessions", {})
    now = {}
    for workspace in workspaces:
        for s in listed_sessions(os.path.expanduser(workspace["config_dir"])):
            if is_managed(s["sessionId"], s.get("name")):
                now[s["sessionId"]] = {"name": s.get("name") or "", "state": s.get("state") or s.get("status")}
    sessions = {i: s for i, s in {**known, **now}.items() if is_managed(i, s["name"])}
    lines = entries(workspaces, set(sessions) | orders)
    snapshot = {"sessions": sessions, "entries": lines}
    if saved is None:
        return [], snapshot

    news = []
    for session_id, s in now.items():
        was = known.get(session_id, {}).get("state")
        if s["state"] in ENDED and was not in ENDED and session_id not in accept:
            news.append(f"session {s['name']} ({session_id}) is {s['state']}")
    seen = set(saved.get("entries", []))
    news += [f"new entry {line}" for line in lines if line not in seen]
    return news, snapshot


def load_saved(path):
    """The saved snapshot, or None when it is missing or unreadable."""
    try:
        saved = json.loads(read(path, "null"))
    except ValueError:
        return None
    return saved if isinstance(saved, dict) else None


def paused(folder):
    """The session ids in a fresh watcher.pause, or None when there is no fresh pause."""
    path = os.path.join(folder, "watcher.pause")
    try:
        if time.time() - os.path.getmtime(path) > PAUSE_LIMIT:
            return None
    except OSError:
        return None
    return set(read(path).split())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--interval", type=float, default=60)
    options = parser.parse_args()
    folder = options.dir
    me = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    with open(os.path.join(folder, "watcher.pid"), "w") as file:
        file.write(f"{os.getpid()}\n")

    state_path = os.path.join(folder, "watcher-state.json")
    saved = load_saved(state_path)
    accept = set()
    while True:
        if not me or read(os.path.join(folder, "pilot.session")).strip() != me:
            return 0
        held = paused(folder)
        if held is not None:
            accept |= held
            time.sleep(min(options.interval, 1))
            continue
        news, snapshot = poll(folder, saved, accept)
        held = paused(folder)
        if held is not None:
            accept |= held
            news = [line for line in news if not any(f"({i})" in line for i in held)]
        else:
            accept = set()
        if news:
            with open(os.path.join(folder, "inbox.txt"), "a") as file:
                file.writelines(line + "\n" for line in news)
        saved = snapshot
        save(folder, saved)
        waiting = [line for line in read(os.path.join(folder, "inbox.txt")).splitlines() if line.strip()]
        if waiting:
            print(waiting[0])
            return 0
        deadline = time.time() + options.interval
        while time.time() < deadline:
            time.sleep(min(1, max(0, deadline - time.time())))
            accept |= paused(folder) or set()


if __name__ == "__main__":
    sys.exit(main())
