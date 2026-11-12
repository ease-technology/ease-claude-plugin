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
    assert config["shared_branches"] and config["prod_markers"] and config["blocked_tools"]


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
