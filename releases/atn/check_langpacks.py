#!/usr/bin/env python3
"""Check the brandShortName in Thunderbird language packs on ATN.

Downloads language packs from addons.thunderbird.net (ATN) and reads
brandShortName from each one's branding/brand.properties, to find locales
whose language packs for a Thunderbird version carry more than one brand
name, or a wrong one.

Examples:
    # list all available locales
    ./check_langpacks.py --list

    # given locale(s), for all available Thunderbird versions
    ./check_langpacks.py --locales de

    # given locale(s), the ATN default version for a specific Thunderbird version
    ./check_langpacks.py --locales de,fr,en-us --version 149

    # all locales, the ATN default version for a specific Thunderbird version
    ./check_langpacks.py --version 149

    # all locales, every version for a specific Thunderbird version, to find
    # locales with more than one brand (slow)
    ./check_langpacks.py --version 149 --all-versions
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ATN_API = "https://addons.thunderbird.net/api/v4"
LANGUAGE_TOOLS_URL = f"{ATN_API}/addons/language-tools/?app=thunderbird&type=language"

BRAND_FILE_RE = re.compile(r"^chrome/[^/]+/locale/branding/brand\.properties$")
BRAND_SHORT_NAME_RE = re.compile(r"brandShortName\s*=\s*(.+)")

# Placeholder "brands" for language packs a brand couldn't be read from.
DOWNLOAD_ERROR = "DOWNLOAD ERROR"
FILE_MISSING = "FILE MISSING"
NOT_FOUND = "NOT FOUND"
INVALID_BRANDS = {DOWNLOAD_ERROR, FILE_MISSING, NOT_FOUND}


class HTTPError(Exception):
    pass


def bust_cache(url):
    """Add a timestamp query parameter so caches between us and ATN don't
    serve stale responses."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != "_t"]
    query.append(("_t", str(int(time.time() * 1000))))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def fetch(url, retries=3, delay=1.0):
    """Fetch url and return the body as bytes, retrying on 429 and 5xx."""
    request = urllib.request.Request(
        bust_cache(url),
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "tb-release",
        },
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            transient = e.code == 429 or e.code >= 500
            if not transient or attempt == retries:
                raise HTTPError(f"HTTP {e.code} for {url}") from None
            wait = delay * attempt
            print(
                f"  [warn] HTTP {e.code}, retrying in {wait * 1000:.0f}ms "
                f"(attempt {attempt}/{retries})...",
                file=sys.stderr,
            )
            time.sleep(wait)


def fetch_json(url):
    return json.loads(fetch(url))


def file_datetime(file):
    """When a language pack file was uploaded to ATN, in UTC, for display:
    its ISO 8601 "created" time (e.g. "2026-03-24T16:19:08Z") with the "T"
    replaced by a space and the "Z" dropped ("2026-03-24 16:19:08")."""
    return file["created"].replace("T", " ").replace("Z", "")


def human_name(addon):
    """The language pack's English name without the "Language Pack" suffix,
    e.g. "Deutsch"."""
    names = addon.get("name") or {}
    raw = names["en-US"] if "en-US" in names else next(iter(names.values()), "")
    return re.sub(r"\s*Language Pack.*$", "", raw or "", flags=re.IGNORECASE).strip()


def fetch_locale_map():
    """Map each target locale (lowercase) to its language pack's slug, and each
    slug to a human-readable name, from the ATN language-tools endpoint. This
    is the authoritative source: each language pack declares exactly which
    locale it targets."""
    data = fetch_json(LANGUAGE_TOOLS_URL)
    locale_map = {}
    human_names = {}
    for addon in data["results"]:
        if not addon.get("target_locale"):
            continue
        locale_map[addon["target_locale"].lower()] = addon["slug"]
        human_names[addon["slug"]] = human_name(addon)
    return locale_map, human_names


def fetch_default_versions(target_major):
    """Map each slug to the ATN-recommended version of its language pack for a
    Thunderbird version, as {version, datetime, url}."""
    data = fetch_json(f"{LANGUAGE_TOOLS_URL}&appversion={target_major}.0")
    defaults = {}
    for addon in data["results"]:
        v = addon.get("current_compatible_version")
        if v:
            defaults[addon["slug"]] = {
                "version": v["version"],
                "datetime": file_datetime(v["files"][0]),
                "url": v["files"][0]["url"],
            }
    return defaults


