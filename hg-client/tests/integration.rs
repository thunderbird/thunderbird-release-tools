use std::process::Command;

use hg_cmdserver::api::types::FileStatus;
use hg_cmdserver::api::{
    AnnotateArgs, CommitArgs, DiffArgs, LogArgs, StatusArgs, UpdateArgs,
};
use hg_cmdserver::{Connection, HgClient, HgRepo};
use tempfile::TempDir;

fn hg_available() -> bool {
    Command::new("hg")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Create a temp hg repo with one committed file.
fn setup_test_repo() -> (TempDir, HgClient) {
    let dir = tempfile::tempdir().unwrap();

    Command::new("hg")
        .arg("init")
        .current_dir(dir.path())
        .status()
        .unwrap();

    std::fs::write(dir.path().join("hello.txt"), "hello world\n").unwrap();

    Command::new("hg")
        .args(["add", "hello.txt"])
        .current_dir(dir.path())
        .status()
        .unwrap();

    Command::new("hg")
        .args(["commit", "-m", "initial commit", "-u", "test"])
        .current_dir(dir.path())
        .status()
        .unwrap();

    let client = HgClient::open(dir.path()).unwrap();
    (dir, client)
}

#[test]
fn connection_hello() {
    if !hg_available() {
        return;
    }
    let dir = tempfile::tempdir().unwrap();
    Command::new("hg")
        .arg("init")
        .current_dir(dir.path())
        .status()
        .unwrap();

    let conn = Connection::open(dir.path()).unwrap();
    let hello = conn.hello();
    assert!(hello.capabilities.contains(&"runcommand".to_string()));
}

#[test]
fn connection_run_command() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let output = client.connection().run_command(&["identify"]).unwrap();
    assert_eq!(output.return_code, 0);
    assert!(!output.stdout.is_empty());
}

#[test]
fn log_returns_entries() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let entries = client.log(LogArgs::default()).unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].desc, "initial commit");
    assert_eq!(entries[0].rev, 0);
}

#[test]
fn log_with_limit() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Add a second commit.
    std::fs::write(dir.path().join("second.txt"), "second\n").unwrap();
    Command::new("hg")
        .args(["add", "second.txt"])
        .current_dir(dir.path())
        .status()
        .unwrap();
    Command::new("hg")
        .args(["commit", "-m", "second commit", "-u", "test"])
        .current_dir(dir.path())
        .status()
        .unwrap();

    let all = client.log(LogArgs::default()).unwrap();
    assert_eq!(all.len(), 2);

    let limited = client
        .log(LogArgs {
            limit: Some(1),
            ..Default::default()
        })
        .unwrap();
    assert_eq!(limited.len(), 1);
}

#[test]
fn status_clean_repo() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let entries = client.status(StatusArgs::default()).unwrap();
    assert!(entries.is_empty());
}

#[test]
fn status_modified_file() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Modify the file.
    std::fs::write(dir.path().join("hello.txt"), "modified\n").unwrap();

    let entries = client.status(StatusArgs::default()).unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].path, "hello.txt");
    assert_eq!(entries[0].file_status(), Some(FileStatus::Modified));
}

#[test]
fn status_untracked_file() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    std::fs::write(dir.path().join("untracked.txt"), "new\n").unwrap();

    let entries = client.status(StatusArgs::default()).unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].path, "untracked.txt");
    assert_eq!(entries[0].file_status(), Some(FileStatus::Unknown));
}

#[test]
fn diff_modified_file() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    std::fs::write(dir.path().join("hello.txt"), "modified\n").unwrap();

    let diff = client.diff(DiffArgs::default()).unwrap();
    assert!(diff.contains("hello.txt"));
    assert!(diff.contains("-hello world"));
    assert!(diff.contains("+modified"));
}

#[test]
fn cat_file() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let content = client.cat("hello.txt".as_ref(), None).unwrap();
    assert_eq!(content, b"hello world\n");
}

#[test]
fn cat_file_at_rev() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Modify and commit.
    std::fs::write(dir.path().join("hello.txt"), "v2\n").unwrap();
    Command::new("hg")
        .args(["commit", "-m", "update", "-u", "test"])
        .current_dir(dir.path())
        .status()
        .unwrap();

    // Cat at rev 0 should give original content.
    let v1 = client.cat("hello.txt".as_ref(), Some("0")).unwrap();
    assert_eq!(v1, b"hello world\n");

    // Cat at tip should give new content.
    let v2 = client.cat("hello.txt".as_ref(), Some("tip")).unwrap();
    assert_eq!(v2, b"v2\n");
}

#[test]
fn summary() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let summary = client.summary().unwrap();
    assert!(summary.contains("parent:"));
}

#[test]
fn identify() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let id = client.identify().unwrap();
    assert!(!id.is_empty());
    // hg identify output typically contains a hash and "tip" tag.
    assert!(id.contains("tip"));
}

#[test]
fn multiple_commands_on_same_connection() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();

    // Run several commands in sequence to ensure the connection stays healthy.
    let _ = client.identify().unwrap();
    let _ = client.log(LogArgs::default()).unwrap();
    let _ = client.status(StatusArgs::default()).unwrap();
    let _ = client.summary().unwrap();
    let _ = client.identify().unwrap();
}

