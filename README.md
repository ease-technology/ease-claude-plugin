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

Each session drives its own run by its run id, so several sessions can work at once: tickets and plans side by side, and builds in different repos. Two builds can't share a repo, because a build works in your normal checkout. Approving a plan for a repo that another run is building in fails with "busy with run …", and you approve again once that run is done.

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

`/ease:build` and `/ease:ticket` read a project's `context.md` on their own. To have it in an ordinary conversation, run `/ease:load-context <project>`, or `/ease:load-context` alone for every project in the workspace.

## Handoff

When a session's context passes about 40% of the window, run `/ease:handoff`, optionally followed by why you are stopping. It writes where the session's work stands to `.ease-context/handoffs/<name>.md`. A session started from a handoff reuses that handoff's path. Otherwise `<name>` is the ticket's slug when the session has one ticket, and a short name for the work when it doesn't. A new handoff to the same path overwrites the old one. The file lists tickets, next steps with owner, waits on and deadline, documents, decisions and the session's story, up to 10% of the writer's window. Then it prints a prompt to paste into a fresh session started in the workspace. The prompt makes the next agent read the file and every document it lists, check git, report where things stand and then wait, also when an ease run is open. The report names the resume command, and the run continues only when you say so. `/ease:handoff` changes nothing else: no commit, push, stash or PR.

Handoffs are kept in `.ease-context/handoffs/`. Add it to your workspace's `.gitignore`, next to `.ease-context/runs/` and `.ease-context/ticket-runs/`.

## TLDR

`/ease:tldr` gives you what you need from the conversation, in something you can read in under a minute. Alone, it gives the gist of Claude's last reply in at most 3 bullets, always including what you have to do or decide. Followed by a question, such as `/ease:tldr everything ok?`, it answers first ("Yes", "No", "Not yet"). Anything unfinished, unconfirmed or waiting on you makes the answer "Not yet" and is named after it, and nothing else is. Followed by topics, such as `/ease:tldr x, y and z`, it gives at most 3 bullets for each. The original stays in the conversation. A warning or error it includes is quoted word for word, and nothing is added.

It uses no tools, runs only when you type it, and leaves later replies unchanged. When there is no earlier reply, it answers in one line that there is nothing to condense. When the last reply is already that short, it answers in one line that it is already short. When the session says nothing about a question or topic you gave, it says so in one line.

## Autopilot

To hand a session a goal and walk away, run `/ease:autopilot <order>`, or say so in plain words, for example "take control, don't ask me, use Jev as the second opinion". The session works in your place through the ease skills and decides every question they would ask you.

It decides by the question rule: first from the record (the order, the ticket, `context.md`, earlier decisions, the code), then by research. Then it asks Jev for a second opinion with `ease-engine jev-opinion`, without telling Jev its pick. When Jev disagrees, it reviews the decision and asks again with its case, up to 3 rounds. If Jev is still not convinced, an important decision waits for you and an unimportant one takes the option that is easier to undo. It answers the engine's questions with `reply <run_id> --by autopilot`.

It never takes these actions alone: merging into a shared branch, writing to production, deploying or releasing, sending anything in your name, force pushes, deleting what it didn't create, spending money, touching credentials or permissions, and weakening a check or a test. Each one is logged as an ASK JUAN entry with the exact command or click.

Every decision goes to `.ease-context/handoffs/<slug>-decisions.md`, numbered and append-only, with why, Jev's picks and how to undo it. A later autopilot session on the same order reads the file and goes on from it. When the order is done, or nothing more can go ahead without you, it runs `/ease:handoff` and ends with three lines: the order's status, the number of ASK JUAN entries, and the path to the decisions file.

Jev never decides, and autopilot leaves `jev_mode` as it is.

## Pilot

The pilot is one session that runs your orders across the ease, Souk and Proper workspaces while you are away. It starts a `/ease:autopilot <goal>` worker session for each order, watches the workers, restarts them when they stop, and brings you only the ASK JUAN actions. You talk to it from the Claude iPhone app: give it a goal, ask "how's it going?", or answer an ASK JUAN entry with yes or no.

To set it up, run `/ease:pilot` once. It creates `~/ease/.ease-context/pilot/` with `orders.md`, `decisions.md`, `approvals.json`, `workspaces.json` and the pilot's and workers' settings files, then prints the launch command. After that, start the pilot with:

```bash
caffeinate -i env CLAUDE_CONFIG_DIR=~/.claude-ease claude --remote-control pilot --settings ~/ease/.ease-context/pilot/pilot-settings.json
```

The pilot and every worker run with a guard, a PreToolUse hook (`pilot/guard.py`) that blocks these actions and tells the session to log them as ASK JUAN entries:

- merging a pull request with `gh pr merge`
- PR and issue comments and reviews (`gh pr comment`, `gh pr review`, `gh issue comment`)
- `gh api` writes (POST, PATCH, PUT, DELETE) to comments, reviews or merges
- `git merge` on, and `git push` to or from, a shared branch: one named in its workspace's `shared_branches` list in `workspaces.json` (Souk and Proper: `dev`, `develop`, `main`, `master`), in any repo or worktree under that workspace's folder
- force pushes
- branch deletes: remote deletes with `git push`, and `git branch -D` of a branch the session did not create
- production database clients (`psql`, `pg_dump`, `mysql`, `mongosh`, `cloud-sql-proxy`) with a `prod_markers` value in their arguments
- any tool matching a pattern in `blocked_tools`, such as sending on Slack or by email

When you say yes to an entry, the pilot adds the exact command to `approvals.json`, and the guard lets it through once.

The guard lives in our harness settings, the `--settings` files under `~/ease/.ease-context/pilot/`, never in a repo's settings.

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

The work happens on a new branch in your normal checkouts. Claude names it the way the project's `context.md` says, for example a Linear issue's `gitBranchName`, and when it says nothing the branch is a slug of the ticket title, like `add-a-login-page`. Before you approve, commit or stash any local changes in those repos.

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
