#!/usr/bin/env python3
"""Generate a page of Bugzilla queries for Thunderbird releases, with a tab
per channel (beta, release, ESR).

Versions come from product-details."""

import argparse
import html
import json
import os
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, urlencode

BUGLIST_URL = "https://bugzilla.mozilla.org/buglist.cgi"

# Bugzilla products that Thunderbird bugs are filed under.
THUNDERBIRD_PRODUCTS = [
    "Calendar",
    "Chat Core",
    "MailNews Core",
    "Thunderbird",
    "Enterprise Products",
]

# Columns shown on the uplift request, approved and potential uplift lists,
# before the channel-specific status columns.
UPLIFT_COLUMNS = [
    "bug_type",
    "short_desc",
    "product",
    "component",
    "assigned_to",
    "bug_status",
    "resolution",
    "changeddate",
    "reporter",
    "opendate",
    "bug_severity",
    "status_whiteboard",
    "version",
    "keywords",
    "target_milestone",
]


def thunderbird_versions():
    """Return the current major version of each Thunderbird channel.

    esr_next is an empty string when there is no upcoming ESR.
    """
    url = "https://product-details.mozilla.org/1.0/thunderbird_versions.json"
    with urllib.request.urlopen(url) as response:
        data = json.load(response)
    keys = {
        "daily": "LATEST_THUNDERBIRD_NIGHTLY_VERSION",
        "beta": "LATEST_THUNDERBIRD_DEVEL_VERSION",
        "release": "LATEST_THUNDERBIRD_VERSION",
        "esr": "THUNDERBIRD_ESR",
        "esr_next": "THUNDERBIRD_ESR_NEXT",
    }
    return {name: data[key].split(".")[0] for name, key in keys.items()}


@dataclass
class Match:
    """A single custom search condition (field, operator, value), e.g.:

    - flagtypes.name equals approval-comm-beta?: a pending beta uplift request
    - cf_status_thunderbird_160 equals affected: version 160 is affected
    - bug_group substring core-security: a security bug

    negate inverts the condition, e.g. flagtypes.name equals
    approval-comm-beta? with negate=True: no pending beta uplift request.
    """
    field: str
    operator: str
    value: str
    negate: bool = False


@dataclass
class Group:
    """Conditions combined with AND or OR."""
    join: str
    criteria: list


def all_of(*criteria):
    """A Group matching bugs that meet every one of criteria.

    Each criterion is either a Match (a single condition) or another Group
    from all_of/any_of, which lets AND and OR be combined. For example,
    security bugs that are fixed on 161 or have target milestone 161:

        all_of(
            Match("bug_group", "substring", "core-security"),
            any_of(
                Match("cf_status_thunderbird_161", "substring", "fixed"),
                Match("target_milestone", "substring", "161"),
            ),
        )
    """
    return Group("AND", list(criteria))


def any_of(*criteria):
    """A Group matching bugs that meet at least one of criteria.

    Each criterion is either a Match (a single condition) or another Group
    from all_of/any_of. For example, bugs with a pending beta uplift
    request, or approved for beta but kept open with leave-open:

        any_of(
            Match("flagtypes.name", "equals", "approval-comm-beta?"),
            all_of(
                Match("flagtypes.name", "equals", "approval-comm-beta+"),
                Match("keywords", "substring", "leave-open"),
            ),
        )
    """
    return Group("OR", list(criteria))


def _custom_search_params(top):
    """Translate a Group into Bugzilla's numbered f/o/v/n/j parameters.

    top is the outermost Group: it isn't bracketed, and its join is set
    with j_top. Groups nested inside it are bracketed with OP/CP.

    Each criterion gets the next number (f1, f2, f3, ...). A Match becomes
    field/operator/value (plus n=1 if negated). A nested Group becomes OP
    (open bracket), its criteria, then CP (close bracket); for any_of, the
    OP gets j=OR.

    AND is Bugzilla's default join, so all_of adds no join parameter, at
    the top level or nested. Only any_of does: j_top=OR at the top level,
    j=OR on the OP when nested.
    """
    params = []
    if top.join == "OR":
        params.append(("j_top", "OR"))
    n = 0

    def add(criteria):
        nonlocal n
        for c in criteria:
            n += 1
            if isinstance(c, Group):
                params.append((f"f{n}", "OP"))
                if c.join == "OR":
                    params.append((f"j{n}", "OR"))
                add(c.criteria)
                n += 1
                params.append((f"f{n}", "CP"))
            else:
                params.append((f"f{n}", c.field))
                params.append((f"o{n}", c.operator))
                params.append((f"v{n}", c.value))
                if c.negate:
                    params.append((f"n{n}", "1"))

    add(top.criteria)
    return params


