import os
import sys
import tempfile
import types
import unittest
from datetime import date
from io import StringIO
from unittest import mock

# Import from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import thunderbird_schedule as ts  # noqa: E402

TASKS_DB = "tasks-db"
TASKS_DS = "tasks-ds"
MILESTONES_DS = "milestones-ds"


def milestone_page(title):
    return f"page:{title}"


TEAMS_DS = "teams-ds"
TEAM_PAGE = "team-build-release"

USERS = [
    {"object": "user", "id": "u-jane", "type": "person", "name": "Jane Doe",
     "person": {"email": "jane@example.com"}},
    {"object": "user", "id": "u-john", "type": "person", "name": "John Smith",
     "person": {"email": "john@example.com"}},
    {"object": "user", "id": "u-bot", "type": "bot", "name": "Jane Doe Bot", "bot": {}},
    {"object": "user", "id": "u-pat1", "type": "person", "name": "Pat Lee",
     "person": {"email": "pat1@example.com"}},
    {"object": "user", "id": "u-pat2", "type": "person", "name": "Pat Lee",
     "person": {"email": "pat2@example.com"}},
]


class FakeAPIError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


class FakeNotion:
    """Minimal stand-in for notion_client.Client that records calls."""

    def __init__(self, estimate_type="select",
                 milestones=("2025 October Releases", "2025 November Releases", "2025 December Releases"),
                 existing_tasks=(), users=USERS, users_status=None, team_type="relation",
                 teams=("Build & Release", "Mobile")):
        self.created = []
        self.queries = []
        self.estimate_type = estimate_type
        self.milestones = list(milestones)
        self.existing_tasks = set(existing_tasks)
        self.users_status = users_status
        self.team_type = team_type
        self.teams = list(teams)
        self._users = list(users)

        self.users = types.SimpleNamespace(list=self._users_list)
        self.databases = types.SimpleNamespace(retrieve=self._db_retrieve)
        self.data_sources = types.SimpleNamespace(retrieve=self._ds_retrieve, query=self._ds_query)
        self.pages = types.SimpleNamespace(create=self._page_create)

    def _users_list(self, start_cursor=None):
        if self.users_status:
            raise FakeAPIError(self.users_status)
        # Paginate two users per page to exercise cursor handling
        start = int(start_cursor or 0)
        page = self._users[start:start + 2]
        more = start + 2 < len(self._users)
        return {"results": page, "has_more": more, "next_cursor": str(start + 2) if more else None}

    def _db_retrieve(self, database_id):
        assert database_id == TASKS_DB
        return {"id": TASKS_DB, "data_sources": [{"id": TASKS_DS, "name": "Tasks"}]}

    def _ds_retrieve(self, data_source_id):
        if data_source_id == TEAMS_DS:
            return {"properties": {"Team name": {"type": "title"}, "Lead": {"type": "people"}}}
        assert data_source_id == TASKS_DS
        team = {"type": self.team_type}
        if self.team_type == "relation":
            team["relation"] = {"database_id": "teams-db", "data_source_id": TEAMS_DS}
        return {"properties": {
            "Name": {"type": "title"},
            "Date": {"type": "date"},
            "Original Due Date": {"type": "date"},
            "Assignee": {"type": "people"},
            "Estimate": {"type": self.estimate_type},
            "Team": team,
            "Milestones": {"type": "relation",
                           "relation": {"database_id": "milestones-db", "data_source_id": MILESTONES_DS}},
        }}

    def _ds_query(self, data_source_id, filter, start_cursor=None):
        self.queries.append((data_source_id, filter))
        title = filter["title"]["equals"]
        if data_source_id == MILESTONES_DS:
            hits = [m for m in self.milestones if m == title]
            return {"results": [{"id": milestone_page(title) + (f"-{i}" if i else ""), "url": "u"}
                                for i, _ in enumerate(hits)], "has_more": False}
        if data_source_id == TEAMS_DS:
            assert filter["property"] == "Team name"
            hits = [t for t in self.teams if t == title]
            return {"results": [{"id": TEAM_PAGE if t == "Build & Release" else f"team-{t}"} for t in hits],
                    "has_more": False}
        hits = [title] if title in self.existing_tasks else []
        return {"results": [{"id": "task"} for _ in hits], "has_more": False}

    def _page_create(self, parent, properties):
        self.created.append((parent, properties))
        return {"id": f"page-{len(self.created)}"}


