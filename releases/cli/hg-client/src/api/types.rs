use serde::Deserialize;

/// A single log entry from `hg log -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct LogEntry {
    pub rev: i64,
    pub node: String,
    pub branch: String,
    pub phase: String,
    pub user: String,
    /// `(unix_timestamp, timezone_offset_seconds)`.
    pub date: (f64, i32),
    pub desc: String,
    #[serde(default)]
    pub bookmarks: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub parents: Vec<String>,
}

/// A single entry from `hg status -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct StatusEntry {
    pub path: String,
    pub status: String,
}

/// Typed representation of a file's status.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileStatus {
    Modified,
    Added,
    Removed,
    Clean,
    Missing,
    Unknown,
    Ignored,
}

impl FileStatus {
    /// Parse the single-character status code from hg.
    pub fn from_code(code: &str) -> Option<Self> {
        match code {
            "M" => Some(FileStatus::Modified),
            "A" => Some(FileStatus::Added),
            "R" => Some(FileStatus::Removed),
            "C" => Some(FileStatus::Clean),
            "!" => Some(FileStatus::Missing),
            "?" => Some(FileStatus::Unknown),
            "I" => Some(FileStatus::Ignored),
            _ => None,
        }
    }
}

impl StatusEntry {
    /// Parse the status code into a typed enum.
    pub fn file_status(&self) -> Option<FileStatus> {
        FileStatus::from_code(&self.status)
    }
}

/// A branch entry from `hg branches -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct BranchEntry {
    pub branch: String,
    pub rev: i64,
    pub node: String,
    pub active: bool,
    pub closed: bool,
    pub current: bool,
}

/// A tag entry from `hg tags -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct TagEntry {
    pub tag: String,
    pub rev: i64,
    pub node: String,
    #[serde(rename = "type", default)]
    pub tag_type: String,
}

/// A bookmark entry from `hg bookmarks -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct BookmarkEntry {
    pub bookmark: String,
    pub rev: i64,
    pub node: String,
    pub active: bool,
}

/// An annotated line from `hg annotate -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct AnnotateLine {
    pub line: String,
    #[serde(default)]
    pub rev: Option<i64>,
    #[serde(default)]
    pub user: Option<String>,
    #[serde(default)]
    pub date: Option<(f64, i32)>,
}

/// Annotation result for a single file from `hg annotate -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct AnnotateResult {
    pub path: String,
    pub lines: Vec<AnnotateLine>,
}

/// A config entry from `hg config -T json`.
#[derive(Debug, Clone, Deserialize)]
pub struct ConfigEntry {
    pub name: String,
    pub source: String,
    pub value: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deserialize_log_entry() {
        let json = r#"[{
            "rev": 0,
            "node": "abc123def456",
            "branch": "default",
            "phase": "draft",
            "user": "Test User <test@example.com>",
            "date": [1700000000.0, 0],
            "desc": "initial commit",
            "bookmarks": [],
            "tags": ["tip"],
            "parents": ["0000000000000000000000000000000000000000"]
        }]"#;
        let entries: Vec<LogEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].rev, 0);
        assert_eq!(entries[0].desc, "initial commit");
        assert_eq!(entries[0].tags, vec!["tip"]);
    }

    #[test]
    fn deserialize_status_entry() {
        let json = r#"[{"path": "foo.txt", "status": "M"}]"#;
        let entries: Vec<StatusEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].file_status(), Some(FileStatus::Modified));
    }

    #[test]
    fn file_status_from_code() {
        assert_eq!(FileStatus::from_code("M"), Some(FileStatus::Modified));
        assert_eq!(FileStatus::from_code("A"), Some(FileStatus::Added));
        assert_eq!(FileStatus::from_code("R"), Some(FileStatus::Removed));
        assert_eq!(FileStatus::from_code("!"), Some(FileStatus::Missing));
        assert_eq!(FileStatus::from_code("?"), Some(FileStatus::Unknown));
        assert_eq!(FileStatus::from_code("I"), Some(FileStatus::Ignored));
        assert_eq!(FileStatus::from_code("C"), Some(FileStatus::Clean));
        assert_eq!(FileStatus::from_code("X"), None);
    }

    #[test]
    fn deserialize_branch_entry() {
        let json = r#"[{
            "active": true,
            "branch": "default",
            "closed": false,
            "current": true,
            "node": "abc123",
            "rev": 1
        }]"#;
        let entries: Vec<BranchEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].branch, "default");
        assert!(entries[0].active);
        assert!(!entries[0].closed);
    }

    #[test]
    fn deserialize_tag_entry() {
        let json = r#"[{
            "node": "abc123",
            "rev": 1,
            "tag": "tip",
            "type": ""
        }]"#;
        let entries: Vec<TagEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].tag, "tip");
    }

    #[test]
    fn deserialize_bookmark_entry() {
        let json = r#"[{
            "active": true,
            "bookmark": "mybook",
            "node": "abc123",
            "rev": 1
        }]"#;
        let entries: Vec<BookmarkEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].bookmark, "mybook");
        assert!(entries[0].active);
    }

    #[test]
    fn deserialize_annotate_result() {
        let json = r#"[{
            "lines": [
                {"line": "line1\n", "rev": 0},
                {"line": "line2\n", "rev": 1}
            ],
            "path": "file.txt"
        }]"#;
        let results: Vec<AnnotateResult> = serde_json::from_str(json).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].path, "file.txt");
        assert_eq!(results[0].lines.len(), 2);
        assert_eq!(results[0].lines[0].rev, Some(0));
        assert_eq!(results[0].lines[1].line, "line2\n");
    }

    #[test]
    fn deserialize_config_entry() {
        let json = r#"[{
            "defaultvalue": "",
            "name": "ui.username",
            "source": "user",
            "value": "Test User <test@example.com>"
        }]"#;
        let entries: Vec<ConfigEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "ui.username");
        assert_eq!(entries[0].value, "Test User <test@example.com>");
    }
}
