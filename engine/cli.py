"""Command line: start / next / reply. Every outcome prints exactly one JSON object."""
import json
import sys

from engine import flow
from engine.workspace import EaseError, find_workspace, load_state

USAGE = "usage: ease-engine start [project] | next | reply  (text on stdin)"


def main(argv: list[str] | None = None) -> int:
    """Run one command on the newest run. The ticket (start) and the reply text come on stdin."""
    args = sys.argv[1:] if argv is None else argv
    try:
        ws = find_workspace()
        if args == ["next"]:
            result = flow.next_action(ws, load_state(ws))
        elif args == ["reply"]:
            result = flow.reply(ws, load_state(ws), sys.stdin.read())
        elif len(args) in (1, 2) and args[0] == "start":
            project_name = args[1] if len(args) == 2 else None
            result = flow.start(ws, project_name, sys.stdin.read())
        else:
            raise EaseError(USAGE)
    except EaseError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    except Exception as error:  # the skill always gets JSON, whatever went wrong
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        return 1
    print(json.dumps(result))
    return 0
