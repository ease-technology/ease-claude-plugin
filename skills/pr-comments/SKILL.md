---
name: pr-comments
description: Use when the user wants to work through the open review comments on a PR, in their own words (for example "handle the comments on PR 12" or "go through the review threads on this branch"), runs /ease:pr-comments, or asks to resume an ease PR comments run. Judges each open thread, fixes the agreed ones on the PR's branch, pushes them and resolves those threads.
---

# ease pr-comments

You are the driver. A Python engine owns the state and every decision, and its agents judge the threads and make the fixes; you only ask the engine what is next, do that, and tell it the result. The user set up /ease:pr-comments so that running the engine is authorized.

Write the full engine command in every Bash call, because shell variables do not persist between calls. Always pass `timeout: 600000` to the Bash tool for engine calls. The engine command is `python3 "<skill base dir>/../../bin/ease-engine" pr-comments`, run from the workspace folder (the one that contains `.ease-context/`). Every call prints one JSON object. If it has an `"error"`, show it word for word and stop. The user can say "resume" once they have fixed it. If the output also shows a `jev: ...` line, mention it to the user in one short line.

## Start

Work out the project and the repo from the user's words; never ask them to name either. The projects are the folders in `.ease-context/projects/`: read each one's `project.json` (its repo names) and `context.md`. Pick the project whose name, repos or context match what the user said or the PR link they gave. If nothing matches, leave the project out and the engine uses `default_project`. If the project has several repos, pass `--repo <name>` with the one that matches; with only one repo, leave it out. If two projects or two repos fit equally well, ask the user which one.

Send the PR's number in digits or its github.com link, or nothing for the PR of the current branch, through a quoted heredoc, so nothing in it is expanded:

```bash
python3 "<skill base dir>/../../bin/ease-engine" pr-comments start [project] [--repo <name>] <<'EASE_PR'
<the PR number or link, or nothing>
EASE_PR
```

Never switch branches for the user. If the engine refuses because the repo is on another branch, that is an error like any other.

The engine answers with the run id. Show it once. Every `pr-comments next` and `pr-comments reply` names this run id, so runs started in other sessions are never touched.

## Resume

"resume" continues a PR comments run. If this conversation already has a run id, use it. Otherwise run `pr-comments runs`, which lists the PR comments runs that aren't done. Take the only one, or the one the user's words point to by its title or id. If more than one fits, ask the user which. If none is listed, say so and stop. Then go to the loop.

## The loop

Run `pr-comments next <run_id>`, do what it says, then run `pr-comments reply <run_id>`, and repeat. Each `next` returns one of three types.

**spawn.** Call the Agent tool with `subagent_type` set to the `agent` value and the prompt set to the `prompt` value, exactly as given. Wait for it to finish. Reply with its final message, unchanged:

```bash
python3 "<skill base dir>/../../bin/ease-engine" pr-comments reply <run_id> <<'EASE_REPLY'
<the agent's final message>
EASE_REPLY
```

**ask_user.** Show `message` as it is. Then call AskUserQuestion once, with `questions` exactly as given. Reply with what the user answered, keyed by each question's text: the option label they picked, or their own words for "Other".

```bash
python3 "<skill base dir>/../../bin/ease-engine" pr-comments reply <run_id> <<'EASE_REPLY'
{"answers": {"<question text>": "<their answer>"}}
EASE_REPLY
```

The reply may list answers under `rejected`, because words for "Other" must start with Fix or Skip. Tell the user so in one line and run `pr-comments next <run_id>` again, which asks about those threads again. The other answers are already saved.

**done.** Show `summary` and stop.

## Rules

Never edit code, run git or post anything to GitHub, not even a drafted reply; only the engine pushes and resolves threads, and the summary's drafted replies are for the user to post. Run one agent at a time. Never edit files in `.ease-context/pr-runs/`. Never repeat a `reply`. If a result is unclear, run `pr-comments next <run_id>`.
