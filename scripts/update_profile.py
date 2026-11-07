#!/usr/bin/env python3
"""Refresh the public-only activity section of the GitHub profile.

Uses GET /users/{username}/repos (public repositories only), then reads
releases and pull requests from those verified public repositories.
Never queries /user/repos, private repositories, or private contribution data.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OWNER = "AaronPG095"
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
START = "<!-- profile-activity:start -->"
END = "<!-- profile-activity:end -->"
FEATURED = {
    "AaronPG095/FluentTimer",
    "AaronPG095/kollektiv-spinnen-website",
    "AaronPG095/my-minimalist-portfolio",
}
RELEASE_PROJECT = "AaronPG095/FluentTimer"
MAX_PAGES = 20
PAGE_SIZE = 100
RECENT_DAYS = 180
MAX_RECENT_PRS = 3


def api_json(path, params=None):
    if not path.startswith("/") or "://" in path:
        raise ValueError("GitHub API path must be relative")
    query = urlencode(params or {})
    url = "https://api.github.com" + path + ("?" + query if query else "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AaronPG095-public-profile",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        return json.load(response)


def pages(path, params=None):
    for page in range(1, MAX_PAGES + 1):
        data = api_json(path, {**(params or {}), "per_page": PAGE_SIZE, "page": page})
        if not isinstance(data, list):
            raise ValueError(f"Expected a list from GitHub API: {path}")
        yield from data
        if len(data) < PAGE_SIZE:
            return
    raise RuntimeError(f"Unexpectedly large paginated response: {path}")


def public_owned_repositories():
    result = []
    for repo in pages(f"/users/{OWNER}/repos", {"type": "owner", "sort": "full_name"}):
        name = repo.get("full_name", "")
        if (
            repo.get("private") is False
            and repo.get("visibility") == "public"
            and repo.get("owner", {}).get("login", "").lower() == OWNER.lower()
            and re.fullmatch(rf"{OWNER}/[A-Za-z0-9_.-]+", name)
        ):
            result.append(name)
    if not result:
        raise ValueError("No public repositories returned; refusing to erase profile data")
    if RELEASE_PROJECT not in result:
        raise ValueError("Release project is no longer public; check profile visibility")
    return result


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def safe_title(value):
    title = re.sub(r"\s+", " ", value).strip()[:95]
    return re.sub(r"([\\\`*_\[\](){}<>|])", r"\\\1", title)


def get_activity(repositories):
    releases = []
    authored_prs = []
    for repo in repositories:
        for release in pages(f"/repos/{repo}/releases"):
            if release.get("draft") or not release.get("published_at"):
                continue
            # A published prerelease is still a release, but not the main stable release.
            releases.append((repo, release))
        for pr in pages(f"/repos/{repo}/pulls", {"state": "all"}):
            if pr.get("user", {}).get("login", "").lower() == OWNER.lower():
                authored_prs.append((repo, pr))
    return releases, authored_prs


def render_activity(repositories, releases, authored_prs, now=None):
    now = now or datetime.now(timezone.utc)
    stable = [
        release for repo, release in releases
        if repo == RELEASE_PROJECT and not release.get("prerelease")
    ]
    stable.sort(key=lambda item: item["published_at"], reverse=True)

    lines = [
        "| Public repositories | Published releases | Authored PRs in own public repositories |",
        "| ---: | ---: | ---: |",
        f"| **{len(repositories)}** | **{len(releases)}** | **{len(authored_prs)}** |",
    ]
    if stable:
        release = stable[0]
        tag = release["tag_name"]
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", tag):
            raise ValueError("Unexpected release tag")
        date = timestamp(release["published_at"]).strftime("%d %b %Y")
        lines += [
            "",
            f"**Latest stable release:** [FluentTimer {tag}](https://github.com/{RELEASE_PROJECT}/releases/tag/{tag}) · {date}",
        ]

    cutoff = now - timedelta(days=RECENT_DAYS)
    recent = []
    for repo, pr in authored_prs:
        if repo not in FEATURED:
            continue
        if pr.get("state") != "open" and not pr.get("merged_at"):
            continue
        updated = pr.get("merged_at") or pr.get("updated_at")
        title = pr.get("title", "")
        if not updated or timestamp(updated) < cutoff:
            continue
        if re.match(r"(?i)^(sync token-lean pack|chore:|docs: refresh)", title):
            continue
        number = pr.get("number")
        if not isinstance(number, int):
            continue
        recent.append((timestamp(updated), repo, number, title))
    recent.sort(reverse=True, key=lambda item: item[0])
    if recent:
        lines += ["", "**Recent pull requests:**"]
        for date, repo, number, title in recent[:MAX_RECENT_PRS]:
            project = repo.split("/", 1)[1]
            url = f"https://github.com/{repo}/pull/{number}"
            lines.append(f"- [{project}: {safe_title(title)}]({url}) · {date.strftime('%d %b %Y')}")

    lines += [
        "",
        "<sub>Counts cover public repositories owned by this account; pull requests in other owners' repositories are not included. Refreshed weekly.</sub>",
    ]
    return "\n".join(lines)


def replace_section(readme, content):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("Expected exactly one profile activity section")
    prefix, remainder = readme.split(START, 1)
    _, suffix = remainder.split(END, 1)
    return f"{prefix}{START}\n{content}\n{END}{suffix}"


def main():
    original = README.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("Activity markers missing; leaving README untouched")

    repositories = public_owned_repositories()
    releases, prs = get_activity(repositories)
    rendered = render_activity(repositories, releases, prs)
    updated = replace_section(original, rendered)
    if updated != original:
        README.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
