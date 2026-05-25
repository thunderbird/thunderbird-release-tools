use mach::MachError;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CliError {
    #[error("missing argument: {0}")]
    MissingArgument(&'static str),
    #[error("hg client: {0}")]
    HgClient(#[from] hg_cmdserver::Error),
    #[error(transparent)]
    MachError(#[from] MachError),
    #[error(transparent)]
    AnyError(#[from] anyhow::Error),
    #[error(transparent)]
    IoError(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, CliError>;