#[test]
fn branches_lists_default() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let branches = client.branches().unwrap();
    assert_eq!(branches.len(), 1);
    assert_eq!(branches[0].branch, "default");
    assert!(branches[0].active);
}

#[test]
fn tags_includes_tip() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let tags = client.tags().unwrap();
    assert!(tags.iter().any(|t| t.tag == "tip"));
}

#[test]
fn bookmarks_empty_by_default() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let bookmarks = client.bookmarks().unwrap();
    assert!(bookmarks.is_empty());
}

#[test]
fn annotate_file() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let result = client
        .annotate("hello.txt".as_ref(), AnnotateArgs::default())
        .unwrap();
    assert_eq!(result.path, "hello.txt");
    assert_eq!(result.lines.len(), 1);
    assert_eq!(result.lines[0].line, "hello world\n");
    assert_eq!(result.lines[0].rev, Some(0));
}

#[test]
fn annotate_with_user_and_date() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let result = client
        .annotate(
            "hello.txt".as_ref(),
            AnnotateArgs {
                user: true,
                date: true,
                ..Default::default()
            },
        )
        .unwrap();
    assert_eq!(result.lines[0].user.as_deref(), Some("test"));
    assert!(result.lines[0].date.is_some());
}

#[test]
fn config_returns_entries() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let config = client.config().unwrap();
    assert!(!config.is_empty());
}

#[test]
fn config_get_existing() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    // bundle.mainreporoot is always set for a repo
    let value = client.config_get("bundle.mainreporoot").unwrap();
    assert!(value.is_some());
}

#[test]
fn config_get_missing() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let value = client.config_get("nonexistent.key").unwrap();
    assert!(value.is_none());
}

#[test]
fn resolve_rev() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();
    let node = client.resolve_rev("0").unwrap();
    // Full node hash is 40 hex characters.
    assert_eq!(node.len(), 40);
    assert!(node.chars().all(|c| c.is_ascii_hexdigit()));
}

#[test]
fn add_and_commit() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Create a new file and add+commit via the API.
    std::fs::write(dir.path().join("new.txt"), "new file\n").unwrap();

    client.add(&["new.txt".as_ref()]).unwrap();

    let status = client.status(StatusArgs::default()).unwrap();
    assert_eq!(status.len(), 1);
    assert_eq!(status[0].status, "A");

    let node = client
        .commit(CommitArgs {
            message: "add new file".into(),
            user: Some("test".into()),
            files: vec![],
            close_branch: false,
            date: None,
        })
        .unwrap();
    assert_eq!(node.len(), 40);

    // Status should be clean now.
    let status = client.status(StatusArgs::default()).unwrap();
    assert!(status.is_empty());

    // Log should show 2 commits.
    let entries = client.log(LogArgs::default()).unwrap();
    assert_eq!(entries.len(), 2);
    assert_eq!(entries[0].desc, "add new file");
}

#[test]
fn remove_file() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();

    client.remove(&["hello.txt".as_ref()]).unwrap();

    let status = client.status(StatusArgs::default()).unwrap();
    assert_eq!(status.len(), 1);
    assert_eq!(status[0].path, "hello.txt");
    assert_eq!(status[0].file_status(), Some(FileStatus::Removed));
}

#[test]
fn update_to_rev() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Create a second commit.
    std::fs::write(dir.path().join("hello.txt"), "v2\n").unwrap();
    Command::new("hg")
        .args(["commit", "-m", "v2", "-u", "test"])
        .current_dir(dir.path())
        .status()
        .unwrap();

    // Update back to rev 0.
    client
        .update(UpdateArgs {
            rev: Some("0".into()),
            ..Default::default()
        })
        .unwrap();

    let content = std::fs::read_to_string(dir.path().join("hello.txt")).unwrap();
    assert_eq!(content, "hello world\n");
}

#[test]
fn update_clean() {
    if !hg_available() {
        return;
    }
    let (dir, mut client) = setup_test_repo();

    // Modify file, then discard with clean update.
    std::fs::write(dir.path().join("hello.txt"), "dirty\n").unwrap();

    client
        .update(UpdateArgs {
            clean: true,
            ..Default::default()
        })
        .unwrap();

    let content = std::fs::read_to_string(dir.path().join("hello.txt")).unwrap();
    assert_eq!(content, "hello world\n");
}

#[test]
fn create_and_delete_bookmark() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();

    client.bookmark("mybookmark", None).unwrap();

    let bookmarks = client.bookmarks().unwrap();
    assert_eq!(bookmarks.len(), 1);
    assert_eq!(bookmarks[0].bookmark, "mybookmark");

    client.bookmark_delete("mybookmark").unwrap();

    let bookmarks = client.bookmarks().unwrap();
    assert!(bookmarks.is_empty());
}

#[test]
fn create_tag() {
    if !hg_available() {
        return;
    }
    let (_dir, mut client) = setup_test_repo();

    client.tag("v1.0", Some("0")).unwrap();

    let tags = client.tags().unwrap();
    assert!(tags.iter().any(|t| t.tag == "v1.0"));
}
