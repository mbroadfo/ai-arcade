#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

load_config "${1:-}"
validate_source

command -v aws >/dev/null 2>&1 || {
  echo "AWS CLI is required." >&2
  exit 5
}

"$SCRIPT_DIR/build-manifest.sh" "${1:-}"
manifest="$AI_ARCADE_STATE_DIR/game-library-sha256.private-manifest.txt"

# Copy local files to the private bucket. --only-show-errors keeps logs usable.
# No --delete by default: a local deletion should not silently erase the backup.
aws s3 sync \
  "$ROM_SOURCE/" \
  "s3://$S3_BUCKET/library/" \
  --region "$AWS_REGION" \
  --only-show-errors

aws s3 cp \
  "$manifest" \
  "s3://$S3_BUCKET/manifests/$(basename "$manifest")" \
  --region "$AWS_REGION" \
  --only-show-errors

echo "Backup completed to s3://$S3_BUCKET/"
