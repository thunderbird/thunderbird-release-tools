# Thunderbird releases on schedule

How often do Thunderbird desktop releases ship on the day they were scheduled?

`on-schedule.py` compares scheduled dates from the public Thunderbird
release calendar with dates that releases actually shipped, and generates a
report.

The report is published on the
[Thunderbird Release Docs](https://github.com/thunderbird/thunderbird-release-docs)
site, which regenerates it daily.

## Usage

Run it as a `tb-release` subcommand (see the [repository README](../../README.md)
to install `tb-release`):

```sh
tb-release on-schedule
```

This writes two files to the current directory:

- `on-schedule.png`: the graph
- `on-schedule.html`: a page with the graph and a table of every release, where
  each scheduled date links to its calendar event and each actual date to its
  product-details record. It also lists shipped releases missing from the calendar.

| Option | Effect |
|---|---|
| `--start-date`, `--end-date` | Only releases scheduled in this range (`YYYY-MM-DD`, inclusive) |
| `--missing` | List shipped releases that aren't on the calendar |
| `--timezone` | Time zone for ship dates, e.g. `UTC` (default `America/New_York`) |
| `--jekyll` | Write `on-schedule.html` as a page for a Jekyll site (for publishing to thunderbird-release-docs) |

## Data sources

- Scheduled dates: [Thunderbird release calendar](https://calendar.google.com/calendar/ical/c_f7b7f2cea6f65593ef05afaf2abfcfb48f87e25794468cd4a19d16495d17b6d1%40group.calendar.google.com/public/basic.ics)
- Actual dates: the time each release shipped, from [product-details](https://product-details.mozilla.org/1.0/thunderbird.json)

## Method

- **Scheduled releases** are calendar events like `Thunderbird 160.0b1` or
  `Thunderbird 153.6.0esr`. Merge, freeze, review and build events are ignored.
  If a version appears more than once, the most recently modified event wins.
- **Channels:** `bN` is Beta, `x.0` and `x.0.y` are Release, everything else
  (including `x.0esr` and `x.0.yesr`, e.g. `140.0esr`) is ESR.
- **Time zone:** the actual date is the ship time in US Eastern
  time, since many releases ship in the US evening, which is already the next
  day in UTC. Use `--timezone` to change it.

## Caveats

- Only releases that are both on the calendar and shipped are counted.
  Scheduled releases that never shipped, and shipped releases missing from the
  calendar (see `--missing`), are left out.
