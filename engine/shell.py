"""Run commands, plus small git and gh helpers."""
import json
import os
import subprocess

from engine.workspace import EaseError

TIMEOUT_S = 540  # just under the skill's 600 s Bash limit, so we answer with JSON first

PR_FIELDS = "number,url,title,state,headRefName,headRefOid,isCrossRepository"

COMMENTS_PAGE = """
pageInfo { hasNextPage endCursor }
nodes { id author { login } body diffHunk }
"""

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line originalLine
          comments(first: 100) { %s }
        }
      }
    }
  }
}
""" % COMMENTS_PAGE

COMMENTS_QUERY = """
query($id: ID!, $cursor: String!) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $cursor) { %s }
    }
  }
}
""" % COMMENTS_PAGE

RESOLVE_MUTATION = """
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { id } }
}
"""


def capture(cmd: list[str], cwd) -> tuple[int, str, str]:
    """Run a command. Returns (exit code, stdout, stderr). Never raises."""
    try:
        done = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S
        )
    except FileNotFoundError as error:  # a missing program or a missing cwd folder; the message names it
        return 127, "", str(error)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {TIMEOUT_S}s"
    return done.returncode, done.stdout, done.stderr


def run(cmd: list[str], cwd) -> tuple[int, str]:
    """Run a command. Returns (exit code, stdout + stderr). Never raises."""
    code, out, err = capture(cmd, cwd)
    return code, out + err


def must(cmd: list[str], cwd) -> str:
    """Like run, but a failing command raises EaseError. Returns the output."""
    code, out = run(cmd, cwd)
    if code != 0:
        raise EaseError(f"`{' '.join(cmd)}` failed: {out.strip()[-500:]}")
    return out.strip()


def git(cwd, *args: str) -> str:
    return must(["git", *args], cwd)


def is_dirty(cwd) -> bool:
    return git(cwd, "status", "--porcelain") != ""


def head(cwd) -> str:
    return git(cwd, "rev-parse", "HEAD")


def current_branch(cwd) -> str:
    """The branch we are on. A detached HEAD gives "HEAD"."""
    return git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def switch_to_branch(cwd, branch: str) -> str:
    """Create `branch` and switch to it (fails if it exists). Returns the branch we were on."""
    base = current_branch(cwd)
    git(cwd, "switch", "-c", branch)
    return base


def commit_all(cwd, message: str) -> None:
    """Commit every change. Does nothing if there is nothing to commit."""
    git(cwd, "add", "-A")
    code, _ = run(["git", "diff", "--cached", "--quiet"], cwd)
    if code == 0:
        return
    git(cwd, "commit", "-m", message)


def run_checks(cwd, command: str) -> tuple[bool, str]:
    """Run the repo's checks in a login shell (so npm/nvm are on PATH)."""
    code, out = run([os.environ.get("SHELL", "/bin/sh"), "-lc", command], cwd)
    last_lines = "\n".join(out.strip().splitlines()[-40:])
    return code == 0, last_lines


def has_remote(cwd) -> bool:
    code, _ = run(["git", "remote", "get-url", "origin"], cwd)
    return code == 0


def commits_ahead(cwd, base: str, branch: str) -> int:
    return int(git(cwd, "rev-list", "--count", f"{base}..{branch}"))


def open_pr(cwd, branch: str, base: str, title: str, body: str) -> str:
    """Push the branch and open a pull request. Returns the PR URL."""
    git(cwd, "push", "-u", "origin", branch)
    out = must(
        ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
        cwd,
    )
    lines = out.splitlines()
    urls = [line for line in lines if line.startswith("https://")]  # gh may add warnings after the URL
    return (urls or lines)[-1]


def push_branch(cwd, branch: str) -> tuple[bool, str]:
    """Push the branch without force. Returns (pushed, output). Never raises."""
    if branch.startswith(("+", "-")):
        return False, f"refused to push branch {branch}: git would read its name as a force refspec or a flag"
    code, out = run(["git", "push", "origin", branch], cwd)
    return code == 0, out.strip()


def gh_json(cwd, *args: str):
    """Run gh and parse its stdout as JSON. A failing call or other output raises EaseError."""
    cmd = ["gh", *args]
    code, out, err = capture(cmd, cwd)
    name = " ".join(" ".join(cmd).split())[:200]  # a GraphQL query is long and spans lines
    reason = (out + err).strip()[-500:]
    if code != 0:
        raise EaseError(f"`{name}` failed: {reason}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise EaseError(f"`{name}` did not return JSON: {reason}") from None


def pr_view(cwd, ref) -> dict:
    """The PR's details. `ref` is a number or a link; empty means the PR of the current branch."""
    return gh_json(cwd, "pr", "view", *([str(ref)] if ref else []), "--json", PR_FIELDS)


def repo_name(cwd) -> str:
    """The repo as owner/name."""
    return gh_json(cwd, "repo", "view", "--json", "nameWithOwner")["nameWithOwner"]


def graphql(cwd, query: str, *variables: str) -> dict:
    """Run a GraphQL call. The query goes last, so an error names the variables before it is cut."""
    return gh_json(cwd, "api", "graphql", *variables, "-f", f"query={query}")["data"]


def all_comments(cwd, thread_id: str, page: dict) -> list[dict]:
    """A thread's comments: `page`, the first page, then every page after it."""
    nodes = list(page["nodes"])
    while page["pageInfo"]["hasNextPage"]:
        cursor = page["pageInfo"]["endCursor"]
        data = graphql(cwd, COMMENTS_QUERY, "-f", f"id={thread_id}", "-f", f"cursor={cursor}")
        page = data["node"]["comments"]
        nodes += page["nodes"]
    return [
        {
            "id": node["id"],
            "author": node["author"]["login"] if node["author"] else "ghost",  # a deleted account has no author
            "body": node["body"],
            "diffHunk": node["diffHunk"],
        }
        for node in nodes
    ]


def review_threads(cwd, owner: str, name: str, number: int) -> tuple[str, list[dict]]:
    """Returns (the viewer's login, every review thread on the PR with all its comments)."""
    threads = []
    after = []  # the first page takes no cursor
    while True:
        data = graphql(
            cwd, THREADS_QUERY, "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"number={number}", *after
        )
        page = data["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            threads.append({**node, "comments": all_comments(cwd, node["id"], node["comments"])})
        if not page["pageInfo"]["hasNextPage"]:
            return data["viewer"]["login"], threads
        after = ["-f", f"cursor={page['pageInfo']['endCursor']}"]


def resolve_thread(cwd, thread_id: str) -> None:
    """Mark a review thread resolved. A failure raises EaseError."""
    graphql(cwd, RESOLVE_MUTATION, "-f", f"id={thread_id}")
