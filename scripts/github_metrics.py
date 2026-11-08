"""Render GitHub totals and public-only daily commit activity."""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

OWNER = "AaronPG095"
STATS_PATH = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"


def graphql(query, token=None):
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to read public contribution statistics")
    req = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "AaronPG095-public-profile",
        },
        method="POST",
    )
    with urlopen(req, timeout=35) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError("GitHub GraphQL query failed: " + str(payload["errors"])[:500])
    data = payload.get("data", {})
    if not data.get("user"):
        raise RuntimeError("GitHub user contributions not available")
    return data["user"]


def iso_start(day):
    return day.isoformat() + "T00:00:00Z"


def iso_end(day):
    return day.isoformat() + "T23:59:59Z"


def public_commit_days(start, today):
    """Count public GitHub commit contributions by UTC date."""
    counts = defaultdict(int)
    window = start
    while window <= today:
        last = min(today, window + timedelta(days=89))
        query = (
            f'query {{ user(login:"{OWNER}") {{ '
            f'contributionsCollection(from:"{iso_start(window)}",to:"{iso_end(last)}") {{ '
            'commitContributionsByRepository(maxRepositories:100) { '
            'repository { visibility } '
            'contributions(first:100) { '
            'pageInfo { hasNextPage } '
            'nodes { occurredAt commitCount isRestricted } '
            '} } } } }'
        )
        collection = graphql(query)["contributionsCollection"]
        entries = collection["commitContributionsByRepository"]
        if len(entries) >= 100:
            raise RuntimeError("Commit repository limit reached; refusing partial totals")
        for entry in entries:
            if entry["repository"]["visibility"] != "PUBLIC":
                continue
            if entry["contributions"]["pageInfo"]["hasNextPage"]:
                raise RuntimeError("Commit contribution limit reached; refusing partial totals")
            for item in entry["contributions"]["nodes"]:
                if not item or item["isRestricted"]:
                    continue
                day = datetime.fromisoformat(item["occurredAt"].replace("Z", "+00:00")).date()
                if not window <= day <= last:
                    raise ValueError("Contribution date fell outside the requested window")
                counts[day] += item["commitCount"]
        window = last + timedelta(days=1)
    return counts


def total_commits(start, today, token):
    """Sum GitHub-counted commits visible to the authenticated account."""
    total = 0
    while start <= today:
        end = min(today, date(start.year, 12, 31))
        query = (
            f'query {{ user(login:"{OWNER}") {{ '
            f'contributionsCollection(from:"{iso_start(start)}",to:"{iso_end(end)}") {{ '
            'totalCommitContributions } } }'
        )
        total += graphql(query, token)["contributionsCollection"]["totalCommitContributions"]
        start = end + timedelta(days=1)
    return total


def streaks(daily, today):
    active = {day for day, count in daily.items() if count > 0}
    longest = run = 0
    for day in sorted(daily):
        run = run + 1 if day in active else 0
        longest = max(longest, run)

    # Today is not complete; yesterday can still sustain the current streak.
    cursor = today if today in active else today - timedelta(days=1)
    current = 0
    while cursor in active:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def metrics_from_data(totals, daily, repos, releases, today=None):
    today = today or datetime.now(timezone.utc).date()
    current, best = streaks(daily, today)
    values = list(daily.values())
    return {
        **totals,
        "repos": repos,
        "releases": releases,
        "current_streak": current,
        "longest_streak_365": best,
        "average_day_365": sum(values) / 365,
        "peak_day_365": max(values, default=0),
        "active_days_365": sum(x > 0 for x in values),
        "recent_days": list(sorted(daily.items()))[-90:],
    }


