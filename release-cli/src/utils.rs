use regex::Regex;

use crate::{
    cli::CommonArgs,
    error::CliError,
    repo::{Repositories, repos_for_channel},
};

/// Rewrites the first line of a commit description for an uplift:
/// - Strips any existing `r+a=` / `a=` annotations
/// - Appends `a=<approver>`; if the approver is also the reviewer (`r=<approver>` already present),
///   collapses it into `r+a=<approver>` instead
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

    tracing::info!("normalized: {}", normalized);

    normalized
}

/// Compares the effective changes of an original commit against its grafted counterpart.
///
/// Strips `hg export` headers and file markers (`+++`/`---`), then compares only the
/// added/removed lines (`+`/`-`) from both patches. Returns an error if they diverge,
/// which indicates the graft introduced unintended changes (e.g. conflict resolution).
pub fn compare_patches(rev: &str, original: &str, grafted: &str) -> Result<(), CliError> {
    let orig_lines = extract_change_lines(original);
    let graft_lines = extract_change_lines(grafted);
    if orig_lines == graft_lines {
        tracing::info!("patch {rev} diff: OK");
        Ok(())
    } else {
        Err(CliError::CommandFailed(format!(
            "patch {rev} diverged after graft"
        )))
    }
}

/// Extracts only the added/removed lines from an `hg export` patch.
///
/// Skips the changeset header and commit message (everything before the first `diff` line),
/// then filters to lines starting with `+` or `-`, excluding `+++`/`---` file markers.
/// Works across multi-file patches — all hunks from all files are included.
fn extract_change_lines(patch: &str) -> Vec<&str> {
    patch
        .lines()
        .skip_while(|l| !l.starts_with("diff "))
        .filter(|l| {
            (l.starts_with('+') || l.starts_with('-'))
                && !l.starts_with("+++")
                && !l.starts_with("---")
        })
        .collect()
}

pub fn build_repos_from_args(common: &CommonArgs) -> Result<Repositories, CliError> {
    let (comm, moz) = repos_for_channel(
        &common.comm_dir,
        &common.channel,
        common.version.as_ref().expect("missing --version"),
    );
    Ok(Repositories::new(comm, moz))
}
