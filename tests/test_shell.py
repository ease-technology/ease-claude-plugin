import re
import subprocess
from pathlib import Path

import pytest

from conftest import git_repo
from engine import shell
from engine.workspace import EaseError


def thread(thread_id, comments=(), more_comments=None):
    """A reviewThreads node. `more_comments` is the cursor of a next page of comments."""
    return {
        "id": thread_id,
        "isResolved": False,
        "isOutdated": False,
        "path": "a.py",
        "line": 3,
        "originalLine": 2,
        "comments": comment_page(comments, more_comments),
    }


def comment(comment_id, author="sam"):
    return {
        "id": comment_id,
        "author": {"login": author} if author else None,
        "body": f"Body of {comment_id}",
        "diffHunk": "@@ -1 +1 @@",
    }


def comment_page(comments, cursor=None):
    return {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": list(comments)}


def threads_page(threads, cursor=None):
    page = {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": threads}
    return {
        "data": {
            "viewer": {"login": "juan"},
            "repository": {"pullRequest": {"reviewThreads": page}},
        }
    }


def comments_response(comments, cursor=None):
    return {"data": {"node": {"comments": comment_page(comments, cursor)}}}


def value_of(call, flag, name):
    """The value given to `flag` for variable `name` in a gh api graphql call, or None."""
    for position, arg in enumerate(call):
        if arg.startswith(f"{name}=") and call[position - 1] == flag:
            return arg.split("=", 1)[1]
    return None


def test_run_still_merges_stdout_and_stderr(tmp_path):
    assert shell.run(["sh", "-c", "echo out; echo err >&2; exit 3"], tmp_path) == (3, "out\nerr\n")


def test_run_still_reports_a_missing_program_without_raising(tmp_path):
    code, out = shell.run(["no-such-program-here"], tmp_path)
    assert code == 127
    assert "no-such-program-here" in out


def test_review_threads_reads_every_page_of_threads(tmp_path, scripted_gh):  # AC1
    scripted_gh.answer(
        {"match": "cursor=PAGE2", "stdout": threads_page([thread("T2", [comment("C2")])])},
        {"match": "reviewThreads", "stdout": threads_page([thread("T1", [comment("C1")])], cursor="PAGE2")},
    )

    viewer, threads = shell.review_threads(tmp_path, "acme", "app", 7)

    assert viewer == "juan"
    assert [t["id"] for t in threads] == ["T1", "T2"]
    assert [[c["id"] for c in t["comments"]] for t in threads] == [["C1"], ["C2"]]

    first, second = scripted_gh.calls()
    assert first[:2] == ["api", "graphql"]
    assert value_of(first, "-f", "owner") == "acme"
    assert value_of(first, "-f", "name") == "app"
    assert value_of(first, "-F", "number") == "7"
    assert value_of(first, "-f", "cursor") is None
    assert value_of(second, "-f", "cursor") == "PAGE2"
    assert "reviewThreads(first: 100, after: $cursor)" in value_of(first, "-f", "query")


def test_review_threads_reads_every_page_of_a_threads_comments(tmp_path, scripted_gh):  # AC1
    scripted_gh.answer(
        {"match": "cursor=COMMENTS3", "stdout": comments_response([comment("C3")])},
        {"match": "cursor=COMMENTS2", "stdout": comments_response([comment("C2")], cursor="COMMENTS3")},
        {
            "match": "reviewThreads",
            "stdout": threads_page([thread("T1", [comment("C1")], more_comments="COMMENTS2"), thread("T2", [comment("C9")])]),
        },
    )

    _, threads = shell.review_threads(tmp_path, "acme", "app", 7)

    assert [[c["id"] for c in t["comments"]] for t in threads] == [["C1", "C2", "C3"], ["C9"]]
    _, page_two, page_three = scripted_gh.calls()
    assert value_of(page_two, "-f", "id") == "T1"
    assert value_of(page_two, "-f", "cursor") == "COMMENTS2"
    assert value_of(page_three, "-f", "cursor") == "COMMENTS3"


def test_review_threads_keeps_the_selected_fields_and_a_null_author_is_ghost(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "reviewThreads", "stdout": threads_page([thread("T1", [comment("C1", author=None)])])})

    _, threads = shell.review_threads(tmp_path, "acme", "app", 7)

    assert threads == [
        {
            "id": "T1",
            "isResolved": False,
            "isOutdated": False,
            "path": "a.py",
            "line": 3,
            "originalLine": 2,
            "comments": [{"id": "C1", "author": "ghost", "body": "Body of C1", "diffHunk": "@@ -1 +1 @@"}],
        }
    ]


def test_a_failure_on_a_later_page_raises(tmp_path, scripted_gh):  # AC2
    scripted_gh.answer(
        {"match": "cursor=PAGE2", "stderr": "gh: API rate limit exceeded\n", "code": 1},
        {"match": "reviewThreads", "stdout": threads_page([thread("T1")], cursor="PAGE2")},
    )

    with pytest.raises(EaseError, match="API rate limit exceeded"):
        shell.review_threads(tmp_path, "acme", "app", 7)


def test_gh_json_survives_a_warning_on_stderr(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "repo view", "stdout": {"nameWithOwner": "acme/app"}, "stderr": "Warning: gh is old\n"})

    assert shell.gh_json(tmp_path, "repo", "view") == {"nameWithOwner": "acme/app"}


