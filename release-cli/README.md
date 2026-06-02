# release

A Rust CLI for automating Thunderbird release cuts.

## What it does

`release-cli` automates the steps needed to cut a Thunderbird release across the `comm` and `mozilla` Mercurial repositories:

- **pull-update** — pulls both repos and updates to the tip of their branch
- **pin** — pins `.gecko_rev.yml` to the latest Mozilla tag for the current major version and commits the result
- **uplift** — dry-runs, grafts, and rewrites the commit message (including approver) for one or more commits
- **update-version** — bumps `mail/config/version.txt` and `mail/config/version_display.txt` and commits the result
- **rust-check-upstream** — checks whether Rust dependencies are in sync with upstream via `./mach tb-rust check-upstream`
- **rust-sync** — syncs Rust dependencies with upstream via `./mach tb-rust sync`
- **rust-vendor** — vendors Rust dependencies via `./mach tb-rust vendor`
- **all** — runs the full workflow: pull-update, pin, update-version (ESR only), rust sync+vendor if needed, then uplift

## Prerequisites

- Rust toolchain
- A local Thunderbird checkout with `comm/` nested inside the mozilla directory
- Mercurial with the `histedit`, `evolve`, and `firefoxtree` extensions enabled (required for `uplift`)

## Installation

```sh
cargo install --git https://github.com/kryoseu/thunderbird-release-cli --bin release-cli
```

This should add the binary to the `~/.cargo/bin/` path.

## Usage

```
release-cli <SUBCOMMAND> --comm-dir <PATH> --channel <beta|release|esr> [--version <N>]
```

### Common args

| Arg | Description |
|------|-------------|
| `-d, --comm-dir <PATH>` | Path to the `comm/` directory inside the mozilla repo |
| `-c, --channel <CHANNEL>` | Release channel: `beta`, `release`, or `esr` |
| `-v, --version <N>` | Major version number. Required for `esr` channel and the `update-version` and `all` subcommands. For ESR, pass either `140` or `140esr` — the `esr` suffix is written to `version_display.txt` and stripped for `version.txt` |

### Examples

```sh
# Pull and update both the comm and mozilla repos to the tip of their branch
release-cli pull-update --comm-dir ~/src/comm --channel beta

# Pin gecko rev on the beta channel
release-cli pin --comm-dir ~/src/comm --channel beta

# Uplift two commits on release (--approver is required)
release-cli uplift --comm-dir ~/src/comm --channel release --approver kryoseu --revs abc123 def456

# Bump version files for ESR 140 (accepts "140" or "140esr")
release-cli update-version --comm-dir ~/src/comm --channel esr --version 140esr

# Check whether Rust dependencies are in sync with upstream
release-cli rust-check-upstream --comm-dir ~/src/comm --channel release

# Sync Rust dependencies with upstream
release-cli rust-sync --comm-dir ~/src/comm --channel release

# Vendor Rust dependencies
release-cli rust-vendor --comm-dir ~/src/comm --channel release

# Run the full release workflow for ESR 140
release-cli all --comm-dir ~/src/comm --channel esr --version 140esr --approver kryoseu --revs abc123 def456
```

## Workspace crates

| Crate | Purpose |
|-------|---------|
| `release-cli` | CLI binary and release orchestration |
| [hg-client](https://github.com/ericmarkmartin/hg-client/commit/2dc80c5c0219b54eb28f9d40f8e00336b3153093) | Mercurial command server client |
| `mach` | Thin wrapper around `./mach` commands |
