pub mod commands;
mod error;
use crate::{commands::MachCommand, error::Result};
pub use error::MachError;
use std::{
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Command, Stdio},
    thread,
};
use tracing::{info, warn};

pub struct CommandOutput {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub return_code: i32,
}

impl CommandOutput {
    // https://searchfox.org/comm-central/source/python/rocbuild/rocbuild/rust.py#788
    // Exit code 88 means dependencies are out of sync, not a failure.
    pub fn is_acceptable_exit_code(&self, cmd: MachCommand) -> bool {
        match cmd {
            MachCommand::RustCheckUpstream => matches!(self.return_code, 0 | 88),
            _ => self.return_code == 0,
        }
    }
}

pub struct Mach {
    pub cwd: PathBuf,
}

impl Mach {
    pub fn new(cwd: PathBuf) -> Self {
        Self { cwd }
    }

    /// Executes the given command, streaming stdout and stderr lines to the log as they arrive.
    /// Returns the full output so callers can inspect stdout/stderr and the return code.
    pub fn run_command(&self, cmd: MachCommand) -> Result<CommandOutput> {
        let args = cmd.into_args();

        let mut child = Command::new("./mach")
            .args(&args)
            .current_dir(&self.cwd)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        let stderr_reader = BufReader::new(child.stderr.take().expect("stderr is piped"));
        let stderr_thread = thread::spawn(move || {
            let mut stderr = Vec::new();
            for line in stderr_reader.lines() {
                let line = line.unwrap_or_default();
                warn!("{}", line);
                stderr.extend_from_slice(line.as_bytes());
                stderr.push(b'\n');
            }
            stderr
        });

        let mut stdout = Vec::new();
        for line in BufReader::new(child.stdout.take().expect("stdout is piped")).lines() {
            let line = line?;
            info!("{}", line);
            stdout.extend_from_slice(line.as_bytes());
            stdout.push(b'\n');
        }

        let status = child.wait()?;
        let stderr = stderr_thread.join().unwrap_or_default();
        let return_code = status.code().unwrap_or(-1);

        Ok(CommandOutput {
            stdout,
            stderr,
            return_code,
        })
    }

    /// Run a command and return stdout as a string.
    ///
    /// Returns an error if the command exits with a nonzero code.
    pub fn run_command_string(&self, cmd: MachCommand) -> Result<String> {
        tracing::info!("mach {}", &cmd.into_args().join(" "));

        let output = self.run_command(cmd)?;
        if output.return_code != 0 {
            return Err(MachError::CommandFailed {
                code: output.return_code,
                stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            });
        }

        Ok(String::from_utf8_lossy(&output.stdout).into_owned())
    }
}
