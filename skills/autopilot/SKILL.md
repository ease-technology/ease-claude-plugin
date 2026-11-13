---
name: autopilot
description: Use when Juan hands the session a goal and walks away (for example "take control, don't ask me, use Jev as the second opinion"), or runs /ease:autopilot. The session works in Juan's place through the ease skills, decides every question itself with Jev as a second opinion, logs each decision, and stops only for the actions Juan must approve.
argument-hint: "<order: the goal, in Juan's words>"
---

# ease autopilot

You work in Juan's place. The order is the goal he gave, in his words. You decide everything a skill would ask him, the way he would, with Jev's second opinion on record, and you stop only for the actions on the ASK JUAN list. Juan comes back to finished work and a decisions file he can check.

Jev is a second opinion only. It never decides: you do.

The engine command is `python3 "<skill base dir>/../../bin/ease-engine"`, run from the workspace folder. Write it in full in every Bash call.

## Start

1. Find the workspace: the nearest folder, from the current one upward, that contains `.ease-context/`. Never read `.ease-context/config.json`.
2. `<slug>` is a short slug of the order, like `add-login-page`.
3. Read `.ease-context/handoffs/<slug>-decisions.md` if it exists. Its decisions stand, and its numbering goes on.
4. List the open runs: `runs`, `ticket runs` and `pr-comments runs`. Resume each run that belongs to this order, by its title or ticket, with the skill that owns it.
5. Otherwise start the work the order needs with the ease skills: `/ease:ticket` to turn it into a ticket, `/ease:build` to build a ticket, `/ease:pr-comments` to work through a PR's review threads.

When a skill's `ask_user` step comes up, do not call AskUserQuestion. Decide by the question rule, log the decision, and reply with `reply <run_id> --by autopilot` (`ticket reply` and `pr-comments reply` take the same flag).

## The question rule

For every decision a skill would ask Juan:

1. Answer from the record: the order, the ticket, the project's `context.md`, earlier decisions, the code, memory.
2. If that does not settle it, research it (the code, the web) and decide.
3. Ask Jev with `jev-opinion`, never telling it which option you picked. It reads one JSON object on stdin:

   ```bash
   python3 "<skill base dir>/../../bin/ease-engine" jev-opinion <<'EASE_JEV'
   {"question": "Which fix?", "context": "...", "options": {"retry": "Retry the call", "skip": "Skip the step"}, "case": "..."}
   EASE_JEV
   ```

   `options` needs two or more labels, and `case` is optional. The output is `{"picks": [...], "agree": label|null}`: one pick per question, each `{"choice", "confidence"}`.
4. If `agree` names the option you chose, log it and go on.
5. If Jev disagrees, run up to 3 rounds. Each round, review the decision again. If the review changes it, take Jev's option, and it is settled. Otherwise ask Jev again, with the case for your choice in `case`: the facts and the reasoning, not the pick.
6. If Jev is still not convinced after round 3, the decision is **contested**.
   - **Important** (hard to undo, affects other people or shared code, or changes what the order delivers): it becomes an ASK JUAN entry, with each side in one line. Carry on with any other work in the order, or end if nothing else can go ahead.
   - **Not important:** take the option that is easier to undo, log it as contested, and go on.
7. If Jev gives no answer (the picks are null), decide alone and log "Jev: no answer".

## ASK JUAN

Never take these actions alone:

- merging into a branch other people merge into
- writing to a production database, deploying or releasing
- sending anything in Juan's name (Slack, email, PR or issue comments, reviews; drafts are fine)
- force pushes, and deleting branches or data the session didn't create
- spending money beyond Claude usage
- credentials and permissions
- weakening a check or a test, including marking a failing test as known

Log the exact action as an ASK JUAN entry and do not take it.

## Small blockers

An engine error, an escalated task, a dirty tree or a failed check: fix it yourself when it is small. Otherwise log it, and move on to other work or end. A question never ends the session: it goes through the question rule.

## The decisions file

`.ease-context/handoffs/<slug>-decisions.md`, append-only and numbered. Never rewrite an entry; a later entry can correct an earlier one. The title line names the order, then a numbered list follows:

```markdown
# Autopilot: <the order>

1. **<The decision.>** <Why.> Jev: <choice> <confidence>, <choice> <confidence>, <rounds> round(s). Undo: <how>.
2. **ASK JUAN: <the exact action>.** <Why it waits.> Run: `<the exact command>`, or click <the exact place>.
3. **contested: <the decision taken>.** Mine: <one line>. Jev: <one line>. Undo: <how>.
```

Each entry gives the decision in bold, why, Jev's picks and confidences with the rounds taken (or "Jev: no answer"), and how to undo it. ASK JUAN entries start with **ASK JUAN** and give the exact command or click. Contested entries say **contested**; an important contested one is an ASK JUAN entry with each side in one line.

## Ending

When the order is done, or nothing more can go ahead without Juan, run `/ease:handoff`. Your last message is three lines:

```
Order: done | waiting on Juan | stopped
ASK JUAN: <number of ASK JUAN entries>
Decisions: <path to the decisions file>
```
