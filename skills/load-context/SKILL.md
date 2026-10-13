---
name: load-context
description: Use when the user runs /ease:load-context, or asks to load an ease project's context into the conversation.
---

# ease load-context

Load an ease project's context into this conversation, so the rest of it knows the project. Change nothing.

1. Find the workspace: the current folder, or the nearest folder above it, that contains `.ease-context/`. If there is none, say so and stop.
2. Pick the project from the user's words. The projects are the folders in `.ease-context/projects/`; match the user's words against their names, the repo names in each `project.json`, and what each `context.md` describes. If the user named no project, load every project.
3. Read each chosen project's `project.json` and `context.md`. Never read `.ease-context/config.json`: it holds the API key.
4. Reply in one line: the projects loaded and the absolute paths of their repos (each repo's `path` is relative to the workspace).
