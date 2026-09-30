#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 CONFIG_FILE RESTORE_DESTINATION" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

load_config "$1"
destination="$2"
mkdir -p "$destination"

aws s3 sync \
  "s3://$S3_BUCKET/library/" \
  "$destination/" \
  --region "$AWS_REGION" \
  --only-show-errors

echo "Restore completed to: $destination"
