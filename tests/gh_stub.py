"""Stand-in for the gh CLI in test_request_workflow.py. State lives in $GH_STUB_DIR:
pulls.json (open PRs in REST shape), calls.log, comments.log, and fail_pr_create (flag file).
The `head=owner:branch` filter of `gh api .../pulls` matches the branch name only, so the
script's own repository check is what keeps fork PRs out."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

STATE = Path(os.environ["GH_STUB_DIR"])
REPO = os.environ["GITHUB_REPOSITORY"]
PULLS = STATE / "pulls.json"


def option(args, name):
    return args[args.index(name) + 1] if name in args else None


def load_pulls():
    return json.loads(PULLS.read_text(encoding="utf-8")) if PULLS.exists() else []


def save_pulls(pulls):
    PULLS.write_text(json.dumps(pulls), encoding="utf-8")


def api(args):
    parts = urlsplit(args[-1])
    query = parse_qs(parts.query)
    pulls = load_pulls()
    if "head" in query:
        branch = query["head"][0].split(":", 1)[-1]
        pulls = [pull for pull in pulls if pull["head"]["ref"] == branch]
    per_page = int(query.get("per_page", ["30"])[0])
    pages = [pulls[start:start + per_page] for start in range(0, len(pulls), per_page)] or [[]]
    print(json.dumps(pages if "--paginate" in args else pages[0]))


def pr_list(args):
    limit = int(option(args, "--limit") or 30)
    rows = [{
        "headRefName": pull["head"]["ref"], "title": pull["title"], "url": pull["html_url"],
        "isCrossRepository": pull["head"]["repo"]["full_name"] != REPO,
    } for pull in load_pulls()[:limit]]
    print(json.dumps(rows))


def pr_create(args):
    if (STATE / "fail_pr_create").exists():
        return 1
    pulls = load_pulls()
    head = option(args, "--head")
    if any(pull["head"]["ref"] == head and pull["head"]["repo"]["full_name"] == REPO for pull in pulls):
        print(f"a pull request for branch {head} already exists", file=sys.stderr)
        return 1
    number = max([pull["number"] for pull in pulls] + [0]) + 1
    url = f"https://github.com/{REPO}/pull/{number}"
    owner = REPO.split("/")[0]
    pulls.append({"number": number, "title": option(args, "--title"), "html_url": url,
                  "head": {"ref": head, "label": f"{owner}:{head}", "repo": {"full_name": REPO}}})
    save_pulls(pulls)
    print(url)
    return 0


def pr_edit(args):
    pulls = load_pulls()
    match = [pull for pull in pulls if pull["html_url"] == args[2]]
    if not match:
        return 1
    match[0]["title"] = option(args, "--title")
    save_pulls(pulls)
    return 0


def issue_comment(args):
    body = option(args, "--body")
    if body is None:
        body = Path(option(args, "--body-file")).read_text(encoding="utf-8")
    with open(STATE / "comments.log", "a", encoding="utf-8") as log:
        log.write(body + "\n")
    return 0


def main(args):
    with open(STATE / "calls.log", "a", encoding="utf-8") as log:
        log.write(" ".join(args) + "\n")
    if args[0] == "api":
        api(args)
        return 0
    handlers = {("pr", "list"): pr_list, ("pr", "create"): pr_create, ("pr", "edit"): pr_edit,
                ("issue", "comment"): issue_comment}
    handler = handlers.get(tuple(args[:2]))
    if handler is None:
        return 2
    return handler(args) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
