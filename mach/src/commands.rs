pub enum MachCommand {
    RustCheckUpstream,
    RustSync,
    RustVendor,
}

impl MachCommand {
    pub fn into_args(&self) -> Vec<String> {
        match self {
            MachCommand::RustCheckUpstream => vec!["tb-rust".into(), "check-upstream".into()],
            MachCommand::RustSync => vec!["tb-rust".into(), "sync".into()],
            MachCommand::RustVendor => vec!["tb-rust".into(), "vendor".into()],
        }
    }
}
