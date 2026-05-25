# Progress

## Milestone 1: Protocol layer
- [x] `error.rs` — Error enum with `Io`, `CommandFailed`, `ProtocolError`, `ParseError`, `ServerNotRunning`
- [x] `protocol.rs` — `Channel` enum, `read_message`, `write_payload`, `write_runcommand`
- [x] Unit tests for protocol (12 tests)

## Milestone 2: Process + Connection
- [x] `process.rs` — `HgProcess::spawn`, `Drop` impl
- [x] `connection.rs` — `Connection::open`, hello parsing, `run_command`, `run_command_string`
- [x] Unit tests for connection (8 tests)

## Milestone 3: High-level API
- [x] `api/types.rs` — `LogEntry`, `StatusEntry`, `FileStatus` with serde deserialization
- [x] `api/mod.rs` — `HgClient`, `HgRepo` trait, argument structs (`LogArgs`, `StatusArgs`, `DiffArgs`)
- [x] `log()` implementation
- [x] `status()` implementation
- [x] `diff()` implementation
- [x] `cat()` implementation
- [x] `summary()` implementation
- [x] `identify()` implementation
- [x] `lib.rs` — public re-exports
- [x] Integration tests (13 tests)

## Milestone 4: Polish
- [x] `docs/design.md`
- [x] `docs/progress.md`
- [x] README
- [x] Crate-level doc comments

## Milestone 5: Expanded API (git2 parity)

### Read operations
- [x] `branches()` — list named branches
- [x] `tags()` — list tags
- [x] `bookmarks()` — list bookmarks
- [x] `annotate()` — file annotation (blame)
- [x] `config()` — list all config entries
- [x] `config_get()` — get a single config value
- [x] `resolve_rev()` — resolve a revspec to a full node hash

### Write operations
- [x] `add()` — stage files for tracking
- [x] `remove()` — mark files for removal
- [x] `commit()` — create a commit, returns node hash
- [x] `update()` — update working directory (with clean option)
- [x] `tag()` — create a tag
- [x] `bookmark()` — create/move a bookmark
- [x] `bookmark_delete()` — delete a bookmark

### Types added
- [x] `BranchEntry`, `TagEntry`, `BookmarkEntry`, `AnnotateResult`, `AnnotateLine`, `ConfigEntry`
- [x] `CommitArgs`, `UpdateArgs`, `AnnotateArgs`

### Tests added
- [x] 5 new unit tests (deserialize branch/tag/bookmark/annotate/config)
- [x] 15 new integration tests

## Future Work
- [ ] Async support behind a feature flag (`tokio::process`, `AsyncRead`/`AsyncWrite`)
- [ ] Streaming API for large outputs (`run_command_streaming` returning an iterator of `ServerMessage`)
- [ ] Connection pooling
- [ ] Graceful shutdown (`close()` method)
- [ ] Additional commands (pull, push, merge, graft, shelve/unshelve, init, clone)
- [ ] CI setup
