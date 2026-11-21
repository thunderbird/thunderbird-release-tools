# Shared script functions
# 
# Include this file using `. .shared.sh`


# Printing functions
echo_info() {
    printf "%b(i)%b %b\n" "\e[1;94m" "\e[0m" "$@"
}

echo_warn() {
    printf "%b/!\%b %b\n" "\e[1;93m" "\e[0m" "$@" >&2
}

echo_err() {
    printf "%b[x]%b %b\n" "\e[1;91m" "\e[0m" "$@" >&2
}

party_print() {
    if ! [ -z $wet_blanket ]; then
        return
    fi

    local str="*.^~ $1 \`-*."

    for (( i=0; i<${#str}; i++ )); do
        local color="\e[1;9$(($i % 5 + 1))m"

        printf "$color${str:$i:1}"
        sleep 0.005
    done

    echo ""
}


# Argument parsing functions
parse_args() {
    # Get list of valid, non-option parameters
    local valid=("${!1}")

    # Get maximum number of non-option parameters
    declare -i max_params=$2

    # Shift by 2, so that remaining function arguments are script arguments
    shift 2

    declare -a opts        # Script options
    declare -a params      # Script non-option parameters
    declare -i n_params=0  # Running total of non-option parameters

    # Loop through script arguments
    for arg in "$@"; do
        if [[ $arg =~ ^--[^-]+$ ]]; then
            arg="${arg:2}"

            # If option is invalid
            if [[ ! " ${valid[@]} " =~ [[:space:]]$arg[[:space:]] ]]; then
                echo_err "invalid option \`--$arg\`"
                exit -1
            fi

            opts+=("$arg")
        elif [[ $arg =~ ^-[^-]+$ ]]; then
            arg="${arg:1}"

            # Loop over single-character options in argument
            for (( i=0; i<${#arg}; i++ )); do
                opt=${arg:$i:1}

                # If option is invalid
                if [[ ! " ${valid[@]} " =~ [[:space:]]$opt[[:space:]] ]]; then
                    echo_err "invalid option \`-$opt\`"
                    exit -1
                fi

                opts+=("$opt")
            done
        else
            params+=("$arg")
            n_params+=1

            # If there are too many non-option parameters
            if (( $n_params > $max_params )); then
                echo_err "unknown extra parameter \`$arg\`"
                exit -1
            fi
        fi
    done

    declare -rga OPTS=("${opts[@]}")
    declare -rga PARAMS=("${params[@]}")
}

opt_passed() {
    # Convert supplied option forms to list
    local opt=(${1})

    # If option was passed
    for opt in "${opt[@]}"; do
        if [[ " ${OPTS[@]} " =~ [[:space:]]$opt[[:space:]] ]]; then
            return
        fi
    done

    false
}


# Repo functions
verify_git_repo() {
    if ! $(git rev-parse --is-inside-work-tree 2> /dev/null); then
        echo_err "current working directory must be part of a git repository"
        exit -1
    fi
}

verify_comm_checkout() {
    git_root="$(git rev-parse --show-toplevel)"

    if ! [ -e "$git_root/.gecko_rev.yml" ]; then
        echo_err "current working directory must be part of a comm checkout"
        exit -1
    fi
}

git_wrap() {
    printf "%b  $ %b%b%b\n" "\e[1;92m" "\e[0m" "git $1" "\e[0;37m"
    git "$@" 2>&1 | sed 's/^/    /'
    printf "\e[0m"
}

hg2git () {
    # The first parameter should be either "firefox" or "thunderbird"
    declare -A repo_map
    repo_map[firefox]="mozilla-unified"
    repo_map[thunderbird]="comm-unified"

    local json=$(curl -sL "https://hg-edge.mozilla.org/${repo_map[$1]}/json-pushes?changeset=$2" | jq -r "to_entries[].value")
    local idx=$(jq -r ".changesets|to_entries[]|select(.value|startswith(\"$2\"))|.key" <<< "$json" 2> /dev/null)

    echo -n $(set +e; jq -r ".git_changesets[$idx]" <<< "$json" 2> /dev/null; set -e)
}

git2hg () {
    # The first parameter should be either "firefox" or "thunderbird"
    declare -A repo_map
    repo_map[firefox]="firefox"
    repo_map[thunderbird]="thunderbird-desktop"

    curl -sL "https://lando.moz.tools/api/git2hg/${repo_map[$1]}/$2" | jq -r '.hg_hash'
}
