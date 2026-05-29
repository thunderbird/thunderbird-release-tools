use std::path::Path;

use anyhow::{Context, Result, bail};
use regex::Regex;
use serde::Deserialize;
use tracing::info;

use crate::error::CliError;

#[derive(Deserialize)]
struct TagsResponse {
    tags: Vec<TagEntry>,
}

#[derive(Deserialize)]
struct TagEntry {
    tag: String,
    node: String,
}

pub struct TagData {
    pub tag: String,
    pub node: String,
}

const HG_JSON_TAGS_URL: &str = "https://hg.mozilla.org/releases/{repo}/json-tags";

/// Read the major version number from mail/config/version.txt in the comm repo.
pub fn read_major_version(comm_cwd: &Path) -> Result<String, CliError> {
    let path = comm_cwd.join("mail/config/version.txt");

    let content = std::fs::read_to_string(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;

    let major = content
        .trim()
        .split('.')
        .next()
        .context("version.txt is empty")?;

    Ok(major.to_string())
}

/// Fetch the most recent suitable Firefox tag from the hg JSON tags API.
///
/// Tags are in reverse-chronological order; we check the first 10 and return
/// the first that matches either the BASE or RELEASE/BUILD pattern for the
/// given major version.
pub fn fetch_latest_tag(moz_repo_name: &str, major_version: &str) -> Result<TagData> {
    let url = HG_JSON_TAGS_URL.replace("{repo}", moz_repo_name);

    let base_re = Regex::new(&format!(r"^FIREFOX_RELEASE_{}_BASE$", major_version))?;
    let release_re = Regex::new(&format!(
        r"^FIREFOX_{}_[\dbesr_]+(RELEASE|BUILD\d)$",
        major_version
    ))?;

    info!("fetching tags from {}", url);
    let response: TagsResponse = ureq::get(&url)
        .call()
        .context("failed to fetch tags")?
        .into_body()
        .read_json()
        .context("failed to parse tags response")?;

    for entry in response.tags.iter().take(10) {
        if base_re.is_match(&entry.tag) || release_re.is_match(&entry.tag) {
            info!("found tag: {} ({})", entry.tag, &entry.node[..12]);
            return Ok(TagData {
                tag: entry.tag.clone(),
                node: entry.node.clone(),
            });
        }
    }

    bail!(
        "no matching tag found in first 10 tags for version {}",
        major_version
    )
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
