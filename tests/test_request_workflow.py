"""Runs the two scripts of .github/workflows/short-link-request.yml the way the workflow does:
scripts/run_request.sh on a fresh checkout of main, then scripts/comment_failure.sh when it fails.
git pushes to a local bare origin; gh is tests/gh_stub.py, which records calls."""
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
REPO = "osim-yoter-org/oy-public"
PULL = f"https://github.com/{REPO}/pull"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "short-link-request.yml"


def pull(number, branch, title, repo=REPO):
    return {"number": number, "title": title, "html_url": f"https://github.com/{repo}/pull/{number}",
            "head": {"ref": branch, "label": f"{repo.split('/')[0]}:{branch}", "repo": {"full_name": repo}}}


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
        python = Path(sys.executable).as_posix()
        stub_script = (REPO_ROOT / "tests" / "gh_stub.py").as_posix()
        (bin_dir / "gh").write_text(f'#!/usr/bin/env bash\nexec "{python}" "{stub_script}" "$@"\n', encoding="utf-8", newline="\n")
        (bin_dir / "python3").write_text(f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8", newline="\n")
        for stub in bin_dir.iterdir():
            stub.chmod(0o755)
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

    def seed_pulls(self, pulls):
        (self.stub / "pulls.json").write_text(json.dumps(pulls), encoding="utf-8")

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
        self.assertIn(f"{PULL}/1", self.comments())

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
        self.assertIn(f"pr edit {PULL}/1 --title Add short link /renamed-link", self.calls())

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
        self.assertIn(f"{PULL}/1", self.comments())

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
        self.seed_pulls([pull(3, "short-link/issue-3", "Add short link /new-link")])
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"/new-link is already requested in {PULL}/3", self.comments())
        self.assertNotIn("short-link/issue-7", self.remote_branches())

    def test_when_request_breaks_a_rule_comments_problems_and_run_link(self):
        result = self.process_issue(7, issue_body("new-link", "http://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("url must be a full https:// address", self.comments())
        self.assertIn(RUN_URL, self.comments())
        self.assertNotIn("short-link/issue-7", self.remote_branches())

    def test_when_a_fork_pr_uses_the_issue_branch_name_it_is_not_adopted(self):
        self.seed_pulls([pull(5, "short-link/issue-7", "Add short link /new-link", repo="attacker/oy-public")])
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("pull/5", self.calls())
        self.assertNotIn("pull/5", self.comments())
        self.assertIn("pr create --base main --head short-link/issue-7", self.calls())
        self.assertIn(f"{PULL}/6", self.comments())

    def test_when_a_fork_pr_has_the_same_title_it_does_not_block_the_request(self):
        self.seed_pulls([pull(5, "short-link/issue-3", "Add short link /new-link", repo="attacker/oy-public")])
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{PULL}/6", self.comments())

    def test_when_over_200_prs_are_open_an_edit_still_finds_its_own_pr(self):
        self.seed_pulls([pull(n, f"other/branch-{n}", f"Other PR {n}") for n in range(1, 201)])
        self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        result = self.process_issue(7, issue_body("new-link", "https://example.com/b"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls().count("pr create"), 1)
        self.assertIn(f"pr edit {PULL}/201", self.calls())
        self.assertEqual(self.remote_links("short-link/issue-7")["new-link"]["url"], "https://example.com/b")

    def test_when_over_200_prs_are_open_a_duplicate_slug_is_still_found(self):
        pulls = [pull(n, f"other/branch-{n}", f"Other PR {n}") for n in range(1, 201)]
        self.seed_pulls(pulls + [pull(201, "short-link/issue-3", "Add short link /new-link")])
        result = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"/new-link is already requested in {PULL}/201", self.comments())

    def test_when_two_issues_ask_for_one_slug_the_later_run_is_refused(self):
        first = self.process_issue(7, issue_body("new-link", "https://example.com/a"))
        second = self.process_issue(8, issue_body("new-link", "https://example.com/b"))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn(f"/new-link is already requested in {PULL}/1", self.comments())
        self.assertNotIn("short-link/issue-8", self.remote_branches())

    def test_requests_run_one_at_a_time_across_all_issues(self):
        """Runs that overlap would both miss each other's PR; one shared group makes the later run see it."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("concurrency:\n  group: short-link-request\n  cancel-in-progress: false\n  queue: max\n", text)


if __name__ == "__main__":
    unittest.main()
