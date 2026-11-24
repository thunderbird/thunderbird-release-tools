#!/bin/bash

set -e


# Include shared functions
. "$(dirname "$0")/.shared.sh"


usage() {
    printf "\e[1;97musage:\033[0m $(basename "$0") [--help/-h|--phab/-p|--continue/-c] approver [changeset|phab ID]\n"
    printf "uplifts git or mercurial changeset to the current checkout and adds approver\n"
    printf "pass -p to use Phabricator ID instead of changeset\n\n"

    printf "\e[92m100%% organic\e[0m\n"
    printf "\e[32mmade without ai\e[0m\n"
}

is_cherry_picking() {
    local result="$(set +e; git rev-parse --verify CHERRY_PICK_HEAD 2> /dev/null; set -e)"

    if [ -z "$result" ]; then
        false
    else
        true
    fi
}

moz_wrap() {
    printf "%b  $ %b%b%b\n    " "\e[1;92m" "\e[0m" "moz-phab $1" "\e[0;37m"

    (
        shopt -s lastpipe
        shopt -so pipefail

        local result=0
        local user_prompt=false

        moz-phab "$@" 2>&1 |
        while IFS= read -rd ' ' word; do
            if $user_prompt; then
                user_prompt=false
                printf "\e[0;37m    "
            fi

            if [[ "$word" == *"(NO/Yes)?"* ]]; then
                user_prompt=true
                printf "\e[1;97m"
            fi

            echo -n "${word//$'\n'/$'\n'    } "
        done
        result=$?
        printf "$word\e[0m"

        return $result
    )
}

err_uplift_in_progress() {
    echo_err "cherry-pick already in progress"
    echo_info "resolve conflicts, then run \`$(basename "$0") [approver] --continue\` to complete"
    echo_info "run \`git cherry-pick --abort\` to discard"

    exit -1
}


# Parse arguments
declare -A valid_args=(
    [help]='h help'
    [phab]='p phab'
    [continue]='c continue'
)
parse_args valid_args[@] 2 "$@"


# Verify requirements
verify_git_repo
verify_comm_checkout


msg_file="/tmp/commit_msg.txt"
approver="${PARAMS[0]}"


