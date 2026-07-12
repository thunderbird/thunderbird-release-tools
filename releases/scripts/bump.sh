#!/bin/bash

set -e


echo_info() {
    printf "%b(i)%b %b\n" "\e[1;94m" "\e[0m" "$*"
}

echo_warn() {
    printf "%b/!\%b %b\n" "\e[1;93m" "\e[0m" "$*" >&2
}

echo_err() {
    printf "%b[x]%b %b\n" "\e[1;91m" "\e[0m" "$*" >&2
}

usage() {
    echo -e "\e[1;97musage:\e[0m $(basename "$0") major|minor|patch\n"

    echo -e "\e[92m100% organic\e[0m"
    echo -e "\e[32mmade without ai\e[0m"
}

git_wrap() {
    printf "%b  $%b %b\n%b" "\e[1;92m" "\e[0;36m" "git $1" "\e[0m"
    git "$@" | sed 's/^/        /'
}

party_print() {
    for (( i=0; i<${#1}; i++ )); do
        COLOR="\e[1;9$(($i % 5 + 1))m"

        echo -e -n "$COLOR${1:$i:1}"
        sleep 0.005
    done

    echo ""
}


VER_LVL="$1"


if [ -z "$VER_LVL" ]; then
    usage
    exit 0
fi

if ! [[ "$VER_LVL" =~ ^(major|minor|patch)$ ]]; then
    echo_err "incorrect version level $VER_LVL"
    exit -1
fi

if [ ! -d ".git" ]; then
    echo_err "current working directory must be a git repository"
    exit -1
fi


# Get currently active branch
BRANCH="$(git branch --show-current)"

if ! [[ "$BRANCH" =~ ^(release|esr[0-9]+)$ ]]; then
    echo_err "branch $BRANCH is not supported; must be release or esr###"
    exit -1
fi


# Get paths to version files
GIT_ROOT="$(git rev-parse --show-toplevel)"

VER_TXT="$GIT_ROOT/mail/config/version.txt"
VER_DISP_TXT="$GIT_ROOT/mail/config/version_display.txt"


# Get current (old) version numbers
OLD_VER="$(cat $VER_TXT)"
OLD_VER_DISP="$(cat $VER_DISP_TXT)"


# Get components of version number
IFS='.' read -r MAJOR MINOR PATCH < $VER_TXT

if [[ "$OLD_VER_DISP" =~ [0-9]+\.[0-9]+\.[0-9]+([a-z]+) ]]; then
    SUFFIX=${BASH_REMATCH[1]}
fi


# Increment appropriate version level
case $VER_LVL in
    major)
        MAJOR=$((MAJOR+1))
        ;;

    minor)
        MINOR=$((MINOR+1))
        ;;

    patch)
        PATCH=$((PATCH+1))
        ;;
esac

NEW_VER="$MAJOR.$MINOR.$PATCH"
NEW_VER_DISP="$NEW_VER$SUFFIX"


# Write new versions to disk
echo "$NEW_VER" > "$VER_TXT"
echo "$NEW_VER_DISP" > "$VER_DISP_TXT"

echo_info "old version is $OLD_VER_DISP"
echo_info "new version is $NEW_VER_DISP"


# Commit version bump
COMMIT_MSG="No bug - Set version $NEW_VER_DISP for release. r+a=release"

git_wrap add "$VER_TXT" "$VER_DISP_TXT"
git_wrap commit -q -m "$COMMIT_MSG"


# Output diff
git_wrap diff --color HEAD~1 HEAD


# Success
party_print "*.^~ bump successful! \`-*."
