---
name: handoff
description: Saves where the session's work stands to .ease-context/handoffs/<name>.md, then prints a ready-to-copy prompt that starts a fresh session from that file. User-invoked only, as /ease:handoff.
argument-hint: "[optional note about why you're stopping]"
disable-model-invocation: true
---

# ease handoff

Two outputs, in this order:

1. **A handoff file** so the session's work can be resumed cold, by you or by a future session, without re-deriving anything.
2. **A prompt in the chat** that the user copies into the next agent. It points at the file.

The file is the record. The prompt is the pointer. Never put something in the prompt that is not in the file.

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

Keep it under 60 lines. Written for a reader with zero context.

```markdown
# Handoff: <feature name>

**Stopped:** <date and time> · **Why:** <$ARGUMENTS, or "context switch">

**Ticket:** <absolute path>

## Goal
<One paragraph. The outcome wanted, not the steps taken.>

## State
- <absolute path>: branch `<branch>`, <N> uncommitted file(s), <N> unpushed commit(s), PR: <url or "none">
- ease <build|ticket> run `<run_id>` is not done: resume it with `/ease:<build|ticket> resume <run_id>`

## Done
- <specific, verifiable things that landed>
- <each decision, with its reason>

## Next
1. <the literal next action, with file:line where known>
2. ...

## Landmines
<Things that cost time and will cost it again: failing test that is unrelated,
a migration that must run first, an env var, a decision already rejected and why.>

## Verify
<command that proves the work is correct>
```

- Write the `**Ticket:**` line only when the feature has a ticket.
- State has one line per touched repo. Write `no remote` in place of the unpushed count when the repo has none. Add `linked worktree of <main checkout path>` to the line of a linked worktree, and `uncommitted changes are work in progress; do not discard them` to the line of a repo with uncommitted files. With no touched repo, write `- no repo touched yet`.
- Write the run line only when an ease run is open. With an open run, Done never lists the run's plan or tasks, because the engine keeps them, and Next item 1 is to resume the run by its id, not to start a new run.

Never write a secret into the file: name the env var or the key, not its value.

## 4. Build the prompt

The reader is an agent with none of this conversation, possibly a different tool. Write it in full sentences, addressed to that agent. No caveman fragments, no "as discussed", no reference to this session.

Fill this template from the file you just wrote. Every line must be true of the file; drop a line whose value is "none" unless the template says otherwise.

```text
You are picking up work in progress on <feature name>.

Working directory: <absolute workspace path>
Handoff file: <absolute handoff path>

Read the handoff file first. It has the goal, what is done, what is next, and what to avoid. Then run `git status` and `git log --oneline -5` in each repo below. If git has moved on since the handoff was written (<date and time>), trust git and tell me what differs before you continue.

Goal: <the Goal section in one or two sentences>

Repos:
<each repo's State line, copied from the file>

Start with: <Next item 1, word for word, with its file:line>
Then: <Next item 2, if there is one>

Watch out for: <each landmine in one sentence; write "nothing known" if the section is empty>

It is done when: <the Verify command> passes.

Do not redo anything listed under Done.
Do not push, merge, or open a pull request until I say so.
```

Rules for the prompt:

- **An open run is resumed, not restarted.** `Start with:` is `/ease:build resume <run_id>` or `/ease:ticket resume <run_id>`, followed by `Do not start a new run.` When the prompt names a build run, the last line is exactly `Apart from the ease run, do not push, merge, or open a pull request until I say so.`, because the run pushes and opens its own PRs.
- **Absolute paths only, in every repo line.** The next agent may start in another folder. Never write `~`.
- **A worktree is named as one.** A linked worktree's repo line keeps `linked worktree of <main checkout path>`, so the next agent works there, not in the main checkout.
- **Uncommitted work is called out.** A repo line with uncommitted files keeps `uncommitted changes are work in progress; do not discard them`.
- **At most 25 lines.** If it needs more, the detail belongs in the file.
- **No secrets, and nothing the file does not say.** `.ease-context/config.json` is never read, so its key can never reach the prompt.
- **The last line stays.** The next agent starts with no approval for anything outward-facing. The user can delete the line when pasting.

## 5. Report

Print exactly this, and nothing after the code block:

1. One line: `Handoff written: <absolute path>`
2. One line: `Prompt for the next agent:`
3. The prompt, alone inside a single fenced `text` block, so it copies cleanly.

Do not re-print the file. Do not add a summary, a question or an offer after the block: the user's next move is copy and paste.
