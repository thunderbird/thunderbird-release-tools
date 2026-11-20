import io
import sys
import unittest
import urllib.parse
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_langpacks as cl  # noqa: E402


def make_xpi(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


BRAND_PATH = "chrome/de/locale/branding/brand.properties"


class BrandFromXpiTest(unittest.TestCase):
    def test_reads_brand_short_name(self):
        xpi = make_xpi(
            {
                "manifest.json": "{}",
                BRAND_PATH: "brandShorterName=TB\r\nbrandShortName = Thunderbird Beta \r\n",
            }
        )
        self.assertEqual(cl.brand_from_xpi(xpi), "Thunderbird Beta")

    def test_file_missing(self):
        xpi = make_xpi({"chrome/de/locale/other/brand.properties": "brandShortName=X"})
        self.assertEqual(cl.brand_from_xpi(xpi), cl.FILE_MISSING)

    def test_not_found(self):
        xpi = make_xpi({BRAND_PATH: "brandFullName=Mozilla Thunderbird\n"})
        self.assertEqual(cl.brand_from_xpi(xpi), cl.NOT_FOUND)

    def test_not_a_zip(self):
        with self.assertRaises(zipfile.BadZipFile):
            cl.brand_from_xpi(b"not a zip")


class HelpersTest(unittest.TestCase):
    def test_display_name(self):
        self.assertEqual(cl.display_name("thunderbird-langpack-de"), "de")
        self.assertEqual(cl.display_name("deutsch"), "deutsch")

    def test_human_name(self):
        addon = {"name": {"en-US": "Deutsch (DE) Language Pack for Thunderbird"}}
        self.assertEqual(cl.human_name(addon), "Deutsch (DE)")
        self.assertEqual(cl.human_name({"name": {"fr": "Français"}}), "Français")
        self.assertEqual(cl.human_name({"name": None}), "")

    def test_bust_cache_keeps_query(self):
        url = cl.bust_cache("https://example.com/v/?page=2&page_size=50")
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.assertEqual(query["page"], "2")
        self.assertEqual(query["page_size"], "50")
        self.assertTrue(query["_t"].isdigit())

    def test_summarize_ignores_invalid_brands(self):
        results = [
            {"brand": "Thunderbird"},
            {"brand": cl.FILE_MISSING},
            {"brand": "Thunderbird Beta"},
            {"brand": "Thunderbird"},
        ]
        s = cl.summarize("de", results, "149.0 (Thunderbird)")
        self.assertEqual(s["brands"], ["Thunderbird", "Thunderbird Beta"])
        self.assertTrue(s["multiple"])
        s = cl.summarize("de", [{"brand": cl.NOT_FOUND}], "N/A")
        self.assertEqual(s["brands"], [])
        self.assertFalse(s["multiple"])


def summary(locale, brands):
    return {
        "locale": locale,
        "brands": brands,
        "multiple": len(brands) >= 2,
        "default_version": "149.0",
    }


class SummaryTableTest(unittest.TestCase):
    def test_sort_full(self):
        summaries = [
            summary("a", ["Thunderbird", "Thunderbird Beta"]),
            summary("b", ["Thunderbird"]),
            summary("c", []),
        ]
        order = [s["locale"] for s in cl.sort_summaries(summaries, False)]
        self.assertEqual(order, ["c", "b", "a"])

    def test_sort_default_only(self):
        summaries = [
            summary("a", ["Thunderbird"]),
            summary("b", ["Thunderbird Beta"]),
            summary("c", []),
        ]
        order = [s["locale"] for s in cl.sort_summaries(summaries, True)]
        self.assertEqual(order, ["c", "b", "a"])

    def test_format_table(self):
        table = cl.format_summary_table(
            [summary("de", ["Thunderbird", "Thunderbird Beta"])], False
        )
        self.assertEqual(
            table.splitlines(),
            [
                " Locale │ Multiple │ ATN Default │ Brands found                  ",
                "────────┼──────────┼─────────────┼───────────────────────────────",
                " de     │ yes      │ 149.0       │ Thunderbird, Thunderbird Beta ",
                "────────┼──────────┼─────────────┼───────────────────────────────",
            ],
        )


if __name__ == "__main__":
    unittest.main()
