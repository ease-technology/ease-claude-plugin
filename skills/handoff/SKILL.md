---
name: handoff
description: Saves where the session's work stands to .ease-context/handoffs/<name>.md, then prints a ready-to-copy prompt that starts a fresh session from that file. Run as /ease:handoff, or by /ease:autopilot when it ends.
argument-hint: "[optional note about why you're stopping]"
---

# ease handoff

Two outputs, in this order:

1. **A handoff file** so the session's work can be resumed cold, by you or by a future session, without re-deriving anything.
2. **A prompt in the chat** that the user copies into the next agent. It points at the file.

The file is the record. The prompt is the pointer. Never put a fact about the work in the prompt.

It writes exactly one file and changes nothing else: no commit, no push, no stash, no pull request, no tracker comment. Every git and gh command it runs only reads. Never read `.ease-context/config.json`: it holds the API key.

## 1. Locate

Find the workspace: the current folder, or the nearest folder above it, that contains `.ease-context/`. If there is none, say so in one line and stop, writing nothing.

Name the handoff, taking the first of these that applies:

1. This session was started from a handoff prompt: reuse that prompt's `Handoff file:` path as it is, even if the session also worked on a ticket. Read that file before overwriting it, because section 3 carries its Documents and Session story forward. An earlier file without those sections carries nothing.
2. The session has exactly one ticket, one it wrote, built or relied on, and its file exists at `.ease-context/projects/<project>/tickets/<slug>.md`: use that file name without `.md`.
3. Several tickets, none, or one that is not written yet: a short lowercase-hyphenated name for the work, like `add-a-login-page`.

The handoff path is `<workspace>/.ease-context/handoffs/<name>.md`, or the reused path in case 1. Run `mkdir -p` on its folder first. If a handoff already exists at that path, **overwrite it**.

## 2. Gather

**Open runs.** Run both of these from the workspace; they only read:

```bash
python3 "<skill base dir>/../../bin/ease-engine" runs
```

```bash
python3 "<skill base dir>/../../bin/ease-engine" ticket runs
```

A run counts as open when one of those commands lists it and this conversation has its id or its title matches one of the session's tickets. Runs from other sessions are left out. For each build run of this session, open or finished, read `<workspace>/.ease-context/runs/<run_id>/state.json` only for `project` and `branch`, and never copy its plan or tasks.

**Touched repos.** The repos in `<workspace>/.ease-context/projects/<project>/project.json` of each build run of this session (each `path` is relative to the workspace) where `git -C <path> branch --list <branch>` prints a line, plus every repo the session worked in. Name each repo by its absolute path.

**Per repo**, read only:

- Branch: `git -C <path> rev-parse --abbrev-ref HEAD`
- HEAD: `git -C <path> rev-parse --short HEAD`, which the State line records so the next agent can tell what changed
- Uncommitted files: the line count of `git -C <path> status --porcelain`, plus `git -C <path> diff --stat` and `git -C <path> diff --cached --stat` for the shape of the work in progress
- Unpushed commits: `git -C <path> rev-list --count HEAD --not --remotes`, or `no remote` (counted as none) when `git -C <path> remote` prints nothing
- Open PR: `gh pr list --head <branch> --json url --jq '.[0].url'`, run inside the repo folder, or `none` when it prints nothing, the repo has no remote, or gh fails
- Linked worktree: when `git -C <path> rev-parse --git-common-dir` points outside the repo; the folder that holds that common dir is the main checkout

**Per ticket**, read only, because a ticket under review is usually not on the checked-out branch. Its branch comes from the `state.json` of its build run or from the conversation; a ticket with neither has nothing to look up. In each touched repo and each repo in the `project.json` of the ticket's project, run `git -C <path> branch --list <branch>`. Inside each repo where that prints a line, run `gh pr list --head <branch> --json url --jq '.[0].url'`, with `none` in the same cases as Open PR above.

**From the conversation:**

- The goal: the outcome wanted, not a summary of tool calls.
- Every ticket the session wrote, built or relied on, with where it stands and who it waits on.
- The closing summary: the last summary of what is left, written by the user or by the agent at the user's request, just before the handoff.
- The next steps, each with its owner, what it waits on and any stated deadline.
- Every document and ticket written or relied on, from the conversation and any earlier handoff, never from a folder scan.
- The `context.md` of each project worked in, only when `<workspace>/.ease-context/projects/<project>/context.md` exists, since it is optional and a missing one would be reported as unreadable.
- Each decision, with its reason.
- The session's story.
- What to avoid.

Nothing is in flight when all three hold: no touched repo has uncommitted files or unpushed commits, no run is open under the rule above, and the session has no stated goal. Then write no file, print no prompt, say so in one line and stop.

## 3. Write the file

Written for a reader with zero context. Keep the sections in the order below, so the only section that gets shortened comes last.

After writing, run `wc -c` on the file. Bytes divided by 4 must be at most 10% of your context window: 100,000 tokens (400,000 bytes) on a 1M window, 20,000 tokens (80,000 bytes) on a 200k window or when you can't tell. When it is over, shorten Session story, oldest part first, rewrite the file and measure again. No other section is cut to fit. It is a ceiling, not a target.

