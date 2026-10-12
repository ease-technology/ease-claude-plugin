"""Command line: start / next / reply for build runs, and the same after `ticket` for ticket runs.
Every outcome prints exactly one JSON object."""
import json
import sys

from engine import flow, ticket
from engine.workspace import EaseError, find_workspace, load_state, load_ticket_state

USAGE = "usage: ease-engine [ticket] start [project] | [ticket] next | [ticket] reply  (text on stdin)"


def main(argv: list[str] | None = None) -> int:
    """Run one command on the newest run. The ticket or idea (start) and the reply text come on stdin."""
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
    """start / next / reply. `steps` is the flow or the ticket module; `load` reads its newest run."""
    if args == ["next"]:
        return steps.next_action(ws, load(ws))
    if args == ["reply"]:
        return steps.reply(ws, load(ws), sys.stdin.read())
    if len(args) in (1, 2) and args[0] == "start":
        return steps.start(ws, args[1] if len(args) == 2 else None, sys.stdin.read())
    raise EaseError(USAGE)
