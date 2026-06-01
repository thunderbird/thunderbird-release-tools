use clap::ValueEnum;

#[derive(ValueEnum, Clone, Debug)]
pub enum Channel {
    Beta,
    Release,
    Esr,
}
