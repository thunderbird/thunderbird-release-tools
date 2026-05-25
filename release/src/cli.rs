use std::path::PathBuf;

use clap::{Args, Parser, Subcommand};
use hg_cmdserver::{
    HgClient, HgRepo,
    api::{CommitArgs, LogArgs},
};
use mach::{Mach, commands::MachCommand};

use crate::{
    channel::Channel,
    error::{CliError, Result},
    pin::{fetch_latest_tag, pin_commit_message, read_major_version, update_gecko_rev},
    utils::{build_repos_from_args, log_output, normalize_uplift_message},
};

#[derive(Parser, Debug)]
#[command(
    disable_version_flag = true,
    about = "Thunderbird release automation tool",
    long_about = None,
    after_help = "\
Examples:
  # Pin gecko rev on the beta channel
  release pin --comm-dir ~/src/comm --channel beta

  # Uplift two commits on release
  release uplift --comm-dir ~/src/comm --channel release --uplifts abc123 def456

  # Check with Rust dependencies are in sync with upstream
  release rust-check-upstream --comm-dir ~/src/comm --channel release

  # Sync Rust dependencies with upstream
  release rust-sync --comm-dir ~/src/comm --channel release

  # Vendor Rust dependencies
  release rust-vendor --comm-dir ~/src/comm --channel release

  # Bump version files on ESR 140
  release update-version --comm-dir ~/src/comm --channel esr --version 140

  # Full release (pin + uplift + rust vendor, etc) on esr140
  release release --comm-dir ~/src/comm --channel esr --version 140 --uplifts abc123 def456"
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
    /// Provide revision hashes as positional arguments. At least one
    /// revision is required.
    Uplift {
        #[command(flatten)]
        common: CommonArgs,
        /// Reviewer to stamp onto each grafted commit (e.g. "jsmith").
        #[arg(short, long)]
        approver: String,
        #[arg(short, long, num_args = 1.., required = true)]
        uplifts: Vec<String>,
    },
    /// Checks with Rust dependencies are okay with upstream.
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
}

pub struct Cli;

impl Cli {
    pub fn run() -> Result<()> {
        let cli = CliArgs::parse();

        match cli.command {
            Command::PullUpdate { common } => {
                let repositories = build_repos_from_args(&common)?;

                let c_repo = repositories.comm();
                let m_repo = repositories.moz();

                let mut c_hg = HgClient::open(&c_repo.cwd)?;
                let mut m_hg = HgClient::open(&m_repo.cwd)?;

                let c_conn = c_hg.connection();
                let m_conn = m_hg.connection();

                let c_output = c_conn.run_command_string(&["pull", c_repo.kind.url().as_str()])?;
                log_output(c_output);

                let m_output = m_conn.run_command_string(&["pull", m_repo.kind.url().as_str()])?;
                log_output(m_output);
            }
            Command::Pin { common } => {
                let repositories = build_repos_from_args(&common)?;

                let c_repo = repositories.comm();
                let m_repo = repositories.moz();

                // TODO: refactor pin functions
                let major_version = read_major_version(&c_repo.cwd)?;
                let m_repo_name = format!("mozilla-{}", m_repo.kind.name());
                let tag = fetch_latest_tag(&m_repo_name, &major_version)?;
                update_gecko_rev(&c_repo.cwd, &m_repo.kind.url(), &tag)?;
                let message = pin_commit_message(&m_repo_name, &tag);

                let mut hg = HgClient::open(&c_repo.cwd)?;

                let output = hg.commit(CommitArgs {
                    message,
                    files: vec![PathBuf::from(".gecko_rev.yml")],
                    close_branch: false,
                    user: None,
                    date: None,
                })?;

                log_output(output);
            }
            Command::Uplift {
                common,
                approver,
                uplifts,
            } => {
                let repositories = build_repos_from_args(&common)?;

                let c_repo = repositories.comm();

                let mut hg = HgClient::open(&c_repo.cwd)?;

                {
                    let conn = hg.connection();

                    // Check hg extensions
                    let extensions = vec!["histedit", "evolve", "firefoxtree"];
                    for extension in extensions {
                        let output = conn.run_command_string(&[
                            "config",
                            format!("extensions.{}", extension).as_str(),
                        ])?;
                        log_output(output);
                    }
                }

                for rev in &uplifts {
                    let log = hg.log(LogArgs {
                        revs: Some(rev.to_string()),
                        limit: None,
                        follow: false,
                        paths: vec![],
                    })?;

                    let conn = hg.connection();

                    // Dry-run
                    conn.run_command_string(&["graft", "-r", rev, "-n"])?;
                    conn.run_command_string(&["graft", "-r", rev])?;

                    let desc = normalize_uplift_message(log[0].desc.as_str(), &approver);

                    conn.run_command_string(&["metaedit", "-m", desc.as_str()])?;
                }
            }
            Command::RustCheckUpstream { common } => {
                let repositories = build_repos_from_args(&common)?;

                let mach = Mach::new(repositories.moz().cwd.clone());
                mach.run_command_string(MachCommand::RustCheckUpstream)?;
            }
            Command::RustSync { common } => {
                let repositories = build_repos_from_args(&common)?;

                let mach = Mach::new(repositories.moz().cwd.clone());
                mach.run_command_string(MachCommand::RustSync)?;
            }
            Command::RustVendor { common } => {
                let repositories = build_repos_from_args(&common)?;

                let mach = Mach::new(repositories.moz().cwd.clone());
                mach.run_command_string(MachCommand::RustVendor)?;
            }
            Command::UpdateVersion { common } => {
                let version = common
                    .version
                    .as_deref()
                    .ok_or(CliError::MissingArgument("--version"))?;

                let repositories = build_repos_from_args(&common)?;

                let c_repo = repositories.comm();

                let version_plain = version.strip_suffix("esr").unwrap_or(version);

                std::fs::write(
                    c_repo.cwd.join("mail/config/version.txt"),
                    format!("{}\n", version_plain),
                )?;

                std::fs::write(
                    c_repo.cwd.join("mail/config/version_display.txt"),
                    format!("{}\n", version),
                )?;

                let mut hg = HgClient::open(&c_repo.cwd)?;

                let message = format!("No bug - Set version {} for release. r+a=release", version);
                let files = vec![
                    PathBuf::from("mail/config/version.txt"),
                    PathBuf::from("mail/config/version_display.txt"),
                ];

                let output = hg.commit(CommitArgs {
                    message,
                    files,
                    close_branch: false,
                    user: None,
                    date: None,
                })?;

                log_output(output);
            }
        }

        Ok(())
    }
}
