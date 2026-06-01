use anyhow::{Context, Result};
use regex::Regex;
use serde::Deserialize;
use std::path::Path;
use tracing::info;

#[derive(Deserialize)]
struct TagsResponse {
    tags: Vec<TagData>,
}

#[derive(Deserialize)]
pub struct TagData {
    pub tag: String,
    pub node: String,
}

/// Fetch the most recent suitable Firefox tag from the hg JSON tags API.
///
/// Tags are in reverse-chronological order; we check the first 10 and return
/// the first that matches either the BASE or RELEASE/BUILD pattern for the
/// given major version.
const TAG_SCAN_LIMIT: usize = 10;
pub fn fetch_latest_tag_from_moz(moz_repo_name: &str, version: &str) -> Result<TagData> {
    let url = format!(
        "https://hg.mozilla.org/releases/{}/json-tags",
        moz_repo_name
    );

    let base_re = Regex::new(&format!(r"^FIREFOX_RELEASE_{}_BASE$", version))?;
    let release_re = Regex::new(&format!(
        r"^FIREFOX_{}_[\dbesr_]+(RELEASE|BUILD\d)$",
        version
    ))?;

    info!("fetching tags from {}", url);
    let response: TagsResponse = ureq::get(&url)
        .call()
        .context("failed to fetch tags")?
        .into_body()
        .read_json()
        .context("failed to parse tags response")?;

    response
        .tags
        .into_iter()
        .take(TAG_SCAN_LIMIT)
        .find(|e| base_re.is_match(&e.tag) || release_re.is_match(&e.tag))
        .inspect(|e| info!("found tag: {} ({})", e.tag, &e.node[..12]))
        .ok_or_else(|| {
            anyhow::anyhow!(
                "no matching tag found in first {} tags for version {}",
                TAG_SCAN_LIMIT,
                version
            )
        })
}

/// Update .gecko_rev.yml in place, preserving comments and unrelated lines.
///
/// Replaces active (non-commented) key lines and inserts missing ones after
/// GECKO_HEAD_REPOSITORY. This avoids a full YAML round-trip which would strip
/// the comment block at the bottom of the file.
pub fn update_gecko_rev(comm_cwd: &Path, moz_repo_url: &str, tag: &TagData) -> Result<()> {
    let path = comm_cwd.join(".gecko_rev.yml");
    let content = std::fs::read_to_string(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;

    let mut lines: Vec<String> = content.lines().map(String::from).collect();

    set_key(&mut lines, "GECKO_HEAD_REPOSITORY", moz_repo_url);

    if !set_key(&mut lines, "GECKO_HEAD_REF", &tag.tag) {
        let idx = lines
            .iter()
            .position(|l| l.starts_with("GECKO_HEAD_REPOSITORY"))
            .context("GECKO_HEAD_REPOSITORY not found in .gecko_rev.yml")?;
        lines.insert(idx + 1, format!("GECKO_HEAD_REF: {}", tag.tag));
    }

    if !set_key(&mut lines, "GECKO_HEAD_REV", &tag.node) {
        let idx = lines
            .iter()
            .position(|l| !l.starts_with('#') && l.starts_with("GECKO_HEAD_REF"))
            .context("GECKO_HEAD_REF not found after insert")?;
        lines.insert(idx + 1, format!("GECKO_HEAD_REV: {}", tag.node));
    }

    std::fs::write(&path, lines.join("\n") + "\n").context("failed to write .gecko_rev.yml")?;

    info!("updated .gecko_rev.yml");
    Ok(())
}

/// Replace the value of `key: ...` on the first non-commented matching line.
/// Returns true if the key was found and updated, false if it wasn't present.
fn set_key(lines: &mut [String], key: &str, value: &str) -> bool {
    for line in lines.iter_mut() {
        if !line.starts_with('#') && line.starts_with(key) {
            *line = format!("{}: {}", key, value);
            return true;
        }
    }
    false
}

/// Build the commit message for a pin operation.
pub fn pin_commit_message(moz_repo_name: &str, tag: &TagData) -> String {
    let approver = std::env::var("USER").unwrap_or_else(|_| "unknown".to_string());
    format!(
        "No bug - Pin {} ({}/{}). r=release a={}",
        moz_repo_name,
        tag.tag,
        &tag.node[..12],
        approver,
    )
}
