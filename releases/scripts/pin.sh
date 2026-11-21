#!/bin/bash

set -e


# Include shared functions
. .shared.sh


usage() {
    printf "\e[1;97musage:\033[0m $(basename "$0") [--help/-h|--tip/-t]\n"
    printf "pins checkout to the latest version of Firefox on the current branch\n"
    printf "pass -t to pin to tip instead\n\n"

    printf "\e[92m100%% organic\e[0m\n"
    printf "\e[32mmade without ai\e[0m\n"
}

nothing_to_commit() {
    if [[ $(git status) == *"nothing to commit"* ]]; then
        true
    else
        false
    fi
}


# Parse arguments
declare -A valid_args=(
    [help]='h help'
    [tip]='t tip'
)
parse_args valid_args[@] 0 "$@"


# Verify requirements
verify_git_repo
verify_comm_checkout


if opt_passed "${valid_args[help]}"; then
    usage
    exit 0
fi


# Get currently active branch
branch="$(git branch --show-current)"


# Get paths to version files and .gecko_rev.yml
git_root="$(git rev-parse --show-toplevel)"

ver_txt="$git_root/mail/config/version.txt"
ver_disp_txt="$git_root/mail/config/version_display.txt"
gecko_rev_yml="$git_root/.gecko_rev.yml"


# Get current version numbers
ver="$(cat "$ver_txt")"
ver_disp="$(cat "$ver_disp_txt")"


# Get components of version number
IFS='.' read -r major minor patch < "$ver_txt"


# Construct base tag and release tag regex
ver_re="${major}_([0-9]+_[0-9]+|[0-9]+)"

case $branch in
    beta)
        ver_re="${ver_re}b[0-9]*"
        ;;

    esr*)
        ver_re="${ver_re}esr"
        ;;
esac

base_tag="FIREFOX_RELEASE_${major}_BASE"
rel_tag_re="FIREFOX_${ver_re}_(RELEASE|BUILD[0-9]+)"


# If pinning to tip
if opt_passed "${valid_args[tip]}"; then
    # Set pin tag to default
    pin_tag="default"

    # Comment out GECKO_HEAD_REV on disk
    sed -i -e "s/^[[:space:]]*GECKO_HEAD_REV:/# GECKO_HEAD_REV:/" "$gecko_rev_yml"

    # Echo tag pinning message
    echo_info "pinning to tip"
else
    # Ensure that GECKO_HEAD_REV is not commented out
    if ! grep -qG "^[[:space:]]*GECKO_HEAD_REV:" "$gecko_rev_yml"; then
        sed -i -e "0,/^#[[:space:]]*GECKO_HEAD_REV:/{s/^#[[:space:]]*GECKO_HEAD_REV:/GECKO_HEAD_REV:/}" "$gecko_rev_yml"
    fi

    # Enter Firefox directory
    cd ..

    # Get tag to pin
    git_wrap fetch -q origin
    tags=(
        $(git for-each-ref --sort=creatordate --format '%(refname)' refs/tags |
        grep -oE "($base_tag|$rel_tag_re)")
    )

    if [ -z "${#tags[@]}" ]; then
        echo_err "no viable tags found"
        exit -1;
    fi

    idx=$((${#tags[@]} - 1))  # Index of last tag in array
    pin_tag="${tags[$idx]}"

    # Retrieve Mercurial revision associated with selected tag
    pin_rev=$(git2hg firefox $(git rev-list -n 1 $pin_tag))


    # Return to Thunderbird directory
    cd "$git_root"

    # Write pin revision to disk
    echo_info "pinning revision $pin_rev"
    sed -i -e "s/^GECKO_HEAD_REV:.*$/GECKO_HEAD_REV: $pin_rev/" "$gecko_rev_yml"

    # Echo tag pinning message
    echo_info "pinning tag $pin_tag"
fi

# Write pin tag to disk
sed -i -e "s/^GECKO_HEAD_REF:.*$/GECKO_HEAD_REF: $pin_tag/" "$gecko_rev_yml"


if nothing_to_commit; then
    if opt_passed "${valid_args[tip]}"; then
        echo_info "you are already pinned to tip"
    else
        echo_info "you are already pinned to the latest tag"
    fi
else
    # Commit version bump
    commit_msg="No bug - Pin to mozilla-$branch (${pin_tag}/${pin_rev:0:12}). r+a=release"

    git_wrap add "$gecko_rev_yml"
    git_wrap commit -q -m "$commit_msg"

    if [ $? -ne 0 ]; then
        echo_err "an unexpected error occurred"
        exit -1
    fi


    # Output diff
    git_wrap diff --color HEAD~1 HEAD


    # Success
    party_print "pinning successful!"
fi
