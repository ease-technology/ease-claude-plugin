import json
from pathlib import Path

import pytest

PILOT = Path(__file__).resolve().parent.parent / "pilot"


def test_workspaces_example_lists_the_three_workspaces_and_config_keys():
    config = json.loads((PILOT / "workspaces.example.json").read_text())
    assert [(w["name"], w["path"], w["config_dir"]) for w in config["workspaces"]] == [
        ("ease", "~/ease", "~/.claude-ease"),
        ("souk", "~/join-souk", "~/.claude-souk"),
        ("proper", "~/dev", "~/.claude-proper"),
    ]
    shared = ["dev", "develop", "main", "master"]
    assert {w["name"]: w["shared_branches"] for w in config["workspaces"]} == {
        "ease": [],
        "souk": shared,
        "proper": shared,
    }
    assert "shared_branches" not in config
    assert config["prod_markers"] and config["blocked_tools"]


@pytest.mark.parametrize("name, approvals", [("worker", False), ("pilot", True)])
def test_settings_template_renders_a_guard_hook(name, approvals):
    guard = "/opt/ease/pilot/guard.py"
    text = (PILOT / f"{name}-settings.template.json").read_text().replace("__GUARD_PY__", guard)
    [entry] = json.loads(text)["hooks"]["PreToolUse"]
    [hook] = entry["hooks"]
    assert entry["matcher"] == "*"
    assert hook["type"] == "command"
    assert hook["command"].startswith(f"python3 {guard} --config ")
    assert ("--approvals" in hook["command"]) is approvals


def test_pilot_settings_allow_waking_a_session_and_stopping_one():
    allow = json.loads((PILOT / "pilot-settings.template.json").read_text())["permissions"]["allow"]
    assert "Bash(claude stop *)" in allow
    assert any("env -i" in rule and "claude --bg --resume" in rule for rule in allow)
    assert "permissions" not in json.loads((PILOT / "worker-settings.template.json").read_text())
