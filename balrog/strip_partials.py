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

    # Windows only and add "no-win-partials" suffix to release name and output file name
    ./strip_partials.py Thunderbird-153.0-build1.json --prefix WIN --suffix no-win-partials

    # a different platform family
    ./strip_partials.py blob.json --prefix Darwin --suffix no-mac-partials
"""

import argparse
import json
import sys
from pathlib import Path


def strip_partials(blob, prefix=""):
    """Remove "partials" from all locales of platforms starting with `prefix`.

    An empty `prefix` (the default) matches every platform.
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
    ap.add_argument("--prefix", default="",
                    help="only strip platforms whose name starts with this "
                         "(default: all platforms)")
    ap.add_argument("--suffix", default="no-partials",
                    help="appended to the release name and the output filename "
                         "(default: no-partials)")
    args = ap.parse_args(argv)

    blob = json.loads(args.input.read_text())

    removed, report = strip_partials(blob, args.prefix)
    for line in report:
        print(line, file=sys.stderr)
    if not report:
        if args.prefix:
            print(f"warning: no platforms start with {args.prefix!r}", file=sys.stderr)
        else:
            print("warning: blob has no platforms", file=sys.stderr)

    old_name = blob.get("name")
    blob["name"] = f"{old_name}-{args.suffix}" if old_name else args.suffix
    print(f'name: {old_name!r} -> {blob["name"]!r}', file=sys.stderr)

    out = args.input.with_name(f"{args.input.stem}-{args.suffix}.json")

    out.write_text(dump(blob))
    print(f"removed {removed} partial entries -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
