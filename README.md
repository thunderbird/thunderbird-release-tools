# release

A Rust CLI for automating Thunderbird release cuts.

## What it does

`release` automates the steps needed to cut a Thunderbird release across the `comm` and `mozilla` Mercurial repositories:

- **pull-update** — pulls both repos and updates to the tip of their branch
- **pin** — pins `.gecko_rev.yml` to the latest Mozilla tag for the current major version and commits the result
- **uplift** — grafts one or more commits onto the current branch, normalizing commit messages and stamping an approver
- **update-version** — bumps `mail/config/version.txt` and `mail/config/version_display.txt` and commits the result
- **rust-check-upstream** — checks whether Rust dependencies are in sync with upstream via `./mach tb-rust check-upstream`
- **rust-sync** — syncs Rust dependencies with upstream via `./mach tb-rust sync`
- **rust-vendor** — vendors Rust dependencies via `./mach tb-rust vendor`

## Prerequisites

- Rust toolchain
- A local Thunderbird checkout with `comm/` nested inside the mozilla directory
- Mercurial with the `histedit`, `evolve`, and `firefoxtree` extensions enabled (required for `uplift`)

## Installation

```sh
cargo install --git https://github.com/kryoseu/thunderbird-release-cli
```

This should add the binary to the `~/.cargo/bin/` path.

## Usage

```
release <SUBCOMMAND> --comm-dir <PATH> --channel <beta|release|esr> [--version <N>]
```

### Common args

| Arg | Description |
|------|-------------|
| `-d, --comm-dir <PATH>` | Path to the `comm/` directory inside the mozilla repo |
| `-c, --channel <CHANNEL>` | Release channel: `beta`, `release`, or `esr` |
| `-v, --version <N>` | Major version number. Required for `esr` channel and the `update-version` subcommand. For ESR, pass either `128` or `128esr` — the `esr` suffix is written to `version_display.txt` and stripped for `version.txt` |

### Examples

```sh
# Pull and update both the comm and mozilla repos to the tip of their branch
release pull-update --comm-dir ~/src/comm --channel beta

# Pin gecko rev on the beta channel
release pin --comm-dir ~/src/comm --channel beta

# Uplift two commits on release (--approver is required)
release uplift --comm-dir ~/src/comm --channel release --approver kryoseu --uplifts abc123 def456

# Bump version files for ESR 128 (accepts "128" or "128esr")
release update-version --comm-dir ~/src/comm --channel esr --version 128esr

# Check whether Rust dependencies are in sync with upstream
release rust-check-upstream --comm-dir ~/src/comm --channel release

# Sync Rust dependencies with upstream
release rust-sync --comm-dir ~/src/comm --channel release

# Vendor Rust dependencies
release rust-vendor --comm-dir ~/src/comm --channel release
```

## Workspace crates

| Crate | Purpose |
|-------|---------|
| `release` | CLI binary and release orchestration |
| `hg-client` | Mercurial command server client |
| `mach` | Thin wrapper around `./mach` commands |
