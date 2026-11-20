# thunderbird-release-tools

A collection of tools for automating Thunderbird release engineering tasks.

## tb-release

`tb-release` runs the non-Rust scripts in this repository as subcommands.
The Rust `thunderbird-release-cli` is a separate tool, installed with `cargo`.

Install `tb-release`:

```sh
uv tool install git+https://github.com/thunderbird/thunderbird-release-tools
```

## Tools

| Tool | Description | Install |
|------|-------------|---------|
|`thunderbird-release-cli` |Automates release tasks: pulling/updating repos, pinning gecko revisions, uplifting commits, and bumping version files | `cargo install --git https://github.com/thunderbird/thunderbird-release-tools --bin thunderbird-release-cli` |
|`tb-release bump`|Bumps the specified version number of the branch you are currently on, and commits the change.|`tb-release`|
|`tb-release pin`|Pins checkout to the latest version of Firefox on the current branch.|`tb-release`|
|`tb-release prep`|Switches to a branch and makes sure the working copy is synced to the branch's remote tip.|`tb-release`|
|`tb-release uplift`|Uplifts the specified changeset to the current checkout with the specified approver.|`tb-release`|
|`tb-release bugzilla-queries`|Generates a page of Bugzilla queries for release management.|`tb-release`|
|`tb-release check-langpacks`|Checks the brand name and version of language packs that ATN offers.|`tb-release`|
|`tb-release on-schedule`|Generates a report on how often desktop releases ship on schedule.|`tb-release`|
|`tb-release schedule`|Generates a Desktop, Desktop ESR, or Android release schedule, and optionally writes it to Google Calendar and Notion.|`tb-release`|
|`tb-release strip-partials`|Strips partial updates from a Balrog release blob.|`tb-release`|

## Development

### Python dependencies and `uv.lock`

`uv.lock` pins the exact version of every Python dependency of `tb-release`,
including indirect ones, so every development environment gets the same
packages. It only affects `uv run` and `uv sync` in a checkout;
`uv tool install` ignores it and installs the newest versions allowed by
`pyproject.toml`.

To add or change a dependency:

1. Edit `dependencies` in `pyproject.toml`.
2. Update the lock file:
   ```sh
   uv lock
   ```
   `uv run` also updates it automatically if it's out of date.
3. Commit `pyproject.toml` and `uv.lock` together.

Other lock file tasks:

- **Upgrade all dependencies:** `uv lock --upgrade`, then run the tests and
  commit `uv.lock`.
- **Upgrade one dependency:** `uv lock --upgrade-package <name>`.
- **Check the lock matches `pyproject.toml`:** `uv lock --check`. CI runs this
  for every change to `pyproject.toml` or `uv.lock`.

Dependabot also opens weekly pull requests to upgrade the locked versions.
