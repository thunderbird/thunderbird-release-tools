#!/usr/bin/env python3
"""Strip partial updates from a Balrog release blob.

About release blobs:
* Release blobs can be found at: https://balrog.mozilla.org/releases
* After creating a new blob, update the Mapping for balrog rule to point at the new blob.

The script reads a release JSON blob, removes the "partials" list from every locale of
every platform, and renames the release blob. Pass --prefix to limit the change to one
platform family. Alias platforms have no locales of their own, so they inherit the
change from whichever platform they point at.

Output is written with the same canonical formatting Balrog blobs use
(2-space indent, sorted keys, trailing newline), so a diff against the input
shows only the intended changes.

Examples:
    # all partials -> Thunderbird-153.0-build1-no-partials.json
    ./strip_partials.py Thunderbird-153.0-build1.json

    # Windows only
    ./strip_partials.py Thunderbird-153.0-build1.json --prefix WIN --suffix no-win-partials

    # explicit output path and release name
    ./strip_partials.py in.json -o out.json --name Thunderbird-153.0-build1-no-partials

    # a different platform family, edited in place
    ./strip_partials.py blob.json --prefix Darwin --suffix no-mac-partials --in-place
"""

import argparse
import json
import sys
from pathlib import Path


def strip_partials(blob, prefix):
    """Remove "partials" from all locales of platforms starting with `prefix`.

    Mutates `blob` in place. Returns (entries_removed, per_platform_report).
    """
    removed = 0
    report = []

    for platform in sorted(blob.get("platforms", {})):
        data = blob["platforms"][platform]
        if not platform.startswith(prefix):
            continue

        if "alias" in data:
            report.append(f"{platform}: alias -> {data['alias']} (inherits)")
            continue

        locales = data.get("locales", {})
        touched = 0
        for locale in locales.values():
            partials = locale.pop("partials", None)
            if partials is not None:
                removed += len(partials)
                touched += 1

        report.append(f"{platform}: stripped {touched}/{len(locales)} locales")

    return removed, report


def dump(blob):
    """Serialize a blob in Balrog's canonical formatting."""
    return json.dumps(blob, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="release blob to read")
    ap.add_argument("-o", "--output", type=Path,
                    help="output path (default: <input stem>-<suffix>.json)")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite the input file instead of writing a new one")
    ap.add_argument("--prefix", default="WIN",
                    help="strip partials from platforms starting with this (default: WIN)")
    ap.add_argument("--suffix", default="no-win-partials",
                    help="appended to the release name and default filename "
                         "(default: no-win-partials)")
    ap.add_argument("--name",
                    help='explicit value for the blob\'s "name" field, overriding --suffix')
    ap.add_argument("--keep-name", action="store_true",
                    help='leave the "name" field unchanged')
    args = ap.parse_args(argv)

    if args.in_place and args.output:
        ap.error("--in-place and --output are mutually exclusive")

    blob = json.loads(args.input.read_text())

    removed, report = strip_partials(blob, args.prefix)
    for line in report:
        print(line, file=sys.stderr)
    if not report:
        print(f"warning: no platforms start with {args.prefix!r}", file=sys.stderr)

    old_name = blob.get("name")
    if not args.keep_name:
        blob["name"] = args.name or (f"{old_name}-{args.suffix}" if old_name else args.suffix)
        if blob["name"] != old_name:
            print(f'name: {old_name!r} -> {blob["name"]!r}', file=sys.stderr)

    if args.in_place:
        out = args.input
    elif args.output:
        out = args.output
    else:
        out = args.input.with_name(f"{args.input.stem}-{args.suffix}.json")

    out.write_text(dump(blob))
    print(f"removed {removed} partial entries -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
