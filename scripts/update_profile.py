#!/usr/bin/env python3
"""Refresh combined profile statistics and curated public activity links."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from time import sleep, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from github_metrics import OWNER, STATS_PATH, metrics_from_data, stats_svg
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
START = "<!-- profile-activity:start -->"
END = "<!-- profile-activity:end -->"
FEATURED = {
    "AaronPG095/AI-Dev-Workflow",
    "AaronPG095/FluentTimer",
    "AaronPG095/TokenHUD",
    "AaronPG095/kollektiv-spinnen-website",
    "AaronPG095/my-minimalist-portfolio",
}
RELEASE_PROJECT = "AaronPG095/FluentTimer"
MAX_PAGES = 20
PAGE_SIZE = 100
RECENT_DAYS = 180
MAX_RECENT_PRS = 3


def api_json(path, params=None, token=None):
    if not path.startswith("/") or "://" in path:
        raise ValueError("GitHub API path must be relative")
    query = urlencode(params or {})
    url = "https://api.github.com" + path + ("?" + query if query else "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AaronPG095-public-profile",
    }
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            if attempt == 2 or error.code not in (403, 429):
                raise
            if error.headers.get("Retry-After"):
                sleep(int(error.headers["Retry-After"]))
            elif error.headers.get("X-RateLimit-Remaining") == "0":
                sleep(max(1, int(error.headers["X-RateLimit-Reset"]) - time() + 1))
            elif error.code in (403, 429):
                sleep(15 * (attempt + 1))
            else:
                raise
        except URLError as error:
            if attempt == 2 or not isinstance(error.reason, (ConnectionResetError, TimeoutError)):
                raise
            sleep(1)


def pages(path, params=None, token=None):
    for page in range(1, MAX_PAGES + 1):
        data = api_json(path, {**(params or {}), "per_page": PAGE_SIZE, "page": page}, token=token)
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
    title = re.sub(r"\s+", " ", value).strip()
    title = re.sub(
        r"(?i)^(?:plan\s*-\s*(?:feature|bug|fix|refactor|docs|chore)|(?:feat|fix|perf|refactor)(?:\([^)]*\))?):\s+",
        "",
        title,
    )[:95]
    title = title[:1].upper() + title[1:]
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


def search_total(kind, token=None):
    visibility = "" if token else " is:public"
    if kind == "commit":
        path = "/search/commits"
        query = f"author:{OWNER}{visibility}"
    else:
        path = "/search/issues"
        query = f"author:{OWNER} is:{kind}{visibility}"
    result = api_json(path, {
        "q": query,
        "per_page": 1,
    }, token=token)
    if result["incomplete_results"]:
        raise RuntimeError(f"Incomplete {kind} search; keeping existing dashboard")
    return result["total_count"]


def owned_private_counts(token):
    if api_json("/user", token=token)["login"].casefold() != OWNER.casefold():
        raise ValueError("The statistics token must belong to the profile owner")
    repos = releases = 0
    try:
        for repo in pages("/user/repos", {"affiliation": "owner", "visibility": "private"}, token):
            if repo["owner"]["login"].casefold() != OWNER.casefold() or not repo["private"]:
                continue
            repos += 1
            releases += sum(
                not release["draft"] and bool(release["published_at"])
                for release in pages(f"/repos/{repo['full_name']}/releases", token=token)
            )
    except Exception:
        raise RuntimeError("Unable to count private repositories or releases") from None
    return repos, releases


def combined_commit_days(today, token):
    start = today - timedelta(days=364)
    counts = {start + timedelta(days=i): 0 for i in range(365)}
    windows = [
        (start + timedelta(days=i), min(today, start + timedelta(days=i + 29)))
        for i in range(0, 365, 30)
    ]
    while windows:
        window, end = windows.pop(0)
        # Overlap adjacent windows by a day to cover author timezone offsets.
        query = (
            f"author:{OWNER} author-date:{window - timedelta(days=1)}"
            f"..{end + timedelta(days=1)}"
        )
        page = 1
        dates = []
        while True:
            result = api_json("/search/commits", {
                "q": query, "sort": "author-date", "order": "asc", "per_page": 100, "page": page,
            }, token=token)
            sleep(2.1)
            if result["incomplete_results"] or result["total_count"] > 1000:
                if window == end:
                    raise RuntimeError("GitHub returned incomplete daily commit search results")
                middle = window + (end - window) // 2
                windows[:0] = [(window, middle), (middle + timedelta(days=1), end)]
                break
            for item in result["items"]:
                day = timestamp(item["commit"]["author"]["date"]).astimezone(timezone.utc).date()
                if window <= day <= end:
                    dates.append(day)
            if page * 100 >= result["total_count"]:
                for day in dates:
                    counts[day] += 1
                break
            page += 1
    return counts


def render_activity(repositories, releases, authored_prs, now=None, metrics=None, preserve_telemetry=False):
    now = now or datetime.now(timezone.utc)
    stable = [
        release for repo, release in releases
        if repo == RELEASE_PROJECT and not release.get("prerelease")
    ]
    stable.sort(key=lambda item: item["published_at"], reverse=True)

    if metrics is not None or preserve_telemetry:
        lines = [
            "![Development telemetry: commits, pull requests, releases, streaks, and 90-day daily commit chart](assets/github-stats.svg)",
        ]
    else:
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
        if re.match(r"(?i)^(sync token-lean pack|chore(?:\([^)]*\))?:|docs: refresh|plan\s*-\s*process:)", title):
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

    if metrics is not None or preserve_telemetry:
        lines += [
            "",
            "<sub>Statistics combine public and private activity visible to the refresh account. "
            "Commits use GitHub's default-branch search; repository and release counts cover "
            "owned repositories; streaks and the daily average use the last 365 UTC days.</sub>",
        ]
    else:
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
    token = os.getenv("PROFILE_TOTALS_TOKEN", "").strip()
    metrics = None
    if token:
        private_repos, private_releases = owned_private_counts(token)
        today = datetime.now(timezone.utc).date()
        daily = combined_commit_days(today, token)
        totals = {
            "commits": search_total("commit", token),
            "pull_requests": search_total("pr", token),
            "issues": search_total("issue", token),
        }
        metrics = metrics_from_data(
            totals, daily, len(repositories) + private_repos, len(releases) + private_releases, today
        )
        STATS_PATH.write_text(stats_svg(metrics), encoding="utf-8")

    rendered = render_activity(
        repositories,
        releases,
        prs,
        metrics=metrics,
        preserve_telemetry=STATS_PATH.exists(),
    )
    updated = replace_section(original, rendered)
    if updated != original:
        README.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
