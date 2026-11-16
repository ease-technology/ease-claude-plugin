"""Every skill's SKILL.md has frontmatter the plugin loader can read."""
import pathlib
import re

SKILLS = pathlib.Path(__file__).parent.parent / "skills"
GUARD_HOOK = (
    'command: python3 "${CLAUDE_PLUGIN_ROOT}/pilot/guard.py" --config ~/ease/.ease-context/pilot/workspaces.json'
    " --approvals ~/ease/.ease-context/pilot/approvals.json --allow-pilot-commands"
)


def frontmatter(path):
    """The lines between the opening and closing `---` of a SKILL.md."""
    lines = path.read_text().splitlines()
    assert lines and lines[0] == "---", f"{path} does not start with ---"
    assert "---" in lines[1:], f"{path} has no closing ---"
    return lines[1 : lines.index("---", 1)]


def field(lines, key):
    """The value of the `key:` line, or None when there is none."""
    for line in lines:
        if line.startswith(f"{key}:"):
            return line[len(key) + 1 :].strip()
    return None


def test_every_skill_has_name_and_description():
    paths = sorted(SKILLS.glob("*/SKILL.md"))
    assert paths, "no skills found"
    for path in paths:
        lines = frontmatter(path)
        assert field(lines, "name") == path.parent.name, path
        assert field(lines, "description"), f"{path} has an empty description"


def test_autopilot_skill_names_its_rules():
    text = (SKILLS / "autopilot" / "SKILL.md").read_text()
    for term in (
        "jev-opinion",
        "--by autopilot",
        "ASK JUAN",
        "CLAUDE_CODE_SESSION_ID",
        "cache_read_input_tokens",
        "200,000",
        "Order: handed off",
        "Handoff: <absolute path>",
        "Continue from <path>",
        "**heavy: started <command>",
        "**heavy: stopped <command>",
    ):
        assert term in text, term


