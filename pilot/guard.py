#!/usr/bin/env python3
"""PreToolUse hook that blocks the ASK JUAN actions.

Reads the hook JSON on stdin. A blocked call exits 2 with one `ASK JUAN:` line on stderr;
anything else exits 0. Standard library only.
"""
import argparse
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
DB_CLIENTS = {"psql", "pg_dump", "mysql", "mongosh", "cloud-sql-proxy"}
GH_API_VALUE_OPTIONS = {
    "-f", "--raw-field", "-F", "--field", "-H", "--header", "--input", "-q", "--jq",
    "-t", "--template", "--hostname", "--cache", "-p", "--preview",
}
PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def split_commands(command):
    """Split on &&, ||, ;, | and newlines that are outside quotes."""
    pieces, current, quote, i = [], [], None, 0
    while i < len(command):
        char = command[i]
        if quote:
            current.append(char)
            if char == "\\" and quote == '"' and i + 1 < len(command):
                current.append(command[i + 1])
                i += 1
            elif char == quote:
                quote = None
        elif char == "\\" and i + 1 < len(command):
            current.append(char + command[i + 1])
            i += 1
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char in ";|\n" or command.startswith("&&", i):
            pieces.append("".join(current))
            current = []
            if command.startswith("&&", i):
                i += 1
        else:
            current.append(char)
        i += 1
    pieces.append("".join(current))
    return [piece for piece in pieces if piece.strip()]


def git_output(folder, *args):
    try:
        result = subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


class Guard:
    def __init__(self, config, own_prefix):
        self.shared = {
            os.path.realpath(os.path.expanduser(repo)): set(branches)
            for repo, branches in config.get("shared_branches", {}).items()
        }
        self.prod_markers = [marker for marker in config.get("prod_markers", []) if marker]
        self.own_prefix = own_prefix

    def shared_branches(self, folder):
        root = git_output(folder, "rev-parse", "--show-toplevel")
        return self.shared.get(os.path.realpath(root), set()) if root else set()

    def current_branch(self, folder):
        return git_output(folder, "rev-parse", "--abbrev-ref", "HEAD")

    def check_command(self, command, folder):
        """The reason the first blocked simple command is blocked, or None."""
        for piece in split_commands(command):
            tokens = shlex.split(piece)
            while tokens and (ASSIGNMENT.match(tokens[0]) or tokens[0] == "env"):
                tokens.pop(0)
            if not tokens:
                continue
            if tokens[0] == "cd":
                target = os.path.expanduser(tokens[1] if len(tokens) > 1 else "~")
                folder = os.path.join(folder, target)
                continue
            reason = self.check(tokens, folder)
            if reason:
                return reason
        return None

    def check(self, tokens, folder):
        program, args = os.path.basename(tokens[0]), tokens[1:]
        if program == "gh":
            return self.check_gh(args)
        if program == "git":
            while len(args) > 1 and args[0] in ("-C", "-c"):
                if args[0] == "-C":
                    folder = os.path.join(folder, os.path.expanduser(args[1]))
                args = args[2:]
            if args and args[0] == "merge":
                return self.check_merge(folder)
            if args and args[0] == "push":
                return self.check_push(args[1:], folder)
            if args and args[0] == "branch":
                return self.check_branch_delete(args[1:])
        if program in DB_CLIENTS:
            for arg in args:
                for marker in self.prod_markers:
                    if marker in arg:
                        return f"{program} against production ({marker})"
        return None

    def check_gh(self, args):
        if args[:2] == ["pr", "merge"]:
            return "gh pr merge merges a pull request"
        if args[:2] in (["pr", "comment"], ["pr", "review"], ["issue", "comment"]):
            return f"gh {args[0]} {args[1]} posts on GitHub"
        if args[:1] == ["api"]:
            method, path, rest = None, None, args[1:]
            while rest:
                arg = rest.pop(0)
                if arg in ("-X", "--method"):
                    method = rest.pop(0) if rest else None
                elif arg.startswith("--method="):
                    method = arg.split("=", 1)[1]
                elif arg.startswith("-X"):
                    method = arg[2:]
                elif arg in GH_API_VALUE_OPTIONS:
                    rest = rest[1:]
                elif not arg.startswith("-") and path is None:
                    path = arg
            if (method or "").upper() in WRITE_METHODS and path and re.search(r"comments|reviews|merge", path):
                return f"gh api {method.upper()} {path} writes to GitHub"
        return None

    def check_merge(self, folder):
        branch = self.current_branch(folder)
        if branch in self.shared_branches(folder):
            return f"git merge on shared branch {branch}"
        return None

    def check_push(self, args, folder):
        positional, rest = [], list(args)
        while rest:
            arg = rest.pop(0)
            if arg in PUSH_VALUE_OPTIONS:
                rest = rest[1:]
            elif arg in ("-f", "--force") or arg.startswith("--force-with-lease"):
                return "forced git push"
            elif arg in ("-d", "--delete"):
                return "git push that deletes a remote branch"
            elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 2:
                if "f" in arg:
                    return "forced git push"
                if "d" in arg:
                    return "git push that deletes a remote branch"
            elif not arg.startswith("-"):
                positional.append(arg)
        refspecs = positional[1:]
        shared = self.shared_branches(folder)
        for refspec in refspecs:
            if refspec.startswith("+"):
                return f"forced git push ({refspec})"
            if refspec.startswith(":"):
                return f"git push that deletes remote branch {refspec[1:]}"
            destination = refspec.split(":", 1)[-1].removeprefix("refs/heads/")
            if destination == "HEAD":
                destination = self.current_branch(folder)
            if destination in shared:
                return f"git push to shared branch {destination}"
        if not refspecs:
            branch = self.current_branch(folder)
            if branch in shared:
                return f"git push from shared branch {branch}"
        return None

    def check_branch_delete(self, args):
        flags = {arg for arg in args if arg.startswith("-")}
        forced_delete = "-D" in flags or (
            flags & {"-d", "--delete"} and flags & {"-f", "--force"}
        )
        if not forced_delete:
            return None
        for name in (arg for arg in args if not arg.startswith("-")):
            if not self.own_prefix or not name.startswith(self.own_prefix):
                return f"git branch -D of {name}, which this session did not create"
        return None


def use_approval(path, command):
    """Spend a one-time approval: remove the exact command from the JSON list and say whether it was there."""
    try:
        with open(path) as file:
            text = file.read()
    except FileNotFoundError:
        return False
    approvals = json.loads(text) if text.strip() else []
    if command not in approvals:
        return False
    approvals.remove(command)
    with open(path, "w") as file:
        json.dump(approvals, file)
    return True


def ask_juan(reason):
    print(
        f"ASK JUAN: {reason}. Log the exact action as an ASK JUAN entry in your decisions file and do not retry it.",
        file=sys.stderr,
    )
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--approvals")
    parser.add_argument("--own-prefix")
    options = parser.parse_args()

    with open(options.config) as file:
        config = json.load(file)
    event = json.load(sys.stdin)
    tool = event.get("tool_name", "")
    if tool != "Bash":
        if any(fnmatch.fnmatchcase(tool, pattern) for pattern in config.get("blocked_tools", [])):
            return ask_juan(f"{tool} is a blocked tool")
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    folder = event.get("cwd") or os.getcwd()

    try:
        reason = Guard(config, options.own_prefix).check_command(command, folder)
    except ValueError as error:
        print(f"guard: could not parse the command ({error}), letting it through", file=sys.stderr)
        return 0
    if not reason or (options.approvals and use_approval(options.approvals, command)):
        return 0
    return ask_juan(reason)


if __name__ == "__main__":
    sys.exit(main())
