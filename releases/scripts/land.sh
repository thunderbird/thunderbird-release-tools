#!/bin/bash

set -e


# Include shared functions
. "$(dirname "$0")/.shared.sh"


usage() {
    printf "\e[1;97musage:\033[0m $(basename "$0") [--help/-h] branch\n"
    printf "lands local patches to remote Thunderbird branch, then updates local repo with remote changes\n"
    printf "for safety, remote branch must always be specified\n\n"

    printf "\e[92m100%% organic\e[0m\n"
    printf "\e[32mmade without ai\e[0m\n"
}

lando_wrap() {
    printf "%b  $ %b%b%b\n    " "\e[1;92m" "\e[0m" "lando $1" "\e[0;37m"

    (
        shopt -s lastpipe
        shopt -so pipefail

        local result=0
        local user_prompt=false

        lando "$@" 2>&1 |
        while IFS= read -rd ' ' word; do
            if $user_prompt; then
                user_prompt=false
                printf "\e[0;37m    "
            fi

            if [[ "$word" == *"[y/N]:"* ]]; then
                user_prompt=true
                printf "\e[1;97m"
            fi

            echo -n "${word//$'\n'/$'\n'    } "
        done
        result=$?
        printf "$word\e[0m"

        # If landing was cancelled
        if [[ "$word" == *"cancelled."* ]]; then
            return 255  # 255 to represent cancellation instead of failure
        fi

        return $result
    )
}


# Parse arguments
declare -A valid_args=(
    [help]='h help'
)
parse_args valid_args[@] 1 "$@"


# Verify requirements
verify_git_repo
verify_comm_checkout


if opt_passed "${valid_args[help]}"; then
    usage
    exit 0
elif [ $# -eq 0 ]; then
    echo_err "for safety, remote branch must be specified"
    exit -1
fi


# Switch to appropriate branch
branch="${PARAMS[0]}"
cur_branch=$(git rev-parse --abbrev-ref HEAD)

if [[ "$cur_branch" != "$branch" ]]; then
    echo_err "local branch \`$cur_branch\` does not match specified remote branch \`$branch\`"
    exit -1
fi


# Land patch
set +e
lando_wrap push-commits --lando-repo thunderbird-desktop-$branch
result=$?
set -e

if ! [ -z $result ]; then
    if [[ $result == 255 ]]; then
        echo_warn "landing cancelled"
    else
        echo_err "failed to land patch"
    fi
    
    exit -1
fi


# If local repo update failed
if ! (wet_blanket=true prep.sh); then
    echo_warn "patch landed successfully, but local repo could not be updated with remote changes"
else
    # Success
    party_print "landing successful!"
fi
