#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

load_config "${1:-}"
validate_source

manifest="$AI_ARCADE_STATE_DIR/game-library-sha256.private-manifest.txt"
manifest_tmp="${manifest}.tmp"

printf '# AI Arcade private library manifest\n' > "$manifest_tmp"
printf '# Generated: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$manifest_tmp"
printf '# Source: %s\n' "$ROM_SOURCE" >> "$manifest_tmp"
printf '# Format: SHA256<TAB>bytes<TAB>relative-path\n' >> "$manifest_tmp"

while IFS= read -r -d '' file; do
  rel="${file#"$ROM_SOURCE"/}"
  hash="$(sha256sum "$file" | awk '{print $1}')"
  bytes="$(stat -c '%s' "$file")"
  printf '%s\t%s\t%s\n' "$hash" "$bytes" "$rel" >> "$manifest_tmp"
done < <(find "$ROM_SOURCE" -type f -print0 | sort -z)

mv "$manifest_tmp" "$manifest"
echo "Manifest written to: $manifest"
