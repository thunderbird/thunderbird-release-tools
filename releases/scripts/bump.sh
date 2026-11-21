#!/bin/bash

set -e


# Include shared functions
. .shared.sh


usage() {
    printf "\e[1;97musage:\e[0m $(basename "$0") [--help/-h] [major|minor|patch]\n"
    printf "bumps the version number of current branch and commits the change\n\n"

    printf "\e[92m100%% organic\e[0m\n"
    printf "\e[32mmade without ai\e[0m\n\n"

    git_root="$(git rev-parse --show-toplevel)"
    echo_info "the current version is $(cat $git_root/mail/config/version_display.txt)"
}


# Parse arguments
declare -A valid_args=(
    [help]='h help'
)
parse_args valid_args[@] 1 "$@"


# Verify requirements
verify_git_repo
verify_comm_checkout


ver_lvl="${PARAMS[0]}"


if [ $# -eq 0 ] || opt_passed "${valid_args[help]}"; then
    usage
    exit 0
elif ! [[ "$ver_lvl" =~ ^(major|minor|patch)$ ]]; then
    echo_err "incorrect version level $ver_lvl"
    exit -1
fi


# Get currently active branch
branch="$(git branch --show-current)"

if ! [[ "$branch" =~ ^(release|esr[0-9]+)$ ]]; then
    echo_err "branch $branch is not supported; must be release or esr###"
    exit -1
fi


# Get paths to version files
git_root="$(git rev-parse --show-toplevel)"

ver_txt="$git_root/mail/config/version.txt"
ver_disp_txt="$git_root/mail/config/version_display.txt"


# Get current (old) version numbers
old_ver="$(cat $ver_txt)"
old_ver_disp="$(cat $ver_disp_txt)"


# Get components of version number
IFS='.' read -r major minor patch < "$ver_txt"
if [ -z $patch ]; then
    patch=0
fi


if [[ "$old_ver_disp" =~ [0-9]+\.[0-9]+\.[0-9]+([a-z]+) ]]; then
    suffix=${BASH_REMATCH[1]}
fi


# Increment appropriate version level
case $ver_lvl in
    major)
        major=$((major+1))
        minor=0
        patch=0
        ;;

    minor)
        minor=$((minor+1))
        patch=0
        ;;

    patch)
        patch=$((patch+1))
        ;;
esac

if [ $minor -eq 0 ] && [ $patch -eq 0 ]; then
    new_ver="$major.0"
else
    new_ver="$major.$minor.$patch"
fi
new_ver_disp="$new_ver$suffix"


# Write new versions to disk
echo "$new_ver" > "$ver_txt"
echo "$new_ver_disp" > "$ver_disp_txt"

echo_info "old version is $old_ver_disp"
echo_info "new version is $new_ver_disp"


# Commit version bump
commit_msg="No bug - Set version $new_ver_disp for release. r+a=release"

git_wrap add "$ver_txt" "$ver_disp_txt"
git_wrap commit -q -m "$commit_msg"

if [ $? -ne 0 ]; then
    echo_err "an unexpected error occurred"
    exit -1
fi


# Output diff
git_wrap diff --color HEAD~1 HEAD


# Success
party_print "bump successful!"