def write_config(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    f.write(text)
    f.close()
    return f.name


BASIC_CONFIG = f'token = "ntn_test"\ndatabase_id = "{TASKS_DB}"\n'


class NotionTestCase(unittest.TestCase):
    def setUp(self):
        self.stderr = StringIO()
        patcher = mock.patch.object(sys, "stderr", self.stderr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def use_config(self, text=BASIC_CONFIG):
        path = write_config(text)
        self.addCleanup(os.unlink, path)
        patcher = mock.patch.dict(os.environ, {ts.NOTION_CONFIG_ENV: path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def use_fake_client(self, fake):
        """Install a fake notion_client module whose Client returns `fake`."""
        self.client_auth = None

        def client_factory(auth):
            self.client_auth = auth
            return fake

        module = types.ModuleType("notion_client")
        module.Client = client_factory
        patcher = mock.patch.dict(sys.modules, {"notion_client": module})
        patcher.start()
        self.addCleanup(patcher.stop)


class TestParseArgs(NotionTestCase):
    BASE = ["tb-release schedule", "desktop", "146", "2025-10-16"]

    def parse(self, *extra):
        return ts.parse_args(self.BASE + list(extra))[3]

    def assertExit2(self, *extra):
        with self.assertRaises(SystemExit) as cm:
            self.parse(*extra)
        self.assertEqual(cm.exception.code, 2)

    def test_defaults(self):
        opts = self.parse()
        self.assertFalse(opts.write_notion)
        self.assertIsNone(opts.assignee)

    def test_space_form(self):
        opts = self.parse("--write-notion", "--assignee", "Jane Doe")
        self.assertTrue(opts.write_notion)
        self.assertEqual(opts.assignee, "Jane Doe")

    def test_equals_form(self):
        opts = self.parse("--assignee=Jane Doe", "--write-notion")
        self.assertEqual(opts.assignee, "Jane Doe")

    def test_milestone_flag_removed(self):
        self.assertExit2("--write-notion", "--assignee", "A", "--milestone", "2026 October Releases")
        self.assertIn("unrecognized arguments", self.stderr.getvalue())

    def test_combined_with_calendar(self):
        opts = self.parse("--write-calendar", "--write-notion", "--assignee", "A")
        self.assertTrue(opts.write_calendar)
        self.assertTrue(opts.write_notion)

    def test_missing_value(self):
        self.assertExit2("--write-notion", "--assignee")
        self.assertExit2("--write-notion", "--assignee=")

    def test_value_flag_does_not_swallow_flags(self):
        self.assertExit2("--assignee", "--write-notion")

    def test_unknown_option(self):
        self.assertExit2("--write-notoin")

    def test_flags_require_write_notion(self):
        self.assertExit2("--assignee", "Jane Doe")

    def test_write_notion_requires_assignee(self):
        self.assertExit2("--write-notion")
        self.assertIn("--write-notion requires --assignee", self.stderr.getvalue())


class TestLoadConfig(NotionTestCase):
    def test_defaults_merged(self):
        self.use_config(BASIC_CONFIG + '[properties]\nestimate = "Points"\n')
        config = ts.load_notion_config()
        self.assertEqual(config["token"], "ntn_test")
        self.assertEqual(config["database_id"], TASKS_DB)
        self.assertEqual(config["properties"]["estimate"], "Points")
        self.assertEqual(config["properties"]["title"], "Name")
        self.assertEqual(config["properties"]["date"], "Original Due Date")
        self.assertEqual(config["properties"]["team"], "Team")
        self.assertEqual(config["properties"]["milestone"], "Milestones")
        self.assertEqual(config["milestone_format"], "{year} {month} Releases")
        self.assertEqual(config["team"], "Build & Release")

    def test_team_override(self):
        self.use_config(BASIC_CONFIG + 'team = "Mobile"\n')
        self.assertEqual(ts.load_notion_config()["team"], "Mobile")

    def test_milestone_format_override(self):
        self.use_config(BASIC_CONFIG + 'milestone_format = "Releases {month} {year}"\n')
        self.assertEqual(ts.load_notion_config()["milestone_format"], "Releases {month} {year}")

    def test_bad_milestone_format(self):
        self.use_config(BASIC_CONFIG + 'milestone_format = "{year} {mon}"\n')
        with self.assertRaises(SystemExit):
            ts.load_notion_config()
        self.assertIn("'milestone_format'", self.stderr.getvalue())

    def test_missing_file(self):
        with mock.patch.dict(os.environ, {ts.NOTION_CONFIG_ENV: "/nonexistent/notion.toml"}):
            with self.assertRaises(SystemExit) as cm:
                ts.load_notion_config()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("not found", self.stderr.getvalue())

    def test_missing_token(self):
        self.use_config(f'database_id = "{TASKS_DB}"\n')
        with self.assertRaises(SystemExit):
            ts.load_notion_config()
        self.assertIn("'token'", self.stderr.getvalue())

    def test_missing_database_id(self):
        self.use_config('token = "ntn_test"\ndatabase_id = ""\n')
        with self.assertRaises(SystemExit):
            ts.load_notion_config()
        self.assertIn("'database_id'", self.stderr.getvalue())


class TestResolveAssignee(NotionTestCase):
    def test_exact_name(self):
        self.assertEqual(ts.resolve_assignee(FakeNotion(), "John Smith"), "u-john")

    def test_case_insensitive(self):
        self.assertEqual(ts.resolve_assignee(FakeNotion(), "  jane doe "), "u-jane")

    def test_email(self):
        self.assertEqual(ts.resolve_assignee(FakeNotion(), "JOHN@example.com"), "u-john")

    def test_bots_ignored(self):
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(), "Jane Doe Bot")

    def test_not_found_with_suggestions(self):
        with self.assertRaises(SystemExit) as cm:
            ts.resolve_assignee(FakeNotion(), "Jane")
        self.assertEqual(cm.exception.code, 1)
        err = self.stderr.getvalue()
        self.assertIn("Notion user 'Jane' not found", err)
        self.assertIn("Did you mean: Jane Doe\n", err)
        self.assertNotIn("Bot", err)

    def test_not_found_suggests_close_spelling(self):
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(), "Jnae Deo")
        self.assertIn("Did you mean: Jane Doe\n", self.stderr.getvalue())

    def test_suggestions_deduplicated(self):
        # Two users are named "Pat Lee"; a typo suggests the name once
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(), "Pat Le")
        self.assertIn("Did you mean: Pat Lee\n", self.stderr.getvalue())

    def test_no_suggestions(self):
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(), "Zzyzx Qwerty")
        self.assertNotIn("Did you mean", self.stderr.getvalue())

    def test_duplicate_names(self):
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(), "Pat Lee")
        err = self.stderr.getvalue()
        self.assertIn("multiple Notion users", err)
        self.assertIn("pat2@example.com", err)
        self.assertEqual(ts.resolve_assignee(FakeNotion(), "pat2@example.com"), "u-pat2")

    def test_forbidden(self):
        with self.assertRaises(SystemExit):
            ts.resolve_assignee(FakeNotion(users_status=403), "Jane Doe")
        self.assertIn("read user information", self.stderr.getvalue())


