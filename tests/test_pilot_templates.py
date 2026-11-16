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


@pytest.mark.parametrize("name", ["worker"])
def test_settings_template_renders_a_guard_hook(name):
    guard = "/opt/ease/pilot/guard.py"
    text = (PILOT / f"{name}-settings.template.json").read_text().replace("__GUARD_PY__", guard)
    [entry] = json.loads(text)["hooks"]["PreToolUse"]
    [hook] = entry["hooks"]
    assert entry["matcher"] == "*"
    assert hook["type"] == "command"
    assert hook["command"].startswith(f"python3 {guard} --config ")
    assert "--approvals" not in hook["command"]


def test_pilot_settings_template_is_gone_and_worker_settings_grant_nothing():
    assert not (PILOT / "pilot-settings.template.json").exists()
    assert "permissions" not in json.loads((PILOT / "worker-settings.template.json").read_text())
