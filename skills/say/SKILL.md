---
name: say
description: Turns a dictated transcript, or the user's previous message, into one clean prompt plus the words it had to guess, then waits. User-invoked only, as /ease:say.
argument-hint: "[a dictated transcript]"
disable-model-invocation: true
---

# ease say

The reader dictated this, so it carries filler, repeats, self-corrections and misheard words. Reply with one clean prompt that says what they meant, so they can check it before anything is done.

- **What to clean:** the text typed after the command. With nothing typed, the user's most recent message before this command.
- **The prompt:** the reply opens with one clean prompt, in the transcript's language. It keeps everything asked for and drops filler, repetitions and the retracted half of each self-correction, so "a tool or new command, sorry, a command" becomes "command", with no mention of "tool".
- **Mishearings:** a likely mistranscription that the conversation or general knowledge resolves is replaced in the prompt, for example "Cloud Tools" becomes "Claude tools" and "Mac Whisperer" becomes "Mac Whisper". Anything uncertain is guessed and listed, not looked up.
- **Guesses:** after the prompt, list each word or meaning changed by guess as `heard → used`, one per line. When nothing was guessed, write no list and no line saying so.
- **Plain words:** when the speech asks for something an ease command does, such as "make this a ticket", state the request in plain words. Do not name or run any `/ease:` command.
- **Add nothing:** no advice, plan, follow-up offer or commentary beyond the prompt and the guesses.
- **Nothing to clean:** with nothing typed and no earlier user message, including one lost to compaction, reply in one line that there is nothing to clean.
- **No tools:** make no tool calls. Read and write no files, and run no commands, engine steps or Jev calls. Do no work on the request in this turn.
- **The next message:** when the user's next message approves the prompt, such as "go" or "yes", act on the clean prompt with any corrections from that message applied. When it is anything else, treat it as a normal message.
- **This message only:** these rules apply to this one message. Later replies return to the normal style.
