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
    echo -e "\e[1;97musage:\033[0m $(basename "$0") approver changeset\n"

    echo -e "\e[92m100% organic\e[0m"
    echo -e "\e[32mmade without ai\e[0m"
}

git_wrap() {
    printf "%b  $%b %b\n%b" "\e[1;92m" "\e[0;36m" "git $1" "\e[0m"
    git "$@" | sed 's/^/        /'
}

hg2git () {
    # The first parameter should be either "firefox" or "thunderbird"
    curl -sL "https://lando.moz.tools/api/hg2git/$1/$2" | jq -r '.git_hash'
}

git2hg () {
    # The first parameter should be either "firefox" or "thunderbird"
    curl -sL "https://lando.moz.tools/api/git2hg/$1/$2" | jq -r '.hg_hash'
}

party_print() {
    for (( i=0; i<${#1}; i++ )); do
        COLOR="\e[1;9$(($i % 5 + 1))m"

        echo -e -n "$COLOR${1:$i:1}"
        sleep 0.005
    done

    echo ""
}


MSG_FILE="/tmp/commit_msg.txt"

APPROVER="$1"
CHANGESET="$2"


if [ -z "$APPROVER" ]; then
    usage
    exit 0
fi

if [ -z "$CHANGESET" ]; then
    echo_err "missing changeset hash"
    usage
    exit -1
fi

if ((${#CHANGESET} < 7 || ${#CHANGESET} > 40)); then
    echo_err "hash length is ${#HASH}; must be between 7 and 40 characters"
    exit -1
fi

if [ ! -d ".git" ]; then
    echo_err "current working directory must be a git repository"
    exit -1
fi

if [[ $(git cat-file -t $CHANGESET 2> /dev/null) != "commit" ]]; then
    echo_warn "changeset not recognized by git"
    echo_info "attempting to convert to mercurial changeset"

    CHANGESET=$(hg2git thunderbird $CHANGESET)
    if [[ "$CHANGESET" == "null" ]]; then
        echo_err "changeset is not a valid git or mercurial hash"
        exit -1
    fi
fi


# Cherry-pick uplift commit
set +e

RESULT=$(git_wrap cherry-pick "$CHANGESET" 2> /dev/null)
echo "$RESULT"
if [[ "$RESULT" == *"nothing to commit"* ]]; then
    echo_info "changeset already uplifted"

    git cherry-pick --abort
    echo_info "cherry-pick aborted"

    exit 0
fi

set -e


# Extract uplift commit message to temporary file
git log -n 1 --format=%B > $MSG_FILE


# Remove any existing approvers from commit message
sed -i -E "1 s/r\+a=/r=/" $MSG_FILE
sed -i -E "1 s/ a=[A-Za-z0-9]+//" $MSG_FILE


# Add specified approver to commit message
read -r < $MSG_FILE

if [[ "$REPLY" == *"r=$APPROVER"* ]]; then
    sed -i -e "1 s/r=$APPROVER/r+a=$APPROVER/" $MSG_FILE
else
    sed -i -e "1 s/$/ a=$APPROVER/" $MSG_FILE
fi


# Remove DONTBUILD from commit message, since uplifts should always build
sed -i -e "1 s/ DONTBUILD//" $MSG_FILE


# Update commit with new message
git_wrap commit --amend -m "$(cat $MSG_FILE)"


# Success!
party_print "*.^~ uplift successful! \`-*."
