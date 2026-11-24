#!/usr/bin/env python3
"""The pilot's outbox: the open items for Juan and the numbering of the last push.

Run as `outbox.py --dir <pilot folder> <command>`. The state lives in <dir>/outbox.json as
{"items": [{ref, kind, text, state}], "last_push": [ref, ...], "sent": [{at, text}, ...]};
a missing file counts as empty. A decision is new until a push sends it, then sent, then closed;
a result is closed by the push that sends it. Every write goes to a temp file and then os.replace.
Standard library only.

  add --kind decision|result --ref <ref> <text...>   refuses an item of 15 or more words
  compose                                            the push for every open item, or nothing
  list                                               the numbering of the last push
  close <n>...                                       closes items by their number in the last push
  drop <ref>... | drop --file <path>                 closes refs, or every ref starting with <path>#
  push-check                                         PreToolUse hook for PushNotification
  stop-check                                         Stop hook

Both hooks read the hook JSON on stdin and allow everything in a session whose id is not the
content of <dir>/pilot.session. push-check refuses (exit 2) any push that is not exactly the
composed push, and every push while no item is new; the exact push is recorded as sent.
stop-check blocks the stop while an item is new.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

MAX_WORDS = 14
OPEN = ("new", "sent")


def load(folder):
    try:
        with open(os.path.join(folder, "outbox.json")) as file:
            return json.load(file)
    except FileNotFoundError:
        return {"items": [], "last_push": []}


def save(folder, state):
    os.makedirs(folder, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=folder, suffix=".tmp", delete=False) as file:
        json.dump(state, file, indent=2)
    os.replace(file.name, os.path.join(folder, "outbox.json"))


def open_items(state):
    """Open items in push order: decisions first, then results, each in the order added."""
    items = [item for item in state["items"] if item["state"] in OPEN]
    return [item for item in items if item["kind"] == "decision"] + [
        item for item in items if item["kind"] == "result"
    ]


def compose(state):
    """The push text for the open items, or "" when none is open."""
    items = open_items(state)
    if not items:
        return ""
    lines = [f"{len(items)} need you"] + [f"{number}. {item['text']}" for number, item in enumerate(items, 1)]
    return "\n".join(lines)


def close_refs(state, refs):
    for item in state["items"]:
        if item["ref"] in refs:
            item["state"] = "closed"


def is_pilot(folder, hook):
    try:
        with open(os.path.join(folder, "pilot.session")) as file:
            pilot = file.read().strip()
    except FileNotFoundError:
        return False
    return bool(pilot) and hook.get("session_id") == pilot


def has_new(state):
    return any(item["state"] == "new" for item in state["items"])


def record_push(state, text):
    """Mark the composed push as sent: new decisions become sent and results closed."""
    items = open_items(state)
    for item in items:
        item["state"] = "sent" if item["kind"] == "decision" else "closed"
    state["last_push"] = [item["ref"] for item in items]
    state.setdefault("sent", []).append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "text": text})


def push_check(folder):
    try:
        hook = json.load(sys.stdin)
        if hook.get("tool_name") != "PushNotification" or not is_pilot(folder, hook):
            return 0
        state = load(folder)
        if not has_new(state):
            print("Push refused: no new item in the outbox, so send no push.", file=sys.stderr)
            return 2
        text = compose(state)
        if (hook.get("tool_input") or {}).get("message") != text:
            print(f"Push refused: send exactly the composed push:\n{text}", file=sys.stderr)
            return 2
        record_push(state, text)
        save(folder, state)
        return 0
    except Exception as error:
        print(f"Push refused: outbox error ({' '.join(str(error).split()) or type(error).__name__})", file=sys.stderr)
        return 2


def stop_check(folder):
    try:
        hook = json.load(sys.stdin)
        if not is_pilot(folder, hook):
            return 0
        state = load(folder)
        if has_new(state):
            reason = f"The outbox has an unsent new item. Call PushNotification with exactly this message:\n{compose(state)}"
            print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    except Exception as error:
        print(f"outbox: stop-check error, stop allowed ({error})", file=sys.stderr)
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    add_parser = commands.add_parser("add")
    add_parser.add_argument("--kind", required=True, choices=["decision", "result"])
    add_parser.add_argument("--ref", required=True)
    add_parser.add_argument("text", nargs="*")
    commands.add_parser("compose")
    commands.add_parser("list")
    close_parser = commands.add_parser("close")
    close_parser.add_argument("numbers", nargs="+", type=int)
    drop_parser = commands.add_parser("drop")
    drop_parser.add_argument("--file")
    drop_parser.add_argument("refs", nargs="*")
    commands.add_parser("push-check")
    commands.add_parser("stop-check")
    options = parser.parse_args()

    if options.command == "push-check":
        return push_check(options.dir)
    if options.command == "stop-check":
        return stop_check(options.dir)

    state = load(options.dir)
    if options.command == "add":
        text = " ".join(" ".join(options.text).split())
        count = len(text.split())
        if count == 0 or count > MAX_WORDS:
            print(f"outbox: item has {count} words; the limit is {MAX_WORDS}", file=sys.stderr)
            return 1
        if any(item["ref"] == options.ref for item in state["items"]):
            print("already in the outbox")
            return 0
        state["items"].append({"ref": options.ref, "kind": options.kind, "text": text, "state": "new"})
        print("added")
    elif options.command == "compose":
        text = compose(state)
        if text:
            print(text)
        return 0
    elif options.command == "list":
        items = {item["ref"]: item for item in state["items"]}
        for number, ref in enumerate(state["last_push"], 1):
            item = items[ref]
            print(f"{number}. [{item['kind']}] {ref} {item['text']} ({item['state']})")
        return 0
    elif options.command == "close":
        unknown = [n for n in options.numbers if not 1 <= n <= len(state["last_push"])]
        if unknown:
            print(f"outbox: no item {unknown[0]} in the last push", file=sys.stderr)
            return 1
        close_refs(state, {state["last_push"][n - 1] for n in options.numbers})
    elif options.command == "drop":
        if not options.file and not options.refs:
            parser.error("drop needs refs or --file")
        refs = set(options.refs)
        if options.file:
            refs |= {item["ref"] for item in state["items"] if item["ref"].startswith(options.file + "#")}
        close_refs(state, refs)
    save(options.dir, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
