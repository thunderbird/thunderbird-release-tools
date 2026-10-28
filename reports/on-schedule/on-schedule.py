#!/usr/bin/env python3
"""Compare scheduled Thunderbird release dates (public Google calendar) with
actual release dates, graph the on-schedule percentage, and write an HTML page
with the graph and every release, each date linked to its source.

Actual dates are the date of the ship time in Mozilla's product-details, in
--timezone (US Eastern by default)."""

import argparse
import base64
import concurrent.futures
import html
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CAL_ID = ("c_f7b7f2cea6f65593ef05afaf2abfcfb48f87e25794468cd4a19d16495d17b6d1"
          "@group.calendar.google.com")
CAL_URL = ("https://calendar.google.com/calendar/ical/"
           f"{urllib.parse.quote(CAL_ID)}/public/basic.ics")
PD_URL = "https://product-details.mozilla.org/1.0"
RELEASES_URL = f"{PD_URL}/thunderbird.json"
DEFAULT_TZ = "America/New_York"
OUT = "on-schedule.png"
HTML_OUT = "on-schedule.html"

RELEASE_RE = re.compile(
    r"^Thunderbird (\d+\.\d+(?:\.\d+)?(?:b\d+)?(?:esr)?)"
    r"(?:\s+ship|\s*\([^)]*\))?\s*$"
)

CHANNELS = [
    ("Beta", "#105bbc"),
    ("Release", "#ea580c"),
    ("ESR", "#0a929d"),
]
TEXT, TEXT2, GRID, SURFACE = "#1a1838", "#52507c", "#e4e4e7", "#fafafa"
TITLE = "Thunderbird desktop releases shipped on schedule"
YEARLY = "#71717a"


def fetch(url):
    """Return the body of url as text; raise on any HTTP or network error."""
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8")


def parse_ics_calendar(text):
    """Parse an iCalendar feed into a list of events.

    Args:
        text: The whole .ics feed.

    Returns:
        A list with one dict per VEVENT, mapping property name to its raw
        value, e.g. {"SUMMARY": "Thunderbird 160.0b1", "DTSTART": "20261110",
        "UID": ...}.
    """
    lines = []
    # unfold lines (ie. lines > 75 bytes are folded into the next line)
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    events, cur = [], None
    # build events dict
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name = key.split(";", 1)[0]
            cur.setdefault(name, value)
    return events


def ics_date(value):
    """Return the date of an iCalendar DATE or DATE-TIME value.

    Args:
        value: e.g. "20261110" or "20261110T150000Z"; any time is ignored.

    Returns:
        A date, e.g. date(2026, 11, 10).
    """
    v = value[:8]
    return date(int(v[:4]), int(v[4:6]), int(v[6:8]))


def calendar_link(uid, day):
    """Return a link to a calendar event.

    Events created in Google Calendar have a UID it can link to directly; for
    others (created by other clients), link to the public calendar's agenda
    for that day.

    Args:
        uid: The event's UID, e.g. "...@google.com", or "" if it has none.
        day: The event's date.

    Returns:
        The URL.
    """
    if uid.endswith("@google.com"):
        eid = f"{uid.removesuffix('@google.com')} {CAL_ID}"
        eid = base64.urlsafe_b64encode(eid.encode()).decode().rstrip("=")
        return f"https://calendar.google.com/calendar/event?eid={eid}"
    days = f"{day:%Y%m%d}/{day + timedelta(days=1):%Y%m%d}"
    return ("https://calendar.google.com/calendar/embed?"
            + urllib.parse.urlencode({"src": CAL_ID, "mode": "AGENDA",
                                      "dates": days}))


def scheduled_releases(events):
    """Return the scheduled date of each release on the calendar.

    If a version appears more than once, the most recently modified event
    wins.

    Args:
        events: Events from parse_ics_calendar.

    Returns:
        {version: (scheduled date, calendar link)}, versions normalized, e.g.
        {"160.0b1": (date(2026, 11, 10), "https://calendar.google.com/...")}.
    """
    found = {}
    for ev in events:
        m = RELEASE_RE.match(ev.get("SUMMARY", "").strip())
        if not m:
            continue
        version = normalize(m.group(1))
        modified = ev.get("LAST-MODIFIED", "")
        if version not in found or modified > found[version][1]:
            found[version] = (ev, modified)
    out = {}
    for v, (ev, _) in found.items():
        day = ics_date(ev["DTSTART"])
        out[v] = (day, calendar_link(ev.get("UID", ""), day))
    return out


