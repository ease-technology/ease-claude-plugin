---
name: say
description: Turns a dictated transcript, or the user's previous message, into one clean prompt, asks the user whether that is what they want to say, and on approval acts on it. User-invoked only, as /ease:say.
argument-hint: "[a dictated transcript]"
disable-model-invocation: true
---

# ease say

The reader dictated this, so it carries filler, repeats, self-corrections and misheard words. Rewrite it as one clean prompt, ask them whether it is what they want to say, and when they approve, act on it as their message.

- **What to clean:** the text typed after the command. With nothing typed, the user's most recent message before this command.
- **The prompt:** one clean prompt, in the transcript's language. It keeps everything asked for and drops filler, repetitions and the retracted half of each self-correction, so "a tool or new command, sorry, a command" becomes "command", with no mention of "tool".
- **Mishearings:** a likely mistranscription that the conversation or general knowledge resolves is replaced in the prompt, for example "Cloud Tools" becomes "Claude tools" and "Mac Whisperer" becomes "Mac Whisper". Anything uncertain is guessed and listed, not looked up.
- **Guesses:** under the prompt, list each word or meaning changed by guess as `heard → used`, one per line. When nothing was guessed, write no list and no line saying so.
- **Plain words:** when the speech asks for something an ease command does, such as "make this a ticket", state the request in plain words. Do not name any `/ease:` command in the prompt.
- **Ask:** write no text, and call AskUserQuestion once. The question is the clean prompt, then the guesses, then "Is this what you want to say?". The header is "Say". The options are **Send**, to act on the prompt now, and **Drop**, to do nothing. The user types corrections into the free-text "Other" answer.
- **Corrections:** apply them to the prompt and ask again the same way, until the user picks Send or Drop.
- **Send:** act on the clean prompt in this same turn, exactly as if the user had sent it as their message. From here on, reply in the normal style.
- **Drop:** reply in one line that nothing was sent, and stop.
- **Before the answer:** make no tool call except AskUserQuestion. Read and write no files, and run no commands, engine steps or Jev calls, until the user picks Send.
- **Nothing to clean:** with nothing typed and no earlier user message, including one lost to compaction, reply in one line that there is nothing to clean, and ask nothing.