def buglist_url(criteria, **params):
    """Build a Bugzilla bug list (buglist.cgi) URL for an advanced search.

    criteria is a Group (from all_of/any_of) of custom search conditions,
    the "Custom Search" part of Bugzilla's advanced search form. It's
    translated into numbered f/o/v parameters by _custom_search_params.

    params are standard search parameters, passed through by name, e.g.
    product, resolution, columnlist, order, keywords. A list value repeats
    the parameter (product=[A, B] becomes product=A&product=B), which
    Bugzilla treats as "any of these". Different parameters are ANDed with
    each other and with criteria.
    """
    pairs = []
    for name, value in params.items():
        if isinstance(value, list):
            pairs.extend((name, v) for v in value)
        else:
            pairs.append((name, value))
    pairs.extend(_custom_search_params(criteria))
    return f"{BUGLIST_URL}?{urlencode(pairs, quote_via=quote)}"


def status_field(version):
    """The versioned status flag field, e.g. status-thunderbird159.

    Used instead of the rolling status-thunderbird-nightly/beta/release
    fields, which Bugzilla can take a while to move to a new version.
    """
    return f"cf_status_thunderbird_{version}"


def esr_status_field(esr):
    """The ESR status flag field, e.g. status-thunderbird_esr153."""
    return f"cf_status_thunderbird_esr{esr}"


def regression_filter(regression):
    """Search params selecting only regressions, or only non-regressions."""
    return {
        "keywords": "regression",
        "keywords_type": "allwords" if regression else "nowords",
    }


def non_esr_potential_uplifts(channel, fixed_in, affects, regression):
    """Bugs fixed in fixed_in that affect an older version, with no uplift
    to channel (beta or release) requested."""
    return buglist_url(
        all_of(
            Match("target_milestone", "substring", fixed_in),
            Match(status_field(affects), "equals", "affected"),
            Match("flagtypes.name", "equals", f"approval-comm-{channel}?", negate=True),
        ),
        product=THUNDERBIRD_PRODUCTS,
        columnlist=",".join(
            UPLIFT_COLUMNS + [status_field(fixed_in), status_field(affects)]
        ),
        resolution="FIXED",
        order="bug_id",
        **regression_filter(regression),
    )


def esr_potential_uplifts(esr, fixed_in, regression):
    """Bugs fixed in fixed_in that are marked affected for the ESR (either
    status-thunderbird_esr<esr> or status-thunderbird<esr>), with no ESR
    uplift requested."""
    return buglist_url(
        all_of(
            any_of(
                Match(esr_status_field(esr), "equals", "affected"),
                Match(status_field(esr), "equals", "affected"),
            ),
            Match("target_milestone", "anywordssubstr", fixed_in),
            Match("flagtypes.name", "equals", f"approval-comm-esr{esr}?", negate=True),
        ),
        product=THUNDERBIRD_PRODUCTS,
        columnlist=",".join(
            UPLIFT_COLUMNS + [status_field(esr), esr_status_field(esr)]
        ),
        resolution="FIXED",
        order="component",
        **regression_filter(regression),
    )


def cve_columns(beta, release, esr):
    return ",".join(
        [
            "bug_type",
            "short_desc",
            "bug_status",
            "changeddate",
            "opendate",
            "component",
            "target_milestone",
            status_field(beta),
            status_field(release),
            esr_status_field(esr),
        ]
    )


# Excludes bugs marked [no-cve] in the whiteboard: they won't get a CVE.
NOT_NO_CVE = Match("status_whiteboard", "notsubstring", "[no-cve]")


