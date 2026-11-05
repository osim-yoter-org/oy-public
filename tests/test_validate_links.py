import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
VALIDATOR = REPO_ROOT / "scripts" / "validate_links.py"
REQUEST = REPO_ROOT / "scripts" / "short_link_request.py"
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(script, *args, env=None):
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", env=env or UTF8_ENV,
    )


def issue_body(slug, url, label, delay="_No response_"):
    return (
        f"### שם הקישור (slug)\n\n{slug}\n\n### כתובת יעד (url)\n\n{url}\n\n"
        f"### טקסט בזמן ההעברה (label)\n\n{label}\n\n### השהיה בשניות (delay)\n\n{delay}\n"
    )


class ValidatorTests(unittest.TestCase):
    def test_when_links_are_valid_exits_0(self):
        result = run(VALIDATOR, FIXTURES / "good.json")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_when_a_rule_is_broken_exits_1_and_names_it(self):
        cases = {
            "duplicate-key.json": "duplicate key 'reserve-day'",
            "reserved-slug.json": "'ads': slug is reserved",
            "http-url.json": "url must be a full https:// address",
            "bad-json.json": "does not parse",
            "delay-11000.json": "delayMs must be a number from 0 to 10000",
            "label-81.json": "label is 81 characters, max 80",
        }
        for fixture, problem in cases.items():
            with self.subTest(fixture=fixture):
                result = run(VALIDATOR, FIXTURES / fixture)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(problem, result.stdout)

    def test_when_run_on_the_repo_data_files_exits_0(self):
        result = run(VALIDATOR)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("whatsapp-groups-json.json", result.stdout)


class ShortLinkRequestTests(unittest.TestCase):
    def setUp(self):
        self.workdir = Path(tempfile.mkdtemp())
        self.links = self.workdir / "links.json"
        shutil.copy(FIXTURES / "good.json", self.links)

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def request(self, body):
        return run(REQUEST, self.links, env={**UTF8_ENV, "ISSUE_BODY": body})

    def test_when_label_holds_shell_syntax_it_is_stored_as_text(self):
        label = "יום \"מילואים\" 'שלי' $(touch pwned) `id` ${HOME}"
        result = self.request(issue_body("reserve-day", "https://example.com/form?a=1&b=2", label, "2.5"))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), "slug=reserve-day")
        entry = json.loads(self.links.read_text(encoding="utf-8"))["reserve-day"]
        self.assertEqual(entry, {"url": "https://example.com/form?a=1&b=2", "label": label, "delayMs": 2500})
        self.assertFalse((self.workdir / "pwned").exists())
        self.assertFalse(Path("pwned").exists())

    def test_when_delay_is_empty_delay_is_0(self):
        result = self.request(issue_body("new-link", "https://example.com/", "קישור"))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(self.links.read_text(encoding="utf-8"))["new-link"]["delayMs"], 0)

    def test_when_slug_exists_refuses_and_leaves_file_untouched(self):
        before = self.links.read_bytes()
        result = self.request(issue_body("reserve-day-2026", "https://example.com/", "קישור"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stdout)
        self.assertEqual(self.links.read_bytes(), before)

    def test_when_fields_break_site_rules_lists_each_problem(self):
        result = self.request(issue_body("Wa Link", "http://example.com/", "קישור", "11"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("slug must use lowercase", result.stdout)
        self.assertIn("url must be a full https:// address", result.stdout)
        self.assertIn("delayMs must be a number from 0 to 10000", result.stdout)

    def test_when_delay_is_not_a_number_refuses(self):
        result = self.request(issue_body("new-link", "https://example.com/", "קישור", "$(id)"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("delay: must be a number of seconds", result.stdout)


if __name__ == "__main__":
    unittest.main()
