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
|`tb-release strip-partials`|Strips partial updates from a Balrog release blob.|`tb-release`|
|`tb-release on-schedule`|Generates a report on how often desktop releases ship on schedule.|`tb-release`|
