use std::io::{Read, Write};

use crate::error::{Error, Result};

/// Identifies which channel a server message arrived on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channel {
    /// 'o' — stdout output from a command.
    Output,
    /// 'e' — stderr output from a command.
    Error,
    /// 'r' — command result (payload is a 4-byte i32 return code).
    Result,
    /// 'I' — server requests bulk input.
    InputReq,
    /// 'L' — server requests a line of input.
    LineInputReq,
    /// 'd' — debug output.
    Debug,
}

impl Channel {
    fn from_byte(b: u8) -> Result<Self> {
        match b {
            b'o' => Ok(Channel::Output),
            b'e' => Ok(Channel::Error),
            b'r' => Ok(Channel::Result),
            b'I' => Ok(Channel::InputReq),
            b'L' => Ok(Channel::LineInputReq),
            b'd' => Ok(Channel::Debug),
            _ => Err(Error::ProtocolError(format!(
                "unknown channel byte: 0x{b:02x}"
            ))),
        }
    }

    /// Returns true if this is a channel where the server expects input from the client.
    pub fn is_input_request(&self) -> bool {
        matches!(self, Channel::InputReq | Channel::LineInputReq)
    }
}

/// A single message frame received from the command server.
#[derive(Debug)]
pub struct ServerMessage {
    pub channel: Channel,
    pub data: Vec<u8>,
}

/// Read one server→client message from the given reader.
///
/// Wire format: 1-byte channel + 4-byte big-endian u32 length + payload.
pub fn read_message(reader: &mut impl Read) -> Result<ServerMessage> {
    let mut header = [0u8; 5];
    reader.read_exact(&mut header)?;

    let channel = Channel::from_byte(header[0])?;
    let length = u32::from_be_bytes([header[1], header[2], header[3], header[4]]) as usize;

    let mut data = vec![0u8; length];
    reader.read_exact(&mut data)?;

    Ok(ServerMessage { channel, data })
}

/// Write a length-prefixed payload to the server.
///
/// Wire format: 4-byte big-endian u32 length + payload.
pub fn write_payload(writer: &mut impl Write, data: &[u8]) -> Result<()> {
    let length = u32::try_from(data.len()).map_err(|_| {
        Error::ProtocolError(format!("payload too large: {} bytes", data.len()))
    })?;
    writer.write_all(&length.to_be_bytes())?;
    writer.write_all(data)?;
    writer.flush()?;
    Ok(())
}

