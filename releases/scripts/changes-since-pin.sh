#!/bin/bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"

git_wrap() {
  echo_info "git $*" >&2
  git -C "$SOURCE_ROOT" "$@" 2> >(sed 's/^/        /' >&2)
}

usage() {
  echo "Usage: $(basename "$0") [OPTIONS]"
  echo ""
  echo "Lists Firefox changes since the commit pinned in .gecko_rev.yml."
  echo "Run from inside comm directory."
  echo ""
  echo "Options:"
  echo "  -h, --help    Show this help message and exit"
}

# Validate input
if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
elif [[ $# -gt 0 ]]; then
  echo_err "unexpected argument '$1'"
  usage
  exit 1
fi

require_comm_root

SOURCE_ROOT="$(git -C "$COMM_ROOT/.." rev-parse --show-toplevel)"

GECKO_REV_YML="$COMM_ROOT/.gecko_rev.yml"
HG_REV=$(sed -n 's/^GECKO_HEAD_REV: *//p' "$GECKO_REV_YML")
if [[ -z $HG_REV ]]; then
  echo_err "no active GECKO_HEAD_REV in $GECKO_REV_YML"
  exit 1
fi

# Map the pinned Firefox repo to its git branch (mozilla-beta -> beta)
GECKO_REPO=$(sed -n 's/^GECKO_HEAD_REPOSITORY: *//p' "$GECKO_REV_YML")
REPO_NAME="${GECKO_REPO##*/}"
SOURCE_BRANCH="${REPO_NAME#mozilla-}"
if [[ $SOURCE_BRANCH == "central" ]]; then
  SOURCE_BRANCH="main"
fi

GIT_REV=$(hg2git firefox "$HG_REV")
if [[ -z $GIT_REV || $GIT_REV == "null" ]]; then
  echo_err "could not map hg rev $HG_REV to a git commit"
  exit 1
fi

echo_info "Checking for changes in firefox-${SOURCE_BRANCH} since ${GIT_REV} (git)"

# Bring source up to speed
echo ""
echo_info "Bringing source repo up to speed"
git_wrap fetch origin --tags

# Check if revision in source repo
echo ""
echo_info "Checking if revision is in firefox repo"
if [[ $(git_wrap cat-file -t "$GIT_REV") != "commit" ]]; then
  echo_err "$GIT_REV not found in source repo"
  exit 1
fi

# Check if revision is on source branch
echo ""
echo_info "Checking if revision is on firefox-${SOURCE_BRANCH}"
if ! git_wrap merge-base --is-ancestor "$GIT_REV" origin/"$SOURCE_BRANCH"; then
  echo_err "$GIT_REV not on origin/$SOURCE_BRANCH"
  exit 1
fi

# Count how many changes since the pinned revision
echo ""
echo_info "Counting changes since pinned revision"
COUNT=$(git_wrap rev-list --count --no-merges "$GIT_REV"..origin/"$SOURCE_BRANCH")
if [[ $COUNT -eq 0 ]]; then
  echo_info "No changes since $GIT_REV"
  exit 0
fi

echo ""
echo_info "$COUNT change(s) since $GIT_REV:"
echo ""

# Print changes since the pinned revision
git -C "$SOURCE_ROOT" --no-pager log \
  --no-merges \
  --format='%h %an — %s' \
  "$GIT_REV"..origin/"$SOURCE_BRANCH"
