use std::path::PathBuf;

use clap::{Args, Parser, Subcommand};
use mach::commands::MachCommand;

use crate::{
    channel::Channel,
    commands::{pin, pull_update, run_mach, update_version, uplifts},
    error::{CliError, Result},
    utils::build_repos_from_args,
};

#[derive(Parser, Debug)]
#[command(
    disable_version_flag = true,
    about = "Thunderbird release automation tool",
    long_about = None,
    after_help = "\
Examples:
  # Pull and update both repos to the tip of their branch
  release pull-update --comm-dir ~/src/comm --channel beta

  # Pin gecko rev on the beta channel
  release pin --comm-dir ~/src/comm --channel beta

  # Uplift two commits on release
  release uplift --comm-dir ~/src/comm --channel release --approver kryoseu --revs abc123 def456

  # Bump version files on ESR 140
  release update-version --comm-dir ~/src/comm --channel esr --version 140

  # Check which Rust dependencies are in sync with upstream
  release rust-check-upstream --comm-dir ~/src/comm --channel release

  # Sync Rust dependencies with upstream
  release rust-sync --comm-dir ~/src/comm --channel release

  # Vendor Rust dependencies
  release rust-vendor --comm-dir ~/src/comm --channel release

  # Run the full release workflow
  release all --comm-dir ~/src/comm --channel esr --version 140 --approver kryoseu --revs abc123 def456"
)]
struct CliArgs {
    #[command(subcommand)]
    command: Command,
}

#[derive(Args, Debug)]
pub struct CommonArgs {
    /// Path to the comm repo inside the mozilla repo.
    ///
    /// Standard checkout layout has comm/ nested directly inside the
    /// mozilla directory, so the mozilla repo is inferred as the parent
    /// of this path.
    #[arg(short = 'd', long)]
    pub comm_dir: PathBuf,
    /// Release channel: beta, release, or esr
    #[arg(short, long)]
    pub channel: Channel,
    /// Version being released (e.g. "152").
    ///
    /// Required when --channel esr, and for the update-version and
    /// release subcommands.
    #[arg(short, long)]
    pub version: Option<String>,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Pull and update both the comm and mozilla repos to the tip of their branch.
    PullUpdate {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Pin .gecko_rev.yml to the most recent suitable Mozilla tag.
    ///
    /// Pulls both the comm and mozilla repos, determines the latest tag
    /// for the current major version, and commits the updated
    /// .gecko_rev.yml in the comm repo.
    Pin {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Graft one or more commits onto the current branch.
    ///
    /// Dry-runs each graft first, then grafts and rewrites the commit
    /// message to include the approver. At least one revision is required.
    Uplift {
        #[command(flatten)]
        common: CommonArgs,
        /// Reviewer to stamp onto each grafted commit (e.g. "jsmith").
        #[arg(short, long)]
        approver: String,
        #[arg(short, long, num_args = 1.., required = true)]
        revs: Vec<String>,
    },
    /// Check which Rust dependencies are out of sync with upstream.
    ///
    /// Runs ./mach tb-rust check-upstream
    RustCheckUpstream {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Sync Rust dependencies with upstream
    ///
    /// Runs ./mach tb-rust sync
    RustSync {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Vendor Rust dependencies
    ///
    /// Runs ./mach tb-rust vendor
    RustVendor {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Update version.txt and version_display.txt.
    ///
    /// Requires --version. Writes the new version string into both
    /// version files and commits the result.
    UpdateVersion {
        #[command(flatten)]
        common: CommonArgs,
    },
    /// Run the full release workflow in sequence.
    ///
    /// Pulls and updates both repos, pins .gecko_rev.yml, bumps version files
    /// (ESR only), syncs and vendors Rust dependencies if they are out of sync,
    /// then grafts each uplift commit.
    All {
        #[command(flatten)]
        common: CommonArgs,
        #[arg(short, long)]
        approver: String,
        #[arg(short, long, num_args = 1.., required = true)]
        revs: Vec<String>,
    },
}

pub struct Cli;

impl Cli {
    pub fn run() -> Result<()> {
        let cli = CliArgs::parse();

        match cli.command {
            Command::Pin { common } => pin(&common)?,
            Command::PullUpdate { common } => pull_update(&common)?,
            Command::UpdateVersion { common } => {
                let version = common
                    .version
                    .as_deref()
                    .ok_or(CliError::MissingArgument("--version"))?;

                update_version(&common, version)?;
            }
            Command::RustSync { common } => {
                run_mach(&common, MachCommand::RustSync)?;
            }
            Command::RustVendor { common } => {
                run_mach(&common, MachCommand::RustVendor)?;
            }
            Command::RustCheckUpstream { common } => {
                run_mach(&common, MachCommand::RustCheckUpstream)?;
            }
            Command::Uplift {
                common,
                approver,
                revs,
            } => uplifts(&common, &approver, &revs)?,

            Command::All {
                common,
                approver,
                revs,
            } => {
                let version = common
                    .version
                    .as_deref()
                    .ok_or(CliError::MissingArgument("--version"))?;

                let repositories = build_repos_from_args(&common)?;
                let c_repo = repositories.comm();

                pull_update(&common)?;
                pin(&common)?;

                if c_repo.is_esr() {
                    update_version(&common, version)?;
                }

                let output = run_mach(&common, MachCommand::RustCheckUpstream)?;

                if !output.eq("Rust dependencies are okay.\n") {
                    run_mach(&common, MachCommand::RustSync)?;
                    run_mach(&common, MachCommand::RustVendor)?;
                }

                uplifts(&common, &approver, &revs)?;
            }
        }

        Ok(())
    }
}
