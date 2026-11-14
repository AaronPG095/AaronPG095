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


def monthly_totals(daily, today, months=12):
    """Aggregate daily counts into the trailing calendar months ending at today's month."""
    end_index = today.year * 12 + (today.month - 1)
    buckets = []
    for offset in range(months - 1, -1, -1):
        ym = end_index - offset
        year, month = divmod(ym, 12)
        month += 1
        total = 0
        active = 0
        for day, count in daily.items():
            if day.year == year and day.month == month:
                total += count
                if count > 0:
                    active += 1
        buckets.append({
            "year": year,
            "month": month,
            "label": f"{datetime(year, month, 1):%b '%y}",
            "full_label": f"{datetime(year, month, 1):%b %Y}",
            "count": total,
            "active_days": active,
        })
    return buckets


def nice_step(peak, ticks=4):
    """Choose a clean, round Y-axis step covering the peak value."""
    raw = max(1, (peak + ticks - 1) // ticks)
    for unit in (1, 5, 10, 25, 50, 100, 250, 500, 1000):
        if raw <= unit * 5:
            return ((raw + unit - 1) // unit) * unit
    return ((raw + 999) // 1000) * 1000


def metrics_from_data(totals, daily, repos, releases, today=None):
    today = today or datetime.now(timezone.utc).date()
    start_365 = today - timedelta(days=364)
    window_365 = {
        start_365 + timedelta(days=i): daily.get(start_365 + timedelta(days=i), 0)
        for i in range(365)
    }
    current, best = streaks(window_365, today)
    values = list(window_365.values())
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
        "monthly": monthly_totals(daily, today, months=12),
    }


def stats_svg(metrics):
    """Render the unified telemetry card (KPIs + 12-month contribution chart)."""
    months = metrics["monthly"]
    peak = max((m["count"] for m in months), default=0)
    step = nice_step(peak)
    baseline = 312
    scale = 28 / step
    chart_left = 64
    chart_right = 832
    chart_width = chart_right - chart_left
    slot_width = chart_width / max(len(months), 1)
    bar_width = min(38.0, slot_width * 0.58)
    total_12m = sum(m["count"] for m in months)
    span_label = (
        f"{months[0]['full_label']} – {months[-1]['full_label']}"
        if months else "Last 12 months"
    )

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
        y = baseline - tick * 28
        shapes.append(
            f'<path d="M{chart_left} {y}H{chart_right}" stroke="#213342"/>'
            f'<text x="{chart_left - 8}" y="{y + 4}" text-anchor="end">{tick * step:,}</text>'
        )
    for index, item in enumerate(months):
        count = item["count"]
        center_x = chart_left + index * slot_width + slot_width / 2
        bar_x = center_x - bar_width / 2
        active = item["active_days"]
        day_unit = "day" if active == 1 else "days"
        contrib_unit = "contribution" if count == 1 else "contributions"
        if count:
            height = max(2.0, count * scale)
            bar_y = baseline - height
            shapes.append(
                f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" '
                f'width="{bar_width:.2f}" height="{height:.2f}" rx="4" fill="#5cc8c5">'
                f'<title>{item["full_label"]}: {count:,} {contrib_unit} ({active} active {day_unit})</title></rect>'
            )
            label_y = max(188.0, bar_y - 6)
            shapes.append(
                f'<text x="{center_x:.2f}" y="{label_y:.2f}" text-anchor="middle" '
                f'font-size="11.5" font-weight="600" fill="#ecf3f5">{count:,}</text>'
            )
        else:
            shapes.append(
                f'<text x="{center_x:.2f}" y="{baseline - 6}" text-anchor="middle" '
                f'font-size="11" fill="#637b86">0</text>'
            )
        shapes.append(
            f'<text x="{center_x:.2f}" y="334" text-anchor="middle">{item["label"]}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="860" height="360" '
        'viewBox="0 0 860 360" role="img" aria-labelledby="title desc">\n'
        '<title id="title">Development telemetry and 12-month contributions</title>\n'
        '<desc id="desc">Combined public and private GitHub totals, streaks, and 12-month contribution totals.</desc>\n'
        '<rect width="860" height="360" rx="12" fill="#101b26" stroke="#213342" stroke-width="1.5"/>\n'
        '<g font-family="Segoe UI, Arial, sans-serif">\n'
        '<path d="M28 24H76" stroke="#5cc8c5" stroke-width="3"/>\n'
        '<text x="28" y="48" font-size="20" font-weight="650" fill="#ecf3f5">Development telemetry</text>\n'
        f'<text x="832" y="48" font-size="13" fill="#91aaaf" text-anchor="end">'
        f'Updated {metrics["updated"]:%d %b %Y} (UTC)</text>\n'
        + "\n".join(kpi_svg)
        + f'\n<text x="28" y="170" font-size="14" font-weight="600" fill="#b8cbd0">'
        f'Monthly contributions · {span_label}</text>\n'
        f'<text x="832" y="170" font-size="12" fill="#91aaaf" text-anchor="end">'
        f'12m total: {total_12m:,} · 365d peak: {metrics["peak_day_365"]:,}/day</text>\n'
        '<g font-size="11.5" fill="#91aaaf">\n'
        + "\n".join(shapes)
        + "\n</g>\n</g>\n</svg>\n"
    )
