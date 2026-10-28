"""Entry point for `tb-release`. Each subcommand runs one of the scripts in
this repository, passing its arguments through unchanged, so `tb-release
<command> --help` shows the script's own help."""

import subprocess
import sys
from importlib.resources import files
from pathlib import Path

# subcommand -> (script path in the repository, description)
COMMANDS = {
    "bump": ("releases/scripts/bump.sh",
             "Bump the version of the current branch and commit it"),
    "pin": ("releases/scripts/pin.sh",
            "Pin the checkout to the latest Firefox tag on the current branch"),
    "prep": ("releases/scripts/prep.sh",
             "Switch to a branch and sync it to the remote tip"),
    "uplift": ("releases/scripts/uplift.sh",
               "Uplift a changeset to the current checkout with an approver"),
    "strip-partials": ("balrog/strip_partials.py",
                       "Strip partial updates from a Balrog release blob"),
    "on-schedule": ("reports/on-schedule/on-schedule.py",
                    "Report how often desktop releases ship on schedule"),
}


def script_path(script_path):
    """An installed tb-release package has the script directories bundled under
    tb_release/scripts/ (see pyproject.toml); when run from a checkout, use
    the repository's path."""
    bundled = files("tb_release") / "scripts" / script_path
    if bundled.is_file():
        return Path(str(bundled))
    return Path(__file__).resolve().parent.parent / script_path


def usage():
    width = max(map(len, COMMANDS))
    lines = ["usage: tb-release <command> [args...]", "", "commands:"]
    lines += [f"  {name:<{width}}  {desc}"
              for name, (_, desc) in COMMANDS.items()]
    lines += ["", "Run `tb-release <command> --help` for a command's options."]
    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(usage())
        return 0
    name, args = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"tb-release: unknown command: {name}\n\n{usage()}",
              file=sys.stderr)
        return 2
    path = script_path(COMMANDS[name][0])
    runner = [sys.executable] if path.suffix == ".py" else ["bash"]
    try:
        return subprocess.call(runner + [str(path)] + args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
