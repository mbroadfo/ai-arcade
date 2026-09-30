#!/usr/bin/env bash
set -euo pipefail

load_config() {
  local config_file="${1:-}"
  if [[ -n "$config_file" ]]; then
    if [[ ! -f "$config_file" ]]; then
      echo "Config file not found: $config_file" >&2
      exit 2
    fi
    # shellcheck disable=SC1090
    set -a
    source "$config_file"
    set +a
  fi

  : "${ROM_SOURCE:?ROM_SOURCE must be set}"
  : "${S3_BUCKET:?S3_BUCKET must be set}"
  : "${AWS_REGION:?AWS_REGION must be set}"

  AI_ARCADE_STATE_DIR="${AI_ARCADE_STATE_DIR:-$HOME/.local/state/ai-arcade}"
  mkdir -p "$AI_ARCADE_STATE_DIR"
}

repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

validate_source() {
  if [[ ! -d "$ROM_SOURCE" ]]; then
    echo "ROM_SOURCE is not a directory: $ROM_SOURCE" >&2
    exit 3
  fi

  local source_real repo_real
  source_real="$(realpath "$ROM_SOURCE")"
  repo_real="$(realpath "$(repo_root)")"

  case "$source_real/" in
    "$repo_real"/*)
      echo "Refusing to use a game library inside the Git repository." >&2
      echo "Move/configure ROM_SOURCE outside: $repo_real" >&2
      exit 4
      ;;
  esac
}
