---
name: build
description: Use when the user runs /ease:build with a ticket, or asks to resume an ease run. Turns a ticket into a planned, built and reviewed branch, and a PR when the repo has a GitHub remote.
---

# ease build

You are the driver. A Python engine owns the state and makes every decision; you only ask it what is next, do that, and tell it the result. The user set up /ease:build so that running the engine is authorized. The engine, not you, commits, pushes and opens PRs.

Write the full engine command in every Bash call, because shell variables do not persist between calls. Always pass `timeout: 600000` to the Bash tool for engine calls. The engine command is `python3 "<skill base dir>/../../bin/ease-engine"`, run from the workspace folder (the one that contains `.ease-context/`). Every call prints one JSON object. If it has an `"error"`, show it word for word and stop. The user can say "resume" once they have fixed it. If the output also shows a `jev: ...` line, mention it to the user in one short line.

## Start

`/ease:build [project] <ticket>` runs `start`. Pass the project as an argument if the user named one (projects are the folders in `.ease-context/projects/`); without one, the engine uses `default_project`.

The user may say it in their own words. The engine takes plain text, so you turn their words into the ticket. If they point at an existing ticket (a number, a link, anything), read it yourself, for example with `gh issue view <number or link>`, run inside the repo folder for a bare number. Then send its title as the first line and its full text below. Otherwise, write the ticket as a clear, self-contained description of the work, including anything relevant from this conversation, because the planner never sees the conversation.

Send the ticket through a quoted heredoc, so nothing in it is expanded:

```bash
python3 "<skill base dir>/../../bin/ease-engine" start [project] <<'EASE_TICKET'
<the ticket>
EASE_TICKET
```

Show the run id once. `/ease:build resume` goes straight to the loop.

## The loop

Run `next`, do what it says, then run `reply`, and repeat. Each `next` returns one of three types.

**spawn.** Call the Agent tool with `subagent_type` set to the `agent` value and the prompt set to the `prompt` value, exactly as given. Wait for it to finish. Reply with its final message, unchanged, through a quoted heredoc so nothing in it is expanded:

```bash
python3 "<skill base dir>/../../bin/ease-engine" reply <<'EASE_REPLY'
<the agent's final message>
EASE_REPLY
```

After a reviewer's reply, print one line: `Task N: <decision> (code rule: <code>, Jev: <jev> <jev_confidence>)`, or `(code rule: <code>, Jev: no answer)` when `jev` is null.

**ask_user.** Show `message` as it is, then ask with AskUserQuestion, with two options: **Approve** and **Cancel**. To change the plan, the user types the changes into its free-text "Other" answer. Reply `approve`, `cancel`, or those changes in the user's own words, using the same heredoc. This is the only question you ask during a run.

**done.** Show `summary` and stop.

## Rules

Never edit code, run git or run checks yourself; reading the ticket at the start is the one exception. Run one agent at a time. Never edit files in `.ease-context/runs/`. Never repeat a `reply`. If a result is unclear, run `next`.
