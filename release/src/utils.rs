use regex::Regex;

use crate::{
    channel::Channel,
    cli::CommonArgs,
    error::CliError,
    repo::{Repositories, repos_for_channel},
};

/// Rewrites the first line of a commit description for an uplift:
/// - Strips any existing `r+a=` / `a=` annotations
/// - Appends `a=<approver>`; if the approver is also the reviewer (`r=<approver>`
///   already present), collapses it into `r+a=<approver>` instead
/// - Removes the `DONTBUILD` marker
pub fn normalize_uplift_message(desc: &str, approver: &str) -> String {
    let (first, rest) = match desc.find('\n') {
        Some(pos) => (&desc[..pos], &desc[pos..]),
        None => (desc, ""),
    };

    let mut first = first.to_string();

    // Collapse r+a= into r= so the a= removal below cleans it up uniformly
    first = first.replace("r+a=", "r=");
    let re = Regex::new(r"a=[A-Za-z0-9]+").unwrap();
    first = re.replace_all(&first, "").to_string();

    // Re-apply approver: upgrade existing r= or append a=
    let r_approver = format!("r={}", approver);
    if first.contains(&r_approver) {
        first = first.replacen(&r_approver, &format!("r+a={}", approver), 1);
    } else {
        first.push_str(&format!(" a={}", approver));
    }

    first = first.replace(" DONTBUILD", "");
    let normalized = format!("{}{}", first, rest);
    tracing::info!("normalized: {normalized}");

    normalized
}

/// Build a [`Config`] from [`CommonArgs`], resolving the comm and mozilla repositories.
///
/// For ESR channels, `--version` is required to construct the versioned
/// branch name (e.g. `comm-esr128` / `mozilla-esr128`).
pub fn build_repos_from_args(common: &CommonArgs) -> Result<Repositories, CliError> {
    let version = match common.channel {
        Channel::Esr => common.version.as_deref().ok_or(CliError::MissingArgument(
            "--version is required when --channel esr",
        ))?,
        _ => "",
    };
    let (comm, moz) = repos_for_channel(&common.comm_dir, &common.channel, version);
    Ok(Repositories::new(comm, moz))
}

pub fn log_output(output: String) {
    for line in output.lines() {
        tracing::info!("{line}");
    }
}