def normalize(version):
    """Return a version in the form both data sources are matched on.

    Keep the esr suffix only where it tells channels apart: 140.0 is a
    Release build and 140.0esr an ESR build, but x.y.z with y >= 1 is always
    ESR, and older ones (e.g. 115.6.0) often have no suffix.

    Args:
        version: e.g. "140.0esr" or "115.6.0esr".

    Returns:
        e.g. "140.0esr" (unchanged) or "115.6.0".
    """
    base = version.removesuffix("esr")
    return version if base.split(".")[1] == "0" else base


def actual_releases(releases, tz, sched):
    """Return when each release actually shipped.

    thunderbird.json only has the UTC date each release shipped; the time is
    in a file per release, so fetch those for versions on the calendar or
    shipped since its first event, a day early to allow for the time zone.
    If a version shipped more than once, the earliest counts.

    Args:
        releases: The "releases" object of product-details' thunderbird.json.
        tz: ZoneInfo to give ship dates in.
        sched: {version: scheduled date} from the calendar.

    Returns:
        {version: (date shipped, product-details link)}, versions normalized,
        e.g. {"159.0": (date(2026, 10, 27), "https://product-details.mozilla
        .org/1.0/l10n/Thunderbird-159.0-build1.json")}.
    """
    # pick the releases to look up
    since = min(sched.values()) - timedelta(days=1)
    names = {}
    for key, rel in releases.items():
        version = key.removeprefix("thunderbird-")
        if rel["date"] and (normalize(version) in sched
                            or date.fromisoformat(rel["date"]) >= since):
            names[f"Thunderbird-{version}-build{rel['build_number']}"] = version

    def shipped(name):
        url = f"{PD_URL}/l10n/{name}.json"
        return name, url, json.loads(fetch(url))["shippedAt"]

    # fetch earliest ship date/url for releases in parallel
    out = {}
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        for name, url, at in pool.map(shipped, names):
            version = normalize(names[name])
            day = datetime.fromisoformat(at).astimezone(tz).date()
            if version not in out or day < out[version][0]:
                out[version] = (day, url)
    return out


def channel(version):
    """Return "Beta", "Release" or "ESR" for a normalized version."""
    if "b" in version:
        return "Beta"
    # x.0 and x.0.y are Release builds, unless suffixed esr (e.g. 140.0esr);
    # x.y.z (y >= 1) are ESR.
    if version.endswith("esr") or version.split(".")[1] != "0":
        return "ESR"
    return "Release"


def quarter(d):
    """Return the quarter a date falls in, e.g. "2026-Q4"."""
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def find_missing(sched, actual, start, end):
    """Return releases that shipped but have no event on the calendar.

    Releases go back to 2004, so with no start date, only look from the
    first calendar event.

    Args:
        sched: {version: scheduled date} for every release on the calendar.
        actual: {version: date shipped}.
        start: Only releases shipped on or after this date, or None.
        end: Only releases shipped on or before this date, or None.

    Returns:
        A sorted list of (date shipped, version).
    """
    start = start or min(sched.values())
    return sorted((d, v) for v, d in actual.items()
                  if v not in sched and d >= start
                  and (end is None or d <= end))


