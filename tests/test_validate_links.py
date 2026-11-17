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
            "label-digits.json": "'phone-label': label must not hold 7 or more digits",
            "label-at.json": "'email-label': label must not hold @",
            "label-http.json": "'url-label': label must not hold a web address",
            "label-www.json": "'www-label': label must not hold a web address",
            "label-phone-spaces.json": "'phone-spaces': label must not hold 7 or more digits",
            "label-id-spaces.json": "'id-spaces': label must not hold 7 or more digits",
            "label-domain.json": "'domain-label': label must not hold a web address",
            "top-level-null.json": "top level must be an object",
            "top-level-list.json": "top level must be an object",
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


class UrlRuleTests(unittest.TestCase):
    """The site accepts a url only when it starts with https:// and the WHATWG URL parser accepts it."""

    def check(self, url):
        with tempfile.TemporaryDirectory() as workdir:
            links = Path(workdir) / "links.json"
            links.write_text(json.dumps({"some-link": {"url": url, "label": "x", "delayMs": 0}}), encoding="utf-8")
            return run(VALIDATOR, links)

    def test_when_url_is_malformed_the_way_the_site_rejects_exits_1(self):
        for url in ["https://example.com:bad", "https://example.com:99999/", "https://%", "https://exa mple.com/"]:
            with self.subTest(url=url):
                result = self.check(url)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("url must be a full https:// address", result.stdout)

    def test_when_url_is_one_the_site_accepts_exits_0(self):
        for url in ["https://wa.me/972500000000?text=a b", "https://example.com:8443/x", "https://xn--4dbrk0ce.com/"]:
            with self.subTest(url=url):
                result = self.check(url)
                self.assertEqual(result.returncode, 0, result.stdout)


class LabelPersonalDataTests(unittest.TestCase):
    """A label is public and reaches Google Analytics, so it must not look like a phone, ID, email or URL."""

    def check(self, label):
        with tempfile.TemporaryDirectory() as workdir:
            links = Path(workdir) / "links.json"
            links.write_text(json.dumps({"some-link": {"url": "https://example.com/", "label": label}}), encoding="utf-8")
            return run(VALIDATOR, links)

    def test_when_label_has_short_numbers_and_no_address_exits_0(self):
        for label in [
            "יום מילואים 2026", "קו 123456", "05/11/2026", "1.1.2026", "גרסה 1.5", "בלי http בכלל",
            "מעבר לאתר צה''ל", "פרסום בקהילה", "Note: חשוב",
            "מילואים 2023-2025", "שנת 2025-2026", "סבב 10-12-2026", "01.01.2026", "15.11.2026",
            "15.11.2026 10:30", "הרשמה 01.12.2026 - 15.12.2026", "מילואים 2023-2025 (3 שנים)",
            "2023-2025 2 סבבים", "7.10.2023 - 2025", "15/11/2026 - 20/11/2026", "פגישה 08:00-16:00",
            "גדוד 8104 ו-8200", "גדודים 8104, 8200", "יחידות 8104 8200", "יחידות 8104, 8200 ו-9210",
        ]:
            with self.subTest(label=label):
                result = self.check(label)
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_when_label_looks_like_personal_data_or_an_address_exits_1(self):
        cases = {
            "להתקשר 050-123-4567": "7 or more digits",
            "להתקשר 050 123 4567": "7 or more digits",
            "להתקשר 03-1234567": "7 or more digits",
            "ת.ז 123 456 789": "7 or more digits",
            "(050) 123-4567": "7 or more digits",
            "050–123–4567": "7 or more digits",
            "050 - 123 - 4567": "7 or more digits",
            "050.123.4567": "7 or more digits",
            "050_123_4567": "7 or more digits",
            "050‐123‐4567": "7 or more digits",
            "050‑123‑4567": "7 or more digits",
            "050 ‒ 123 ‒ 4567": "7 or more digits",
            "050/123/4567": "7 or more digits",
            "050,123,4567": "7 or more digits",
            "+972-50-123-4567": "7 or more digits",
            "+972 (0)50 1234567": "7 or more digits",
            "0 5 0 1 2 3 4 5 6 7": "7 or more digits",
            "050 123 45 67": "7 or more digits",
            "12345678-9": "7 or more digits",
            "10-12-2026 0501234567": "7 or more digits",
            "050-10-12-2026": "7 or more digits",
            "054.12.12.2034": "7 or more digits",
            "יחידות 8104 8200 9210": "7 or more digits",
            "4580 1234 5678 9012": "7 or more digits",
            "٠٥٠١٢٣٤٥٦٧": "7 or more digits",
            "０５０１２３４５６７": "7 or more digits",
            "dani＠example": "must not hold @",
            "dani gmail.com": "web address",
            "ftp://files": "web address",
        }
        for label, problem in cases.items():
            with self.subTest(label=label):
                result = self.check(label)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(problem, result.stdout)


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

    def test_when_label_holds_a_phone_number_refuses(self):
        before = self.links.read_bytes()
        result = self.request(issue_body("new-link", "https://example.com/", "להתקשר 0501234567"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("label must not hold 7 or more digits", result.stdout)
        self.assertEqual(self.links.read_bytes(), before)

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
        self.assertIn("delay: must be a number of seconds from 0 to 10", result.stdout)

    def test_when_delay_is_not_a_number_refuses(self):
        result = self.request(issue_body("new-link", "https://example.com/", "קישור", "$(id)"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("delay: must be a number of seconds", result.stdout)

    def test_when_links_file_is_null_refuses_without_crashing(self):
        self.links.write_text("null\n", encoding="utf-8")
        result = self.request(issue_body("new-link", "https://example.com/", "קישור"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("top level must be an object", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_when_delay_is_out_of_range_or_too_precise_reports_it(self):
        for delay in ["1" + "0" * 309, "10.0004", "0.0004", "11"]:
            with self.subTest(delay=delay[:12]):
                shutil.copy(FIXTURES / "good.json", self.links)
                result = self.request(issue_body("new-link", "https://example.com/", "קישור", delay))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("delay:", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_when_delay_is_a_decimal_within_range_converts_exactly(self):
        for delay, delay_ms in [("10", 10000), ("2.5", 2500), ("0.125", 125), ("0", 0)]:
            with self.subTest(delay=delay):
                shutil.copy(FIXTURES / "good.json", self.links)
                result = self.request(issue_body("new-link", "https://example.com/", "קישור", delay))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                entry = json.loads(self.links.read_text(encoding="utf-8"))["new-link"]
                self.assertEqual(entry["delayMs"], delay_ms)
                self.assertIsInstance(entry["delayMs"], int)


if __name__ == "__main__":
    unittest.main()
