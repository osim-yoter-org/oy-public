"""Runs the two scripts of .github/workflows/short-link-request.yml the way the workflow does:
scripts/run_request.sh on a fresh checkout of main, then scripts/comment_failure.sh when it fails.
git pushes to a local bare origin; gh is a stub that records calls."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Full path: on Windows a bare "bash" resolves to WSL before Git Bash.
BASH = shutil.which("bash")
RUN_URL = "https://github.com/osim-yoter-org/oy-public/actions/runs/42"
GH_STUB = r"""#!/usr/bin/env bash
d="$GH_STUB_DIR"
printf '%s\n' "$*" >> "$d/calls.log"
case "$1 $2" in
  "pr list") cat "$d/pr_list.json" 2>/dev/null || echo "[]" ;;
  "pr create")
    [ -f "$d/fail_pr_create" ] && exit 1
    while [ $# -gt 0 ]; do case "$1" in --head) head="$2"; shift ;; --title) title="$2"; shift ;; esac; shift; done
    printf '[{"number": 9, "headRefName": "%s", "title": "%s", "url": "https://github.com/o/r/pull/9"}]\n' "$head" "$title" > "$d/pr_list.json"
    echo "https://github.com/o/r/pull/9" ;;
  "pr edit") ;;
  "issue comment")
    while [ $# -gt 0 ]; do case "$1" in --body) printf '%s\n' "$2" >> "$d/comments.log"; shift ;; --body-file) cat "$2" >> "$d/comments.log"; shift ;; esac; shift; done ;;
  *) exit 2 ;;
esac
"""


def issue_body(slug, url, label="קישור"):
    return (
        f"### שם הקישור (slug)\n\n{slug}\n\n### כתובת יעד (url)\n\n{url}\n\n"
        f"### טקסט בזמן ההעברה (label)\n\n{label}\n\n### השהיה בשניות (delay)\n\n_No response_\n"
    )


class RequestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.origin = self.root / "origin.git"
        self.stub = self.root / "gh-stub"
        self.temp = self.root / "runner-temp"
        bin_dir = self.root / "bin"
        for folder in (self.stub, self.temp, bin_dir):
            folder.mkdir()
        (bin_dir / "gh").write_text(GH_STUB, encoding="utf-8", newline="\n")
        (bin_dir / "python3").write_text(f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8", newline="\n")
        self.env = {
            **os.environ, "PYTHONIOENCODING": "utf-8", "GH_STUB_DIR": str(self.stub), "RUNNER_TEMP": str(self.temp),
            "GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "osim-yoter-org/oy-public", "GITHUB_RUN_ID": "42",
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
        }
        self.git("init", "-q", "--bare", "-b", "main", str(self.origin))
        seed = self.root / "seed"
        self.git("clone", "-q", str(self.origin), str(seed))
        shutil.copytree(REPO_ROOT / "scripts", seed / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("links.json", "latest_ad.json", "whatsapp-groups-json.json"):
            shutil.copy(REPO_ROOT / name, seed / name)
        self.git("add", "-A", cwd=seed)
        self.git("-c", "user.name=seed", "-c", "user.email=seed@example.com", "commit", "-qm", "seed", cwd=seed)
        self.git("push", "-q", "origin", "HEAD:main", cwd=seed)
        self.runs = 0

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, env=getattr(self, "env", None), check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout

    def bash(self, script, cwd, env):
        return subprocess.run([BASH, script], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")

    def process_issue(self, number, body):
        """One workflow run: fresh checkout of main, run_request.sh, then comment_failure.sh if it failed."""
        self.runs += 1
        checkout = self.root / f"checkout-{self.runs}"
        self.git("clone", "-q", "-b", "main", str(self.origin), str(checkout))
        for leftover in self.temp.iterdir():
            leftover.unlink()
        env = {**self.env, "ISSUE_NUMBER": str(number), "ISSUE_BODY": body}
        request = self.bash("scripts/run_request.sh", checkout, env)
        if request.returncode != 0:
            report = self.bash("scripts/comment_failure.sh", checkout, env)
            self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        return request

    def remote_links(self, branch):
        return json.loads(self.git("--git-dir", str(self.origin), "show", f"{branch}:links.json"))

    def remote_branches(self):
        return self.git("--git-dir", str(self.origin), "branch", "--format=%(refname:short)").split()

    def calls(self):
        path = self.stub / "calls.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def comments(self):
        path = self.stub / "comments.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_when_request_is_valid_opens_pr_from_the_issue_branch(self):
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.remote_links("short-link/issue-7")["new-link"]["url"], "https://example.com/a")
        self.assertIn("pr create --base main --head short-link/issue-7 --title Add short link /new-link", self.calls())
        self.assertIn("https://github.com/o/r/pull/9", self.comments())

    def test_when_label_holds_shell_syntax_it_reaches_the_branch_as_text(self):
        label = "יום \"מילואים\" 'שלי' $(touch pwned) `touch pwned2` ${HOME}"
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a", label))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.remote_links("short-link/issue-7")["new-link"]["label"], label)
        self.assertEqual(list(self.root.rglob("pwned*")), [])

    def test_when_issue_is_edited_updates_its_own_branch_and_pr(self):
        self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        result = self.process_issue(7, issue_body("renamed-link", "https://example.com/b"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        links = self.remote_links("short-link/issue-7")
        self.assertNotIn("new-link", links)
        self.assertEqual(links["renamed-link"]["url"], "https://example.com/b")
        self.assertEqual(self.calls().count("pr create"), 1)
        self.assertIn("pr edit https://github.com/o/r/pull/9 --title Add short link /renamed-link", self.calls())

    def test_when_branch_exists_without_pr_the_next_run_opens_the_pr(self):
        (self.stub / "fail_pr_create").touch()
        failed = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("short-link/issue-7", self.remote_branches())
        self.assertIn("could not open the pull request", self.comments())
        self.assertIn(RUN_URL, self.comments())
        (self.stub / "fail_pr_create").unlink()
        recovered = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(self.calls().count("pr create"), 2)
        self.assertIn("https://github.com/o/r/pull/9", self.comments())

    def test_when_push_is_rejected_comments_the_reason_and_run_link(self):
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho rejected by test >&2\nexit 1\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("push to short-link/issue-7 was rejected", self.comments())
        self.assertIn(RUN_URL, self.comments())
        self.assertNotIn("pr create", self.calls())

    def test_when_another_open_pr_requests_the_same_slug_refuses(self):
        other = [{"number": 3, "headRefName": "short-link/issue-3", "title": "Add short link /new-link",
                  "url": "https://github.com/o/r/pull/3"}]
        (self.stub / "pr_list.json").write_text(json.dumps(other), encoding="utf-8")
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/new-link is already requested in https://github.com/o/r/pull/3", self.comments())
        self.assertNotIn("short-link/issue-7", self.remote_branches())

    def test_when_request_breaks_a_rule_comments_problems_and_run_link(self):
        result = self.process_issue(7, issue_body("new-link", "http://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("url must be a full https:// address", self.comments())
        self.assertIn(RUN_URL, self.comments())
        self.assertNotIn("short-link/issue-7", self.remote_branches())


if __name__ == "__main__":
    unittest.main()