def cve_needed_query(fixed, columns):
    """Security bugs matching the fixed criteria that mention a CVE in
    comments but don't have a CVE alias yet, and aren't marked [no-cve]."""
    return buglist_url(
        all_of(
            Match("bug_group", "substring", "core-security"),
            Match("alias", "notsubstring", "CVE"),
            NOT_NO_CVE,
            fixed,
        ),
        columnlist=columns,
        product=THUNDERBIRD_PRODUCTS,
        resolution="FIXED",
        longdesc="CVE",
        longdesc_type="allwordssubstr",
    )


def can_be_made_public_query(has_cve, columns):
    """Fixed security bugs, which can be made public: those with a CVE
    alias if has_cve, otherwise those without one."""
    return buglist_url(
        all_of(
            Match("bug_group", "substring", "core-security"),
            Match("alias", "substring" if has_cve else "notsubstring", "CVE"),
        ),
        columnlist=columns,
        product=THUNDERBIRD_PRODUCTS,
        resolution="FIXED",
    )


def cve_not_fixed_query(status, columns):
    """Security bugs that mention a CVE in comments and are still affected
    according to the status field, and aren't marked [no-cve]."""
    return buglist_url(
        all_of(
            Match("bug_group", "substring", "core-security"),
            Match(status, "substring", "affected"),
            NOT_NO_CVE,
        ),
        columnlist=columns,
        product=THUNDERBIRD_PRODUCTS,
        resolution="FIXED",
        longdesc="CVE",
        longdesc_type="allwordssubstr",
        order="bug_id",
    )


def security_links(status, milestone, columns):
    """CVE queries for one channel: bugs not fixed yet with a CVE comment,
    and fixed bugs that still need a CVE assigned. A bug also counts as
    fixed if its target milestone matches milestone (when given). Also
    fixed bugs that can be made public, with and without a CVE, which
    aren't channel-specific."""
    fixed = Match(status, "substring", "fixed")
    if milestone:
        fixed = any_of(fixed, Match("target_milestone", "substring", milestone))
    return [
        ("Not yet fixed, with CVE comment", cve_not_fixed_query(status, columns)),
        ("Fixed, needs CVE assigned", cve_needed_query(fixed, columns)),
        (
            "Fixed, CVE assigned, can be made public",
            can_be_made_public_query(True, columns),
        ),
        (
            "Fixed, no CVE, can be made public",
            can_be_made_public_query(False, columns),
        ),
    ]


def _approved_but_not_yet_uplifted(approval, status_field, status_columns, extra=()):
    """Bugs approved for uplift whose status_field isn't fixed yet, or is
    fixed but the bug is leave-open."""
    approved = [
        Match("flagtypes.name", "equals", f"approval-comm-{approval}+"),
        *extra,
    ]
    return buglist_url(
        any_of(
            all_of(*approved, Match(status_field, "nowordssubstr", "fixed verified")),
            all_of(
                *approved,
                Match(status_field, "anywordssubstr", "fixed verified"),
                Match("keywords", "substring", "leave-open"),
            ),
        ),
        product=THUNDERBIRD_PRODUCTS,
        columnlist=",".join(UPLIFT_COLUMNS + status_columns),
        resolution=["---", "FIXED"],
    )


def approved_but_not_yet_uplifted_to_beta(daily, beta):
    return _approved_but_not_yet_uplifted(
        "beta",
        status_field(beta),
        [status_field(daily), status_field(beta)],
        extra=[Match("target_milestone", "substring", daily)],
    )


def approved_but_not_yet_uplifted_to_release(beta, release):
    return _approved_but_not_yet_uplifted(
        "release",
        status_field(release),
        [status_field(beta), status_field(release)],
        extra=[Match(status_field(beta), "anywordssubstr", "fixed verified")],
    )


def approved_but_not_yet_uplifted_to_esr(esr, beta):
    return _approved_but_not_yet_uplifted(
        f"esr{esr}",
        esr_status_field(esr),
        [status_field(beta), esr_status_field(esr)],
    )


