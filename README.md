# ease

A Claude Code plugin that turns a ticket into a planned, built and reviewed branch, and a PR when the repo has a GitHub remote. Claude drives, a small Python engine owns the state and every decision, and Jev (TypeSafe's judgment model) shadows each decision without changing it.

## Run it

```
cd <workspace> && claude --plugin-dir <path to ease-claude-plugin>
/ease:build practice "Clean repo from any boilerplate"
```

The ticket can be plain text or a GitHub issue number. If a run stops, say "resume" or run `/ease:build resume`.

## Config

It lives in your workspace, not in the plugin.

```
<workspace>/.ease-context/
  config.json                    {"default_project": "practice", "typesafe_api_key": "..."}
  projects/<name>/project.json   {"repos": {"practice": {"path": "practice", "checks": "npm run lint && npm run build"}}}
  projects/<name>/context.md     optional notes for the planner
  runs/<run_id>/state.json       run state, including the Jev log
```

`checks` is any shell command the repo already uses, in any language. Without a key, Jev is skipped and the code rule runs alone.

## The flow

The planner agent writes the plan and Jev scores it. You see the plan and the score, then approve, change or cancel. For each task, the worker builds it, the engine commits and runs the checks, the reviewer reviews it, and the engine decides. At the end you get PRs, or just the branch when there is no remote.

The code rule is simple. If the checks pass and the review passes, the task is accepted. Otherwise, on the third attempt it escalates to you, and before that the worker tries again with the problems listed.

Each task changes exactly one repo. The engine works in your normal checkouts and creates the branch `ease/<slug>` from whatever branch each repo has checked out, and that branch is the PR base. When you approve the plan, each repo must be the top folder of its own git repo, with no uncommitted changes and no `ease/<slug>` branch yet.

## Jev

Jev only watches. It scores the plan, and after every review it says what it would do. The answer is logged in `state.json` under `log` next to the code rule's decision, so you can compare them.

## The engine

- `engine/models.py` is the data model: what a run, a task and a decision look like.
- `engine/workspace.py` reads the config and the run state.
- `engine/shell.py` runs git, gh and the repo's checks.
- `engine/jev.py` asks Jev and records its answers.
- `engine/flow.py` holds the steps and the code rule.
- `engine/cli.py` is the `start`, `next` and `reply` commands.

Run the tests with `.venv/bin/python -m pytest -q`.
