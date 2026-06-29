//! A Rust client for the Mercurial command server protocol.
//!
//! This crate communicates with Mercurial via its
//! [command server](https://wiki.mercurial-scm.org/CommandServer) protocol,
//! keeping a persistent `hg` process to amortize startup cost across
//! multiple operations.
//!
//! # Quick start
//!
//! ```no_run
//! use hg_cmdserver::{HgClient, HgRepo};
//! use hg_cmdserver::api::LogArgs;
//!
//! let mut client = HgClient::open("/path/to/repo").unwrap();
//! let entries = client.log(LogArgs::default()).unwrap();
//! for entry in &entries {
//!     println!("{}: {}", entry.rev, entry.desc);
//! }
//! ```
//!
//! For raw command access, use [`Connection::run_command`] directly:
//!
//! ```no_run
//! use hg_cmdserver::Connection;
//!
//! let mut conn = Connection::open("/path/to/repo".as_ref()).unwrap();
//! let output = conn.run_command(&["branches"]).unwrap();
//! println!("{}", String::from_utf8_lossy(&output.stdout));
//! ```

pub mod api;
pub mod connection;
pub mod error;
pub mod process;
pub mod protocol;

pub use api::{HgClient, HgRepo};
pub use connection::Connection;
pub use error::{Error, Result};
