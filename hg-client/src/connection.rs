use std::path::Path;

use crate::error::{Error, Result};
use crate::process::HgProcess;
use crate::protocol::{self, Channel, ServerMessage};

/// Parsed hello message from the command server.
#[derive(Debug)]
pub struct HelloInfo {
    pub capabilities: Vec<String>,
    pub encoding: String,
}

/// Outcome of running a single command.
#[derive(Debug)]
pub struct CommandOutput {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub return_code: i32,
}

/// A live connection to an hg command server process.
pub struct Connection {
    process: HgProcess,
    hello: HelloInfo,
}

impl Connection {
    /// Connect to a repository by spawning the command server and reading
    /// the hello message.
    pub fn open(repo_path: &Path) -> Result<Self> {
        let mut process = HgProcess::spawn(repo_path)?;

        let hello_msg = protocol::read_message(process.stdout())?;
        if hello_msg.channel != Channel::Output {
            return Err(Error::ProtocolError(format!(
                "expected hello on 'o' channel, got {:?}",
                hello_msg.channel
            )));
        }

        let hello = parse_hello(&hello_msg.data)?;

        if !hello.capabilities.iter().any(|c| c == "runcommand") {
            return Err(Error::ProtocolError(
                "server does not support 'runcommand' capability".to_string(),
            ));
        }

        Ok(Connection { process, hello })
    }

    /// Access the hello info received at startup.
    pub fn hello(&self) -> &HelloInfo {
        &self.hello
    }

    /// Run a raw command and collect all output.
    ///
    /// Returns the combined stdout, stderr, and return code. Does not
    /// treat a nonzero return code as an error.
    pub fn run_command(&mut self, args: &[&str]) -> Result<CommandOutput> {
        protocol::write_runcommand(self.process.stdin(), args)?;

        let mut stdout = Vec::new();
        let mut stderr = Vec::new();

        loop {
            let msg: ServerMessage = protocol::read_message(self.process.stdout())?;

            match msg.channel {
                Channel::Output => stdout.extend_from_slice(&msg.data),
                Channel::Error => stderr.extend_from_slice(&msg.data),
                Channel::Result => {
                    let code = parse_return_code(&msg.data)?;
                    return Ok(CommandOutput {
                        stdout,
                        stderr,
                        return_code: code,
                    });
                }
                Channel::Debug => {
                    // Ignore debug output.
                }
                Channel::InputReq | Channel::LineInputReq => {
                    // Send empty input to decline the request.
                    protocol::write_payload(self.process.stdin(), &[])?;
                }
            }
        }
    }

    /// Run a command and return stdout as a string.
    ///
    /// Returns an error if the command exits with a nonzero code.
    pub fn run_command_string(&mut self, args: &[&str]) -> Result<String> {
        let output = self.run_command(args)?;
        if output.return_code != 0 {
            return Err(Error::CommandFailed {
                code: output.return_code,
                stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            });
        }
        let output = String::from_utf8_lossy(&output.stdout).into_owned();

        for line in output.lines() {
            tracing::info!("{line}");
        }

        Ok(output)
    }
}

/// Parse the hello message payload into structured info.
///
/// The hello message is a series of `key: value` lines. Example:
/// ```text
/// capabilities: runcommand getencoding
/// encoding: UTF-8
/// ```
pub(crate) fn parse_hello(data: &[u8]) -> Result<HelloInfo> {
    let text = std::str::from_utf8(data)
        .map_err(|e| Error::ProtocolError(format!("hello message is not UTF-8: {e}")))?;

    let mut capabilities = Vec::new();
    let mut encoding = String::from("UTF-8");

    for line in text.lines() {
        if let Some(value) = line.strip_prefix("capabilities: ") {
            capabilities = value.split_whitespace().map(String::from).collect();
        } else if let Some(value) = line.strip_prefix("encoding: ") {
            encoding = value.trim().to_string();
        }
    }

    if capabilities.is_empty() {
        return Err(Error::ProtocolError(
            "hello message missing capabilities".to_string(),
        ));
    }

    Ok(HelloInfo {
        capabilities,
        encoding,
    })
}

fn parse_return_code(data: &[u8]) -> Result<i32> {
    let bytes: [u8; 4] = data.try_into().map_err(|_| {
        Error::ProtocolError(format!(
            "expected 4-byte return code, got {} bytes",
            data.len()
        ))
    })?;
    Ok(i32::from_be_bytes(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_hello_basic() {
        let data = b"capabilities: runcommand getencoding\nencoding: UTF-8\n";
        let info = parse_hello(data).unwrap();
        assert_eq!(info.capabilities, vec!["runcommand", "getencoding"]);
        assert_eq!(info.encoding, "UTF-8");
    }

    #[test]
    fn parse_hello_missing_encoding() {
        let data = b"capabilities: runcommand\n";
        let info = parse_hello(data).unwrap();
        assert_eq!(info.capabilities, vec!["runcommand"]);
        assert_eq!(info.encoding, "UTF-8"); // default
    }

    #[test]
    fn parse_hello_no_capabilities() {
        let data = b"encoding: UTF-8\n";
        let err = parse_hello(data).unwrap_err();
        assert!(matches!(err, Error::ProtocolError(_)));
    }

    #[test]
    fn parse_hello_extra_fields() {
        let data = b"capabilities: runcommand getencoding\nencoding: UTF-8\npid: 12345\n";
        let info = parse_hello(data).unwrap();
        assert_eq!(info.capabilities, vec!["runcommand", "getencoding"]);
    }

    #[test]
    fn parse_return_code_zero() {
        let code = parse_return_code(&[0, 0, 0, 0]).unwrap();
        assert_eq!(code, 0);
    }

    #[test]
    fn parse_return_code_one() {
        let code = parse_return_code(&[0, 0, 0, 1]).unwrap();
        assert_eq!(code, 1);
    }

    #[test]
    fn parse_return_code_negative() {
        // -1 in big-endian two's complement
        let code = parse_return_code(&[0xff, 0xff, 0xff, 0xff]).unwrap();
        assert_eq!(code, -1);
    }

    #[test]
    fn parse_return_code_wrong_length() {
        let err = parse_return_code(&[0, 0]).unwrap_err();
        assert!(matches!(err, Error::ProtocolError(_)));
    }
}