def plot(rows, out, tz_label):
    """Write the graph to a PNG file.

    Args:
        rows: (version, channel, scheduled date, actual date, days late) for
            each release that is both scheduled and shipped.
        out: Path of the PNG to write.
        tz_label: Name of the time zone of actual dates, for the footnote.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    quarters = sorted({quarter(r[2]) for r in rows})
    years = sorted({r[2].year for r in rows})
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID,
                         "xtick.color": TEXT2, "ytick.color": TEXT2})
    fig, (quarter_ax, year_ax) = plt.subplots(
        2, 1, figsize=(14, 8.6), height_ratios=(3, 1.5), facecolor=SURFACE)

    # Top chart: one line per channel, % on time by scheduled quarter.
    for name, color in CHANNELS:
        on_time, total = Counter(), Counter()  # by quarter
        for _, chan, scheduled, _, days_late in rows:
            if chan == name:
                on_time[quarter(scheduled)] += days_late <= 0
                total[quarter(scheduled)] += 1
        # NaN where a channel had no releases, so the line breaks there.
        pcts = [100 * on_time[q] / total[q] if q in total else float("nan")
                for q in quarters]
        channel_on_time, channel_total = on_time.total(), total.total()
        quarter_ax.plot(
            range(len(quarters)), pcts, color=color, lw=2, marker="o", ms=5,
            markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
            label=f"{name} ({100 * channel_on_time / channel_total:.0f}% "
                  f"of {channel_total})")

    quarter_ax.set_title("Shipped on (or before) the scheduled day",
                         loc="left", color=TEXT, fontsize=11)
    quarter_ax.set_xticks(range(len(quarters)))
    quarter_ax.set_xticklabels(quarters, rotation=45, ha="right")
    quarter_ax.set_xlim(-0.5, len(quarters) - 0.5)
    quarter_ax.legend(loc="lower left", frameon=False, fontsize=9,
                      labelcolor=TEXT2)

    # Yearly chart: share on time across all channels. Pooled over releases, not
    # an average of the quarterly points, so sparse quarters don't count extra.
    pcts, labels = [], []
    for year in years:
        year_days_late = [days_late for _, _, scheduled, _, days_late in rows
                          if scheduled.year == year]
        on_time = sum(days_late <= 0 for days_late in year_days_late)
        pcts.append(100 * on_time / len(year_days_late))
        labels.append(f"{year}\n{len(year_days_late)} releases")

    bars = year_ax.bar(range(len(years)), pcts, width=0.6, color=YEARLY,
                       zorder=3)
    year_ax.bar_label(bars, labels=[f"{p:.0f}%" for p in pcts], padding=3,
                  color=TEXT, fontsize=9)
    year_ax.set_xticks(range(len(years)))
    year_ax.set_xticklabels(labels, fontsize=9)
    year_ax.set_title("By year, all channels", loc="left", color=TEXT,
                  fontsize=10)

    # Style shared by both charts.
    for chart in (quarter_ax, year_ax):
        chart.set_facecolor(SURFACE)
        chart.set_ylim(-3, 110)
        chart.set_yticks(range(0, 101, 20 if chart is quarter_ax else 50))
        chart.yaxis.set_major_formatter(lambda y, _: f"{y:.0f}%")
        chart.grid(axis="y", color=GRID, lw=0.8)
        chart.set_axisbelow(True)
        for side in ("top", "right", "left"):
            chart.spines[side].set_visible(False)
        chart.tick_params(length=0)

    quarter_ax.set_ylabel("Releases on schedule (by scheduled quarter)",
                          color=TEXT2)
    year_ax.set_ylabel("By scheduled year", color=TEXT2)
    fig.text(0.01, 0.005,
             "Scheduled: Thunderbird release calendar. Actual: product-details "
             f"ship time as a {tz_label} date. Versions "
             "scheduled but never shipped are excluded.",
             fontsize=8, color=TEXT2)

    fig.tight_layout(rect=(0, 0.02, 1, 1), h_pad=2)
    fig.savefig(out, dpi=150, facecolor=SURFACE)


PAGE_HEAD = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; color: {text};
         background: {surface}; max-width: 1400px; margin: 2em auto;
         padding: 0 1em; }}
  img {{ width: 100%; height: auto; }}
  p {{ color: {text2}; }}
  table {{ border-collapse: collapse; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 0.2em 1em 0.2em 0; text-align: left; }}
  th {{ border-bottom: 1px solid {grid}; }}
  td.n {{ text-align: right; }}
  a {{ color: inherit; }}
</style>
"""

# With --jekyll: the site's layout supplies the page and styles.
JEKYLL_HEAD = """---
layout: default
title: {title}
---
<style>td.n {{ text-align: right; }}</style>
"""

PAGE_BODY = """<h1>{title}</h1>
<img src="{png}" alt="{title}">
<h2>Releases</h2>
<p>By channel, then scheduled date. Days late: negative is early.</p>
<table>
<tr><th>Version</th><th>Channel</th><th>Scheduled</th><th>Actual</th>
<th>Days late</th></tr>
{rows}
</table>
<h2>Shipped but not on the calendar</h2>
<p>No scheduled date, so not counted above.</p>
<table>
<tr><th>Version</th><th>Channel</th><th>Shipped</th></tr>
{missing}
</table>
<p>Generated {today}</p>
"""


