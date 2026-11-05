# Thunderbird Bugzilla queries

Links to the Bugzilla queries used to manage Thunderbird releases, with a tab
per channel (Beta, Release, ESR).

`bugzilla-queries.py` builds the queries for the current versions and writes
them to a page.

The page is published on the
[Thunderbird Release Docs](https://github.com/thunderbird/thunderbird-release-docs)
site, which regenerates it daily.

## Usage

Run it as a `tb-release` subcommand (see the [repository README](../../README.md)
to install `tb-release`):

```sh
tb-release bugzilla-queries
```

This writes `bugzilla-queries.html` to the current directory and opens it in
your browser.

| Option | Effect |
|---|---|
| `--jekyll` | Write `bugzilla-queries.html` as a page for a Jekyll site (for publishing to thunderbird-release-docs), without opening a browser |

## Queries

Each channel's tab has:

- **Uplift requests:** bugs with a pending `approval-comm-<channel>?` request
  that aren't fixed on the channel yet, and bugs approved for uplift
  (`approval-comm-<channel>+`) that haven't landed.
- **Potential uplifts:** bugs fixed in a newer version that affect the channel
  and have no uplift request, split into regressions and non-regressions.
- **Security:** security bugs with a CVE comment that aren't fixed on the
  channel yet, and fixed security bugs that still need a CVE assigned. Not
  shown for the upcoming ESR.
- **Other** (Beta only): open or fixed bugs with a pending
  `relnote-thunderbird?` request, and bugs fixed in the last two months whose
  target milestone isn't a Thunderbird branch.

When product-details lists an upcoming ESR, it gets a tab too.

Queries cover Calendar, Chat Core, MailNews Core, Thunderbird and
Enterprise Products.

## Data sources

- Versions: [product-details](https://product-details.mozilla.org/1.0/thunderbird_versions.json)
- Queries: [bugzilla.mozilla.org](https://bugzilla.mozilla.org/)
