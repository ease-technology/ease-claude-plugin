---
name: tldr
description: Gives the reader what they need from Claude's last reply, or answers a question about the session, in something read in under a minute. User-invoked only, as /ease:tldr.
argument-hint: "[a question, or topics to condense from the session]"
disable-model-invocation: true
---

# ease tldr

The reader wants what they need from the conversation, read in under a minute. Post that and nothing else. The shape follows what was typed after the command.

- **Nothing typed:** the gist of the last reply, which is Claude's most recent message before this command, in at most 3 bullets. Anything the user has to do or decide always makes it in. Drop the rest.
- **A question** (yes or no, "is X done?", "what's next?"): answer it in the first word or sentence, from anywhere in the session. Anything not finished, still unconfirmed, or still waiting on the user makes "everything is fine" false, so the answer is "No" or "Not yet", never "Yes", and those things are named after it. Name nothing that leaves the answer unchanged. When nothing is left, the answer alone is the reply, even if it is one word.
- **Topics:** the same at most 3 bullets for each topic, from anywhere in the session.
- **Exact text:** a warning or error that is included is quoted word for word. Include it only when it matters for what was asked.
- **Add nothing:** state no fact, opinion or suggestion the conversation does not contain, so no advice, follow-up offer or commentary.
- **Nothing to work from:** with nothing typed and no earlier reply, including one lost to compaction, reply in one line that there is nothing to condense. When the conversation says nothing about a question or a topic, say so in one line for it. With nothing typed, when the last reply is already this short, reply in one line that it is already short and do not repeat it.
- **No tools:** make no tool calls. Read and write no files, and run no commands, engine steps or Jev calls.
- **This message only:** these rules apply to this one message. Write later replies as if the command had never run, with no change of style or length.
