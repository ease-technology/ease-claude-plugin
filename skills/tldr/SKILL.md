---
name: tldr
description: Condenses Claude's last reply into a shorter version that keeps its decisions, questions, warnings and exact error text. User-invoked only, as /ease:tldr.
disable-model-invocation: true
---

# ease tldr

Post a shorter version of the last reply, which is Claude's most recent message in the conversation before this command. Nothing else is condensed, and any text typed after the command is ignored and sets no length or focus.

- **No earlier reply:** when there is no earlier reply, including one no longer available after compaction, reply in one line that there is nothing to condense and post nothing else.
- **Already short:** when the reply cannot be made shorter while keeping everything the keep rule requires, reply in one line that it is already short and do not repeat it.
- **Keep:** every decision and every question to the user stays in the short version, and every warning and exact error text stays word for word.
- **Add nothing:** the short version states no fact, opinion or suggestion that the original does not contain, so it adds no advice, follow-up offer or commentary.
- **Output:** otherwise post only the short version, with fewer words than the original. There is no fixed length limit, since how short it gets depends on what the reply says.
- **No tools:** make no tool calls. Read and write no files, and run no commands, engine steps or Jev calls.
- **This message only:** these rules apply to this one message. Write later replies as if the command had never run, with no change of style or length.
