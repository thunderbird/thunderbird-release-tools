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

git_wrap() {
    printf "%b  $%b %b\n%b" "\e[1;92m" "\e[0;36m" "git $1" "\e[0m"
    git "$@" 2>&1 | sed 's/^/        /'
}

party_print() {
    for (( i=0; i<${#1}; i++ )); do
        COLOR="\e[1;9$(($i % 5 + 1))m"

        printf "$COLOR${1:$i:1}"
        sleep 0.005
    done

    echo ""
}


if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo_err "current working directory must be a git repository"
    exit -1
fi

# Warn if not in repo root
if [ ! "$PWD" = "$(git rev-parse --show-toplevel)" ]; then
    echo_warn "You are not currently in your repo root"
    echo_info "Change to repo root using:"
    echo_info "\n\tcd $(git rev-parse --show-toplevel)\n"
fi


# Fetch origin
git_wrap fetch origin


# Switch to appropriate branch
BRANCH="$1"
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [[ "$CUR_BRANCH" == "$BRANCH" ]]; then
    echo_info "already on specified branch"
elif [ -z "$BRANCH" ]; then
    BRANCH=$CUR_BRANCH
else
    git_wrap switch $BRANCH
fi


# Reset repository to tip of remote
git_wrap reset --hard "origin/$BRANCH"


# Success!
party_print "*.^~ ready to go! \`-*."
