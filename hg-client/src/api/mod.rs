pub mod types;

use crate::{
    connection::Connection,
    error::{Error, Result},
};
use std::path::{Path, PathBuf};
use types::{
    AnnotateResult,
    BookmarkEntry,
    BranchEntry,
    ConfigEntry,
    LogEntry,
    StatusEntry,
    TagEntry,
};

/// Arguments for `hg log`.
#[derive(Debug, Default)]
pub struct LogArgs {
    /// Revision or revset expression (`-r`).
    pub revs: Option<String>,
    /// Maximum number of entries (`-l`).
    pub limit: Option<usize>,
    /// Follow renames (`-f`).
    pub follow: bool,
    /// Restrict to these file paths.
    pub paths: Vec<PathBuf>,
}

/// Arguments for `hg status`.
#[derive(Debug, Default)]
pub struct StatusArgs {
    /// Show changes relative to this revision (`--rev`).
    pub rev: Option<String>,
    /// Show changes in a specific changeset (`--change`).
    pub change: Option<String>,
}

/// Arguments for `hg diff`.
#[derive(Debug, Default)]
pub struct DiffArgs {
    /// Revision(s) to diff (`-r`).
    pub revs: Option<String>,
    /// Restrict to these file paths.
    pub paths: Vec<PathBuf>,
    /// Number of context lines (`-U`).
    pub unified: Option<usize>,
}

/// Arguments for `hg annotate`.
#[derive(Debug, Default)]
pub struct AnnotateArgs {
    /// Annotate at this revision (`-r`).
    pub rev: Option<String>,
    /// Include user information.
    pub user: bool,
    /// Include date information.
    pub date: bool,
}

/// Arguments for `hg commit`.
#[derive(Debug)]
pub struct CommitArgs {
    /// Commit message (`-m`).
    pub message: String,
    /// User/author override (`-u`).
    pub user: Option<String>,
    /// Only commit these files. If empty, commits all tracked changes.
    pub files: Vec<PathBuf>,
    /// Close the current branch head (`--close-branch`).
    pub close_branch: bool,
    /// Record a commit date (`-d`).
    pub date: Option<String>,
}

/// Arguments for `hg update`.
#[derive(Debug, Default)]
pub struct UpdateArgs {
    /// Revision to update to.
    pub rev: Option<String>,
    /// Discard uncommitted changes (`-C`).
    pub clean: bool,
}

/// High-level Mercurial operations.
///
/// Implemented as a trait to allow mocking in downstream tests.
pub trait HgRepo {
    // Read operations
    fn log(&mut self, args: LogArgs) -> Result<Vec<LogEntry>>;
    fn status(&mut self, args: StatusArgs) -> Result<Vec<StatusEntry>>;
    fn diff(&mut self, args: DiffArgs) -> Result<String>;
    fn cat(&mut self, file: &Path, rev: Option<&str>) -> Result<Vec<u8>>;
    fn summary(&mut self) -> Result<String>;
    fn identify(&mut self) -> Result<String>;
    fn branches(&mut self) -> Result<Vec<BranchEntry>>;
    fn tags(&mut self) -> Result<Vec<TagEntry>>;
    fn bookmarks(&mut self) -> Result<Vec<BookmarkEntry>>;
    fn annotate(&mut self, file: &Path, args: AnnotateArgs) -> Result<AnnotateResult>;
    fn config(&mut self) -> Result<Vec<ConfigEntry>>;
    fn config_get(&mut self, name: &str) -> Result<Option<String>>;
    fn resolve_rev(&mut self, rev: &str) -> Result<String>;
    fn export(&mut self, rev: &str) -> Result<String>;

    // Write operations
    fn add(&mut self, files: &[&Path]) -> Result<()>;
    fn remove(&mut self, files: &[&Path]) -> Result<()>;
    fn addremove(&mut self, path: &Path) -> Result<()>;
    fn commit(&mut self, args: CommitArgs) -> Result<String>;
    fn update(&mut self, args: UpdateArgs) -> Result<String>;
    fn tag(&mut self, name: &str, rev: Option<&str>) -> Result<()>;
    fn bookmark(&mut self, name: &str, rev: Option<&str>) -> Result<()>;
    fn bookmark_delete(&mut self, name: &str) -> Result<()>;
}

/// A Mercurial client backed by the command server protocol.
pub struct HgClient {
    conn: Connection,
}