if [ $# -eq 0 ] || opt_passed "${valid_args[help]}"; then
    usage
    exit 0
elif [ -z "${PARAMS[1]}" ]; then
    echo_err "missing changeset hash or phab ID"
    usage

    exit -1
elif opt_passed "${valid_args[continue]}"; then
    continuing=true

    if ! is_cherry_picking; then
        echo_err "no cherry-pick currently in progress"
        exit -1
    fi
elif opt_passed "${valid_args[phab]}"; then
    if is_cherry_picking; then
        err_uplift_in_progress
    fi

    using_phab=true
    phab_token=$(set +e; jq -r '.hosts."https://phabricator.services.mozilla.com/api/".token' $HOME/.arcrc 2> /dev/null; set -e)
    phab_id="${PARAMS[1]}"

    if [ -z "$phab_token" ]; then
        echo_err "unable to load phab token from ~/.arcrc; is moz-phab set up?"
        exit -1
    elif ! [[ "$phab_id" =~ ^D[[:digit:]]+$ ]]; then
        echo_err "phab ID is $phab_id; must fit the format \`D######\` and contain at least one digit"
        exit -1
    fi

    phab_id="${phab_id:1}"
else
    if is_cherry_picking; then
        err_uplift_in_progress
    fi

    changeset="${PARAMS[1]}"

    if (( ${#changeset} < 7 || ${#changeset} > 40 )); then
        echo_err "hash length is ${#hash}; must be between 7 and 40 characters"
        exit -1
    fi

    if [[ $(git cat-file -t $changeset 2> /dev/null) != "commit" ]]; then
        echo_warn "changeset not recognized by git"
        echo_info "attempting to convert to git changeset"

        changeset=$(hg2git thunderbird $changeset)
        if [[ "$changeset" == "" ]]; then
            echo_err "changeset is not a valid git or mercurial hash"
            exit -1
        fi
    fi
fi


# Uplift commit
if [ "$using_phab" = true ]; then
    # Apply patch using moz-phab
    if ! moz_wrap patch "$phab_id" --skip-dependencies --no-branch -a here; then
        echo_err "failed to apply patch"
        exit -1
    fi
elif [ "$continuing" = true ]; then
    echo_info "continuing cherry-pick"

    git_wrap add .
    GIT_EDITOR=true git_wrap cherry-pick --continue
else
    result=$(set +e; git_wrap cherry-pick "$changeset" 2> /dev/null; set -e)
    echo "$result"

    if [[ "$result" == *"nothing to commit"* ]]; then
        echo_info "changeset already uplifted"

        git cherry-pick --abort
        echo_info "cherry-pick aborted"

        exit 0
    elif [[ "$result" == *"CONFLICT"* ]]; then
        echo_err "merge conflicts occurred"
        echo_info "resolve conflicts, then run \`$(basename "$0") $approver --continue\`"

        exit -1
    fi
fi


# Extract uplift commit message to temporary file
git log -n 1 --format=%B > $msg_file


# Remove DONTBUILD from commit message, since uplifts should always build
sed -i -e "1 s/ DONTBUILD//" $msg_file


# If using Phabricator, update commit message to use actual reviewers
if [ "$using_phab" = true ]; then
    echo_info "retrieving reviewer data"
    
    # Retrieve Phabricator patch data
    json=$(
        curl -s https://phabricator.services.mozilla.com/api/differential.revision.search \
            -d api.token="$phab_token" \
            -d constraints[ids][0]="$phab_id" \
            -d attachments[reviewers]=1
    )

    # Extract reviewer PHIDs
    reviewer_phids=($(
        jq -r '
            .result.data[0].attachments.reviewers.reviewers|
            to_entries[]|
            select(
                (.value.status=="accepted") and
                (.value.reviewerPHID|startswith("PHID-USER"))
            )|
            .value.reviewerPHID' <<< "$json"
    ))

    if [ -z "$reviewer_phids" ]; then
        echo_err "no individual reviewers have accepted this revision"
        exit -1
    fi


    # Retrieve reviewer user data
    curl_cmd="curl -s https://phabricator.services.mozilla.com/api/phid.lookup -d api.token=$phab_token"
    for i in $(seq 0 $(((${#reviewer_phids[@]} - 1)))); do
        curl_cmd="$curl_cmd -d names[$i]=${reviewer_phids[$i]}"
    done
    json=$($curl_cmd)

    # Extract reviewer names
    usernames=$(jq -r ".result[].name" <<< "$json")
    full_names=$(jq -r ".result[].fullName" <<< "$json")
    
    reviewers="${usernames[@]//$'\n'/,}"


    # Remove any existing reviewers/approvers from commit message
    sed -i -E "1 s/\s(r|r\+a|a)=[#A-Za-z0-9]+//g" $msg_file

    # Add reviewer(s) and specified approver to commit message
    if [[ "$reviewers" == "$approver" ]]; then
        sed -i -e "1 s/$/ r+a=$approver/" $msg_file
    else
        sed -i -e "1 s/$/ r=$reviewers/" $msg_file
        sed -i -e "1 s/$/ a=$approver/" $msg_file
    fi
else
    # Remove any existing approvers from commit message
    sed -i -E "1 s/r\+a=/r=/" $msg_file
    sed -i -E "1 s/ a=[A-Za-z0-9]+//" $msg_file


    # Add specified approver to commit message
    read -r < $msg_file

    if [[ "$REPLY" == *"r=$approver"* ]]; then
        sed -i -e "1 s/r=$approver/r+a=$approver/" $msg_file
    else
        sed -i -e "1 s/$/ a=$approver/" $msg_file
    fi
fi


# Update commit with new message
git_wrap commit --amend -m "$(cat $msg_file)"


# Success!
if [ $? -eq 0 ]; then
    party_print "uplift successful!"
else
    echo_err "an unexpected error occurred"
fi