def iter_versions(slug, target_major):
    """Yield every version of a language pack, or only those for target_major.

    Pages are ordered by upload date, not version number (ESR releases
    interleave), so all pages must be scanned; we can't stop early when
    filtering by major version."""
    url = f"{ATN_API}/addons/addon/{slug}/versions/?page_size=50"
    while url:
        page = fetch_json(url)
        for v in page["results"]:
            if not target_major or v["version"].split(".")[0] == target_major:
                yield v
        url = page.get("next")


def brand_from_xpi(data):
    """Read brandShortName from a language pack's XPI (a ZIP file)."""
    with zipfile.ZipFile(io.BytesIO(data)) as xpi:
        name = next((n for n in xpi.namelist() if BRAND_FILE_RE.match(n)), None)
        if name is None:
            return FILE_MISSING
        text = xpi.read(name).decode("utf-8")
    match = BRAND_SHORT_NAME_RE.search(text)
    return match.group(1).strip() if match else NOT_FOUND


def get_brand(xpi_url):
    """Download a language pack's XPI and return its brandShortName, or
    DOWNLOAD_ERROR if it can't be downloaded. An XPI that isn't a valid ZIP
    file raises zipfile.BadZipFile."""
    try:
        data = fetch(xpi_url)
    except (HTTPError, urllib.error.URLError, OSError) as e:
        print(f"  [error] failed to download {xpi_url}: {e}", file=sys.stderr)
        return DOWNLOAD_ERROR
    return brand_from_xpi(data)


def analyze_locale(slug, target_major):
    """Check every version of a locale's language pack, or only those for
    target_major, printing a row for each as it's checked. Returns the rows,
    as {version, datetime, brand}. Versions without a file are skipped.

    Used for --all-versions, without --version, and when ATN has no default
    version of the language pack for --version."""
    results = []
    for v in iter_versions(slug, target_major):
        files = v.get("files") or []
        if not files or not files[0].get("url"):
            continue
        row = {
            "version": v["version"],
            "datetime": file_datetime(files[0]),
            "brand": get_brand(files[0]["url"]),
        }
        results.append(row)
        print_row(row)
    return results


def print_header():
    print("Version\t\t\t\tDate/Time\t\tbrandShortName")


def print_row(row):
    print(f"{row['version']}\t{row['datetime']}\t{row['brand']}", flush=True)


def summarize(locale, results, default_version):
    """Summarize a locale's rows for the summary: the distinct brands found,
    in the order first seen, leaving out the DOWNLOAD_ERROR, FILE_MISSING and
    NOT_FOUND placeholders, and whether there is more than one.
    default_version is the ATN default label to show, e.g.
    "149.0.20260320.185705 (Thunderbird)" or "N/A"."""
    brands = list(
        dict.fromkeys(r["brand"] for r in results if r["brand"] not in INVALID_BRANDS)
    )
    return {
        "locale": locale,
        "brands": brands,
        "multiple": len(brands) >= 2,
        "default_version": default_version,
    }


def display_name(slug):
    """A short display name for a slug: strip any "*-langpack-" prefix."""
    return re.sub(r"^[a-z]+-langpack-", "", slug) or slug


def sort_summaries(summaries, default_only):
    """Order summaries for the summary table so the locales most likely to
    need attention come first. Without --all-versions, that's locales with no
    brand found, then the longest brand, so e.g. "Thunderbird Beta" sorts
    above "Thunderbird". With it, locales with a single brand come first
    (those with none before those with one), then those with more than one.
    The sort is stable, so ties keep the order ATN listed the locales in."""
    if default_only:
        # Locales with no brand first, then the longest brand first.
        def key(s):
            return (len(s["brands"]) > 0, -len(", ".join(s["brands"])))
    else:
        # Single brand first; within those, locales with no brand first.
        def key(s):
            return (s["multiple"], len(s["brands"]))

    return sorted(summaries, key=key)


