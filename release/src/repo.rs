use std::path::{Path, PathBuf};

use crate::channel::Channel;

pub enum CommRepository {
    Beta,
    Release,
    Esr(String),
}

pub enum MozillaRepository {
    Beta,
    Release,
    Esr(String),
}

pub enum RepositoryKind {
    Comm(CommRepository),
    Mozilla(MozillaRepository),
}

pub struct Repository {
    pub cwd: PathBuf,
    pub kind: RepositoryKind,
}

impl Repository {
    pub fn is_esr(&self) -> bool {
        matches!(
            self.kind,
            RepositoryKind::Comm(CommRepository::Esr(_))
                | RepositoryKind::Mozilla(MozillaRepository::Esr(_))
        )
    }
}

pub struct Repositories {
    comm: Repository,
    moz: Repository,
}

impl Repositories {
    pub fn new(comm: Repository, moz: Repository) -> Self {
        Self { comm, moz }
    }
    pub fn comm(&self) -> &Repository {
        &self.comm
    }

    pub fn moz(&self) -> &Repository {
        &self.moz
    }
}

/// Returns the comm and mozilla repositories for the given channel.
///
/// `comm_dir` is the path to the comm repository (passed via `--comm-dir`).
/// The mozilla repository lives in the parent of `comm_dir`, since the standard
/// checkout layout places comm/ inside the mozilla directory.
pub fn repos_for_channel(
    comm_dir: &Path,
    channel: &Channel,
    version: &str,
) -> (Repository, Repository) {
    let moz_dir = comm_dir
        .parent()
        .expect("comm_dir has no parent")
        .to_path_buf();

    match channel {
        Channel::Beta => (
            Repository {
                kind: RepositoryKind::Comm(CommRepository::Beta),
                cwd: comm_dir.to_path_buf(),
            },
            Repository {
                kind: RepositoryKind::Mozilla(MozillaRepository::Beta),
                cwd: moz_dir,
            },
        ),
        Channel::Release => (
            Repository {
                kind: RepositoryKind::Comm(CommRepository::Release),
                cwd: comm_dir.to_path_buf(),
            },
            Repository {
                kind: RepositoryKind::Mozilla(MozillaRepository::Release),
                cwd: moz_dir,
            },
        ),
        Channel::Esr => (
            Repository {
                kind: RepositoryKind::Comm(CommRepository::Esr(version.to_string())),
                cwd: comm_dir.to_path_buf(),
            },
            Repository {
                kind: RepositoryKind::Mozilla(MozillaRepository::Esr(version.to_string())),
                cwd: moz_dir,
            },
        ),
    }
}

const HG_URL: &str = "https://hg.mozilla.org/releases/";

impl RepositoryKind {
    pub fn name(&self) -> String {
        match self {
            RepositoryKind::Comm(comm_repository) => match comm_repository {
                CommRepository::Beta => "comm-beta".to_string(),
                CommRepository::Release => "comm-release".to_string(),
                CommRepository::Esr(version) => format!("comm-esr{}", version),
            },
            RepositoryKind::Mozilla(mozilla_repository) => match mozilla_repository {
                MozillaRepository::Beta => "beta".to_string(),
                MozillaRepository::Release => "release".to_string(),
                MozillaRepository::Esr(version) => format!("esr{}", version),
            },
        }
    }

    /// Comm: https://hg.mozilla.org/releases/comm-beta
    /// Mozilla: https://hg.mozilla.org/releases/mozilla-beta
    pub fn url(&self) -> String {
        match self {
            RepositoryKind::Comm(comm_repository) => match comm_repository {
                CommRepository::Esr(version) => format!("{}{}{}", HG_URL, self.name(), version),
                _ => format!("{}{}", HG_URL, self.name()),
            },
            RepositoryKind::Mozilla(mozilla_repository) => match mozilla_repository {
                MozillaRepository::Esr(version) => {
                    format!("{}mozilla-{}{}", HG_URL, self.name(), version)
                }
                _ => format!("{}mozilla-{}", HG_URL, self.name()),
            },
        }
    }
}
