"""Render GitHub totals and combined daily commit activity."""

from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

OWNER = "AaronPG095"
STATS_PATH = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"


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
        ("Issues opened", f'{metrics["issues"]:,}', "Public + private, all time"),
        ("Repositories", f'{metrics["repos"]:,}', "Public + private, owned"),
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
    shapes.append('<text x="28" y="338" font-size="18" fill="#e8f1f5">Daily commits · last 90 days</text>')
    if days:
        shapes.append(f'<text x="28" y="437" font-size="14" fill="#a7bdc6">{days[0][0]}</text>')
        shapes.append(
            f'<text x="1252" y="437" text-anchor="end" font-size="14" fill="#a7bdc6">{days[-1][0]}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="475" '
        'viewBox="0 0 1280 475" role="img" aria-labelledby="title desc">\n'
        '<title id="title">GitHub development statistics</title>\n'
        '<desc id="desc">Public and private commits, pull requests, issues, repositories and releases; '
        '365-day daily commit averages and streaks. See README for details.</desc>\n'
        '<rect width="1280" height="475" rx="13" fill="#111e29"/>\n'
        '<path d="M28 30H91" stroke="#63c9c5" stroke-width="3"/>\n'
        '<text x="28" y="66" font-family="Segoe UI, Arial, sans-serif" font-size="25" '
        'font-weight="650" fill="#e8f1f5">Development statistics</text>\n'
        '<g font-family="Segoe UI, Arial, sans-serif">\n'
        + "\n".join(shapes)
        + '\n<text x="28" y="459" font-size="12" fill="#9db0bb">'
        'Counts combine public and private activity. Daily measures use UTC.'
        '</text>\n</g>\n</svg>\n'
    )
