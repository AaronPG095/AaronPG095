#!/usr/bin/env python3
"""Update the profile README with the latest release from public, allowlisted repos.

This script intentionally cannot enumerate private repositories or personal activity.
It changes only the marked section in README.md.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
START = "<!-- public-releases:start -->"
END = "<!-- public-releases:end -->"
PUBLIC_REPOS = ("AaronPG095/FluentTimer",)


def latest_public_release(repo: str) -> str:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AaronPG095-profile",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with urlopen(Request(url, headers=headers), timeout=20) as response:
        release = json.load(response)

    tag = release["tag_name"]
    page = release["html_url"]
    published = release["published_at"]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", tag):
        raise ValueError(f"Invalid release tag: {tag!r}")
    if not page.startswith(f"https://github.com/{repo}/releases/tag/"):
        raise ValueError(f"Unexpected release URL: {page!r}")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Latest release unexpectedly marked as draft or prerelease")

    date = datetime.fromisoformat(published.replace("Z", "+00:00")).strftime("%d %b %Y")
    name = repo.rsplit("/", 1)[-1]
    return f"- [{name} {tag}]({page}) — {date}"


def main() -> None:
    original = README.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("Expected exactly one public release section")
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)

    # API errors fail the workflow rather than deleting the last known-good links.
    lines = [latest_public_release(repo) for repo in PUBLIC_REPOS]
    updated = before + START + "\n" + "\n".join(lines) + "\n" + END + after
    if updated != original:
        README.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
