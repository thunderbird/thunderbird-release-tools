#!/usr/bin/env python3
"""
Thunderbird schedule generator.

Generates a Thunderbird Desktop, Desktop ESR, or Android release schedule from
the version's start date (the '<major>.0a1 starts' date, or for ESR, the ESR
release date), and optionally writes it to Google Calendar and/or Notion.
"""
import argparse
from dataclasses import dataclass
from difflib import get_close_matches
from datetime import date, datetime, timedelta
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True)
class TemplateMilestone:
    # Logical key for this milestone (used for anchoring)
    key: str
    # Days offset from the start date (the first milestone is 0)
    delta_days: int
    # Weekday (0=Monday..6=Sunday) to enforce
    weekday: int
    # Label format string; filled in with {major}, or {esr} and {esr_dot1} for ESR
    label: str
    # Notion task estimate
    estimate: int = 1
    # Whether --write-notion creates a task for this milestone
    notion_task: bool = True

# Build the template for Desktop relative to the start date (a1 starts)
TEMPLATE_DESKTOP: List[TemplateMilestone] = [
    TemplateMilestone("a1-starts", 0, 3, "Thunderbird {major}.0a1 starts", notion_task=False),
    TemplateMilestone("a1-merge", 14, 3, "Thunderbird merge {major}.0a1 main->beta"),
    TemplateMilestone("b1", 18, 0, "Thunderbird {major}.0b1", estimate=2),
    TemplateMilestone("b2", 20, 2, "Thunderbird {major}.0b2"),
    TemplateMilestone("b3", 25, 0, "Thunderbird {major}.0b3"),
    TemplateMilestone("b4", 27, 2, "Thunderbird {major}.0b4"),
    TemplateMilestone("b4-merge", 27, 2, "Thunderbird merge {major}.0 beta->release"),
    TemplateMilestone("ga", 33, 1, "Thunderbird {major}.0"),
    TemplateMilestone("dot1", 40, 1, "Thunderbird {major}.0.1"),
]

# Build the template for Android relative to the start date (a1 starts)
TEMPLATE_ANDROID: List[TemplateMilestone] = [
    TemplateMilestone("a1-starts", 0, 3, "TfA {major}.0a1 starts", notion_task=False),
    TemplateMilestone("a1-merge", 28, 3, "TfA merge {major}.0a1 main->beta"),
    TemplateMilestone("b1", 32, 0, "TfA {major}.0b1", estimate=2),
    TemplateMilestone("b2", 39, 0, "TfA {major}.0b2"),
    TemplateMilestone("b3", 46, 0, "TfA {major}.0b3"),
    TemplateMilestone("b-merge", 53, 0, "TfA merge {major}.0 beta->release"),
    TemplateMilestone("ga", 60, 0, "TfA {major}.0"),
    TemplateMilestone("dot1", 74, 0, "TfA {major}.1"),
]

# Build the template for Desktop ESR relative to the ESR release date
TEMPLATE_DESKTOP_ESR: List[TemplateMilestone] = [
    TemplateMilestone("esr", 0, 1, "Thunderbird {esr}esr"),
    TemplateMilestone("esr-dot1", 7, 1, "Thunderbird {esr_dot1}esr"),
]

# Desktop ESR versions, e.g. "153.0esr" or "153.5.0esr"
ESR_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?esr$")

WEEKDAY_NAME = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]


@dataclass(frozen=True)
class Options:
    write_calendar: bool = False
    write_notion: bool = False
    assignee: Optional[str] = None
    calendar_id: str = "c_f7b7f2cea6f65593ef05afaf2abfcfb48f87e25794468cd4a19d16495d17b6d1@group.calendar.google.com"


HELP_EPILOG = """\
The start date is the '<application> <major>.0a1 starts' milestone and must be
a Thursday for both desktop and android. For a desktop ESR version, it's the
ESR release date and must be a Tuesday.

examples:
  tb-release schedule desktop 146 2025-10-16
  tb-release schedule desktop 153.0esr 2026-07-21
  tb-release schedule desktop 153.5.0esr 2026-10-13
  tb-release schedule android 15 2025-10-16 --write-calendar
  tb-release schedule desktop 146 2025-10-16 --write-notion --assignee "Jane Doe"
"""


def iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("date must be in YYYY-MM-DD format")


def version_arg(value: str) -> int | str:
    """Parse a major version (e.g. "146" -> 146) or a desktop ESR version (e.g. "153.0esr")."""
    if value.isdigit():
        return int(value)
    if ESR_VERSION_RE.match(value):
        return value
    raise argparse.ArgumentTypeError(
        "version must be a major version (e.g. 146) or an ESR version (e.g. 153.0esr or 153.5.0esr)")


def is_esr(version: int | str | None) -> bool:
    return isinstance(version, str)


def esr_label_fields(version: str) -> Dict[str, str]:
    """Return the ESR version and its first dot release: 153.0esr -> 153.0.1, 153.5.0esr -> 153.5.1."""
    major, minor, patch = ESR_VERSION_RE.match(version).groups()
    if patch is None:
        return {"esr": f"{major}.{minor}", "esr_dot1": f"{major}.{minor}.1"}
    return {"esr": f"{major}.{minor}.{patch}", "esr_dot1": f"{major}.{minor}.{int(patch) + 1}"}


def non_empty(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("value must not be empty")
    return value.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-release schedule",
        description="Generate a Thunderbird Desktop or Android release schedule.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("application", type=str.lower, choices=["desktop", "android"])
    parser.add_argument("version", type=version_arg,
                        help="major version (e.g. 146), or a desktop ESR version (e.g. 153.0esr)")
    parser.add_argument("start_date", metavar="start-date", type=iso_date,
                        help="YYYY-MM-DD: the .0a1 start date (a Thursday), or the ESR release date (a Tuesday)")
    parser.add_argument("--write-calendar", action="store_true",
                        help="write events to Google Calendar (requires setup)")
    parser.add_argument("--write-notion", action="store_true", help="create the tasks")
    parser.add_argument("--assignee", type=non_empty, metavar="NAME",
                        help="Notion user (name or email) to assign the tasks to (required with --write-notion)")
    return parser


def parse_args(argv: List[str]) -> Tuple[str, int | str, date, Options]:
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    # enforce weekday constraint based on application
    if is_esr(args.version):
        if args.application != "desktop":
            parser.error("ESR versions are only supported for desktop")
        if args.start_date.weekday() != 1:
            parser.error("desktop ESR start date must be a Tuesday")
    elif args.start_date.weekday() != 3:
        parser.error(f"{args.application} a1 start date must be a Thursday")

    if args.write_notion and args.assignee is None:
        parser.error("--write-notion requires --assignee")
    if args.assignee is not None and not args.write_notion:
        parser.error("--assignee requires --write-notion")

    return args.application, args.version, args.start_date, Options(
        write_calendar=args.write_calendar,
        write_notion=args.write_notion,
        assignee=args.assignee,
    )


def find_template_by_key(template: List[TemplateMilestone], key: str) -> TemplateMilestone:
    for tm in template:
        if tm.key == key:
            return tm
    raise KeyError(f"unknown anchor key: {key}")


def get_template(application: str, version: int | str | None = None) -> List[TemplateMilestone]:
    """Return the appropriate template based on application and version."""
    if application == "desktop" and is_esr(version):
        return TEMPLATE_DESKTOP_ESR
    elif application == "desktop":
        return TEMPLATE_DESKTOP
    elif application == "android":
        return TEMPLATE_ANDROID
    else:
        raise ValueError(f"unknown application: {application}")


def generate_schedule(application: str, version: int | str, start_date: date) -> List[Tuple[date, str]]:
    # Select template based on application and version (major version, or ESR version string)
    template = get_template(application, version)
    fields = esr_label_fields(version) if is_esr(version) else {"major": version}
    # start_date is the first milestone's date (offset is 0)
    out: List[Tuple[date, str]] = []
    for tm in template:
        # Compute target date from start_date using template offset
        target = start_date + timedelta(days=tm.delta_days)

        # Verify the calculated date falls on the expected weekday
        label = tm.label.format(**fields)
        if target.weekday() != tm.weekday:
            print(f"error: milestone '{label}' falls on {WEEKDAY_NAME[target.weekday()]} "
                  f"but template expects {WEEKDAY_NAME[tm.weekday]}", file=sys.stderr)
            print(f"  calculated date: {target}", file=sys.stderr)
            print(f"  template offset: {tm.delta_days} days from start date", file=sys.stderr)
            sys.exit(1)

        out.append((target, label))
    return out


def format_date(d: date) -> str:
    # Built from parts because strftime's no-padding day code differs by platform (%-d vs %#d)
    return f"{d:%B} {d.day}, {d.year}"


def write_to_google_calendar(schedule: List[Tuple[date, str]], application: str, version: int | str,
                             calendar_id: str):
    """Write schedule events to Google Calendar using the API."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import os.path
        import pickle
    except ImportError:
        print("Error: Google Calendar API libraries not installed.", file=sys.stderr)
        sys.exit(1)

    SCOPES = ['https://www.googleapis.com/auth/calendar.events']
    creds = None

    # Token file stores user's access and refresh tokens
    token_file = os.path.expanduser('~/.thunderbird-schedule-token.pickle')

    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Need credentials.json from Google Cloud Console
            creds_file = os.path.expanduser('~/.thunderbird-schedule-credentials.json')
            if not os.path.exists(creds_file):
                print("Error: Google Calendar credentials file not found.", file=sys.stderr)
                print(f"Expected at: {creds_file}", file=sys.stderr)
                print("\nTo set up:", file=sys.stderr)
                print("1. Go to https://console.cloud.google.com/", file=sys.stderr)
                print("2. Create a project and enable Google Calendar API", file=sys.stderr)
                print("3. Create OAuth 2.0 credentials (Desktop app)", file=sys.stderr)
                print(f"4. Download credentials.json and save to {creds_file}", file=sys.stderr)
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run, readable only by the owner
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.chmod(token_file, 0o600)  # also tighten a token file created by an older version
        with os.fdopen(fd, 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    # Create events
    print(f"Writing {len(schedule)} events to Google Calendar...", file=sys.stderr)
    for event_date, label in schedule:
        event = {
            'summary': label,
            'start': {
                'date': event_date.isoformat(),
                'timeZone': 'America/New_York',
            },
            'end': {
                'date': event_date.isoformat(),
                'timeZone': 'America/New_York',
            },
            'description': f'{application.capitalize()} {version} milestone',
            'transparency': 'transparent',  # Show as "free" instead of "busy"
        }

        try:
            created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
            print(f"Created: {event_date} - {label}", file=sys.stderr)
        except Exception as e:
            print(f"Error creating event for {event_date}: {e}", file=sys.stderr)

    print(f"\nSuccessfully wrote schedule to calendar!", file=sys.stderr)
    print(f"View at: https://calendar.google.com/calendar/embed?src={calendar_id}", file=sys.stderr)

NOTION_CONFIG_ENV = "THUNDERBIRD_SCHEDULE_NOTION_CONFIG"
NOTION_CONFIG_FILE = "~/.thunderbird-schedule-notion.toml"
NOTION_DEFAULT_TEAM = "Build & Release"
# Each task is linked to the milestone for its month, e.g. "2026 October Releases"
NOTION_DEFAULT_MILESTONE_FORMAT = "{year} {month} Releases"
MONTH_NAME = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
NOTION_DEFAULT_PROPERTIES = {
    "title": "Name",
    "date": "Original Due Date",
    "assignee": "Assignee",
    "estimate": "Estimate",
    "team": "Team",
    "milestone": "Milestones",
    "milestone_title": "Name",
}


def notion_fail(message: str):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def load_notion_config() -> Dict[str, Any]:
    """Load the local Notion config (token, tasks database ID, property names)."""
    import tomllib

    path = os.path.expanduser(os.environ.get(NOTION_CONFIG_ENV) or NOTION_CONFIG_FILE)
    if not os.path.exists(path):
        print(f"Error: Notion config file not found at {path}", file=sys.stderr)
        print("\nCreate it with at least:", file=sys.stderr)
        print('  token = "ntn_..."', file=sys.stderr)
        print('  database_id = "<tasks database id>"', file=sys.stderr)
        print("\nSee README.md for details.", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        notion_fail(f"could not parse {path}: {e}")

    for key in ("token", "database_id"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            notion_fail(f"'{key}' is missing from {path}")
    team = raw.get("team", NOTION_DEFAULT_TEAM)
    if not isinstance(team, str) or not team.strip():
        notion_fail(f"'team' in {path} must be a non-empty string")
    milestone_format = raw.get("milestone_format", NOTION_DEFAULT_MILESTONE_FORMAT)
    try:
        milestone_format.format(year=2026, month="October")
    except (AttributeError, KeyError, IndexError, ValueError):
        notion_fail(f"'milestone_format' in {path} may only use {{year}} and {{month}}")

    return {
        "token": raw["token"].strip(),
        "database_id": raw["database_id"].strip(),
        "team": team.strip(),
        "milestone_format": milestone_format,
        "properties": {**NOTION_DEFAULT_PROPERTIES, **raw.get("properties", {})},
    }


def notion_paginate(method, **kwargs) -> List[Dict[str, Any]]:
    """Collect all results from a paginated Notion API call."""
    results: List[Dict[str, Any]] = []
    cursor = None
    while True:
        if cursor:
            kwargs["start_cursor"] = cursor
        response = method(**kwargs)
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            return results
        cursor = response.get("next_cursor")


def resolve_assignee(client, name: str) -> str:
    """Return the Notion user ID for `name` (display name or email); exit if not exactly one match."""
    try:
        users = notion_paginate(client.users.list)
    except Exception as e:
        if getattr(e, "status", None) == 403:
            notion_fail("the Notion token cannot list users. It needs permission to "
                        "read user information (see README.md).")
        raise

    people = [u for u in users if u.get("type") == "person"]
    wanted = name.strip().casefold()

    def email(user):
        return (user.get("person") or {}).get("email") or ""

    matches = [u for u in people
               if (u.get("name") or "").strip().casefold() == wanted or email(u).casefold() == wanted]
    if len(matches) == 1:
        return matches[0]["id"]
    if matches:
        print(f"Error: multiple Notion users match '{name}':", file=sys.stderr)
        for u in matches:
            print(f"  {u.get('name')}  {email(u) or u['id']}", file=sys.stderr)
        print("Pass the user's email to --assignee instead.", file=sys.stderr)
        sys.exit(1)

    print(f"Error: Notion user '{name}' not found", file=sys.stderr)
    # Suggest names that contain the input (partial names) or are spelled similarly (typos)
    names = {(u.get("name") or "").strip().casefold(): u.get("name") for u in people if u.get("name")}
    similar = get_close_matches(wanted, names)
    suggestions = sorted(names[n] for n in names if wanted in n or n in similar)
    if suggestions:
        print(f"Did you mean: {', '.join(suggestions)}", file=sys.stderr)
    sys.exit(1)


def get_data_source_id(client, database_id: str) -> str:
    """Return the single data source ID backing a Notion database."""
    sources = client.databases.retrieve(database_id=database_id).get("data_sources", [])
    if len(sources) != 1:
        notion_fail(f"expected Notion database {database_id} to have exactly one data source, "
                    f"found {len(sources)}")
    return sources[0]["id"]


def get_property(schema: Dict[str, Any], name: str, types: Tuple[str, ...]) -> Dict[str, Any]:
    """Return the tasks database property `name`, exiting if it's missing or not one of `types`."""
    prop = schema.get(name)
    if not prop or prop.get("type") not in types:
        notion_fail(f"tasks database has no {' or '.join(types)} property named '{name}'")
    return prop


def get_relation_data_source(client, prop: Dict[str, Any]) -> str:
    relation = prop["relation"]
    return relation.get("data_source_id") or get_data_source_id(client, relation["database_id"])


def get_title_property(client, data_source_id: str) -> str:
    schema = client.data_sources.retrieve(data_source_id=data_source_id).get("properties", {})
    for name, prop in schema.items():
        if prop.get("type") == "title":
            return name
    notion_fail(f"Notion data source {data_source_id} has no title property")


def inspect_tasks_database(client, config: Dict[str, Any]) -> Dict[str, Any]:
    """Check the tasks database's fields and return what's needed to create tasks.

    Looks up the data source behind config["database_id"] and checks that each field
    named in config["properties"] exists with a usable type:

      title      title
      date       date
      assignee   people
      milestone  relation (to the milestones database)
      estimate   select or number
      team       relation (to the teams database), select, or multi_select

    Exits with an error naming the first field that's missing or has the wrong type,
    so nothing is written to Notion with a bad field name.

    Returns a dict with:
      tasks_ds       data source ID of the tasks database (where tasks are created)
      milestones_ds  data source ID the milestone relation points to
      estimate_type  "select" or "number", which decides how Estimate is written
      team_type      "relation", "select", or "multi_select"
      team_ds        data source ID the team relation points to, or None if Team
                     isn't a relation
    """
    props = config["properties"]
    tasks_ds = get_data_source_id(client, config["database_id"])
    schema = client.data_sources.retrieve(data_source_id=tasks_ds).get("properties", {})

    for key, prop_type in (("title", "title"), ("date", "date"), ("assignee", "people")):
        get_property(schema, props[key], (prop_type,))
    milestone_prop = get_property(schema, props["milestone"], ("relation",))
    estimate_prop = get_property(schema, props["estimate"], ("select", "number"))
    team_prop = get_property(schema, props["team"], ("relation", "select", "multi_select"))

    return {
        "tasks_ds": tasks_ds,
        "milestones_ds": get_relation_data_source(client, milestone_prop),
        "estimate_type": estimate_prop["type"],
        "team_type": team_prop["type"],
        "team_ds": get_relation_data_source(client, team_prop) if team_prop["type"] == "relation" else None,
    }


def find_pages_by_title(client, data_source_id: str, title_prop: str, title: str) -> List[Dict[str, Any]]:
    """Return every page in a Notion data source whose title is exactly `title`.

    data_source_id  the database to search (tasks, milestones, or teams)
    title_prop      the name of that database's title field, e.g. "Name"
    title           the title to match; this is an exact match, not a "contains" search

    Returns a list of Notion page objects, collected across all result pages, or an
    empty list if nothing matches. Used by find_unique_page for the milestone and team
    lookups, and by write_to_notion to skip tasks that already exist.
    """
    return notion_paginate(
        client.data_sources.query,
        data_source_id=data_source_id,
        filter={"property": title_prop, "title": {"equals": title}},
    )


def find_unique_page(client, data_source_id: str, title_prop: str, name: str, kind: str) -> str:
    """Return the ID of the single page titled `name`; exit if there are none or several."""
    pages = find_pages_by_title(client, data_source_id, title_prop, name)
    if not pages:
        notion_fail(f"Notion {kind} '{name}' not found")
    if len(pages) > 1:
        print(f"Error: multiple Notion {kind}s are titled '{name}':", file=sys.stderr)
        for page in pages:
            print(f"  {page.get('url') or page['id']}", file=sys.stderr)
        sys.exit(1)
    return pages[0]["id"]


def milestone_name(config: Dict[str, Any], task_date: date) -> str:
    """Return the Notion milestone title for a task date, e.g. "2026 October Releases"."""
    return config["milestone_format"].format(year=task_date.year, month=MONTH_NAME[task_date.month - 1])


def resolve_milestones(client, config: Dict[str, Any], milestones_ds: str,
                       schedule: List[Tuple[date, str]]) -> Dict[str, str]:
    """Return {milestone title: page ID} for every month in the schedule; exit if any is missing."""
    title_prop = config["properties"]["milestone_title"]
    names = dict.fromkeys(milestone_name(config, d) for d, _ in schedule)
    return {name: find_unique_page(client, milestones_ds, title_prop, name, "milestone") for name in names}


def resolve_team(client, config: Dict[str, Any], tasks_db_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Return the Team property value for new tasks."""
    team = config["team"]
    if tasks_db_fields["team_type"] == "select":
        return {"select": {"name": team}}
    if tasks_db_fields["team_type"] == "multi_select":
        return {"multi_select": [{"name": team}]}
    team_ds = tasks_db_fields["team_ds"]
    title_prop = get_title_property(client, team_ds)
    return {"relation": [{"id": find_unique_page(client, team_ds, title_prop, team, "team")}]}


NOTION_TITLE_PREFIXES = ("Thunderbird ", "TfA ")


def notion_task_title(label: str) -> str:
    """Return the Notion task title for a schedule label, without the application prefix."""
    for prefix in NOTION_TITLE_PREFIXES:
        if label.startswith(prefix):
            return label.removeprefix(prefix)
    return label


def write_to_notion(schedule: List[Tuple[date, str]], application: str, assignee: str,
                    version: int | str | None = None):
    """Create a Notion task for each schedule date, linked to the existing milestone for its month."""
    config = load_notion_config()
    try:
        from notion_client import Client
    except ImportError:
        print("Error: Notion API library not installed.", file=sys.stderr)
        print("Install with: pip install notion-client", file=sys.stderr)
        sys.exit(1)

    client = Client(auth=config["token"])
    props = config["properties"]
    tasks = [(tm, task_date, notion_task_title(label))
             for tm, (task_date, label) in zip(get_template(application, version), schedule) if tm.notion_task]
    task_schedule = [(task_date, title) for _, task_date, title in tasks]

    # Validate everything before writing anything
    try:
        user_id = resolve_assignee(client, assignee)
        tasks_db_fields = inspect_tasks_database(client, config)
        milestone_ids = resolve_milestones(client, config, tasks_db_fields["milestones_ds"], task_schedule)
        team_value = resolve_team(client, config, tasks_db_fields)
    except Exception as e:
        if getattr(e, "status", None) is None:
            raise
        notion_fail(f"Notion API request failed ({e.status}): {e}")

    print(f"Writing {len(tasks)} tasks to Notion...", file=sys.stderr)
    for tm, task_date, label in tasks:
        try:
            if find_pages_by_title(client, tasks_db_fields["tasks_ds"], props["title"], label):
                print(f"Skipped (already exists): {task_date} - {label}", file=sys.stderr)
                continue

            if tasks_db_fields["estimate_type"] == "select":
                estimate = {"select": {"name": str(tm.estimate)}}
            else:
                estimate = {"number": tm.estimate}
            properties = {
                props["title"]: {"title": [{"text": {"content": label}}]},
                props["date"]: {"date": {"start": task_date.isoformat()}},
                props["estimate"]: estimate,
                props["milestone"]: {"relation": [{"id": milestone_ids[milestone_name(config, task_date)]}]},
                props["assignee"]: {"people": [{"id": user_id}]},
                props["team"]: team_value,
            }

            client.pages.create(
                parent={"type": "data_source_id", "data_source_id": tasks_db_fields["tasks_ds"]},
                properties=properties,
            )
            print(f"Created: {task_date} - {label} ({milestone_name(config, task_date)})", file=sys.stderr)
        except Exception as e:
            print(f"Error creating task for {task_date}: {e}", file=sys.stderr)


def main(argv: List[str]) -> int:
    application, version, start_date, opts = parse_args(argv)
    schedule = generate_schedule(application, version, start_date)

    # Print aligned columns: Date | Weekday | Label
    rows = [(format_date(d), WEEKDAY_NAME[d.weekday()], label) for d, label in schedule]
    # Set column widths
    date_w = max(len(r[0]) for r in rows) if rows else 0
    day_w = max(len(r[1]) for r in rows) if rows else 0
    for date_str, day_str, label in rows:
        print(f"{date_str:<{date_w}}  {day_str:<{day_w}}  {label}")

    # Write to Google Calendar if requested
    if opts.write_calendar:
        write_to_google_calendar(schedule, application, version, opts.calendar_id)

    # Create Notion tasks if requested
    if opts.write_notion:
        write_to_notion(schedule, application, opts.assignee, version)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