def stats_svg(metrics):
    """Render a compact, dependency-free, ten-metric SVG panel."""
    items = [
        ("Commits", f'{metrics["commits"]:,}', "Public + private, all time"),
        ("Pull requests", f'{metrics["pull_requests"]:,}', "Public + private, all time"),
        ("Issues opened", f'{metrics["issues"]:,}', "Public, all time"),
        ("Repositories", f'{metrics["repos"]:,}', "Public, owned"),
        ("Releases", f'{metrics["releases"]:,}', "Published, owned"),
        ("Current streak", f'{metrics["current_streak"]:,} days', "Last 365 days"),
        ("Longest streak", f'{metrics["longest_streak_365"]:,} days', "Last 365 days"),
        ("Average per day", f'{metrics["average_day_365"]:.1f}', "Commits, last 365 days"),
        ("Most in a day", f'{metrics["peak_day_365"]:,}', "Commits, last 365 days"),
        ("Active days", f'{metrics["active_days_365"]:,}', "Last 365 days"),
    ]
    shapes = []
    for index, (label, value, note) in enumerate(items):
        row, col = divmod(index, 5)
        x, y = 28 + col * 245, 86 + row * 116
        shapes.extend([
            f'<rect x="{x}" y="{y}" width="231" height="103" rx="9" fill="#192936" stroke="#304454"/>',
            f'<text x="{x+15}" y="{y+24}" font-size="14" fill="#a7bdc6">{escape(label)}</text>',
            f'<text x="{x+15}" y="{y+63}" font-size="31" font-weight="650" fill="#edf5f8">{escape(value)}</text>',
            f'<text x="{x+15}" y="{y+85}" font-size="12" fill="#88a5ac">{escape(note)}</text>',
        ])
    days = metrics["recent_days"]
    peak = max(1, *(count for _, count in days))
    for index, (day, count) in enumerate(days):
        height = max(2, round(56 * count / peak))
        color = "#63c9c5" if count else "#304454"
        shapes.append(
            f'<rect x="{28 + index * 13.6:.1f}" y="{414 - height}" width="10" '
            f'height="{height}" fill="{color}"><title>{day}: {count} commits</title></rect>'
        )
    shapes.append('<text x="28" y="338" font-size="18" fill="#e8f1f5">Daily public commits · last 90 days</text>')
    if days:
        shapes.append(f'<text x="28" y="437" font-size="14" fill="#a7bdc6">{days[0][0]}</text>')
        shapes.append(
            f'<text x="1252" y="437" text-anchor="end" font-size="14" fill="#a7bdc6">{days[-1][0]}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="475" '
        'viewBox="0 0 1280 475" role="img" aria-labelledby="title desc">\n'
        '<title id="title">GitHub development statistics</title>\n'
        '<desc id="desc">All-time commits and pull requests, plus public issues, repositories and releases; '
        '365-day daily commit averages and streaks. See README for details.</desc>\n'
        '<rect width="1280" height="475" rx="13" fill="#111e29"/>\n'
        '<path d="M28 30H91" stroke="#63c9c5" stroke-width="3"/>\n'
        '<text x="28" y="66" font-family="Segoe UI, Arial, sans-serif" font-size="25" '
        'font-weight="650" fill="#e8f1f5">Development statistics</text>\n'
        '<g font-family="Segoe UI, Arial, sans-serif">\n'
        + "\n".join(shapes)
        + '\n<text x="28" y="459" font-size="12" fill="#9db0bb">'
        'Daily measures use public commits and UTC dates.'
        '</text>\n</g>\n</svg>\n'
    )


def collect_metrics(repositories, releases, search_total, today=None):
    today = today or datetime.now(timezone.utc).date()
    user = graphql(f'query {{ user(login:"{OWNER}") {{ createdAt }} }}')
    start = date.fromisoformat(user["createdAt"][:10])
    token = os.environ["PROFILE_TOTALS_TOKEN"]
    counts = public_commit_days(today - timedelta(days=364), today)
    daily = {today - timedelta(days=i): counts.get(today - timedelta(days=i), 0) for i in range(364, -1, -1)}
    totals = {
        "commits": total_commits(start, today, token),
        "pull_requests": search_total("pr", token),
        "issues": search_total("issue"),
    }
    return metrics_from_data(totals, daily, len(repositories), len(releases), today)
