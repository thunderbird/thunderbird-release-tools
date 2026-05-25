use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

use crate::error::{Error, Result};

/// Manages the hg command server child process.
pub struct HgProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: ChildStdout,
}

impl HgProcess {
    /// Spawn `hg serve --cmdserver pipe` in the given repository directory.
    pub fn spawn(repo_path: &Path) -> Result<Self> {
        let mut child = Command::new("hg")
            .args(["serve", "--cmdserver", "pipe"])
            .current_dir(repo_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        let stdin = child.stdin.take().ok_or_else(|| {
            Error::ProtocolError("failed to capture child stdin".to_string())
        })?;
        let stdout = child.stdout.take().ok_or_else(|| {
            Error::ProtocolError("failed to capture child stdout".to_string())
        })?;

        Ok(HgProcess {
            child,
            stdin,
            stdout,
        })
    }

    pub fn stdin(&mut self) -> &mut ChildStdin {
        &mut self.stdin
    }

    pub fn stdout(&mut self) -> &mut ChildStdout {
        &mut self.stdout
    }
}

impl Drop for HgProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
