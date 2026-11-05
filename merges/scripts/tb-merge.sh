#!/usr/bin/env bash

set -eu

echo_info() {
    printf "%b(i)%b %b\n" "\e[1;94m" "\e[0m" "$*"
}

echo_warn() {
    printf "%b/!\%b %b\n" "\e[1;93m" "\e[0m" "$*" >&2
}

echo_err() {
    printf "%b[x]%b %b\n" "\e[1;91m" "\e[0m" "$*" >&2
}

hg2git () {
    # The first parameter should be either "firefox" or "thunderbird"
    local repo
    case "$1" in
        firefox) repo="mozilla-unified" ;;
        #thunderbird) repo="comm-unified" ;;
        thunderbird) repo="conduit-testing/comm-infra-testing/" ;;
        *) echo_err "unknown project: $1"; return 1 ;;
    esac

    JSON=$(curl -fsSL "https://hg-edge.mozilla.org/$repo/json-pushes?changeset=$2" | jq -r "to_entries[].value")
    IDX=$(jq -r ".changesets|to_entries[]|select(.value|startswith(\"$2\"))|.key" <<< "$JSON")
    
    jq -r ".git_changesets[$IDX]" <<< "$JSON"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <from> <to> [<rev>]

Merge <from> into <to> through Lando, then restore <to>'s .gecko_rev.yml.

  <from>, <to>  main or autoland
  <rev>         revision of <from> to merge; defaults to the tip of <from>

Examples:
  $(basename "$0") main autoland
  $(basename "$0") autoland main 0123abcd
EOF
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac
if [[ $# -lt 2 ]]; then
    usage >&2; exit 1
fi

FROM=$1; TO=$2; REV=${3:-}

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo_err "Uncommitted changes in the working tree; commit or stash them first."
    exit 1
fi

git fetch origin
PRE=$(git rev-parse "origin/$TO")        # destination before the merge
if [[ -n "$REV" ]]; then
  
    if [[ $(git cat-file -t "$REV" 2> /dev/null) != "commit" ]]; then
        echo_warn "rev not recognized by git"
        echo_info "attempting to convert to git rev"

        REV=$(hg2git thunderbird "$REV")
        if [[ -z "$REV" || "$REV" == "null" || "$REV" == *$'\n'* ]]; then
            echo_err "rev is not a valid git or mercurial hash"
            exit 1 
        fi
    fi

    TARGET=$(git rev-parse --verify "$REV^{commit}")
    if ! git merge-base --is-ancestor "$TARGET" "origin/$FROM"; then
        echo_err "$REV is not on origin/$FROM."
        exit 1
    fi
else
    TARGET=$(git rev-parse "origin/$FROM")
fi

lando push-merge --lando-repo "staging-thunderbird-$TO" \
    --target-commit "$TARGET" --commit-message "Merge $FROM to $TO"

# lando exits 0 even if the job failed, so verify it landed
git fetch origin
if [ "$(git rev-parse "origin/$TO")" = "$PRE" ] ||
   ! git merge-base --is-ancestor "$TARGET" "origin/$TO"; then
    echo_err "Merge did not land; check the Lando job."
    exit 1
fi

if git diff --quiet "$PRE" "origin/$TO" -- .gecko_rev.yml; then
    echo_info ".gecko_rev.yml unchanged by merge; no fixup needed."
    exit 0
fi

# Fixup on top of Lando's merge, on a scratch branch
git switch -C tb-merge-fixup "origin/$TO"
trap 'echo_warn "Stopped on branch tb-merge-fixup; run git switch - to return."' ERR
git checkout "$PRE" -- .gecko_rev.yml
git commit -m "No Bug - Restore $TO .gecko_rev.yml after merge from $FROM" -- .gecko_rev.yml
lando push-commits --lando-repo "staging-thunderbird-$TO" --branch tb-merge-fixup

# As above, lando exits 0 even if the job failed
git fetch origin
if ! git diff --quiet "$PRE" "origin/$TO" -- .gecko_rev.yml; then
    echo_err "Fixup did not land; check the Lando job. The fixup commit is on tb-merge-fixup."
    exit 1
fi
trap - ERR
git switch -