def non_esr_uplift_requests(channel, version, status_columns):
    """Bugs with a pending uplift request for channel (beta or release)
    that aren't fixed in version yet."""
    return buglist_url(
        all_of(
            Match("flagtypes.name", "equals", f"approval-comm-{channel}?"),
            Match(status_field(version), "notsubstring", "fixed"),
        ),
        product=THUNDERBIRD_PRODUCTS,
        columnlist=",".join(UPLIFT_COLUMNS + status_columns),
        resolution=["---", "FIXED", "DUPLICATE"],
    )


def esr_uplift_requests(esr, beta):
    """Bugs with a pending ESR uplift request that aren't fixed on ESR yet."""
    return buglist_url(
        all_of(
            Match("flagtypes.name", "equals", f"approval-comm-esr{esr}?"),
            Match(esr_status_field(esr), "notequals", "fixed"),
        ),
        product=THUNDERBIRD_PRODUCTS,
        columnlist=",".join(
            UPLIFT_COLUMNS + [status_field(beta), esr_status_field(esr)]
        ),
        resolution=["---", "FIXED", "DUPLICATE"],
    )


# Open or fixed bugs with a pending relnote-thunderbird? request.
PROPOSED_RELEASE_NOTES_URL = (
    "https://bugzilla.mozilla.org/buglist.cgi?f1=cf_tracking_thunderbird_relnote"
    "&o1=substring&resolution=---&resolution=FIXED&v1=%3F"
    "&order=bug_status,priority,assigned_to,bug_id"
)

# Bugs fixed in the last two months whose target milestone isn't set
# to a Thunderbird branch.
MISSING_TARGET_MILESTONE_URL = (
    "https://bugzilla.mozilla.org/buglist.cgi?query_format=advanced"
    "&classification=Client%20Software&classification=Components"
    "&product=Calendar&product=Chat%20Core&product=MailNews%20Core"
    "&product=Thunderbird&resolution=FIXED"
    "&chfield=resolution&chfieldvalue=fixed&chfieldfrom=2m"
    "&f1=OP&f2=target_milestone&o2=nowordssubstr&v2=thunderbird%20branch&f3=CP"
)


# (description, url) pairs, rendered as a list of links.
Links = list[tuple[str, str]]


@dataclass
class ChannelTab:
    """The links shown on one channel's tab of the page."""
    # Used in the tab's HTML ids (tab-<id>, panel-<id>)
    id: str
    name: str
    uplifts: Links
    potential_caption: str
    # Heading of the potential uplifts table's first column
    potential_column: str
    # (row label, regression url, non-regression url)
    potential: list[tuple[str, str, str]]
    security: Links = field(default_factory=list)
    other: Links = field(default_factory=list)


def beta_tab(versions, sec_columns):
    daily, beta = versions["daily"], versions["beta"]
    return ChannelTab(
        id="beta",
        name=f"Beta {beta}",
        uplifts=[
            (
                "Uplift requested (approval-comm-beta?)",
                non_esr_uplift_requests(
                    "beta", beta, [status_field(daily), status_field(beta)]
                ),
            ),
            (
                "Approved but not yet uplifted",
                approved_but_not_yet_uplifted_to_beta(daily, beta),
            ),
        ],
        potential_caption=(
            f"Bugs fixed in {daily} that affect an older version and have no "
            "approval-comm-beta? request."
        ),
        potential_column="Affects",
        potential=[
            (
                str(version),
                non_esr_potential_uplifts("beta", daily, version, True),
                non_esr_potential_uplifts("beta", daily, version, False),
            )
            for version in reversed(range(int(daily) - 3, int(daily)))
        ],
        security=security_links(status_field(beta), beta, sec_columns),
        other=[
            (
                "Proposed release notes (relnote-thunderbird?)",
                PROPOSED_RELEASE_NOTES_URL,
            ),
            ("Missing target milestone", MISSING_TARGET_MILESTONE_URL),
        ],
    )