class TestInspectAndMilestone(NotionTestCase):
    def config(self, **props):
        return {"token": "t", "database_id": TASKS_DB, "milestone_format": ts.NOTION_DEFAULT_MILESTONE_FORMAT,
                "properties": {**ts.NOTION_DEFAULT_PROPERTIES, **props}}

    def test_inspect(self):
        result = ts.inspect_tasks_database(FakeNotion(estimate_type="number"), self.config())
        self.assertEqual(result, {"tasks_ds": TASKS_DS, "milestones_ds": MILESTONES_DS,
                                  "estimate_type": "number", "team_type": "relation", "team_ds": TEAMS_DS})

    def test_inspect_bad_milestone_property(self):
        with self.assertRaises(SystemExit):
            ts.inspect_tasks_database(FakeNotion(), self.config(milestone="Assignee"))
        self.assertIn("relation property named 'Assignee'", self.stderr.getvalue())

    def test_inspect_missing_date_property(self):
        with self.assertRaises(SystemExit):
            ts.inspect_tasks_database(FakeNotion(), self.config(date="Due Date"))
        self.assertIn("date property named 'Due Date'", self.stderr.getvalue())

    def test_inspect_bad_team_property(self):
        with self.assertRaises(SystemExit):
            ts.inspect_tasks_database(FakeNotion(team_type="rich_text"), self.config())
        self.assertIn("property named 'Team'", self.stderr.getvalue())

    def test_resolve_team_relation(self):
        fake = FakeNotion()
        tasks_db_fields = ts.inspect_tasks_database(fake, self.config())
        value = ts.resolve_team(fake, {**self.config(), "team": "Build & Release"}, tasks_db_fields)
        self.assertEqual(value, {"relation": [{"id": TEAM_PAGE}]})

    def test_resolve_team_select(self):
        fake = FakeNotion(team_type="select")
        tasks_db_fields = ts.inspect_tasks_database(fake, self.config())
        value = ts.resolve_team(fake, {**self.config(), "team": "Build & Release"}, tasks_db_fields)
        self.assertEqual(value, {"select": {"name": "Build & Release"}})

    def test_resolve_team_not_found(self):
        fake = FakeNotion(teams=("Mobile",))
        tasks_db_fields = ts.inspect_tasks_database(fake, self.config())
        with self.assertRaises(SystemExit):
            ts.resolve_team(fake, {**self.config(), "team": "Build & Release"}, tasks_db_fields)
        self.assertIn("Notion team 'Build & Release' not found", self.stderr.getvalue())

    def test_inspect_bad_estimate_property(self):
        with self.assertRaises(SystemExit):
            ts.inspect_tasks_database(FakeNotion(estimate_type="rich_text"), self.config())
        self.assertIn("'Estimate'", self.stderr.getvalue())

    def test_milestone_name(self):
        self.assertEqual(ts.milestone_name(self.config(), date(2026, 10, 26)), "2026 October Releases")
        self.assertEqual(ts.milestone_name(self.config(), date(2026, 11, 2)), "2026 November Releases")
        custom = {**self.config(), "milestone_format": "{month} {year}"}
        self.assertEqual(ts.milestone_name(custom, date(2027, 1, 7)), "January 2027")

    def test_resolve_milestones_one_lookup_per_month(self):
        fake = FakeNotion(milestones=("2026 October Releases", "2026 November Releases"))
        schedule = ts.generate_schedule("desktop", 160, date(2026, 10, 8))
        ids = ts.resolve_milestones(fake, self.config(milestone_title="Title"), MILESTONES_DS, schedule)
        self.assertEqual(ids, {"2026 October Releases": milestone_page("2026 October Releases"),
                               "2026 November Releases": milestone_page("2026 November Releases")})
        self.assertEqual(fake.queries, [
            (MILESTONES_DS, {"property": "Title", "title": {"equals": "2026 October Releases"}}),
            (MILESTONES_DS, {"property": "Title", "title": {"equals": "2026 November Releases"}}),
        ])

    def test_resolve_milestones_missing_month(self):
        fake = FakeNotion(milestones=("2026 October Releases",))
        schedule = ts.generate_schedule("desktop", 160, date(2026, 10, 8))
        with self.assertRaises(SystemExit) as cm:
            ts.resolve_milestones(fake, self.config(), MILESTONES_DS, schedule)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Notion milestone '2026 November Releases' not found", self.stderr.getvalue())

    def test_resolve_milestones_ambiguous(self):
        fake = FakeNotion(milestones=("2026 October Releases", "2026 October Releases"))
        with self.assertRaises(SystemExit):
            ts.resolve_milestones(fake, self.config(), MILESTONES_DS, [(date(2026, 10, 8), "x")])
        self.assertIn("multiple Notion milestones", self.stderr.getvalue())


