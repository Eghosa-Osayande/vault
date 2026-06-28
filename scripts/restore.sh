#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

usage() {
    printf 'Usage: %s [backup-archive] [--replace-existing]\n' "./scripts/restore.sh"
}

archive_argument=""
replace_existing=0
temp_restore_directory=""
recovery_path=""
restored_previous_vault=0

cleanup_restore_temp() {
    safe_remove_temp_dir "$temp_restore_directory" || true
}

trap cleanup_restore_temp EXIT INT TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        --replace-existing)
            replace_existing=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            usage >&2
            die "Unknown option: $1"
            ;;
        *)
            if [ -n "$archive_argument" ]; then
                usage >&2
                die "Only one archive path may be provided."
            fi
            archive_argument="$1"
            ;;
    esac
    shift
done

validate_extracted_tree() {
    local temp_directory="$1"
    local top_level_entries
    local top_level_entry=""
    local entry_count=0
    local symlink_path
    local extracted_path
    local extracted_listing
    local parent_directory
    local resolved_path
    local old_ifs

    top_level_entries="$(find -P "$temp_directory" -mindepth 1 -maxdepth 1 -print 2>/dev/null)"
    [ -n "$top_level_entries" ] || die "Restored data is empty."

    old_ifs="$IFS"
    IFS=$'\n'
    for top_level_entry in $top_level_entries; do
        entry_count=$((entry_count + 1))
    done

    if [ "$entry_count" -ne 1 ]; then
        IFS="$old_ifs"
        die "Backup archive must extract to exactly one top-level directory."
    fi

    top_level_entry="$top_level_entries"
    IFS="$old_ifs"

    [ -L "$top_level_entry" ] && die "Restored vault root must not be a symbolic link."
    [ -d "$top_level_entry" ] || die "Restored vault root is not a directory."
    [ "$(basename -- "$top_level_entry")" = "$VAULT_BASENAME" ] || die "Backup archive restored an unexpected top-level directory."

    symlink_path="$(find -P "$temp_directory" -type l -print -quit 2>/dev/null || true)"
    if [ -n "$symlink_path" ]; then
        die "Restored data contains a symbolic link: $symlink_path"
    fi

    extracted_listing="$(find -P "$temp_directory" -mindepth 1 -print 2>/dev/null)"
    IFS=$'\n'
    for extracted_path in $extracted_listing; do
        parent_directory="$(dirname -- "$extracted_path")"
        resolved_path="$(cd -- "$parent_directory" && pwd -P)/$(basename -- "$extracted_path")"

        case "$resolved_path" in
            "$temp_directory"|"$temp_directory"/*)
                ;;
            *)
                IFS="$old_ifs"
                die "Restored data escaped the temporary directory: $extracted_path"
                ;;
        esac
    done
    IFS="$old_ifs"
}

create_recovery_path() {
    local vault_parent
    local candidate

    vault_parent="$(dirname -- "$VAULT_PATH_ABS")"

    while :; do
        candidate="$vault_parent/$VAULT_BASENAME.recovery-$(utc_timestamp)"
        if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        sleep 1
    done
}

load_config
validate_git_protection
require_commands age tar gzip find mktemp awk

ARCHIVE_PATH="$(resolve_archive_argument "$archive_argument")"
validate_archive_file "$ARCHIVE_PATH" 0

if ! validate_archive_listing "$ARCHIVE_PATH"; then
    die "Backup verification failed."
fi

if ! archive_has_safe_entry_types "$ARCHIVE_PATH"; then
    die "Backup archive contains symbolic links or hard links, or could not be listed safely."
fi

temp_restore_directory="$(make_private_temp_dir "obsidian-vault-restore")"

if ! age --decrypt "$ARCHIVE_PATH" | tar -xzf - -C "$temp_restore_directory"; then
    die "Failed to extract the backup archive."
fi

validate_extracted_tree "$temp_restore_directory"

mkdir -p "$(dirname -- "$VAULT_PATH_ABS")"

if [ -L "$VAULT_PATH_ABS" ]; then
    die "Existing vault path must not be a symbolic link: $VAULT_PATH_REL"
fi

if [ -e "$VAULT_PATH_ABS" ] && [ ! -d "$VAULT_PATH_ABS" ]; then
    die "Existing vault path is not a directory: $VAULT_PATH_REL"
fi

if [ -d "$VAULT_PATH_ABS" ]; then
    if directory_is_empty "$VAULT_PATH_ABS"; then
        rmdir -- "$VAULT_PATH_ABS" || die "Failed to remove the empty existing vault directory."
    elif [ "$replace_existing" -eq 1 ]; then
        recovery_path="$(create_recovery_path)"
        mv -- "$VAULT_PATH_ABS" "$recovery_path" || die "Failed to move the existing vault to the recovery path."
        restored_previous_vault=1
    else
        die "Existing vault is not empty. Re-run with --replace-existing to replace it."
    fi
fi

if ! mv -- "$temp_restore_directory/$VAULT_BASENAME" "$VAULT_PATH_ABS"; then
    if [ "$restored_previous_vault" -eq 1 ]; then
        if ! mv -- "$recovery_path" "$VAULT_PATH_ABS"; then
            error "Failed to restore the previous vault after placement failure."
        fi
    fi
    die "Failed to place the restored vault at $VAULT_PATH_REL."
fi

if [ -n "$recovery_path" ]; then
    printf 'Restored vault to: %s\nRecovery vault kept at: %s\n' "$VAULT_PATH_ABS" "$recovery_path"
else
    printf 'Restored vault to: %s\n' "$VAULT_PATH_ABS"
fi
