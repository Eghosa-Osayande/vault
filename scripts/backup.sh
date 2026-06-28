#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

usage() {
    printf 'Usage: %s [filename.tar.gz.age]\n' "./scripts/backup.sh"
}

archive_filename=""
archive_filename_from_env="${BACKUP_FILENAME:-}"
PARTIAL_ARCHIVE_ABS=""
FINAL_ARCHIVE_ABS=""

cleanup_partial_archive() {
    safe_remove_backup_temp_file "$PARTIAL_ARCHIVE_ABS" || true
}

trap cleanup_partial_archive EXIT INT TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            usage >&2
            die "Unknown option: $1"
            ;;
        *)
            if [ -n "$archive_filename" ]; then
                usage >&2
                die "Only one archive filename may be provided."
            fi
            if [ -n "$archive_filename_from_env" ]; then
                usage >&2
                die "Specify the backup filename either through BACKUP_FILENAME or as an argument, not both."
            fi
            archive_filename="$1"
            ;;
    esac
    shift
done

if [ -z "$archive_filename" ]; then
    archive_filename="$archive_filename_from_env"
fi

load_config
validate_git_protection

[ -e "$VAULT_PATH_ABS" ] || die "Vault directory not found: $VAULT_PATH_REL"
[ -L "$VAULT_PATH_ABS" ] && die "Vault directory must not be a symbolic link: $VAULT_PATH_REL"
[ -d "$VAULT_PATH_ABS" ] || die "Vault path is not a directory: $VAULT_PATH_REL"

require_commands age tar gzip find mktemp

symlink_path="$(find -P "$VAULT_PATH_ABS" -mindepth 1 -type l -print -quit 2>/dev/null || true)"
if [ -n "$symlink_path" ]; then
    symlink_path="${symlink_path#"$VAULT_PATH_ABS"/}"
    die "Symbolic links inside the vault are not allowed: $symlink_path"
fi

if [ -e "$BACKUP_DIRECTORY_ABS" ] && [ -L "$BACKUP_DIRECTORY_ABS" ]; then
    die "Backup directory must not be a symbolic link: $BACKUP_DIRECTORY_REL"
fi

mkdir -p "$BACKUP_DIRECTORY_ABS"

if [ -L "$BACKUP_DIRECTORY_ABS" ]; then
    die "Backup directory must not be a symbolic link: $BACKUP_DIRECTORY_REL"
fi

if [ -n "$archive_filename" ]; then
    archive_filename="$(validate_archive_filename "$archive_filename")"
    FINAL_ARCHIVE_ABS="$BACKUP_DIRECTORY_ABS/$archive_filename"
    PARTIAL_ARCHIVE_ABS="$FINAL_ARCHIVE_ABS.partial"

    if [ -e "$FINAL_ARCHIVE_ABS" ] || [ -e "$PARTIAL_ARCHIVE_ABS" ]; then
        if ! prompt_for_confirmation "Replace existing backup $(basename -- "$FINAL_ARCHIVE_ABS")?"; then
            die "Backup replacement cancelled."
        fi

        safe_remove_backup_file "$FINAL_ARCHIVE_ABS" || die "Failed to remove the existing backup archive."
        safe_remove_backup_temp_file "$PARTIAL_ARCHIVE_ABS" || die "Failed to remove the existing partial backup archive."
    fi
else
    while :; do
        timestamp="$(utc_timestamp)"
        FINAL_ARCHIVE_ABS="$BACKUP_DIRECTORY_ABS/$ARCHIVE_PREFIX-$timestamp.tar.gz.age"
        PARTIAL_ARCHIVE_ABS="$FINAL_ARCHIVE_ABS.partial"

        if [ ! -e "$FINAL_ARCHIVE_ABS" ] && [ ! -e "$PARTIAL_ARCHIVE_ABS" ]; then
            break
        fi

        sleep 1
    done
fi

vault_parent="$(dirname -- "$VAULT_PATH_ABS")"

if ! tar -C "$vault_parent" -czf - "$VAULT_BASENAME" | age --passphrase --output "$PARTIAL_ARCHIVE_ABS"; then
    die "Backup creation failed."
fi

if ! verify_archive_stream "$PARTIAL_ARCHIVE_ABS"; then
    die "Backup verification failed."
fi

mv -- "$PARTIAL_ARCHIVE_ABS" "$FINAL_ARCHIVE_ABS" || die "Failed to finalize the backup archive."
PARTIAL_ARCHIVE_ABS=""

printf 'Backup created: %s (%s bytes)\n' "$FINAL_ARCHIVE_ABS" "$(file_size_bytes "$FINAL_ARCHIVE_ABS")"