def release_tab(versions, sec_columns):
    beta, release = versions["beta"], versions["release"]
    return ChannelTab(
        id="release",
        name=f"Release {release}",
        uplifts=[
            (
                "Uplift requested (approval-comm-release?)",
                non_esr_uplift_requests(
                    "release", release, [status_field(beta), status_field(release)]
                ),
            ),
            (
                "Approved but not yet uplifted",
                approved_but_not_yet_uplifted_to_release(beta, release),
            ),
        ],
        potential_caption=(
            f"Bugs fixed in {beta} that affect an older version and have no "
            "approval-comm-release? request."
        ),
        potential_column="Affects",
        potential=[
            (
                str(version),
                non_esr_potential_uplifts("release", beta, version, True),
                non_esr_potential_uplifts("release", beta, version, False),
            )
            for version in reversed(range(int(beta) - 3, int(beta)))
        ],
        security=security_links(status_field(release), release, sec_columns),
    )


def esr_tab(esr, versions, sec_columns=None):
    """The tab for an ESR. Security links are only included when
    sec_columns is given (for the current ESR, not the upcoming one)."""
    daily, beta = versions["daily"], versions["beta"]
    return ChannelTab(
        id=f"esr{esr}",
        name=f"ESR {esr}",
        uplifts=[
            (
                f"Uplift requested (approval-comm-esr{esr}?)",
                esr_uplift_requests(esr, beta),
            ),
            (
                "Approved but not yet uplifted",
                approved_but_not_yet_uplifted_to_esr(esr, beta),
            ),
        ],
        potential_caption=(
            f"Bugs fixed in each version that affect {esr}esr: the esr{esr} or "
            f"{esr} status is affected, and there's no approval-comm-esr{esr}? "
            "request."
        ),
        potential_column="Fixed in",
        potential=[
            (
                str(version),
                esr_potential_uplifts(esr, version, True),
                esr_potential_uplifts(esr, version, False),
            )
            for version in reversed(range(int(esr) + 1, int(daily) + 1))
        ],
        security=(
            security_links(esr_status_field(esr), None, sec_columns)
            if sec_columns
            else []
        ),
    )


TITLE = "Thunderbird Bugzilla queries"

