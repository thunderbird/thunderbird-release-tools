# Shared helpers for the release scripts. Source this file; don't run it.

echo_info() {
  printf "%b(i)%b %b\n" "\e[1;94m" "\e[0m" "$*"
}

echo_warn() {
  printf "%b/!\%b %b\n" "\e[1;93m" "\e[0m" "$*" >&2
}

echo_err() {
  printf "%b[x]%b %b\n" "\e[1;91m" "\e[0m" "$*" >&2
}

require_git_repo() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo_err "current working directory must be a git repository"
    exit 1
  fi
}

require_comm_root() {
  require_git_repo
  COMM_ROOT="$(git rev-parse --show-toplevel)"

  if [[ ! -f "$COMM_ROOT/.gecko_rev.yml" ]]; then
    echo_err "must be run from inside the comm directory"
    exit 1
  fi
}

party_print() {
  for ((i = 0; i < ${#1}; i++)); do
    COLOR="\e[1;9$(($i % 5 + 1))m"

    printf "$COLOR${1:$i:1}"
    sleep 0.005
  done

  echo ""
}

hg2git() {
  # The first parameter should be either "firefox" or "thunderbird"
  declare -A REPO_MAP
  REPO_MAP[firefox]="firefox"
  REPO_MAP[thunderbird]="thunderbird-desktop"

  curl -sL "https://lando.moz.tools/api/hg2git/${REPO_MAP[$1]}/$2" | jq -r '.git_hash'
}