impl HgClient {
    /// Open a connection to the hg repository at the given path.
    pub fn open(repo_path: impl AsRef<Path>) -> Result<Self> {
        let conn = Connection::open(repo_path.as_ref())?;
        Ok(HgClient { conn })
    }

    /// Access the underlying connection for running raw commands.
    pub fn connection(&mut self) -> &mut Connection {
        &mut self.conn
    }
}

impl HgRepo for HgClient {
    fn log(&mut self, args: LogArgs) -> Result<Vec<LogEntry>> {
        let mut cmd_args: Vec<String> = vec!["log".into(), "-T".into(), "json".into()];

        if let Some(ref revs) = args.revs {
            cmd_args.push("-r".into());
            cmd_args.push(revs.clone());
        }
        if let Some(limit) = args.limit {
            cmd_args.push("-l".into());
            cmd_args.push(limit.to_string());
        }
        if args.follow {
            cmd_args.push("-f".into());
        }
        for path in &args.paths {
            cmd_args.push(path.to_string_lossy().into_owned());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        let output = self.conn.run_command_string(&refs)?;

        if output.trim().is_empty() {
            return Ok(Vec::new());
        }

        let entries: Vec<LogEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn status(&mut self, args: StatusArgs) -> Result<Vec<StatusEntry>> {
        let mut cmd_args: Vec<String> = vec!["status".into(), "-T".into(), "json".into()];

        if let Some(ref rev) = args.rev {
            cmd_args.push("--rev".into());
            cmd_args.push(rev.clone());
        }
        if let Some(ref change) = args.change {
            cmd_args.push("--change".into());
            cmd_args.push(change.clone());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        let output = self.conn.run_command_string(&refs)?;

        if output.trim().is_empty() {
            return Ok(Vec::new());
        }

        let entries: Vec<StatusEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn diff(&mut self, args: DiffArgs) -> Result<String> {
        let mut cmd_args: Vec<String> = vec!["diff".into()];

        if let Some(ref revs) = args.revs {
            cmd_args.push("-r".into());
            cmd_args.push(revs.clone());
        }
        if let Some(unified) = args.unified {
            cmd_args.push("-U".into());
            cmd_args.push(unified.to_string());
        }
        for path in &args.paths {
            cmd_args.push(path.to_string_lossy().into_owned());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        self.conn.run_command_string(&refs)
    }

    fn cat(&mut self, file: &Path, rev: Option<&str>) -> Result<Vec<u8>> {
        let file_str = file.to_string_lossy();
        let mut cmd_args: Vec<&str> = vec!["cat", &file_str];

        if let Some(rev) = rev {
            cmd_args.push("-r");
            cmd_args.push(rev);
        }

        let output = self.conn.run_command(&cmd_args)?;
        if output.return_code != 0 {
            return Err(Error::CommandFailed {
                code: output.return_code,
                stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            });
        }
        Ok(output.stdout)
    }

    fn summary(&mut self) -> Result<String> {
        self.conn.run_command_string(&["summary"])
    }

    fn identify(&mut self) -> Result<String> {
        let output = self.conn.run_command_string(&["identify"])?;
        Ok(output.trim().to_string())
    }

    fn branches(&mut self) -> Result<Vec<BranchEntry>> {
        let output = self.conn.run_command_string(&["branches", "-T", "json"])?;
        if output.trim().is_empty() {
            return Ok(Vec::new());
        }
        let entries: Vec<BranchEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn tags(&mut self) -> Result<Vec<TagEntry>> {
        let output = self.conn.run_command_string(&["tags", "-T", "json"])?;
        if output.trim().is_empty() {
            return Ok(Vec::new());
        }
        let entries: Vec<TagEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn bookmarks(&mut self) -> Result<Vec<BookmarkEntry>> {
        let output = self.conn.run_command_string(&["bookmarks", "-T", "json"])?;
        if output.trim().is_empty() {
            return Ok(Vec::new());
        }
        let entries: Vec<BookmarkEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn annotate(&mut self, file: &Path, args: AnnotateArgs) -> Result<AnnotateResult> {
        let file_str = file.to_string_lossy();
        let mut cmd_args: Vec<String> = vec![
            "annotate".into(),
            "-T".into(),
            "json".into(),
            file_str.into_owned(),
        ];

        if let Some(ref rev) = args.rev {
            cmd_args.push("-r".into());
            cmd_args.push(rev.clone());
        }
        if args.user {
            cmd_args.push("--user".into());
        }
        if args.date {
            cmd_args.push("--date".into());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        let output = self.conn.run_command_string(&refs)?;

        let results: Vec<AnnotateResult> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;

        results
            .into_iter()
            .next()
            .ok_or_else(|| Error::ProtocolError("annotate returned no results".to_string()))
    }

    fn config(&mut self) -> Result<Vec<ConfigEntry>> {
        let output = self.conn.run_command_string(&["config", "-T", "json"])?;
        if output.trim().is_empty() {
            return Ok(Vec::new());
        }
        let entries: Vec<ConfigEntry> =
            serde_json::from_str(&output).map_err(|e| Error::ParseError {
                source: e,
                raw: output,
            })?;
        Ok(entries)
    }

    fn config_get(&mut self, name: &str) -> Result<Option<String>> {
        let output = self.conn.run_command(&["config", name])?;
        if output.return_code != 0 {
            return Ok(None);
        }
        Ok(Some(
            String::from_utf8_lossy(&output.stdout).trim().to_string(),
        ))
    }

    fn resolve_rev(&mut self, rev: &str) -> Result<String> {
        let output = self
            .conn
            .run_command_string(&["log", "-r", rev, "-T", "{node}"])?;
        Ok(output)
    }

    fn export(&mut self, rev: &str) -> Result<String> {
        let out = self.conn.run_command(&["export", "-r", rev])?;
        if out.return_code != 0 {
            return Err(Error::CommandFailed {
                code: out.return_code,
                stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
            });
        }
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    }

    fn add(&mut self, files: &[&Path]) -> Result<()> {
        let mut cmd_args: Vec<String> = vec!["add".into()];
        for file in files {
            cmd_args.push(file.to_string_lossy().into_owned());
        }
        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        self.conn.run_command_string(&refs)?;
        Ok(())
    }

    fn remove(&mut self, files: &[&Path]) -> Result<()> {
        let mut cmd_args: Vec<String> = vec!["remove".into()];
        for file in files {
            cmd_args.push(file.to_string_lossy().into_owned());
        }
        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        self.conn.run_command_string(&refs)?;
        Ok(())
    }

    fn addremove(&mut self, path: &Path) -> Result<()> {
        self.conn
            .run_command_string(&["addremove", &path.to_string_lossy()])?;
        Ok(())
    }

    fn commit(&mut self, args: CommitArgs) -> Result<String> {
        let mut cmd_args: Vec<String> = vec!["commit".into(), "-m".into(), args.message];

        if let Some(ref user) = args.user {
            cmd_args.push("-u".into());
            cmd_args.push(user.clone());
        }
        if let Some(ref date) = args.date {
            cmd_args.push("-d".into());
            cmd_args.push(date.clone());
        }
        if args.close_branch {
            cmd_args.push("--close-branch".into());
        }
        for file in &args.files {
            cmd_args.push(file.to_string_lossy().into_owned());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        self.conn.run_command_string(&refs)?;

        // Return the node of the newly created commit.
        self.resolve_rev(".")
    }

    fn update(&mut self, args: UpdateArgs) -> Result<String> {
        let mut cmd_args: Vec<String> = vec!["update".into()];

        if let Some(ref rev) = args.rev {
            cmd_args.push("-r".into());
            cmd_args.push(rev.clone());
        }
        if args.clean {
            cmd_args.push("-C".into());
        }

        let refs: Vec<&str> = cmd_args.iter().map(|s| s.as_str()).collect();
        let output = self.conn.run_command_string(&refs)?;
        Ok(output)
    }

    fn tag(&mut self, name: &str, rev: Option<&str>) -> Result<()> {
        let mut cmd_args: Vec<&str> = vec!["tag", name];
        if let Some(rev) = rev {
            cmd_args.push("-r");
            cmd_args.push(rev);
        }
        self.conn.run_command_string(&cmd_args)?;
        Ok(())
    }

    fn bookmark(&mut self, name: &str, rev: Option<&str>) -> Result<()> {
        let mut cmd_args: Vec<&str> = vec!["bookmark", name];
        if let Some(rev) = rev {
            cmd_args.push("-r");
            cmd_args.push(rev);
        }
        self.conn.run_command_string(&cmd_args)?;
        Ok(())
    }

    fn bookmark_delete(&mut self, name: &str) -> Result<()> {
        self.conn
            .run_command_string(&["bookmark", "--delete", name])?;
        Ok(())
    }
}
