"""Command line: start / runs / next / reply for build runs, and the same after `ticket` for ticket runs.
next and reply name their run, so several sessions can each drive their own. Every outcome prints exactly
one JSON object."""
import json
import sys

from engine import flow, ticket
from engine.workspace import EaseError, find_workspace, load_state, load_ticket_state

USAGE = (
    "usage: ease-engine [ticket] start [project] | start [project] --branch <name>"
    " | [ticket] runs | [ticket] next <run_id> | [ticket] reply <run_id>  (text on stdin)"
)


def main(argv: list[str] | None = None) -> int:
    """Run one command. The ticket or idea (start) and the reply text come on stdin."""
    args = sys.argv[1:] if argv is None else argv
    try:
        ws = find_workspace()
        if args[:1] == ["ticket"]:
            result = command(ws, args[1:], ticket, load_ticket_state)
        else:
            result = command(ws, args, flow, load_state)
    except EaseError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    except Exception as error:  # the skill always gets JSON, whatever went wrong
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        return 1
    print(json.dumps(result))
    return 0


def command(ws, args: list[str], steps, load) -> dict:
    """start / runs / next / reply. `steps` is the flow or the ticket module; `load` reads one of its runs."""
    if args == ["runs"]:
        return steps.open_runs(ws)
    if len(args) == 2 and args[0] == "next":
        return steps.next_action(ws, load(ws, args[1]))
    if len(args) == 2 and args[0] == "reply":
        return steps.reply(ws, load(ws, args[1]), sys.stdin.read())
    if len(args) in (1, 2) and args[0] == "start":
        return steps.start(ws, args[1] if len(args) == 2 else None, sys.stdin.read())
    if steps is flow and len(args) in (3, 4) and args[0] == "start" and args[-2] == "--branch":  # only builds branch
        return flow.start(ws, args[1] if len(args) == 4 else None, sys.stdin.read(), args[-1])
    raise EaseError(USAGE)
