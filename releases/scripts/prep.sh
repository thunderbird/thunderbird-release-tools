#!/bin/bash

set -e


# Include shared functions
. .shared.sh


usage() {
    printf "\e[1;97musage:\033[0m $(basename "$0") [--help/-h] branch\n"
    printf "switches to a branch and makes sure the working copy is synced to the branch's remote tip\n"
    printf "if no branch is specified, the current branch is updated instead\n\n"

    printf "\e[92m100%% organic\e[0m\n"
    printf "\e[32mmade without ai\e[0m\n"
}


# Parse arguments
declare -A valid_args=(
    [help]='h help'
)
parse_args valid_args[@] 1 "$@"


# Verify requirements
verify_git_repo


if opt_passed "${valid_args[help]}"; then
    usage
    exit 0
fi


# Fetch origin
git_wrap fetch origin


# Switch to appropriate branch
branch="${PARAMS[0]}"
cur_branch=$(git rev-parse --abbrev-ref HEAD)

if [[ "$cur_branch" == "$branch" ]]; then
    echo_info "already on specified branch"
elif [ -z "$branch" ]; then
    branch=$cur_branch
else
    git_wrap switch $branch
fi


# Reset repository to tip of remote
git_wrap reset --hard "origin/$branch"


# Success!
party_print "ready to go!"
