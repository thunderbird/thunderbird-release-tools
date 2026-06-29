use std::io;

/// Errors that can occur when communicating with the Mercurial command server.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),

    #[error("command failed with exit code {code}: {stderr}")]
    CommandFailed { code: i32, stderr: String },

    #[error("protocol error: {0}")]
    ProtocolError(String),

    #[error("failed to parse output: {source}")]
    ParseError {
        source: serde_json::Error,
        raw: String,
    },

    #[error("server is not running")]
    ServerNotRunning,
}

impl From<serde_json::Error> for Error {
    fn from(err: serde_json::Error) -> Self {
        Error::ParseError {
            source: err,
            raw: String::new(),
        }
    }
}

pub type Result<T> = std::result::Result<T, Error>;