def write_html(out, png, rows, missing, sched_info, actual_info, jekyll=False):
    """Write the HTML page: the graph, then a table of every release.

    Args:
        out: Path of the HTML file to write.
        png: Path of the graph, relative to the page.
        rows: As for plot.
        missing: (date shipped, version) of releases not on the calendar,
            from find_missing.
        sched_info: {version: (scheduled date, calendar link)}.
        actual_info: {version: (date shipped, product-details link)}.
        jekyll: Write front matter for the site's layout instead of a
            standalone page.
    """
    def link(d, url):
        return f'<a href="{html.escape(url)}">{d}</a>'

    order = [c for c, _ in CHANNELS]

    def sort_key(row):
        """Return the sort key for a table row.

        By channel; ESR by version (numerically, so 128.x stays together and
        128.10.0 follows 128.9.0) then date; others by date.
        """
        version, chan, scheduled = row[:3]
        if chan == "ESR":
            version_parts = tuple(
                int(part) for part in version.removesuffix("esr").split("."))
            return (order.index(chan), version_parts, scheduled)
        return (order.index(chan), (), scheduled, version)

    body = [
        f"<tr><td>{v.removesuffix('esr')}</td><td>{ch}</td>"
        f"<td>{link(s, sched_info[v][1])}</td>"
        f"<td>{link(a, actual_info[v][1])}</td>"
        f'<td class="n">{late:+d}</td></tr>'.replace(">+0<", ">0<")
        for v, ch, s, a, late in sorted(rows, key=sort_key)]
    extra = [f"<tr><td>{v.removesuffix('esr')}</td><td>{channel(v)}</td>"
             f"<td>{link(d, actual_info[v][1])}</td></tr>"
             for d, v in missing]
    with open(out, "w", encoding="utf-8") as f:
        f.write(((JEKYLL_HEAD if jekyll else PAGE_HEAD) + PAGE_BODY).format(
            title=TITLE, today=date.today(),
            png=png, rows="\n".join(body), missing="\n".join(extra),
            text=TEXT, text2=TEXT2, grid=GRID, surface=SURFACE))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="only releases scheduled on or after this date")
    ap.add_argument("--end-date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="only releases scheduled on or before this date")
    ap.add_argument("--missing", action="store_true",
                    help="list shipped releases that aren't on the calendar")
    ap.add_argument("--jekyll", action="store_true",
                    help="write the HTML page for a Jekyll site instead of a"
                         "standalone page (for thunderbird-release-docs)")
    ap.add_argument("--timezone", default=DEFAULT_TZ, metavar="ZONE",
                    help="Time zone for actual ship dates, e.g. UTC or "
                         f"Europe/Berlin (default {DEFAULT_TZ})")

    args = ap.parse_args()
    try:
        tz = ZoneInfo(args.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        ap.error(f"unknown time zone: {args.timezone}")
    tz_label = ("US Eastern (EST/EDT)" if args.timezone == DEFAULT_TZ
                else args.timezone)

    sched_info = scheduled_releases(parse_ics_calendar(fetch(CAL_URL)))
    all_sched = {v: d for v, (d, _) in sched_info.items()}
    actual_info = actual_releases(
        json.loads(fetch(RELEASES_URL))["releases"], tz, all_sched)
    actual = {v: d for v, (d, _) in actual_info.items()}
    sched = {v: s for v, s in all_sched.items()
             if (args.start_date is None or s >= args.start_date)
             and (args.end_date is None or s <= args.end_date)}

    rows = []
    for v, s in sched.items():
        if v in actual:
            rows.append((v, channel(v), s, actual[v], (actual[v] - s).days))
    if not rows:
        ap.error("no scheduled releases matched in the given date range")

    unmatched = sorted(v for v, s in sched.items()
                       if v not in actual and s < date.today())
    if unmatched:
        print(f"{len(unmatched)} past scheduled versions never shipped "
              f"(excluded): {', '.join(unmatched)}")

    missing = find_missing(all_sched, actual, args.start_date, args.end_date)
    if args.missing:
        print(f"{len(missing)} shipped releases not on the calendar"
              f"{':' if missing else ''}")
        for d, v in missing:
            print(f"  {v:<10} {channel(v):<7} shipped {d}")

    plot(rows, OUT, tz_label)
    write_html(HTML_OUT, OUT, rows, missing, sched_info, actual_info,
               args.jekyll)
    print(f"wrote {OUT} and {HTML_OUT}")


if __name__ == "__main__":
    main()
