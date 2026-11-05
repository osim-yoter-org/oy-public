#!/usr/bin/env python3
"""Validate links.json against the site's short-link rules and check every *.json parses.

Usage:
  validate_links.py              check links.json in the repo root, then every *.json in the repo (tests/ excluded)
  validate_links.py FILE         check FILE as a links.json

Prints one line per problem and exits 1, or prints one OK line and exits 0.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
MAX_DELAY_MS = 10000
MAX_LABEL_LENGTH = 80

# Copied from the website repo (osimyoter-website): src/shortLinks/shortLinks.ts RESERVED_SLUGS =
# APP_PAGE_SLUGS + the slugs of src/forwardRoutes.ts + ARCHIVE_SLUGS + REDIRECT_SLUGS.
# Keep this list in step with those two files whenever a site page or forward route is added.
APP_PAGE_SLUGS = [
    "michtav-nechitzoot", "michtav_nechitzoot", "privacy-policy", "pp", "accessibility", "u", "wa", "search", "ads",
    "ykm-tlv", "ads_coupon", "ba-shabak", "tg_ad", "mitgaisim", "milbot-reminder", "r",
]
FORWARD_ROUTE_SLUGS = [
    "direct", "close-ad", "tg", "fb", "li", "podcasts", "instagram", "telegram", "jobnikim", "paybox", "sosa", "צמה",
    "chamal-org-consultant", "urgent", "w", "wa-old",
]
ARCHIVE_SLUGS = ["magazine-2024", "medics-training", "modash-aman", "miluim-photo"]
REDIRECT_SLUGS = ["u1", "uu"]
RESERVED_SLUGS = set(APP_PAGE_SLUGS + FORWARD_ROUTE_SLUGS + ARCHIVE_SLUGS + REDIRECT_SLUGS)


def load_json(path):
    """Parse a JSON file strictly. Returns (value, problems); value is None when the file does not parse."""
    problems = []

    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                problems.append(f"{path.name}: duplicate key {key!r}")
            seen[key] = value
        return seen

    def reject_constant(name):
        raise ValueError(f"{name} is not valid JSON")

    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return None, [f"{path.name}: does not parse: {error}"]
    return value, problems


def is_https_url(value):
    if not isinstance(value, str) or not value.startswith("https://"):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == "https" and bool(parts.hostname)


def check_links(links, name="links.json"):
    """Return one problem string per rule the links object breaks."""
    if not isinstance(links, dict):
        return [f"{name}: top level must be an object of slug -> entry"]
    problems = []
    for slug, entry in links.items():
        where = f"{name}: {slug!r}"
        if not SLUG_PATTERN.match(slug):
            problems.append(f"{where}: slug must use lowercase a-z, 0-9 and - only")
        if slug in RESERVED_SLUGS:
            problems.append(f"{where}: slug is reserved by a site page or route")
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry must be an object with url, label, delayMs")
            continue
        if not is_https_url(entry.get("url")):
            problems.append(f"{where}: url must be a full https:// address")
        if "label" in entry:
            label = entry["label"]
            if not isinstance(label, str):
                problems.append(f"{where}: label must be text")
            elif len(label) > MAX_LABEL_LENGTH:
                problems.append(f"{where}: label is {len(label)} characters, max {MAX_LABEL_LENGTH}")
        if "delayMs" in entry:
            delay = entry["delayMs"]
            if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= MAX_DELAY_MS:
                problems.append(f"{where}: delayMs must be a number from 0 to {MAX_DELAY_MS}")
    return problems


def check_links_file(path):
    links, problems = load_json(path)
    if links is None:
        return problems
    return problems + check_links(links, path.name)


def repo_json_files():
    skipped = {".git", "tests"}
    return sorted(
        path for path in REPO_ROOT.rglob("*.json")
        if not skipped.intersection(path.relative_to(REPO_ROOT).parts)
    )


def main(argv):
    if len(argv) > 1:
        print("usage: validate_links.py [LINKS_FILE]")
        return 1
    if argv:
        checked = [Path(argv[0])]
        problems = check_links_file(checked[0])
    else:
        links_path = REPO_ROOT / "links.json"
        checked = [links_path] + [path for path in repo_json_files() if path != links_path]
        problems = check_links_file(links_path)
        for path in checked[1:]:
            problems += load_json(path)[1]
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("OK: " + ", ".join(path.name for path in checked))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