def test_a_failing_gh_call_raises_naming_the_command_and_the_reason(tmp_path, scripted_gh):  # AC2
    scripted_gh.answer({"match": "pr view", "stderr": "no pull requests found\n", "code": 1})

    with pytest.raises(EaseError) as error:
        shell.gh_json(tmp_path, "pr", "view", "7")

    assert "gh pr view 7" in str(error.value)
    assert "no pull requests found" in str(error.value)


def test_output_that_is_not_json_raises_naming_the_command(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "pr view", "stdout": "<html>oops</html>"})

    with pytest.raises(EaseError) as error:
        shell.gh_json(tmp_path, "pr", "view", "7")

    assert "gh pr view 7" in str(error.value)
    assert "<html>oops</html>" in str(error.value)


def test_a_missing_gh_raises(tmp_path, monkeypatch):  # AC2
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(EaseError, match="`gh pr view 7` failed"):
        shell.gh_json(tmp_path, "pr", "view", "7")


def test_a_graphql_failure_names_the_command_without_the_whole_query(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "reviewThreads", "stderr": "gh: Could not resolve to a PullRequest\n", "code": 1})

    with pytest.raises(EaseError) as error:
        shell.review_threads(tmp_path, "acme", "app", 7)

    assert "gh api graphql -f owner=acme -f name=app -F number=7" in str(error.value)
    assert "Could not resolve to a PullRequest" in str(error.value)
    assert "\n" not in str(error.value).split("failed:")[0]
    assert "originalLine" not in str(error.value)


def test_pr_view_asks_for_the_fields_a_run_needs(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "pr view", "stdout": {"number": 7}})

    assert shell.pr_view(tmp_path, "7") == {"number": 7}
    assert scripted_gh.calls() == [
        ["pr", "view", "7", "--json", "number,url,title,state,headRefName,headRefOid,isCrossRepository"]
    ]


def test_pr_view_with_no_ref_asks_for_the_current_branchs_pr(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "pr view", "stdout": {"number": 7}})

    shell.pr_view(tmp_path, "")

    assert scripted_gh.calls()[0][:3] == ["pr", "view", "--json"]


def test_repo_name_gives_owner_and_name(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "repo view", "stdout": {"nameWithOwner": "acme/app"}})

    assert shell.repo_name(tmp_path) == "acme/app"
    assert scripted_gh.calls() == [["repo", "view", "--json", "nameWithOwner"]]


def test_resolve_thread_sends_the_mutation(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "resolveReviewThread", "stdout": {"data": {"resolveReviewThread": {"thread": {"id": "T1"}}}}})

    shell.resolve_thread(tmp_path, "T1")

    call = scripted_gh.calls()[0]
    assert value_of(call, "-f", "id") == "T1"
    assert "resolveReviewThread" in value_of(call, "-f", "query")


def test_resolve_thread_raises_on_failure(tmp_path, scripted_gh):
    scripted_gh.answer({"match": "resolveReviewThread", "stderr": "gh: Resource not accessible\n", "code": 1})

    with pytest.raises(EaseError, match="Resource not accessible"):
        shell.resolve_thread(tmp_path, "T1")


def test_no_helper_posts_a_comment_reply_or_review():  # AC19
    source = Path(shell.__file__).read_text()

    assert re.findall(r"mutation\(.*?\{\s*(\w+)", source, re.DOTALL) == ["resolveReviewThread"]
    assert not re.search(r'"comment"|"review"|addPullRequestReview|addComment', source)


def clone_with_origin(tmp_path):
    """A repo on branch main, with a bare origin that has its commit."""
    git_repo(tmp_path / "seed")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", tmp_path / "seed", origin], check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=tmp_path / "seed", check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=tmp_path / "seed", check=True)
    return tmp_path / "seed", origin


def commit(repo, message, *flags):
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message, *flags], cwd=repo, check=True)


def head_of(repo, ref="main"):
    return subprocess.run(["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_push_branch_pushes(tmp_path):
    repo, origin = clone_with_origin(tmp_path)
    commit(repo, "second")

    ok, _ = shell.push_branch(repo, "main")

    assert ok
    assert head_of(origin) == head_of(repo)


def test_a_rejected_push_returns_the_output_and_does_not_force(tmp_path):  # AC17
    repo, origin = clone_with_origin(tmp_path)
    before = head_of(origin)
    commit(repo, "rewritten", "--amend")

    ok, output = shell.push_branch(repo, "main")

    assert not ok
    assert "rejected" in output
    assert head_of(origin) == before


def test_push_branch_does_not_raise_without_an_origin(tmp_path):
    git_repo(tmp_path / "app")

    ok, output = shell.push_branch(tmp_path / "app", "main")

    assert not ok
    assert "origin" in output


def test_a_branch_name_cannot_turn_the_push_into_a_force_push(tmp_path):  # AC17
    repo, origin = clone_with_origin(tmp_path)
    before = head_of(origin)
    commit(repo, "rewritten", "--amend")
    subprocess.run(["git", "switch", "-q", "-c", "+main"], cwd=repo, check=True)

    ok, output = shell.push_branch(repo, "+main")

    assert not ok
    assert "+main" in output
    assert head_of(origin) == before
