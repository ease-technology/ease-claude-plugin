---
name: ticket
description: Use when the user wants to turn an idea into a ticket or spec before building it, in their own words (for example "I want to improve the component sync in ease studio" or "let's write a ticket for..."), runs /ease:ticket, or asks to resume an ease ticket.
---

# ease ticket

You are the driver. A Python engine owns the state and every decision, and an interviewer agent does the thinking; you only ask the engine what is next, do that, and tell it the result.

Write the full engine command in every Bash call, because shell variables do not persist between calls. Always pass `timeout: 600000` to the Bash tool for engine calls. The engine command is `python3 "<skill base dir>/../../bin/ease-engine" ticket`, run from the workspace folder (the one that contains `.ease-context/`). Every call prints one JSON object. If it has an `"error"`, show it word for word and stop. The user can say "resume" once they have fixed it. If the output also shows a `jev: ...` line, mention it to the user in one short line.

## Start

Work out the project from the user's words; never ask them to name it. The projects are the folders in `.ease-context/projects/`: read each one's `project.json` (its repo names) and `context.md`. Pick the project whose name, repos or context match what the user said. If nothing matches, leave the project out and the engine uses `default_project`. If two projects fit equally well, ask the user which one.

Write the idea as a clear, self-contained description, including anything relevant from this conversation, because the interviewer never sees it. Send it through a quoted heredoc, so nothing in it is expanded:

```bash
python3 "<skill base dir>/../../bin/ease-engine" ticket start [project] <<'EASE_IDEA'
<the idea>
EASE_IDEA
```

Show the run id once. "resume" goes straight to the loop.

## The loop

Run `ticket next`, do what it says, then run `ticket reply`, and repeat. Each `next` returns one of three types.

**spawn.** Call the Agent tool with `subagent_type` set to the `agent` value and the prompt set to the `prompt` value, exactly as given. Wait for it to finish. Reply with its final message, unchanged:

```bash
python3 "<skill base dir>/../../bin/ease-engine" ticket reply <<'EASE_REPLY'
<the agent's final message>
EASE_REPLY
```

**ask_user.** Show `message` as it is, when it isn't empty. Then call AskUserQuestion once, with `questions` exactly as given. Reply with what the user answered, keyed by each question's text: the option label they picked, or their own words for "Other".

```bash
python3 "<skill base dir>/../../bin/ease-engine" ticket reply <<'EASE_REPLY'
{"answers": {"<question text>": "<their answer>"}}
EASE_REPLY
```

**done.** Show `summary` and stop.

## Rules

Never edit code, run git or write the ticket yourself; the engine writes it. Run one agent at a time. Never edit files in `.ease-context/ticket-runs/`. Never repeat a `reply`. If a result is unclear, run `ticket next`.
