#!/bin/bash

set -e


echo_warn() {
    printf "%bwarning:%b %b\n" "\033[1;93m" "\033[0m" "$*" >&2
}

echo_err() {
    printf "%berror:%b %b\n" "\033[1;91m" "\033[0m" "$*" >&2
}

echo_info() {
    echo -e "\e[0;36m$1\e[0m"
}

git_wrap() {
    echo -e "\e[0;36mrunning \e[1;96mgit $1\e[0m"
    git "$@"
}

party_print() {
    for (( i=0; i<${#1}; i++ )); do
        COLOR="\e[1;9$(($i % 5 + 1))m"

        echo -e -n "$COLOR${1:$i:1}"
        sleep 0.005
    done

    echo ""
}


if [ ! -d ".git" ]; then
    echo_err "Current working directory must be a git repository"
    exit -1
fi


# Get currently active branch
BRANCH="$(git branch --show-current)"


# Get paths to version files and .gecko_rev.yml
GIT_ROOT="$(git rev-parse --show-toplevel)"

VER_TXT="$GIT_ROOT/mail/config/version.txt"
VER_DISP_TXT="$GIT_ROOT/mail/config/version_display.txt"
GECKO_REV_YML="$GIT_ROOT/.gecko_rev.yml"


# Get current version numbers
VER="$(cat $VER_TXT)"
VER_DISP="$(cat $VER_DISP_TXT)"


# Get components of version number
IFS='.' read -r MAJOR MINOR PATCH < $VER_TXT

if [[ "$VER_DISP" =~ [0-9]+.[0-9]+.[0-9]+([a-z]+[0-9]*) ]]; then
    SUFFIX=${BASH_REMATCH[1]}
fi


# Construct base tag and release tag regex
VER_RE="${MAJOR}_([0-9]+_[0-9]+|[0-9]+)"

case $BRANCH in
    beta)
        VER_RE="${VER_RE}b[0-9]*"
        ;;

    esr*)
        VER_RE="${VER_RE}esr"
        ;;
esac

BASE_TAG="FIREFOX_RELEASE_${MAJOR}_BASE"
REL_TAG_RE="FIREFOX_${VER_RE}_(RELEASE|BUILD[0-9]+)"


# Enter Firefox directory
cd ..


# Get tag to pin
git_wrap fetch -q origin
TAGS=($(
    git for-each-ref --sort=-creatordate --format '%(refname)' refs/tags |
    grep -oE "($BASE_TAG|$REL_TAG_RE)"
))

if [ -z "${#TAGS[@]}" ]; then
    echo_err "No viable tags found"
    exit -1;
fi

PIN_TAG="${TAGS[0]}"


# Retrieve Mercurial revision associated with selected tag
HG_TAG_URL="https://hg-edge.mozilla.org/mozilla-unified/raw-rev/${PIN_TAG}"
TAG_PATCH_FILE="/tmp/tag.patch"
curl $HG_TAG_URL > "$TAG_PATCH_FILE"

PIN_REV=$(sed -nE 's/# Node ID ([a-f0-9]+)/\1/p' "$TAG_PATCH_FILE")


# Return to Thunderbird directory
cd "$GIT_ROOT"


# Write pin tag and revision to disk
sed -i -e "s/^GECKO_HEAD_REF:.*$/GECKO_HEAD_REF: $PIN_TAG/g" "$GECKO_REV_YML"
sed -i -e "s/^GECKO_HEAD_REV:.*$/GECKO_HEAD_REV: $PIN_REV/g" "$GECKO_REV_YML"

echo_info "pinning tag $PIN_TAG"
echo_info "pinning revision $PIN_REV"


# Commit version bump
COMMIT_MSG="No bug - Pin to mozilla-$BRANCH (${PIN_TAG}/${PIN_REV:0:12}). r+a=release"

git_wrap add "$GECKO_REV_YML"
git_wrap commit -q -m "$COMMIT_MSG"


# Output diff
git_wrap diff HEAD~1 HEAD


# Success
party_print "*.^~ pinning successful! \`-*."
