//! Thunderbird release automation CLI.
//!
//! Automates the steps needed to cut a Thunderbird release:
//! pulling the comm and mozilla repos, pinning `.gecko_rev.yml`
//! to the appropriate Mozilla tag, grafting uplift commits, and
//! bumping version files.

mod channel;
mod cli;
mod commands;
mod error;
mod pin;
mod repo;
mod utils;

use crate::cli::Cli;
use tracing::level_filters::LevelFilter;
use tracing_subscriber::EnvFilter;

fn main() {
    // Default to INFO; override with RUST_LOG env var.
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::builder()
                .with_default_directive(LevelFilter::INFO.into())
                .from_env_lossy(),
        )
        .init();

    if let Err(e) = Cli::run() {
        tracing::error!("{e}");
        std::process::exit(1);
    }
}
