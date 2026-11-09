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
    """Render the 90-day chart at a size suited to a narrow README."""
    days = metrics["recent_days"]
    peak = max((count for _, count in days), default=0)
    step = max(1, (peak + 3) // 4)
    baseline = 224
    scale = 40 / step
    spacing = 500 / max(len(days), 1)
    shapes = []
    for tick in range(5):
        y = baseline - tick * 40
        shapes.append(
            f'<path d="M54 {y}H554" stroke="#304454"/>'
            f'<text x="46" y="{y + 5}" text-anchor="end">{tick * step}</text>'
        )
    for index, (day, count) in enumerate(days):
        if count:
            height = count * scale
            shapes.append(
                f'<rect x="{54 + index * spacing:.2f}" y="{baseline - height:.2f}" '
                f'width="{spacing * 0.78:.2f}" height="{height:.2f}" fill="#63c9c5">'
                f'<title>{day}: {count} commits</title></rect>'
            )
    if days:
        shapes.append(f'<text x="54" y="252">{days[0][0]:%d %b}</text>')
        shapes.append(f'<text x="554" y="252" text-anchor="end">{days[-1][0]:%d %b}</text>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="580" height="274" '
        'viewBox="0 0 580 274" role="img" aria-labelledby="title desc">\n'
        '<title id="title">Daily commits over the last 90 days</title>\n'
        '<desc id="desc">Combined public and private commit counts by UTC date.</desc>\n'
        '<rect width="580" height="274" rx="12" fill="#111e29"/>\n'
        '<g font-family="Segoe UI, Arial, sans-serif" font-size="17" fill="#a7bdc6">\n'
        '<text x="24" y="36" font-size="23" fill="#e8f1f5">Daily commits · last 90 days</text>\n'
        + "\n".join(shapes)
        + "\n</g>\n</svg>\n"
    )
