#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

usage() {
    printf 'Usage: %s [backup-archive]\n' "./scripts/verify.sh"
}

[ "$#" -le 1 ] || {
    usage >&2
    die "verify.sh accepts at most one archive path."
}

case "${1:-}" in
    --help|-h)
        usage
        exit 0
        ;;
esac

load_config
require_commands age tar gzip

ARCHIVE_PATH="$(resolve_archive_argument "${1:-}")"
validate_archive_file "$ARCHIVE_PATH" 0

if ! verify_archive_stream "$ARCHIVE_PATH"; then
    die "Backup verification failed."
fi

printf 'Verified backup: %s\n' "$ARCHIVE_PATH"
