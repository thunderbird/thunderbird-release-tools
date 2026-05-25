use thiserror::Error;

#[derive(Debug, Error)]
pub enum MachError {
    #[error("command failed with exit code {code}: {stderr}")]
    CommandFailed { code: i32, stderr: String },
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, MachError>;
