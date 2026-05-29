use std::path::PathBuf;

use hg_cmdserver::{
    HgClient, HgRepo,
    api::{CommitArgs, LogArgs},
};
use mach::{Mach, commands::MachCommand};

use crate::{
    cli::CommonArgs,
    error::Result,
    pin::{fetch_latest_tag, pin_commit_message, read_major_version, update_gecko_rev},
    utils::{build_repos_from_args, normalize_uplift_message},
};

pub fn pull_update(common: &CommonArgs) -> Result<()> {
    let repositories = build_repos_from_args(common)?;

    let c_repo = repositories.comm();
    let m_repo = repositories.moz();

    let mut c_hg = HgClient::open(&c_repo.cwd)?;
    let mut m_hg = HgClient::open(&m_repo.cwd)?;

    let c_conn = c_hg.connection();
    let m_conn = m_hg.connection();

    c_conn.run_command_string(&["pull", &c_repo.kind.url()])?;
    c_conn.run_command_string(&["up", &c_repo.kind.name(), "-C"])?;

    m_conn.run_command_string(&["pull", &m_repo.kind.url()])?;
    m_conn.run_command_string(&["up", &m_repo.kind.name(), "-C"])?;

    Ok(())
}

pub fn pin(common: &CommonArgs) -> Result<()> {
    let repositories = build_repos_from_args(common)?;

    let c_repo = repositories.comm();
    let m_repo = repositories.moz();

    // TODO: refactor pin functions
    let major_version = read_major_version(&c_repo.cwd)?;
    let m_repo_name = format!("mozilla-{}", m_repo.kind.name());
    let tag = fetch_latest_tag(&m_repo_name, &major_version)?;
    update_gecko_rev(&c_repo.cwd, &m_repo.kind.url(), &tag)?;
    let message = pin_commit_message(&m_repo_name, &tag);

    let mut hg = HgClient::open(&c_repo.cwd)?;

    hg.commit(CommitArgs {
        message,
        files: vec![PathBuf::from(".gecko_rev.yml")],
        close_branch: false,
        user: None,
        date: None,
    })?;

    Ok(())
}

pub fn uplifts(common: &CommonArgs, approver: &str, revs: &[String]) -> Result<()> {
    let repositories = build_repos_from_args(common)?;
    let c_repo = repositories.comm();
    let mut hg = HgClient::open(&c_repo.cwd)?;

    {
        let conn = hg.connection();

        // Check hg extensions
        let extensions = vec!["histedit", "evolve", "firefoxtree"];
        for extension in extensions {
            conn.run_command_string(&["config", format!("extensions.{}", extension).as_str()])?;
        }
    }

    for rev in revs {
        let log = hg.log(LogArgs {
            revs: Some(rev.to_string()),
            limit: None,
            follow: false,
            paths: vec![],
        })?;

        let conn = hg.connection();

        // Dry-run
        conn.run_command_string(&["graft", "-r", rev, "-n"])?;
        conn.run_command_string(&["graft", "-r", rev])?;

        let desc = normalize_uplift_message(log[0].desc.as_str(), approver);

        conn.run_command_string(&["metaedit", "-m", desc.as_str()])?;
    }

    Ok(())
}

pub fn update_version(common: &CommonArgs, version: &str) -> Result<()> {
    let repositories = build_repos_from_args(common)?;
    let c_repo = repositories.comm();
    let version_plain = version.strip_suffix("esr").unwrap_or(version);

    std::fs::write(
        c_repo.cwd.join("mail/config/version.txt"),
        format!("{}\n", version_plain),
    )?;

    std::fs::write(
        c_repo.cwd.join("mail/config/version_display.txt"),
        format!("{}\n", version),
    )?;

    let mut hg = HgClient::open(&c_repo.cwd)?;

    let message = format!("No bug - Set version {} for release. r+a=release", version);
    let files = vec![
        PathBuf::from("mail/config/version.txt"),
        PathBuf::from("mail/config/version_display.txt"),
    ];

    hg.commit(CommitArgs {
        message,
        files,
        close_branch: false,
        user: None,
        date: None,
    })?;

    Ok(())
}

pub fn run_mach(common: &CommonArgs, cmd: MachCommand) -> Result<String> {
    let repositories = build_repos_from_args(common)?;
    let mach = Mach::new(repositories.moz().cwd.clone());
    let output = mach.run_command_string(cmd)?;

    Ok(output)
}
