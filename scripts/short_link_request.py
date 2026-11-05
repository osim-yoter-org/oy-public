#!/usr/bin/env python3
"""Turn a "new short link" issue body into a links.json entry.

Reads the issue body from the ISSUE_BODY environment variable only, so its text is never run as shell.
On success: writes the new links.json and prints `slug=<slug>` (the workflow appends it to GITHUB_OUTPUT).
On failure: prints one line per problem and exits 1; links.json is left untouched.

Usage: short_link_request.py LINKS_FILE
"""
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

from validate_links import NOT_PARSED, check_links, load_json

# The text in parentheses at the end of each issue form label (.github/ISSUE_TEMPLATE/new-short-link.yml).
FIELD_HEADING = re.compile(r"^###\s+.*\((slug|url|label|delay)\)\s*$")
DELAY_SECONDS = re.compile(r"^\d+(\.\d+)?$")
MAX_DELAY_SECONDS = Decimal(10)
NO_RESPONSE = "_No response_"


def parse_issue_body(body):
    """Return {field: value} for the form fields found in a GitHub issue form body."""
    fields = {}
    current = None
    for line in body.replace("\r\n", "\n").split("\n"):
        heading = FIELD_HEADING.match(line)
        if heading:
            current = heading.group(1)
            fields[current] = []
        elif line.startswith("### "):
            current = None
        elif current:
            fields[current].append(line)
    values = {name: "\n".join(lines).strip() for name, lines in fields.items()}
    return {name: ("" if value == NO_RESPONSE else value) for name, value in values.items()}


def build_entry(fields):
    """Return (slug, entry, problems) from the parsed form fields."""
    problems = []
    slug = fields.get("slug", "")
    url = fields.get("url", "")
    label = fields.get("label", "")
    delay = fields.get("delay", "")
    if not label:
        problems.append("label: missing")
    if "\n" in label:
        problems.append("label: must be a single line")
    delay_ms = 0
    if delay:
        seconds = Decimal(delay) if DELAY_SECONDS.match(delay) else None
        if seconds is None or seconds > MAX_DELAY_SECONDS:
            problems.append("delay: must be a number of seconds from 0 to 10")
        elif len(delay.partition(".")[2]) > 3:
            problems.append("delay: at most 3 digits after the decimal point")
        else:
            delay_ms = int(seconds.scaleb(3))
    return slug, {"url": url, "label": label, "delayMs": delay_ms}, problems


def main(argv):
    links_path = Path(argv[0])
    slug, entry, problems = build_entry(parse_issue_body(os.environ.get("ISSUE_BODY", "")))
    links, load_problems = load_json(links_path)
    problems += load_problems
    if links is NOT_PARSED:
        pass
    elif isinstance(links, dict):
        if slug in links:
            problems.append(f"{slug!r}: this slug already exists in links.json")
        updated = {**links, slug: entry}
        problems += check_links(updated)
    else:
        problems.append("links.json: top level must be an object of slug -> entry")
    if problems:
        for problem in problems:
            print(problem)
        return 1
    links_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"slug={slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
