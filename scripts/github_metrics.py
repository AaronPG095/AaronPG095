"""Generate a public-only, GitHub-counted contribution statistics panel.

Uses GitHub GraphQL with the workflow's repository-scoped GITHUB_TOKEN.
Private/internal contributions require additional user scopes; never grant them.
Counts reflect GitHub contribution rules, not all Git objects on every branch.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

OWNER = "AaronPG095"
STATS_PATH = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"


def graphql(query):
    token = os.environ.get("GITHUB_TOKEN")
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


def periods(year):
    """Split each year to stay safely below the API's one-year span limit."""
    jan = date(year, 1, 1)
    jul = date(year, 7, 1)
    dec = date(year, 12, 31)
    return ((jan, jul - timedelta(days=1)), (jul, dec))


def all_time_totals():
    years = graphql(f'query {{ user(login:"{OWNER}") {{ contributionsCollection {{ contributionYears }} }} }}')[
        "contributionsCollection"
    ]["contributionYears"]
    current_year = datetime.now(timezone.utc).year
    years = sorted({year for year in years if 2008 <= year <= current_year})
    if not years:
        raise ValueError("No contribution years found; keeping existing dashboard")

    fields = []
    for year in years:
        for part, (start, end) in enumerate(periods(year)):
            fields.append(
                f'y{year}_{part}: contributionsCollection(from:"{iso_start(start)}", '
                f'to:"{iso_end(end)}") '
                '{ totalCommitContributions totalPullRequestContributions totalIssueContributions }'
            )
    totals = {"commits": 0, "pull_requests": 0, "issues": 0}
    # Bound each GraphQL request to 8 half-year intervals.
    for offset in range(0, len(fields), 8):
        query = f'query {{ user(login:"{OWNER}") {{ ' + " ".join(fields[offset:offset + 8]) + " } }"
        result = graphql(query)
        for value in result.values():
            totals["commits"] += value["totalCommitContributions"]
            totals["pull_requests"] += value["totalPullRequestContributions"]
            totals["issues"] += value["totalIssueContributions"]
    return totals


def daily_public_commits(today=None):
    """Retrieve commit contributions per UTC date for the trailing 365 calendar days."""
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    counts = defaultdict(int)
    window = start

    # 90-day segments avoid 100-node-per-repository pagination.
    while window <= today:
        last = min(today, window + timedelta(days=89))
        query = (
            f'query {{ user(login:"{OWNER}") {{ '
            f'contributionsCollection(from:"{iso_start(window)}",to:"{iso_end(last)}") {{ '
            'commitContributionsByRepository(maxRepositories:100) { '
            'repository { nameWithOwner isPrivate } '
            'contributions(first:100) { '
            'pageInfo { hasNextPage } '
            'nodes { occurredAt commitCount isRestricted } '
            '} } } } }'
        )
        response = graphql(query)
        entries = response["contributionsCollection"]["commitContributionsByRepository"]
        for entry in entries:
            repository = entry["repository"]
            if repository["isPrivate"]:
                continue
            if entry["contributions"]["pageInfo"]["hasNextPage"]:
                raise RuntimeError("Unexpected commit contribution pagination; refusing partial totals")
            for item in entry["contributions"]["nodes"]:
                if not item or item["isRestricted"]:
                    continue
                day = datetime.fromisoformat(item["occurredAt"].replace("Z", "+00:00")).date()
                if not (window <= day <= last):
                    raise ValueError("Contribution date fell outside the requested window")
                counts[day] += item["commitCount"]
        window = last + timedelta(days=1)

    return {start + timedelta(days=i): counts[start + timedelta(days=i)] for i in range(365)}


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
    }


def stats_svg(metrics):
    """Render a compact, dependency-free, ten-metric SVG panel."""
    items = [
        ("Public commits", f'{metrics["commits"]:,}', "GitHub-counted, all time"),
        ("Pull requests", f'{metrics["pull_requests"]:,}', "Public, all time"),
        ("Issues opened", f'{metrics["issues"]:,}', "Public, all time"),
        ("Repositories", f'{metrics["repos"]:,}', "Public, owned"),
        ("Releases", f'{metrics["releases"]:,}', "Published, owned"),
        ("Current streak", f'{metrics["current_streak"]:,} days', "Commit days"),
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
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="355" '
        'viewBox="0 0 1280 355" role="img" aria-labelledby="title desc">\n'
        '<title id="title">Public GitHub development statistics</title>\n'
        '<desc id="desc">All-time public commits, pull requests, issues, repositories and releases; '
        '365-day daily commit averages and streaks. See README for details.</desc>\n'
        '<rect width="1280" height="355" rx="13" fill="#111e29"/>\n'
        '<path d="M28 30H91" stroke="#63c9c5" stroke-width="3"/>\n'
        '<text x="28" y="66" font-family="Segoe UI, Arial, sans-serif" font-size="25" '
        'font-weight="650" fill="#e8f1f5">Development statistics</text>\n'
        '<g font-family="Segoe UI, Arial, sans-serif">\n'
        + "\n".join(shapes)
        + '\n<text x="28" y="339" font-size="12" fill="#9db0bb">'
        'Public GitHub contribution data. Daily measures use UTC; statistics refresh weekly.'
        '</text>\n</g>\n</svg>\n'
    )


def collect_metrics(repositories, releases, today=None):
    today = today or datetime.now(timezone.utc).date()
    totals = all_time_totals()
    daily = daily_public_commits(today)
    return metrics_from_data(totals, daily, len(repositories), len(releases), today)