PAGE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2em auto;
         max-width: 1000px; padding: 0 1em; }}
  a {{ color: #105bbc; }}
  table {{ border-collapse: collapse; }}
  th, td {{ padding: 0.2em 1.5em 0.2em 0; text-align: left; }}
  th {{ border-bottom: 1px solid #e4e4e7; }}
  h2 {{ font-size: 1.1em; margin-top: 1.5em; }}
</style>
</head>
<body>
"""

PAGE_FOOT = """</body>
</html>
"""

# With --jekyll: the site's layout supplies the page and styles.
JEKYLL_HEAD = """---
layout: default
title: {title}
---
"""

# Tabs without JavaScript: a radio button per tab, each showing its panel
# when checked. Used by both the standalone page and the Jekyll page.
TABS_STYLE = """<style>
  .versions {{ margin-bottom: 1em; }}
  /* Equal percentage widths make every column as wide as the widest. */
  .versions th, .versions td {{ width: {version_width}; text-align: left; }}
  .tabs > input {{ position: absolute; opacity: 0; }}
  .tabs > label {{ display: inline-block; padding: 0.4em 1em;
                  cursor: pointer; border-bottom: 2px solid transparent; }}
  .tabs > input:checked + label {{ border-bottom-color: currentColor;
                                  font-weight: 600; }}
  .tabs > input:focus-visible + label {{ outline: 2px solid; }}
  .tabs > section {{ display: none; border-top: 1px solid #e4e4e7;
                    padding-top: 0.5em; }}
  {panel_rules} {{ display: block; }}
</style>
"""

PAGE_BODY = """<h1>{title}</h1>
<h2>What train is it now?</h2>
{versions}
<div class="tabs">
{tabs}
</div>
<p>Generated {generated}.</p>
"""


def _link(text, url):
    return f'<a href="{html.escape(url)}" target="_blank">{html.escape(text)}</a>'


def _link_list(links):
    items = "\n".join(f"<li>{_link(text, url)}</li>" for text, url in links)
    return f"<ul>\n{items}\n</ul>"


def _panel_html(tab):
    rows = "\n".join(
        f"<tr><td>{html.escape(label)}</td>"
        f"<td>{_link('regressions', regression)}</td>"
        f"<td>{_link('non-regressions', non_regression)}</td></tr>"
        for label, regression, non_regression in tab.potential
    )
    parts = [
        "<h2>Uplift requests</h2>",
        _link_list(tab.uplifts),
        "<h2>Potential uplifts</h2>",
        f"<p>{html.escape(tab.potential_caption)}</p>",
        "<table>",
        f"<tr><th>{html.escape(tab.potential_column)}</th>"
        "<th>Regressions</th><th>Non-regressions</th></tr>",
        rows,
        "</table>",
    ]
    if tab.security:
        parts += ["<h2>Security</h2>", _link_list(tab.security)]
    if tab.other:
        parts += ["<h2>Other</h2>", _link_list(tab.other)]
    return "\n".join(parts)


def render_html(output_file, versions, tabs, jekyll=False):
    """Write the page: a tab per channel, the first one selected.

    With jekyll, write it as a page for a Jekyll site (front matter for the
    site's layout, no <html> wrapper) instead of a standalone page.
    """
    # Radio buttons and labels first, then the panels, so CSS can select
    # each checked button's panel as a later sibling.
    tab_html = [
        f'<input type="radio" name="tab" id="tab-{tab.id}"'
        f'{" checked" if i == 0 else ""}>'
        f'<label for="tab-{tab.id}">{html.escape(tab.name)}</label>'
        for i, tab in enumerate(tabs)
    ]
    tab_html += [
        f'<section id="panel-{tab.id}">\n{_panel_html(tab)}\n</section>'
        for tab in tabs
    ]
    panel_rules = ",\n  ".join(
        f"#tab-{tab.id}:checked ~ #panel-{tab.id}" for tab in tabs
    )
    version_rows = [
        ("Daily", versions["daily"]),
        ("Beta", versions["beta"]),
        ("Release", versions["release"]),
        ("ESR", versions["esr"]),
    ]
    if versions["esr_next"]:
        version_rows.append(("ESR next", versions["esr_next"]))
    version_html = "\n".join(
        [
            '<table class="versions">',
            "<tr>"
            + "".join(f"<th>{html.escape(label)}</th>" for label, _ in version_rows)
            + "</tr>",
            "<tr>"
            + "".join(f"<td>{html.escape(version)}</td>" for _, version in version_rows)
            + "</tr>",
            "</table>",
        ]
    )
    if jekyll:
        template = JEKYLL_HEAD + TABS_STYLE + PAGE_BODY
    else:
        template = PAGE_HEAD + TABS_STYLE + PAGE_BODY + PAGE_FOOT
    with open(output_file, "w", encoding="utf-8") as file:
        file.write(
            template.format(
                title=TITLE,
                versions=version_html,
                tabs="\n".join(tab_html),
                generated=date.today(),
                panel_rules=panel_rules,
                version_width=f"{100 / len(version_rows):g}%",
            )
        )
    print(f"HTML file generated at {output_file}")


def print_versions(versions):
    rows = [
        ("daily version", versions["daily"]),
        ("beta version", versions["beta"]),
        ("release version", versions["release"]),
        ("esr version", versions["esr"]),
    ]
    if versions["esr_next"]:
        rows.append(("esr next version", versions["esr_next"]))
    width = max(len(label) for label, _ in rows)
    for label, version in rows:
        print(f"{label:<{width}}  {version}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a page of Bugzilla queries for Thunderbird releases."
    )
    parser.add_argument(
        "--jekyll",
        action="store_true",
        help="write the page for a Jekyll site (for publishing to "
        "thunderbird-release-docs) and don't open it in a browser",
    )
    args = parser.parse_args()

    versions = thunderbird_versions()
    print_versions(versions)

    sec_columns = cve_columns(versions["beta"], versions["release"], versions["esr"])
    tabs = [
        beta_tab(versions, sec_columns),
        release_tab(versions, sec_columns),
        esr_tab(versions["esr"], versions, sec_columns),
    ]
    if versions["esr_next"]:
        tabs.append(esr_tab(versions["esr_next"], versions))

    output_file = os.path.join(os.getcwd(), "bugzilla-queries.html")
    render_html(output_file, versions, tabs, jekyll=args.jekyll)
    if not args.jekyll:
        webbrowser.open(f"file://{output_file}")


if __name__ == "__main__":
    main()