/// Write a `runcommand` invocation to the server.
///
/// Sends `"runcommand\n"` followed by a length-prefixed payload of
/// null-separated arguments.
pub fn write_runcommand(writer: &mut impl Write, args: &[&str]) -> Result<()> {
    writer.write_all(b"runcommand\n")?;

    let payload: Vec<u8> = args
        .iter()
        .enumerate()
        .flat_map(|(i, arg)| {
            let sep = if i > 0 { Some(b'\0') } else { None };
            sep.into_iter().chain(arg.bytes())
        })
        .collect();

    write_payload(writer, &payload)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::io::Cursor;

    use super::*;

    #[test]
    fn read_output_message() {
        // Channel 'o', length 5, payload "hello"
        let data = b"o\x00\x00\x00\x05hello";
        let mut cursor = Cursor::new(&data[..]);
        let msg = read_message(&mut cursor).unwrap();
        assert_eq!(msg.channel, Channel::Output);
        assert_eq!(msg.data, b"hello");
    }

    #[test]
    fn read_error_message() {
        let data = b"e\x00\x00\x00\x03err";
        let mut cursor = Cursor::new(&data[..]);
        let msg = read_message(&mut cursor).unwrap();
        assert_eq!(msg.channel, Channel::Error);
        assert_eq!(msg.data, b"err");
    }

    #[test]
    fn read_result_message() {
        // 'r' channel, length 4, return code 0
        let data = b"r\x00\x00\x00\x04\x00\x00\x00\x00";
        let mut cursor = Cursor::new(&data[..]);
        let msg = read_message(&mut cursor).unwrap();
        assert_eq!(msg.channel, Channel::Result);
        assert_eq!(msg.data, &[0, 0, 0, 0]);
    }

    #[test]
    fn read_result_nonzero() {
        // Return code 1
        let data = b"r\x00\x00\x00\x04\x00\x00\x00\x01";
        let mut cursor = Cursor::new(&data[..]);
        let msg = read_message(&mut cursor).unwrap();
        assert_eq!(msg.channel, Channel::Result);
        let code = i32::from_be_bytes(msg.data[..4].try_into().unwrap());
        assert_eq!(code, 1);
    }

    #[test]
    fn read_unknown_channel() {
        let data = b"X\x00\x00\x00\x01a";
        let mut cursor = Cursor::new(&data[..]);
        let err = read_message(&mut cursor).unwrap_err();
        assert!(matches!(err, Error::ProtocolError(_)));
    }

    #[test]
    fn read_empty_payload() {
        let data = b"o\x00\x00\x00\x00";
        let mut cursor = Cursor::new(&data[..]);
        let msg = read_message(&mut cursor).unwrap();
        assert_eq!(msg.channel, Channel::Output);
        assert!(msg.data.is_empty());
    }

    #[test]
    fn write_payload_roundtrip() {
        let mut buf = Vec::new();
        write_payload(&mut buf, b"test data").unwrap();
        assert_eq!(&buf[..4], &[0, 0, 0, 9]); // length = 9
        assert_eq!(&buf[4..], b"test data");
    }

    #[test]
    fn write_runcommand_single_arg() {
        let mut buf = Vec::new();
        write_runcommand(&mut buf, &["log"]).unwrap();
        assert!(buf.starts_with(b"runcommand\n"));
        let payload = &buf[b"runcommand\n".len()..];
        // 4-byte length prefix + "log"
        assert_eq!(&payload[..4], &[0, 0, 0, 3]);
        assert_eq!(&payload[4..], b"log");
    }

    #[test]
    fn write_runcommand_multiple_args() {
        let mut buf = Vec::new();
        write_runcommand(&mut buf, &["log", "-r", "."]).unwrap();
        let payload = &buf[b"runcommand\n".len()..];
        // "log\0-r\0." = 8 bytes
        assert_eq!(&payload[..4], &[0, 0, 0, 8]);
        assert_eq!(&payload[4..], b"log\0-r\0.");
    }

    #[test]
    fn write_runcommand_empty_args() {
        let mut buf = Vec::new();
        write_runcommand(&mut buf, &[]).unwrap();
        let payload = &buf[b"runcommand\n".len()..];
        assert_eq!(&payload[..4], &[0, 0, 0, 0]);
        assert_eq!(payload.len(), 4);
    }

    #[test]
    fn read_multiple_messages() {
        let mut data = Vec::new();
        data.extend_from_slice(b"o\x00\x00\x00\x02hi");
        data.extend_from_slice(b"e\x00\x00\x00\x04warn");
        data.extend_from_slice(b"r\x00\x00\x00\x04\x00\x00\x00\x00");

        let mut cursor = Cursor::new(data);

        let msg1 = read_message(&mut cursor).unwrap();
        assert_eq!(msg1.channel, Channel::Output);
        assert_eq!(msg1.data, b"hi");

        let msg2 = read_message(&mut cursor).unwrap();
        assert_eq!(msg2.channel, Channel::Error);
        assert_eq!(msg2.data, b"warn");

        let msg3 = read_message(&mut cursor).unwrap();
        assert_eq!(msg3.channel, Channel::Result);
    }

    #[test]
    fn channel_is_input_request() {
        assert!(!Channel::Output.is_input_request());
        assert!(!Channel::Error.is_input_request());
        assert!(!Channel::Result.is_input_request());
        assert!(Channel::InputReq.is_input_request());
        assert!(Channel::LineInputReq.is_input_request());
        assert!(!Channel::Debug.is_input_request());
    }
}