class TestTemplates(unittest.TestCase):
    def test_only_b1_has_estimate_2(self):
        for template in (ts.TEMPLATE_DESKTOP, ts.TEMPLATE_ANDROID):
            for tm in template:
                self.assertEqual(tm.estimate, 2 if tm.key == "b1" else 1, tm.key)


class TestWriteToNotion(NotionTestCase):
    def run_write(self, fake, application="desktop", assignee="Jane Doe", start_date=date(2025, 10, 16)):
        self.use_config()
        self.use_fake_client(fake)
        major = 146 if application == "desktop" else 15
        schedule = ts.generate_schedule(application, major, start_date)
        ts.write_to_notion(schedule, application, assignee)
        return schedule

    def created_titles(self, fake):
        return [props["Name"]["title"][0]["text"]["content"] for _, props in fake.created]

    def test_creates_tasks(self):
        fake = FakeNotion()
        schedule = self.run_write(fake, assignee="Jane Doe")
        self.assertEqual(self.client_auth, "ntn_test")
        # No task for "0a1 starts", and no "Thunderbird " prefix
        self.assertEqual(self.created_titles(fake), [
            "merge 146.0a1 main->beta",
            "146.0b1",
            "146.0b2",
            "146.0b3",
            "146.0b4",
            "merge 146.0 beta->release",
            "146.0",
            "146.0.1",
        ])
        for (parent, props), (task_date, label) in zip(fake.created, schedule[1:]):
            self.assertEqual(parent, {"type": "data_source_id", "data_source_id": TASKS_DS})
            self.assertEqual(props["Name"], {"title": [{"text": {"content": label.removeprefix("Thunderbird ")}}]})
            self.assertEqual(props["Original Due Date"], {"date": {"start": task_date.isoformat()}})
            self.assertEqual(props["Team"], {"relation": [{"id": TEAM_PAGE}]})
            self.assertNotIn("Date", props)
            month = "October" if task_date.month == 10 else "November"
            self.assertEqual(props["Milestones"], {"relation": [{"id": milestone_page(f"2025 {month} Releases")}]})
            self.assertEqual(props["Assignee"], {"people": [{"id": "u-jane"}]})
            expected = "2" if label.endswith("146.0b1") else "1"
            self.assertEqual(props["Estimate"], {"select": {"name": expected}})

    def test_number_estimate_android(self):
        fake = FakeNotion(estimate_type="number")
        self.run_write(fake, application="android")
        estimates = {props["Name"]["title"][0]["text"]["content"]: props["Estimate"]
                     for _, props in fake.created}
        self.assertEqual(estimates["15.0b1"], {"number": 2})
        self.assertEqual(estimates["15.0b2"], {"number": 1})
        milestones = {props["Name"]["title"][0]["text"]["content"]: props["Milestones"]["relation"][0]["id"]
                      for _, props in fake.created}
        self.assertEqual(milestones["15.1"], milestone_page("2025 December Releases"))
        # No "TfA " prefix and no "0a1 starts" task
        self.assertEqual(self.created_titles(fake), [
            "merge 15.0a1 main->beta",
            "15.0b1",
            "15.0b2",
            "15.0b3",
            "merge 15.0 beta->release",
            "15.0",
            "15.1",
        ])

    def test_desktop_esr(self):
        self.use_config()
        fake = FakeNotion(milestones=("2026 July Releases",))
        self.use_fake_client(fake)
        schedule = ts.generate_schedule("desktop", "153.0esr", date(2026, 7, 21))
        ts.write_to_notion(schedule, "desktop", "Jane Doe", "153.0esr")
        self.assertEqual(self.created_titles(fake), ["153.0esr", "153.0.1esr"])
        for _, props in fake.created:
            self.assertEqual(props["Milestones"], {"relation": [{"id": milestone_page("2026 July Releases")}]})
            self.assertEqual(props["Estimate"], {"select": {"name": "1"}})

    def test_a1_month_milestone_not_required(self):
        # a1 starts in September, but every task falls in October or November
        fake = FakeNotion(milestones=("2025 October Releases", "2025 November Releases"))
        self.run_write(fake, start_date=date(2025, 9, 25))
        self.assertEqual(len(fake.created), 8)
        looked_up = [f["title"]["equals"] for ds, f in fake.queries if ds == MILESTONES_DS]
        self.assertEqual(looked_up, ["2025 October Releases", "2025 November Releases"])

    def test_skips_existing(self):
        fake = FakeNotion(existing_tasks={"146.0b1", "146.0"})
        self.run_write(fake)
        titles = self.created_titles(fake)
        self.assertEqual(len(titles), 6)
        self.assertNotIn("146.0b1", titles)
        self.assertIn("Skipped (already exists): 2025-11-03 - 146.0b1", self.stderr.getvalue())

    def test_unknown_assignee_writes_nothing(self):
        fake = FakeNotion()
        with self.assertRaises(SystemExit):
            self.run_write(fake, assignee="Nobody")
        self.assertEqual(fake.created, [])

    def test_unknown_team_writes_nothing(self):
        fake = FakeNotion(teams=())
        with self.assertRaises(SystemExit):
            self.run_write(fake)
        self.assertEqual(fake.created, [])

    def test_missing_milestone_writes_nothing(self):
        # The desktop schedule spans October and November; only October exists
        fake = FakeNotion(milestones=("2025 October Releases",))
        with self.assertRaises(SystemExit):
            self.run_write(fake)
        self.assertEqual(fake.created, [])
        self.assertIn("'2025 November Releases' not found", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
