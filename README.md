# ease

A Claude Code plugin that turns a ticket into a planned, built and reviewed branch, and a PR when the repo has a GitHub remote. Claude drives, a small Python engine owns the state and every decision, and Jev (TypeSafe's judgment model) either shadows each decision or, in live mode, makes it.

## Install

In any Claude Code session:

```
/plugin install ease --marketplace ease-technology/ease-claude-plugin
```

If it asks for a scope, pick "Install for you" (user scope) so it works in every project. Then run `/reload-plugins`.

The engine needs Python 3.10 or newer as `python3`, standard library only.

To get a new version later:

1. `/plugin marketplace update ease-technology` in Claude Code
2. `claude plugin update ease@ease-technology` in a terminal
3. `/reload-plugins`

## Run it

Start Claude in your workspace, the folder that holds `.ease-context/`, and say what you want in your own words:

```
cd <workspace> && claude
/ease:build Clean the practice repo from any boilerplate
```

The ticket can be anything Claude can read: your own words, an issue number, an issue link, a ticket file, or what you just discussed. You never name the project; Claude works it out from your words and falls back to `default_project`. If a run stops, say "resume" or run `/ease:build resume`. Claude picks up the session's own run, or, in a new session, lists the runs that aren't done and takes the one you name.

Each session drives its own run by its run id, so several sessions can work at once: tickets and plans side by side, and builds in different repos. A plain `approve` builds in your normal checkout, so approving a plan for a repo that another run is building in fails with "busy with run …", and a repo with local changes fails with the uncommitted-changes error. Answer `approve worktree` instead to build in its own git worktree at `<workspace>/.ease-context/worktrees/<repo>-<run slug>`, branched from the branch your checkout is on, or from that run's base when your checkout is on a run's branch. Its PR goes into that base. A worktree has no dependencies or ignored files such as `.env`, so the worker sets them up there. The worktree is removed when the run is done or cancelled, and the branch is kept. A worktree with uncommitted changes, or one from an escalated run, is kept, and the summary names it.

## Tickets

To shape an idea before building it, say so in plain words, for example "I want to improve the component sync in ease studio", or run `/ease:ticket <idea>`. An interviewer agent reads the code, looks up facts and how other products solve the same problem on the web, and asks you only what research can't answer: up to 4 questions at a time, each with a recommended answer, until nothing important is left open (5 rounds at most). Then it writes a one-page ticket to `.ease-context/projects/<name>/tickets/<slug>.md`. The ticket opens with a job story and has numbered acceptance criteria, and you build it with `/ease:build <that path>`.

Jev answers every question too, without seeing the recommendation, and scores whether the ticket is ready to build by comparing it with the interview.

- In shadow mode every question comes to you, and an option says "Jev would pick this" where Jev differs from the recommendation. You approve the ticket before it is written.
- In live mode a question is settled without you when Jev picks the recommended option with confidence 0.5 or more. A readiness score of 4 or more (confidence 0.5 or more) writes the ticket without asking you; a lower one first gets one more round of questions.

The summary tells you how often Jev agreed with you, and how often you agreed when Jev and the recommendation agreed. That's the number to watch before you turn live mode on.

Ticket runs are kept in `.ease-context/ticket-runs/`. Add it to your workspace's `.gitignore`, next to `.ease-context/runs/`.

## PR comments

To work through the open review threads on a PR, run `/ease:pr-comments` with its number or link, or alone for the PR of the current branch, or say so in plain words, for example "handle the comments on PR 12". It never switches branches for you, so check out the PR's branch first.

Each command makes one pass, and it never polls or waits for a re-review. A read-only agent proposes fix or skip for each thread, and Jev picks without seeing the proposal. Once every thread has a verdict, each fix goes through the same steps as a build task, as its own task with up to 3 attempts: worker, checks, commit, reviewer and the decision. When every fix is accepted, the engine pushes the branch once without force, resolves the fixed threads and leaves the skipped ones open. If a fix escalates, the run ends with nothing pushed and nothing resolved. To take another pass, run the command again.

- In shadow mode every thread comes to you with Fix and Skip, at most 4 on a screen. The proposal is marked as recommended, and Jev's pick is marked where it differs.
- In live mode a thread settles without you when Jev picks the proposal with confidence 0.5 or more, and the summary lists it as settled. Every other thread comes to you.

The skill never posts a comment, reply or review to GitHub. The summary has a drafted reply for each thread, "Resolved by <commit>" or "Skipped because <reason>", and you paste the ones you agree with. A skip is remembered: the next run leaves that thread alone while it has no new comment or only your pasted draft, and judges it again on any other new comment.

A run stops before it changes anything if the PR is closed, merged or from a fork, if the repo has uncommitted changes or is on another branch, if another open run is on that branch, or if your HEAD differs from the PR's head. That includes commits a stopped run left unpushed, which are yours to push or reset. If a run stops midway, say "resume".

Every open thread enters a run, whoever wrote it, so comment text from anyone reaches a worker that has Bash. In live mode that can lead to a pushed fix nobody read first. The protection is that the agents treat comment text as data, not instructions, that the agent proposing fixes has no Edit, Write or Bash tools, and that hidden HTML comments are stripped before any agent or Jev sees the text.

To judge a thread, Jev gets the PR's title and body, the thread's comments and the code around its line, and it judges each fix like any other task. So comment text and your code go to TypeSafe's API.

PR comments runs are kept in `.ease-context/pr-runs/`. Add it to your workspace's `.gitignore`, next to `.ease-context/runs/` and `.ease-context/ticket-runs/`.

## Project context

`/ease:build` and `/ease:ticket` read a project's `context.md` on their own. To have it in an ordinary conversation, run `/ease:load-context <project>`, or `/ease:load-context` alone for every project in the workspace. When it loads several projects, it skips a project whose `context.md` is byte-identical to one already loaded and names the skipped copies.

## Handoff

When a session's context reaches 350,000 tokens, run `/ease:handoff`, optionally followed by why you are stopping. It writes where the session's work stands to `.ease-context/handoffs/<name>.md`. The pilot's handoff is always `~/ease/.ease-context/handoffs/pilot.md`. A session started from a handoff, or with a `Continue from <path>` line, reuses that handoff's path. Otherwise `<name>` is the ticket's slug when the session has one ticket, and a short name for the work when it doesn't. A new handoff to the same path overwrites the old one. The file lists tickets, next steps with owner, waits on and deadline, documents, decisions and the session's story, up to 10% of the writer's window. Then it prints a prompt to paste into a fresh session started in the workspace. The prompt makes the next agent read the file and every document it lists, check git, report where things stand and then wait, also when an ease run is open. The report names the resume command, and the run continues only when you say so. `/ease:handoff` changes nothing else: no commit, push, stash or PR.

Handoffs are kept in `.ease-context/handoffs/`. Add it to your workspace's `.gitignore`, next to `.ease-context/runs/` and `.ease-context/ticket-runs/`.

## TLDR

`/ease:tldr` gives you what you need from the conversation, in something you can read in under a minute. Alone, it gives the gist of Claude's last reply in at most 3 bullets, always including what you have to do or decide. Followed by a question, such as `/ease:tldr everything ok?`, it answers first ("Yes", "No", "Not yet"). Anything unfinished, unconfirmed or waiting on you makes the answer "Not yet" and is named after it, and nothing else is. Followed by topics, such as `/ease:tldr x, y and z`, it gives at most 3 bullets for each. The original stays in the conversation. A warning or error it includes is quoted word for word, and nothing is added.

It uses no tools, runs only when you type it, and leaves later replies unchanged. When there is no earlier reply, it answers in one line that there is nothing to condense. When the last reply is already that short, it answers in one line that it is already short. When the session says nothing about a question or topic you gave, it says so in one line.

## Say

`/ease:say <transcript>` turns something you dictated into one clean prompt. Alone, it uses your previous message. It asks you "Is this what you want to say?", showing the prompt and the words it had to guess as `heard → used`. Pick **Send** and Claude acts on the prompt as your message, pick **Drop** to do nothing, or type corrections and it asks again.

It touches nothing until you pick Send, runs only when you type it, and never names an ease command in the prompt. When there is nothing to clean, it answers in one line.

## Message

`/ease:message <what it is for, and who reads it>` drafts something people will read, such as a Slack message, a handoff note for your team or an email, the way you would say it to a teammate. It puts the ask or the news first, keeps it as short as the content allows, uses plain words with no headers or bold in a chat message and one link where a link does it, and names what the reader has to check or decide instead of listing everything done.

Sessions use it on their own when you ask them for a message, autopilot sessions included. It only drafts: it never sends anything, because sending in your name stays an ASK JUAN action.

## Autopilot

To hand a session a goal and walk away, run `/ease:autopilot <order>`, or say so in plain words, for example "take control, don't ask me, use Jev as the second opinion". The session works in your place through the ease skills and decides every question they would ask you.

It decides by the question rule: first from the record (the order, the ticket, `context.md`, earlier decisions, the code), then by research. Then it asks Jev for a second opinion with `ease-engine jev-opinion`, without telling Jev its pick. When Jev disagrees, it reviews the decision and asks again with its case, up to 3 rounds. If Jev is still not convinced, an important decision waits for you and an unimportant one takes the option that is easier to undo. It answers the engine's questions with `reply <run_id> --by autopilot`.

It never takes these actions alone: merging into a shared branch, writing to production, deploying or releasing, sending anything in your name, force pushes, deleting what it didn't create, spending money, touching credentials or permissions, and weakening a check or a test. Each one is logged as an ASK JUAN entry with the exact command or click.

Every decision goes to `.ease-context/handoffs/<slug>-decisions.md`, numbered and append-only, with why, Jev's picks and how to undo it. The title names the order and the session, as `# Autopilot: <order> (session <id>)`, and a session that continues the file adds its own id there. When you answer an ASK JUAN entry in the session's own window, it appends an `answered: ASK JUAN <n>` entry before it acts on your answer. A later autopilot session on the same order reads the file and goes on from it. When the order is done, or nothing more can go ahead without you, it runs `/ease:handoff` and ends with three lines: the order's status, the number of ASK JUAN entries, and the path to the decisions file.

It measures its own context at the end of Start and after each step: each engine `next` or `reply` and each skill that ends. The size is the input, cache creation and cache read tokens of the last assistant message in its transcript, found by `$CLAUDE_CODE_SESSION_ID`. Under 350,000 tokens it goes on. At 350,000 or more, for every model, it finishes the current step, runs `/ease:handoff` and ends with four lines: `Order: handed off`, the number of ASK JUAN entries, the decisions file and `Handoff: <absolute path>`. To go on, start a new autopilot session with the same order and a `Continue from <path>` line naming that handoff. It reads the file and every document it lists, keeps the same decisions file, and resumes the open runs without waiting for you. Its own handoff reuses the same path, so the chain keeps one file.

Whenever autopilot starts or stops a test suite, a container, a dev server or a long build, it appends a numbered heavy entry to the decisions file that names the command and says started or stopped. It does not clean up or throttle that work on its own.

Jev never decides, and autopilot leaves `jev_mode` as it is.

## Pilot

The pilot is one session that runs your orders across the ease, Souk and Proper workspaces while you are away. It starts a `/ease:autopilot <goal>` worker session for each order, watches the workers, restarts them when they stop, and brings you only the ASK JUAN actions. You talk to it in its window, or from the Claude iPhone app after you type `/rc` there: give it a goal, ask "how's it going?", answer an ASK JUAN entry with yes or no, say "show sessions" to get one read-only line per session in each workspace, with its context size in K tokens, say "take over <session>, <goal>" to hand it a session, "tell <session> <message>" to send a handed-over session a message, or "give back <session>" to take it back. A handed-over session stays the same session under its own name, so you can still `claude attach` it; it keeps its own settings, so the guard does not bind it. For an interactive one, the pilot asks you to press ← or `/bg` first and never stops it.

The pilot acts only on its own `pilot-*` sessions and the ones you handed over, and only reads the rest.

When a worker or a handed-over session ends with `Order: handed off`, the pilot continues it in a fresh session during the same wake, with the same order and a `Continue from <path>` line naming its handoff. A worker's successor is `pilot-<slug>-<n>`, with the guard. A handed-over session's successor is `<original name>-<n>`, or `<slug>-<n>` when it had no name, and runs without the guard like the session it replaces. It takes that session's place in `orders.md`, so the pilot watches it from then on and never messages the old one again. A handoff is not a restart and does not count toward the 3-restart limit. The pilot logs the old session, the new one and the old one's token count in `decisions.md`. When a fresh session does not appear in `claude agents --json` within 60 seconds of its start, the pilot changes nothing in `orders.md`, logs the failure and adds it to the outbox as a question for you.

The pilot hands itself off too. After each wake and each reply to you, it measures its own context. At 350,000 tokens or more it runs `/ease:handoff`, which writes `~/ease/.ease-context/handoffs/pilot.md`, and adds one item to the outbox: "Pilot is full. Type /ease:pilot stop, then /clear, then /ease:pilot." It goes on as the pilot until you do. The next `/ease:pilot` reads `handoffs/pilot.md` and every document it lists.

The pilot wakes a background session with a message using `env -i HOME=… PATH=… USER=… LOGNAME=… claude --bg --resume <full session id> "<message>"` and no other flags. `USER` and `LOGNAME` must stay, or the session starts "Not logged in". With the calling session's Claude variables, any flag or a short id, the CLI starts a copy that never gets the message. The pilot starts sessions under `env -i HOME PATH USER LOGNAME` too, because its own Claude variables would make `claude --bg` drop the prompt. The pilot skill's own guard hook allows the wake command, `claude stop` and the exact `env -i` worker start, so auto mode does not block them.

The pilot wakes only on news. Its watcher, `pilot/watcher.py`, is a background script that costs no tokens and checks at once, then every 60 seconds. It writes each piece of news as one line in `inbox.txt` in the pilot folder and exits, which wakes the pilot. News is a managed session that becomes done, stopped, blocked, failed or waiting, a new ASK JUAN, `heavy: started` or `answered: ASK JUAN` line in a workspace decisions file whose title names a session the pilot drives, or a due timer. `heavy: stopped`, lines in files of sessions it does not drive, and moves among busy, working and idle wake nothing. The watcher keeps its last snapshot in `watcher-state.json` and the news waits in `inbox.txt`, so a restarted watcher still finds what happened while none ran. Each wake takes the inbox, re-reads `instructions.md` and starts the watcher again only when none is running. When the pilot runs `claude stop` itself, to message a session or slow it down, it pauses the watcher around the stop with a `watcher.pause` file that names the session, so its own stop does not wake it. An hourly `/loop` backstop restarts the watcher only when none is running.

Timers start runs without you typing. Say "every weekday at 08:00, souk: read Slack and tell me what needs me" or "in 2 hours, check the launch" to set one, "show timers" to get one line per timer with its next time and last run, and "cancel the <slug> timer" to cancel it. They live in `timers.md` in the pilot folder, and the watcher fires them when they come due, so waiting on a timer costs no tokens. When the pilot was not running at a timer's time, the timer fires once when the pilot is back, however many runs it missed, and that run reads everything since the last real run. A recurring timer whose order is still open from its last run is skipped, and the next run still covers the skipped window. A timer run's results reach your phone only as ASK JUAN items, which stay open in every push until you answer them; a run that finds nothing needing you sends no push. The pilot also sets its own one-time follow-ups, such as unpausing an order on the date it was paused until or restarting a worker when a spend limit resets.

On every wake the pilot weighs the process trees of the sessions it manages and the Mac as a whole, by judgment and with no thresholds. When a managed session is too heavy, the pilot asks it to slow down: it stops the session, waits 10 seconds and resumes it with a concrete lighter way to do the work, so the session is never left paused. It tells you in one line, and also in one line when the load comes from something it cannot act on. Otherwise it sends nothing about resources. "How's the computer?" gets a one-line answer. New workers still start by `max_workers` only.

When another live session may use the same repo, the pilot adds "build in a worktree" to a worker's goal, and it holds a PR comments order until that order's repo is free.

When you ask the pilot for a message people will read, such as a Slack message, a handoff note for your team or an email, it asks the session that owns the work to draft it with `/ease:message` and brings you that draft.

Each instruction you give about an order, like "make Sanity work on dev and prod" or "no clicks from me", becomes a checklist line in your words under that order in `orders.md`, as `  - [ ] <your words>`. It goes into the worker's goal, so every worker, restart and successor gets it, and a running worker gets it as a message. Before the pilot tells you an order is done, it asks the owning session to confirm each open line with evidence, pushes it to finish any line that is not met, and marks a line `[x]` only when the evidence comes back. The pilot never checks anything itself.

A session's plan or ask that breaks your rules is sent back to it with the rule, logged in `decisions.md`, and kept out of the outbox. That covers asking you for a click, a check or a login when the session could do it another way, a plan to log in as you, a wall of text for people, and an estimate it cannot back. An ask reaches you only when there is truly no other way. Late in your day, or when you say you are closing the day, the pilot asks you for nothing new: it logs every item that blocks no one and adds it to the outbox at your first message of the next day.

The project index, `~/ease/.ease-context/pilot/projects.md`, lists the projects a worker can start in: one entry per project in every workspace, with its workspace, its repos and a two-line summary of its `context.md`. Folders with byte-identical `context.md` files are one entry that lists the copies. The pilot writes it at start when it is missing, and "refresh the project index" rewrites it.

Every pilot message fits a phone: at most 3 short lines, with no tables, headings or code blocks. Pushes go through the outbox, `outbox.json` in the pilot folder, which holds the open items for you: ASK JUAN questions and results you asked for, each in at most 14 words. Every push is exactly the composed push from `pilot/outbox.py compose`: the line `<N> need you`, then every open item numbered from 1, questions first. The pilot sends it once, at the end of a wake, and only when a new item joined the outbox, so each new item brings one push. Worker starts and restarts, finished work you did not ask about and quiet wakes send no push. Answer by number, such as `1 yes, 2 no`, or with a bare yes or no when the push has one item; the pilot acts on each answer and closes the item without a push. An item also leaves when you answer it in the session's own window, which adds an `answered: ASK JUAN <n>` entry there. Two hooks hold the pilot to this: one refuses any PushNotification that is not the composed push, and the other blocks the pilot's turn from ending while a new item is unsent. Chat replies answer what you ask, whenever you ask; you say "more" to get the details, and "how's it going?" starts with the open items. When a wake finds nothing new, the pilot sends nothing, not even after restarting its watcher.

To start it, run `/ease:pilot` in a `~/ease` session in auto mode; that window becomes the pilot. In any other mode it answers in one line that the pilot needs auto mode, and starts nothing. When this window or another one is already the pilot, it answers in one line that the pilot is already running, and starts nothing. The first time, it creates `~/ease/.ease-context/pilot/` with `orders.md`, `decisions.md`, `approvals.json`, `workspaces.json`, `instructions.md`, `timers.md` and the workers' settings file. `instructions.md` holds the pilot's push rules, and every wake re-reads it, however long the session has grown. Then the pilot starts its watcher, its hourly backstop loop and `caffeinate`, which keeps the Mac awake. Remote Control stays off until you type `/rc`; then you can reach the pilot from the Claude app. Keep the Mac plugged in with the lid open: closing the lid still puts it to sleep. `/ease:pilot stop`, typed in the pilot window, stops it in place: the watcher, the loop and `caffeinate` end, the window stays open, and the workers keep running until they end. Closing the window stops the pilot.

Workers start with `claude --bg -n pilot-<slug> --permission-mode auto --disallowedTools AskUserQuestion --settings ~/ease/.ease-context/pilot/worker-settings.json "<prompt>"`, under `env -i`. The prompt's lines are `/ease:load-context <project>` with the project from the index, left out when none fits, then `/ease:autopilot <goal>`, then the order's checklist lines, then up to two lines of starting context from the project's entry.

The pilot and every worker run with a guard, a PreToolUse hook (`pilot/guard.py`) that blocks these actions and tells the session to log them as ASK JUAN entries:

- merging a pull request with `gh pr merge`
- PR and issue comments and reviews (`gh pr comment`, `gh pr review`, `gh issue comment`)
- `gh api` writes (POST, PATCH, PUT, DELETE) to comments, reviews or merges
- `git merge` on, and `git push` to or from, a shared branch: one named in its workspace's `shared_branches` list in `workspaces.json` (Souk and Proper: `dev`, `develop`, `main`, `master`), in any repo or worktree under that workspace's folder
- force pushes
- branch deletes: remote deletes with `git push`, and `git branch -D` of a branch the session did not create
- production database clients (`psql`, `pg_dump`, `mysql`, `mongosh`, `cloud-sql-proxy`) with a `prod_markers` value in their arguments
- any tool matching a pattern in `blocked_tools`, such as sending on Slack or by email

When you say yes to an entry, the pilot adds the exact command to `approvals.json` and tells the worker that asked to run it; the worker's guard lets it through once. The pilot never runs it itself: its own guard does not read `approvals.json`.

Workers get the guard from `~/ease/.ease-context/pilot/worker-settings.json`, and the pilot from the hook in the pilot skill's frontmatter, which stays registered in that window until it closes. The guard is never in a repo's settings.

## Change the plugin

Try local changes without installing: `claude --plugin-dir <path to ease-claude-plugin>`. To release them, bump `version` in `.claude-plugin/plugin.json` and push. Installed copies only update when the version changes.

## Config

It lives in your workspace, not in the plugin.

```
<workspace>/.ease-context/
  config.json                    {"default_project": "practice", "typesafe_api_key": "...", "jev_mode": "shadow"}
  projects/<name>/project.json   {"repos": {"practice": {"path": "practice", "checks": "npm run lint && npm run build"}}}
  projects/<name>/context.md     optional notes for the planner
  runs/<run_id>/state.json       run state, including the Jev log
  pr-runs/<run_id>/state.json    a PR comments run's state, including its threads and verdicts
  handoffs/<name>.md             where a session's work stands, written by /ease:handoff
```

`checks` is any shell command the repo already uses, in any language. `default_project` is used when Claude can't tell the project from your words. `jev_mode` is `"shadow"` (the default) or `"live"`; anything else is an error when a run starts. `typesafe_api_key` turns Jev on; see [Jev](#jev).

## The flow

The planner agent writes the plan and Jev scores it. You see the plan and the score, then approve, change or cancel. For each task, the worker builds it, the engine runs the checks and commits, the reviewer reviews it, and the engine decides. At the end you get PRs, or just the branch when there is no remote.

The code rule is simple. If the checks pass and the review passes, the task is accepted. Otherwise, on the third attempt it escalates to you, and before that the worker tries again with the problems listed.

A ticket can touch several repos. The plan splits it into tasks, each in one repo, and at the end you get one PR per repo that changed. Each PR goes into the branch that repo had checked out when you approved the plan, so check out `develop` (or whatever you merge into) first.

The work happens on a new branch in your normal checkouts. Claude names it the way the project's `context.md` says, for example a Linear issue's `gitBranchName`, and when it says nothing the branch is a slug of the ticket title, like `add-a-login-page`. Before you approve, commit or stash any local changes in those repos. A run you approve with `approve worktree` works in its own worktree instead, so local changes in your checkout don't block it.

## Jev

To turn Jev on, put your TypeSafe API key in `<workspace>/.ease-context/config.json`:

```json
{"default_project": "practice", "typesafe_api_key": "<your key>", "jev_mode": "shadow"}
```

The key is a secret, so add `.ease-context/config.json` to your workspace's `.gitignore`. Without a key, Jev is skipped and the code rule decides alone. If a call to Jev fails, the run goes on without it, and Claude shows you the `jev: ...` error line.

Jev scores how fully the plan covers the ticket, and after every review it says what it would do. The answer is logged in `state.json` under `log` next to the code rule's decision, so you can compare them. Each plan you answer goes under `plan_log`, with Jev's score, its confidence and your answer (approve, change or cancel). Ticket runs do the same for drafts under `draft_log`, and each question keeps Jev's pick next to your answer. This shadow data is what live mode's thresholds can later be set from. A run keeps the `jev_mode` it started with.

When a session answers in your place, it replies with `reply <run_id> --by autopilot` (in build, `ticket` and `pr-comments`). The answer is recorded as `decided_by: "autopilot"` on questions, threads and plan and draft verdicts, and the summaries name it. Jev's agreement with you counts only your own answers.

`ease-engine jev-opinion` asks Jev for a second opinion on any choice. It reads a JSON object on stdin:

```json
{"question": "Which fix?", "context": "...", "options": {"retry": "Retry the call", "skip": "Skip the step"}, "case": "..."}
```

`case` is optional, and `options` needs two or more labels. Jev favors the first option slightly, so the same question is asked twice in one call, with the options in opposite orders. The output is `{"picks": [...], "agree": label|null}`: one pick per question, each `{"choice", "confidence"}`, and `agree` is the label when both picks are the same. With no key, or when Jev fails, the picks are null and a `jev: ...` line goes to stderr. Malformed input gives `{"error": ...}`. It is a second opinion only: it never decides anything.

To judge a task, Jev gets the ticket, the task, its diff (the first 20,000 characters), the checks and the review. So your code goes to TypeSafe's API.

In shadow mode Jev only watches: the code rule decides. In live mode Jev decides, but three guardrails always win:

- If Jev gives no answer, or its confidence is below 0.5, the code rule's decision stands.
- Jev can never accept a task whose checks or review failed.
- Jev can ask for a fix only if there is something to fix (a failed check or a review finding), and only on the first two attempts. Otherwise the code rule's decision stands.

## The engine

- `engine/models.py` holds the data model: what a run, a task, a decision and a ticket run look like.
- `engine/workspace.py` reads the config and the run state.
- `engine/shell.py` runs git, gh and the repo's checks.
- `engine/jev.py` asks Jev its questions.
- `engine/flow.py` holds the steps, the code rule and the live rule.
- `engine/ticket.py` holds the ticket flow: the interview, the question rule and the ready rule.
- `engine/pr_comments.py` holds the PR comments flow: the refusals, the remembered skips, the fix tasks, the push and the summary.
- `engine/cli.py` is the `start`, `runs`, `next <run_id>` and `reply <run_id> [--by autopilot]` commands, for build and, after `ticket`, for tickets, and after `pr-comments`, for PR comments runs. `pr-comments start` also takes `--repo <name>`. `jev-opinion` asks Jev for a second opinion and never decides.

Run the tests from a fresh clone:

```
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```
