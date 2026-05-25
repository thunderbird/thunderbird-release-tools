# hg-cmdserver

A Rust client for the Mercurial command server protocol.

Instead of spawning a new `hg` process for every command (paying Python startup + repo loading each time), this library keeps a persistent command server process and communicates over its binary protocol. This is analogous to what [git2](https://crates.io/crates/git2) provides for Git via libgit2, but using Mercurial's built-in command server rather than FFI bindings.

## Usage

```rust
use hg_cmdserver::{HgClient, HgRepo};
use hg_cmdserver::api::{LogArgs, StatusArgs, DiffArgs};

let mut client = HgClient::open("/path/to/repo")?;

// Structured log output
let entries = client.log(LogArgs {
    limit: Some(5),
    ..Default::default()
})?;
for entry in &entries {
    println!("{}: {}", entry.rev, entry.desc);
}

// Working directory status
let status = client.status(StatusArgs::default())?;
for file in &status {
    println!("{} {}", file.status, file.path);
}

// Diff
let diff = client.diff(DiffArgs::default())?;
println!("{diff}");

// File contents at a specific revision
let content = client.cat("README.md".as_ref(), Some("tip"))?;

// Raw commands via the underlying connection
let output = client.connection().run_command(&["branches"])?;
println!("{}", String::from_utf8_lossy(&output.stdout));
```

## Requirements

- Mercurial (`hg`) must be installed and available on `PATH`.

## License

MIT
