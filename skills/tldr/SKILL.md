---
name: tldr
description: Condenses Claude's last reply, or what the session said about the topics named after the command, into a shorter version that keeps decisions, questions, warnings and exact error text. User-invoked only, as /ease:tldr.
argument-hint: "[topics to condense from the session]"
disable-model-invocation: true
---

# ease tldr

With nothing typed after the command, post a shorter version of the last reply, which is Claude's most recent message in the conversation before this command.

With text typed after the command, that text names the topics to condense. Post a shorter version of what the conversation says about them, from anywhere in the session, and leave out everything else. The text sets the focus and not the length.

- **No earlier reply:** with no text, when there is no earlier reply, including one no longer available after compaction, reply in one line that there is nothing to condense and post nothing else.
- **Topic not found:** when the conversation still available says nothing about a named topic, say so in one line for that topic.
- **Already short:** with no text, when the reply cannot be made shorter while keeping everything the keep rule requires, reply in one line that it is already short and do not repeat it. With text, when what was said about a topic cannot be made shorter, post it as it is.
- **Keep:** every decision and every question to the user in what is being condensed stays in the short version, and every warning and exact error text stays word for word.
- **Add nothing:** the short version states no fact, opinion or suggestion that the conversation does not contain, so it adds no advice, follow-up offer or commentary.
- **Output:** otherwise post only the short version, with fewer words than what it condenses. There is no fixed length limit, since how short it gets depends on what was said.
- **No tools:** make no tool calls. Read and write no files, and run no commands, engine steps or Jev calls.
- **This message only:** these rules apply to this one message. Write later replies as if the command had never run, with no change of style or length.
