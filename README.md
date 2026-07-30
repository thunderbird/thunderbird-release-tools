# thunderbird-release-tools

A collection of tools for automating Thunderbird release engineering tasks.

## Tools

| Tool | Description | Install |
|------|-------------|---------|
|`thunderbird-release-cli` |Automates release tasks: pulling/updating repos, pinning gecko revisions, uplifting commits, and bumping version files | `cargo install --git https://github.com/thunderbird/thunderbird-release-tools --bin thunderbird-release-cli` |
|`bump.sh`|Bumps the specified version number of the branch you are currently on, and commits the change.|Add `releases/scripts/` to PATH|
|`pin.sh`|Pins checkout to the latest version of Firefox on the current branch.|Add `releases/scripts/` to PATH|
|`uplift.sh`|Uplifts the specified changeset to the current checkout with the specified approver.|Add `releases/scripts/` to PATH|