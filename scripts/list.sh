#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

usage() {
    printf 'Usage: %s\n' "./scripts/list.sh"
}

[ "$#" -eq 0 ] || {
    usage >&2
    die "list.sh does not accept arguments."
}

load_config
require_commands find sort wc date

if [ ! -d "$BACKUP_DIRECTORY_ABS" ]; then
    printf 'No completed backups found in %s.\n' "$BACKUP_DIRECTORY_REL"
    exit 0
fi

archive_list="$(find "$BACKUP_DIRECTORY_ABS" -maxdepth 1 -type f -name "${ARCHIVE_PREFIX}-*.tar.gz.age" -print 2>/dev/null | LC_ALL=C sort -r)"

if [ -z "$archive_list" ]; then
    printf 'No completed backups found in %s.\n' "$BACKUP_DIRECTORY_REL"
    exit 0
fi

printf '%-48s  %-12s  %s\n' "Filename" "Size (bytes)" "Modified"

old_ifs="$IFS"
IFS=$'\n'
for archive_path in $archive_list; do
    printf '%-48s  %-12s  %s\n' \
        "$(basename -- "$archive_path")" \
        "$(file_size_bytes "$archive_path")" \
        "$(date -r "$archive_path" '+%Y-%m-%d %H:%M:%S %Z')"
done
IFS="$old_ifs"