def format_summary_table(summaries, default_only):
    """Format summaries as a table, sorted by sort_summaries, with each column
    as wide as its widest cell. Without --all-versions the table has only the
    Locale and ATN Default columns; with it, also Multiple and Brands found."""
    def yn(b):
        return "yes" if b else "no"

    if default_only:
        headers = ["Locale", "ATN Default"]
    else:
        headers = ["Locale", "Multiple", "ATN Default", "Brands found"]

    rows = []
    for s in sort_summaries(summaries, default_only):
        if default_only:
            rows.append([s["locale"], s["default_version"]])
        else:
            rows.append(
                [
                    s["locale"],
                    yn(s["multiple"]),
                    s["default_version"],
                    ", ".join(s["brands"]) or "none",
                ]
            )

    widths = [max(len(c) for c in column) for column in zip(headers, *rows)]

    def line(cells):
        return "│".join(f" {c:<{w}} " for c, w in zip(cells, widths))

    sep = "┼".join("─" * (w + 2) for w in widths)
    return "\n".join([line(headers), sep, *map(line, rows), sep])


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="tb-release check-langpacks",
        description=__doc__.split("\n\n")[0],
        epilog="At least one of --list, --locales or --version is required.",
    )
    parser.add_argument(
        "-l",
        "--locales",
        help="comma-separated locale(s) to check, e.g. de,fr,en-us",
    )
    parser.add_argument(
        "-v",
        "--version",
        help="Thunderbird major version to check, e.g. 149; required with "
        "more than one locale",
    )
    parser.add_argument(
        "-L", "--list", action="store_true", help="list all available locales"
    )
    parser.add_argument(
        "-a",
        "--all-versions",
        action="store_true",
        help="with --version, check every language pack version for it, to "
        "find locales with more than one brand, not just the ATN default "
        "version (slow)",
    )
    args = parser.parse_args(argv)
    if not (args.list or args.locales or args.version):
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: one of --list, --locales or --version is required",
            file=sys.stderr,
        )
        sys.exit(1)
    return args


def resolve_slug(locale, locale_map):
    """Return the slug of the language pack for a locale, matched without
    regard to case. For an unknown locale, print the available locales and
    exit."""
    slug = locale_map.get(locale.lower())
    if not slug:
        print(f'Unknown locale: "{locale}"', file=sys.stderr)
        print(f"Available locales: {', '.join(locale_map)}", file=sys.stderr)
        sys.exit(1)
    return slug


def main(argv=None):
    args = parse_args(argv)
    target_major = args.version
    default_only = not args.all_versions

    locale_map, human_names = fetch_locale_map()

    if args.list:
        print(f"Available locales ({len(locale_map)}):\n{', '.join(locale_map)}")
        return 0

    default_versions = fetch_default_versions(target_major) if target_major else {}

    if args.locales:
        slugs = [resolve_slug(l.strip(), locale_map) for l in args.locales.split(",")]
    else:
        # --version only: scan all locales
        slugs = list(locale_map.values())
        names = ", ".join(map(display_name, slugs))
        print(f"Found {len(slugs)} locales: {names}\n")

    multi = len(slugs) > 1

    if multi and not target_major:
        print(
            "Error: --version is required when specifying multiple locales.",
            file=sys.stderr,
        )
        print(
            "Example: tb-release check-langpacks --locales de,fr,en-us --version 149",
            file=sys.stderr,
        )
        return 1

    summaries = []

    for i, slug in enumerate(slugs, 1):
        name = display_name(slug)
        default = default_versions.get(slug)
        label = f"{name}: {human_names[slug]}" if human_names.get(slug) else name
        if multi:
            print(f"\n── {label} ({i}/{len(slugs)}) ──")
        if default:
            print(f"ATN default: {default['version']} ({default['datetime']})")
        print_header()

        try:
            if default_only and default:
                # Fast path: only check the single ATN default version
                row = {
                    "version": default["version"],
                    "datetime": default["datetime"],
                    "brand": get_brand(default["url"]),
                }
                print_row(row)
                results = [row]
            else:
                results = analyze_locale(slug, target_major)
        except Exception as e:
            print(f"  [error] locale {name} failed: {e} — skipping", file=sys.stderr)
            continue

        if target_major:
            default_brand = ""
            if default:
                default_brand = next(
                    (r["brand"] for r in results if r["version"] == default["version"]),
                    "",
                )
            if default:
                default_label = default["version"]
                if default_brand:
                    default_label += f" ({default_brand})"
            else:
                default_label = "N/A"
            s = summarize(name, results, default_label)
            summaries.append(s)

            if not multi:
                print(f"\nSummary for {name} (TB {target_major}):")
                print(f"  ATN default:   {s['default_version']}")
                if not (default_only and default):
                    print(f"  Brands found:  {', '.join(s['brands']) or 'none'}")
                    print(f"  Multiple:      {'yes' if s['multiple'] else 'no'}")

    if multi and target_major:
        print(f"\n── Summary (TB {target_major}) ──")
        print(format_summary_table(summaries, default_only))

    return 0


if __name__ == "__main__":
    sys.exit(main())