def test_pilot_skill_names_its_rules():
    path = SKILLS / "pilot" / "SKILL.md"
    assert field(frontmatter(path), "disable-model-invocation") == "true"
    text = path.read_text()
    for term in (
        "orders.md",
        "approvals.json",
        "pilot-*",
        "act only on `pilot-*` sessions and the sessions Juan handed over, which `orders.md` names by id, and only read every other session",
        "Take over <session>, <goal>",
        "env -i HOME=\"$HOME\" PATH=\"$PATH\" USER=\"$USER\" LOGNAME=\"$LOGNAME\" CLAUDE_CONFIG_DIR=<dir> claude --bg --resume <sessionId> \"<message>\"",
        "Never add other flags",
        "(session <sessionId>)",
        "Tell <session> <message>",
        "give back <session>",
        "never stop an interactive session",
        "Press ← or type /bg in that window, then tell me again.",
        "with the session's name and id",
        "## Talking to Juan",
        "at most 3 short lines",
        "A wake that finds nothing new sends nothing",
        "is never sent again on a later wake",
        "Show sessions",
        "--disallowedTools AskUserQuestion",
        "/ease:autopilot",
        "jev-opinion",
        "ASK JUAN",
        "/ease:pilot stop",
        "caffeinate.pid",
        "counts as order `<slug>`'s worker",
        "size unknown",
        "cache_read_input_tokens",
        "Order: handed off",
        "Continue from <path>",
        "pilot-<slug>-<n>",
        "<original name>-<n>",
        "does not count toward the 3-restart limit",
        "within 60 seconds",
        "handoffs/pilot.md",
        "grep -H '^[0-9]*\\. \\*\\*heavy: '",
        "grep -H '^[0-9]*\\. \\*\\*ASK JUAN'",
        "run_in_background",
        "watcher.pid",
        "kill -0",
        "done, stopped, blocked, failed or waiting",
        "Moves among busy, working and idle are not news, and neither is a move from one ended state to another, such as blocked to stopped after `claude stop`.",
        "each next wakeup is set to the 1-hour maximum",
        ".ease-context/handoffs/*-decisions.md",
        'w["path"]',
        "**Weigh the load.**",
        "run `ps` on its process tree: `ps -A -o pid=,ppid=,rss=,%cpu=,command=`, walked from that pid",
        "Decide by judgment; no number triggers an action.",
        "send it a slow-down request with [Sending a message](#sending-a-message): `claude stop <id>`, wait 10 seconds, then the exact resume command",
        "names the lighter way, such as rerun the tests with `--maxWorkers=1`",
        "a stale `.git/index.lock`",
        "A stop is always followed at once by the resume; nothing is paused.",
        "Never stop an interactive session or any session that is not `pilot-*` or handed over in `orders.md`.",
        "Do not ask the same session again until it has a new heavy entry.",
        "with the session's name, the reason and the heavy entry it answers",
        "that no managed session noted or owns",
        "stop nothing, log it in `decisions.md`, and tell Juan in one line, once.",
        "Each request to slow down is exactly one line naming the session and the request.",
        "Unmanaged load is one line.",
        "A wake that finds nothing heavy sends nothing about resources.",
        "Starts still follow `max_workers` only.",
        "How's the computer?",
        "11. Measure your own size",
        GUARD_HOOK,
        "--allow-pilot-commands",
        "pilot.session",
        "permissionMode",
        "Type /rc to reach it from your phone",
        "The pilot is already running",
        "Pilot is full. Type /ease:pilot stop, then /clear, then /ease:pilot.",
        'env -i HOME="$HOME" PATH="$PATH" USER="$USER" LOGNAME="$LOGNAME" CLAUDE_CONFIG_DIR=<config_dir> claude --bg -n pilot-<slug> --permission-mode auto --disallowedTools AskUserQuestion --settings ~/ease/.ease-context/pilot/worker-settings.json',
        "claude --bg -n pilot-<slug> --permission-mode auto --disallowedTools AskUserQuestion --settings ~/ease/.ease-context/pilot/worker-settings.json",
        'env -i HOME="$HOME" PATH="$PATH" USER="$USER" LOGNAME="$LOGNAME" CLAUDE_CONFIG_DIR=<dir> claude --bg -n <original name>-<n>',
        "ignoring --session-id", "the shell does not expand `~` after `=` in an argument to `env`", "a session that is busy, idle or even done still counts as running",
        "add \"build in a worktree\" to the worker's goal",
        "Do the same when you can't tell.",
        "When an order is to answer a PR's review comments and another live session may be using that repo, hold the order until the repo is free.",
    ):
        assert term in text, term


def test_pilot_waking_names_no_monitor_and_no_ten_minutes():
    text = (SKILLS / "pilot" / "SKILL.md").read_text()
    waking = text[text.index("## Waking") : text.index("## Each wake")]
    for term in ("Monitor", "10 minutes"):
        assert term not in waking, term


def test_pilot_skill_runs_in_the_foreground_without_remote_control():
    text = (SKILLS / "pilot" / "SKILL.md").read_text()
    for term in ("--remote-control", "/ease:pilot run", "pilot-settings.json"):
        assert term not in text, term
    lines = [line for line in text.splitlines() if "claude --bg -n" in line]
    assert lines
    for line in lines:
        assert "env -i HOME=" in line.split("claude --bg -n")[0], line


def test_skills_use_worktrees_instead_of_a_workspace_limit():
    assert "at most one per workspace" not in (SKILLS / "pilot" / "SKILL.md").read_text()
    for name in ("build", "autopilot"):
        assert "`approve worktree`" in (SKILLS / name / "SKILL.md").read_text(), name


def test_skills_name_no_resource_threshold():
    number = re.compile(r"\d+(\.\d+)?\s*(GB|MB|%)|load average\D{0,5}\d", re.IGNORECASE)
    for name in ("autopilot", "pilot"):
        text = (SKILLS / name / "SKILL.md").read_text()
        match = number.search(text)
        assert not match, f"{name}: {match and match.group(0)}"
