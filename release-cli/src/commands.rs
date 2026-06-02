use crate::{
    error::{CliError, Result},
    pin::{fetch_latest_tag_from_moz, pin_commit_message, update_gecko_rev},
    repo::Repositories,
    utils::{compare_patches, normalize_uplift_message},
};
use hg_cmdserver::{
    HgClient, HgRepo,
    api::{CommitArgs, LogArgs},
};
use mach::{Mach, commands::MachCommand};
use std::path::{Path, PathBuf};

pub fn pull_update(repos: &Repositories) -> Result<()> {
    let c_repo = repos.comm();
    let m_repo = repos.moz();

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

pub fn pin(repos: &Repositories) -> Result<()> {
    let c_repo = repos.comm();
    let m_repo = repos.moz();

    let path = c_repo.cwd.join("mail/config/version.txt");
    let content = std::fs::read_to_string(&path)?;
    let version = content.trim().split('.').next().ok_or_else(|| {
        CliError::CommandFailed(format!("version not found in {}", path.display()))
    })?;

    let m_repo_name = format!("mozilla-{}", m_repo.kind.name());
    let tag = fetch_latest_tag_from_moz(&m_repo_name, version)?;
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

pub fn uplifts(repos: &Repositories, approver: &str, revs: &[String]) -> Result<()> {
    let c_repo = repos.comm();
    let mut hg = HgClient::open(&c_repo.cwd)?;

    {
        let conn = hg.connection();

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

        let original_patch = hg.export(rev)?;

        let conn = hg.connection();

        // Dry-run
        conn.run_command_string(&["graft", "-r", rev, "-n"])?;
        conn.run_command_string(&["graft", "-r", rev])?;

        let desc = normalize_uplift_message(log[0].desc.as_str(), approver);
        conn.run_command_string(&["metaedit", "-m", desc.as_str()])?;

        let grafted_patch = hg.export(".")?;
        // Compare origin vs uplifted patch
        compare_patches(rev, &original_patch, &grafted_patch)?;
    }

    Ok(())
}

pub fn update_version(repos: &Repositories, version: &str) -> Result<()> {
    let c_repo = repos.comm();
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

pub fn run_mach(repos: &Repositories, cmd: MachCommand) -> Result<String> {
    let mach = Mach::new(repos.moz().cwd.clone());
    Ok(mach.run_command_string(cmd)?)
}

pub fn all(repos: &Repositories, version: &str, approver: &str, revs: &[String]) -> Result<()> {
    pull_update(repos)?;
    pin(repos)?;

    if repos.comm().is_esr() {
        update_version(repos, version)?;
    }

    let mach = Mach::new(repos.moz().cwd.clone());
    let check = mach.run_command(MachCommand::RustCheckUpstream)?;

    match check.return_code {
        0 => {}
        // https://searchfox.org/comm-central/source/python/rocbuild/rocbuild/rust.py#788
        88 => {
            run_mach(repos, MachCommand::RustSync)?;
            run_mach(repos, MachCommand::RustVendor)?;

            let c_repo = repos.comm();
            let moz_name = format!("mozilla-{}", repos.moz().kind.name());
            let mut hg = HgClient::open(&c_repo.cwd)?;
            hg.addremove(Path::new("third_party/rust"))?;
            hg.commit(CommitArgs {
                message: format!(
                    "No Bug - Vendored Rust from {}. r=release r+a={}",
                    moz_name, approver
                ),
                files: vec![],
                close_branch: false,
                user: None,
                date: None,
            })?;
        }
        code => {
            return Err(CliError::CommandFailed(format!(
                "mach tb-rust check-upstream failed with exit code {code}"
            )));
        }
    }

    uplifts(repos, approver, revs)
}
