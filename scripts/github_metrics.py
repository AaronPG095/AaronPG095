"""Render GitHub totals and combined daily commit activity."""

from datetime import datetime, timedelta, timezone
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
        "updated": today,
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
    """Render the unified telemetry card (KPIs + 90-day daily commit chart)."""
    days = metrics["recent_days"]
    peak = max((count for _, count in days), default=0)
    step = max(1, (peak + 3) // 4)
    baseline = 316
    scale = 30 / step
    chart_left = 64
    chart_right = 832
    chart_width = chart_right - chart_left
    spacing = chart_width / max(len(days), 1)

    cards = [
        ("COMMITS", f"{metrics['commits']:,}", f"{metrics['average_day_365']:.1f}/day · 365d avg"),
        ("PULL REQUESTS", f"{metrics['pull_requests']:,}", f"{metrics['repos']:,} owned repos"),
        ("RELEASES", f"{metrics['releases']:,}", "Public &amp; private"),
        (
            "STREAK",
            f"{metrics['current_streak']}d current",
            f"{metrics['longest_streak_365']}d best · {metrics['active_days_365']}d active",
        ),
    ]
    kpi_svg = []
    for idx, (label, value, sub) in enumerate(cards):
        cx = 28 + idx * 204
        kpi_svg.append(
            f'<rect x="{cx}" y="68" width="192" height="70" rx="8" fill="#152432" stroke="#243848"/>\n'
            f'<text x="{cx + 16}" y="88" font-size="11" font-weight="600" letter-spacing="0.9" fill="#91aaaf">{label}</text>\n'
            f'<text x="{cx + 16}" y="113" font-size="21" font-weight="650" fill="#ecf3f5">{value}</text>\n'
            f'<text x="{cx + 16}" y="130" font-size="11.5" fill="#91aaaf">{sub}</text>'
        )

    shapes = []
    for tick in range(5):
        y = baseline - tick * 30
        shapes.append(
            f'<path d="M{chart_left} {y}H{chart_right}" stroke="#213342"/>'
            f'<text x="{chart_left - 8}" y="{y + 4}" text-anchor="end">{tick * step}</text>'
        )
    for index, (day, count) in enumerate(days):
        if count:
            height = count * scale
            unit = "commit" if count == 1 else "commits"
            shapes.append(
                f'<rect x="{chart_left + index * spacing:.2f}" y="{baseline - height:.2f}" '
                f'width="{spacing * 0.72:.2f}" height="{height:.2f}" rx="1.5" fill="#5cc8c5">'
                f'<title>{day}: {count} {unit}</title></rect>'
            )
    if days:
        shapes.append(f'<text x="{chart_left}" y="338">{days[0][0]:%d %b}</text>')
        shapes.append(
            f'<text x="{chart_left + chart_width // 2}" y="338" text-anchor="middle">'
            f'{days[len(days) // 2][0]:%d %b}</text>'
        )
        shapes.append(f'<text x="{chart_right}" y="338" text-anchor="end">{days[-1][0]:%d %b}</text>')

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="860" height="360" '
        'viewBox="0 0 860 360" role="img" aria-labelledby="title desc">\n'
        '<title id="title">Development telemetry and daily commits</title>\n'
        '<desc id="desc">Combined public and private GitHub totals, streaks, and 90-day commit activity.</desc>\n'
        '<rect width="860" height="360" rx="12" fill="#101b26" stroke="#213342" stroke-width="1.5"/>\n'
        '<g font-family="Segoe UI, Arial, sans-serif">\n'
        '<path d="M28 24H76" stroke="#5cc8c5" stroke-width="3"/>\n'
        '<text x="28" y="48" font-size="20" font-weight="650" fill="#ecf3f5">Development telemetry</text>\n'
        f'<text x="832" y="48" font-size="13" fill="#91aaaf" text-anchor="end">'
        f'Updated {metrics["updated"]:%d %b %Y} (UTC)</text>\n'
        + "\n".join(kpi_svg)
        + '\n<text x="28" y="170" font-size="14" font-weight="600" fill="#b8cbd0">'
        'Daily commits · last 90 days</text>\n'
        f'<text x="832" y="170" font-size="12" fill="#91aaaf" text-anchor="end">'
        f'365d peak: {metrics["peak_day_365"]:,} commits/day</text>\n'
        '<g font-size="12" fill="#91aaaf">\n'
        + "\n".join(shapes)
        + "\n</g>\n</g>\n</svg>\n"
    )
