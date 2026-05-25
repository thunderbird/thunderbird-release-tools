# Design: hg-cmdserver-rs

## Context

There's no Rust equivalent of git2 for Mercurial. The only option today is spawning `hg` as a subprocess per command, which is slow due to Python/repo init overhead. Mercurial's command server protocol (`hg serve --cmdserver pipe`) keeps a persistent process and amortizes startup cost. This library wraps that protocol in an ergonomic Rust API.

## Crate Structure

```
hg-cmdserver-rs/
  Cargo.toml
  src/
    lib.rs              -- re-exports, crate docs
    error.rs            -- Error enum, Result alias
    protocol.rs         -- wire format: Channel, read_message, write_runcommand
    process.rs          -- spawn hg, own Child, Drop kills it
    connection.rs       -- Connection: hello parsing + run_command
    api/
      mod.rs            -- HgRepo trait, HgClient, argument structs
      types.rs          -- LogEntry, StatusEntry, etc. (serde)
  tests/
    integration.rs      -- requires hg on PATH, uses tempfile repos
```

## Architecture

### Layer 1: Protocol (`protocol.rs`)

Low-level wire format operating on generic `Read`/`Write` traits:

- **Server→Client messages**: 1-byte channel + 4-byte BE u32 length + payload
  - `o` (Output), `e` (Error), `r` (Result), `I` (InputReq), `L` (LineInputReq), `d` (Debug)
- **Client→Server**: 4-byte BE u32 length + payload
- **runcommand**: `"runcommand\n"` + length-prefixed null-separated args

Using generic traits makes this layer unit-testable with `Cursor<Vec<u8>>` — no hg process needed.

### Layer 2: Process (`process.rs`)

`HgProcess` spawns `hg serve --cmdserver pipe`, owns the `Child` + piped stdin/stdout. `Drop` kills the child and waits to prevent zombies.

### Layer 3: Connection (`connection.rs`)

`Connection` ties process + protocol together:
- `open(repo_path)` — spawns the server, reads and parses the hello message
- `run_command(args)` — sends runcommand, loops reading messages, collects output, returns on result channel
- `run_command_string(args)` — convenience that errors on nonzero exit

### Layer 4: High-level API (`api/`)

`HgClient` owns a `Connection` and implements the `HgRepo` trait:
- `log(LogArgs)` → `Vec<LogEntry>` — uses `-T json` for structured output
- `status(StatusArgs)` → `Vec<StatusEntry>` — uses `-T json`
- `diff(DiffArgs)` → `String` — raw diff output
- `cat(file, rev)` → `Vec<u8>` — file contents
- `summary()` → `String`
- `identify()` → `String`

## Key Design Decisions

- **Sync-first, async later.** Start with sync for simplicity. Async is genuinely useful (non-blocking for async consumers, cancellation, multi-connection concurrency), but the protocol layer uses generic `Read`/`Write` traits which will translate naturally to `AsyncRead`/`AsyncWrite` later. Async support can be added behind a feature flag without breaking the sync API.
- **`-T json` for structured output.** Avoids parsing locale-dependent human output. Commands without JSON support (diff) return raw strings.
- **`HgRepo` trait.** Enables mocking in downstream code and future alternative backends.
- **Argument structs with `Default`** instead of builders. `LogArgs { limit: Some(10), ..Default::default() }` is idiomatic and avoids boilerplate.
- **`Drop` kills child.** Prevents zombie processes. Explicit `close()` can be added later for graceful shutdown.
- **No connection pooling.** One connection per `HgClient`. Users open multiple clients for concurrency. Simple, no mutex complexity.
- **No streaming initially.** `run_command` collects all output into memory. Streaming iterator can be layered on later.

## Dependencies

```toml
[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
thiserror = "2"

[dev-dependencies]
tempfile = "3"
```

## Testing Strategy

- **Unit tests (no hg):** Protocol read/write with `Cursor<Vec<u8>>`, hello parsing, JSON deserialization of hardcoded strings
- **Integration tests (hg on PATH):** Create temp repos with `hg init` + commits, open `HgClient`, test log/status/diff/cat. Skip if hg not found.