```markdown
# Handoff: <short name of the work>

**Stopped:** <date and time> · **Why:** <$ARGUMENTS, or "context switch">

## Goal
<One paragraph. The outcome wanted, not the steps taken.>

## Where we stopped
<The closing summary, word for word.>

## Tickets
- <title> · <absolute path, or "not written yet"> · <where it stands> · branch `<branch>` · PR: <url> · Waits on: <the user, a named teammate, the agent, or nobody>

## Next
1. <the literal next action, with file:line where known> · Owner: <who> · Waits on: <what it waits on, or "nothing"> · Deadline: <as the conversation stated it, or "none stated">
2. ...

## State
- <absolute path>: branch `<branch>` at `<sha>`, <N> uncommitted file(s), <N> unpushed commit(s), PR: <url or "none">
- ease <build|ticket> run `<run_id>` is not done: resume it with `/ease:<build|ticket> resume <run_id>`

## Documents
- <absolute path>

## Decisions
- <each decision, with its reason>

## Done
- <specific, verifiable things that landed>

## Landmines
<Things that cost time and will cost it again: failing test that is unrelated,
a migration that must run first, an env var, a decision already rejected and why.>

## Verify
<command that proves the work is correct>

## Session story
<In order: what was asked, what was tried and dropped, where the direction changed and why, and what the user cared about.>
```

- **Where we stopped** holds the closing summary word for word, with no reformatting. The only permitted change is replacing a secret value with the name of its env var or key, and every other character stays, so `KEY=value` becomes `KEY=KEY`. Leave the section out when there is no closing summary.
- **Tickets** has one bullet per ticket. Write `not written yet` in place of the path of a ticket with no file. Leave out a branch or PR it does not have, and give one PR per repo when it has several. Waits on holds only one of its four values, with no reason beside it, because where the ticket stands carries the reason. When work is left and the conversation names nobody, it is `the user`. With no tickets, write `- none`.
- **Next** holds only the numbered list, in the order the work happens, with no text before or after it. A step's owner is who the conversation names, or `the user` when it names nobody. A step's Waits on is a dependency the conversation stated, or exactly `nothing`. A deadline never appears unless the conversation stated it. With a closing summary, Next has the same steps in the same order and adds none.
- **State** has one line per touched repo. Write `no remote` in place of the unpushed count when the repo has none. Add `linked worktree of <main checkout path>` to the line of a linked worktree, and `uncommitted changes are work in progress; do not discard them` to the line of a repo with uncommitted files. With no touched repo, write `- no repo touched yet`. State is the only home of these notes, so none is left out. Write one resume line per open run, with its exact command.
- **Documents** lists every document and ticket the session wrote or relied on, plus the `context.md` of each project it worked in when that file exists. It never lists `.ease-context/config.json`. When the session started from a handoff, the earlier list is carried forward. Document text is never copied into the file.
- **Done** never lists a run's plan or tasks, because the engine keeps them.
- **Session story** carries the earlier story first when the session started from a handoff, and this session's part follows it. A second `/ease:handoff` in the same session rewrites this session's part instead of repeating it. When an earlier part is missing because of compaction or the ceiling, the story's first line says so.

Never write a secret anywhere in the file: not in Goal, Where we stopped, Tickets, Next, State, Documents, Decisions, Done, Landmines, Verify or Session story, and that includes the word-for-word summary and the story. Only the name of the env var or key is ever written, never its value.

## 4. Build the prompt

The reader is an agent with none of this conversation, possibly a different tool. Copy this template word for word and fill in only the two paths. The only other change is the last line, as the rules below say.

```text
You are taking over work from an earlier session. Read everything below, report where things stand, and wait for me.

Working directory: <absolute workspace path>
Handoff file: <absolute handoff path>

Before your first reply, do these in order and change nothing in any file or repo:
1. Read the handoff file in full, past any tool's default length limit. If you cannot read it, say so in one line with its path, report no state, and stop.
2. Read every path under Documents in full the same way. If one cannot be read, go on and name its path in your reply.
3. Run `git status` and `git log --oneline -5` in each repo under State.

Your first reply gives:
- each ticket's state and who it waits on;
- the next steps in order, each with its owner, what it waits on and its deadline;
- each open ease run with its exact resume command;
- what git shows has changed since the handoff was written.

After that reply, stop and wait for me. Start no step and run no `/ease:build` or `/ease:ticket`, even when the first step is yours and waits on nothing, and also when an ease run is open.

Do not push, merge, or open a pull request until I say so.
```

Rules for the prompt:

- **At most 25 lines.** The detail belongs in the file.
- **Absolute paths only.** The next agent may start in another folder. Never write `~`.
- **Only the pointer.** No goal, ticket state, next step, repo line, resume command, `Start with:`, `Then:` or `It is done when:`. The file holds all of those.
- **No secrets.** `.ease-context/config.json` is never read, so its key can never reach the prompt.
- **The last line stays.** The next agent starts with no approval for anything outward-facing. The user can delete the line when pasting.
- **An open build run changes the last line's wording.** When the file lists an open build run, the last line is exactly `Apart from the ease run, do not push, merge, or open a pull request until I say so.`, because the run pushes and opens its own PRs. An open ticket run keeps the plain last line.

## 5. Report

Print exactly this, and nothing after the code block:

1. One line: `Handoff written: <absolute path>`
2. One line: `Prompt for the next agent:`
3. The prompt, alone inside a single fenced `text` block, so it copies cleanly.

Do not re-print the file. Do not add a summary, a question or an offer after the block: the user's next move is copy and paste.
