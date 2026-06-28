# shellcheck shell=bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

error() {
    printf '%s\n' "$*" >&2
}

die() {
    error "Error: $*"
    exit 1
}

normalize_relative_path() {
    local label="$1"
    local raw_path="$2"
    local trimmed="$raw_path"
    local component
    local current_path="$REPO_ROOT"
    local components=()
    local IFS='/'

    [ -n "$raw_path" ] || die "$label must not be empty."

    case "$raw_path" in
        /*)
            die "$label must be relative to the repository root."
            ;;
        *$'\n'*|*$'\r'*)
            die "$label must not contain a newline."
            ;;
        *'//'*)
            die "$label must not contain repeated path separators."
            ;;
    esac

    while [ "$trimmed" != "${trimmed%/}" ]; do
        trimmed="${trimmed%/}"
    done

    [ -n "$trimmed" ] || die "$label must not resolve to the repository root."

    read -r -a components <<< "$trimmed"

    for component in "${components[@]}"; do
        case "$component" in
            ""|"."|"..")
                die "$label contains an unsafe path component: $raw_path"
                ;;
        esac

        if [ -L "$current_path/$component" ]; then
            die "$label must not resolve through a symbolic link: $raw_path"
        fi

        current_path="$current_path/$component"
    done

    printf '%s\n' "$trimmed"
}

path_is_within() {
    local parent_path="$1"
    local child_path="$2"

    case "$child_path" in
        "$parent_path"|"$parent_path"/*)
            return 0
            ;;
    esac

    return 1
}

resolve_repo_path() {
    local label="$1"
    local relative_path="$2"
    local normalized_path

    normalized_path="$(normalize_relative_path "$label" "$relative_path")" || return 1
    printf '%s\n' "$REPO_ROOT/$normalized_path"
}

load_config() {
    local config_path="$REPO_ROOT/config.sh"

    [ -f "$config_path" ] || die "Missing config.sh at $config_path"

    # shellcheck disable=SC1090
    . "$config_path"

    VAULT_PATH_REL="$(normalize_relative_path "VAULT_PATH" "${VAULT_PATH:-}")"
    BACKUP_DIRECTORY_REL="$(normalize_relative_path "BACKUP_DIRECTORY" "${BACKUP_DIRECTORY:-}")"
    VAULT_PATH_ABS="$REPO_ROOT/$VAULT_PATH_REL"
    BACKUP_DIRECTORY_ABS="$REPO_ROOT/$BACKUP_DIRECTORY_REL"
    VAULT_BASENAME="$(basename -- "$VAULT_PATH_ABS")"

    [ -n "${ARCHIVE_PREFIX:-}" ] || die "ARCHIVE_PREFIX must not be empty."

    case "$ARCHIVE_PREFIX" in
        *"/"*|*$'\n'*|*$'\r'*)
            die "ARCHIVE_PREFIX must be a simple filename prefix."
            ;;
    esac

    [ "$VAULT_PATH_ABS" != "$REPO_ROOT" ] || die "VAULT_PATH must not be the repository root."
    [ "$VAULT_PATH_ABS" != "$BACKUP_DIRECTORY_ABS" ] || die "VAULT_PATH and BACKUP_DIRECTORY must be different."

    path_is_within "$VAULT_PATH_ABS" "$BACKUP_DIRECTORY_ABS" && die "BACKUP_DIRECTORY must not be inside VAULT_PATH."
    path_is_within "$BACKUP_DIRECTORY_ABS" "$VAULT_PATH_ABS" && die "VAULT_PATH must not be inside BACKUP_DIRECTORY."

    if [ -e "$VAULT_PATH_ABS" ] && [ ! -d "$VAULT_PATH_ABS" ]; then
        die "VAULT_PATH exists but is not a directory: $VAULT_PATH_REL"
    fi

    if [ -e "$BACKUP_DIRECTORY_ABS" ] && [ ! -d "$BACKUP_DIRECTORY_ABS" ]; then
        die "BACKUP_DIRECTORY exists but is not a directory: $BACKUP_DIRECTORY_REL"
    fi
}

installation_hint() {
    local command_name="$1"

    case "$command_name" in
        age)
            printf 'Install age with Homebrew (`brew install age`) on macOS or your Linux package manager.\n' >&2
            ;;
        tar)
            printf 'Install tar from your system package manager.\n' >&2
            ;;
        gzip)
            printf 'Install gzip from your system package manager.\n' >&2
            ;;
        git)
            printf 'Install Git from https://git-scm.com/ or your system package manager.\n' >&2
            ;;
        find)
            printf 'Install the standard find utility from your system package manager.\n' >&2
            ;;
        mktemp)
            printf 'Install mktemp from your system package manager.\n' >&2
            ;;
        *)
            printf 'Install `%s` and try again.\n' "$command_name" >&2
            ;;
    esac
}

require_commands() {
    local command_name

    for command_name in "$@"; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            error "Missing required command: $command_name"
            installation_hint "$command_name"
            return 1
        fi
    done
}

validate_git_protection() {
    local tracked_paths

    require_commands git || return 1
    git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Repository root is not inside a Git working tree."

    if ! git -C "$REPO_ROOT" check-ignore -q -- "$VAULT_PATH_REL/.gitignore-probe"; then
        die "Vault path is not ignored by Git: $VAULT_PATH_REL"
    fi

    tracked_paths="$(git -C "$REPO_ROOT" ls-files -- "$VAULT_PATH_REL")"
    if [ -n "$tracked_paths" ]; then
        error "Vault files are already tracked by Git."
        error "$tracked_paths"
        return 1
    fi
}

utc_timestamp() {
    date -u '+%Y-%m-%dT%H-%M-%SZ'
}

file_size_bytes() {
    wc -c < "$1" | tr -d '[:space:]'
}

find_newest_completed_backup() {
    local newest_backup

    if [ ! -d "$BACKUP_DIRECTORY_ABS" ]; then
        return 1
    fi

    newest_backup="$(find "$BACKUP_DIRECTORY_ABS" -maxdepth 1 -type f -name "${ARCHIVE_PREFIX}-*.tar.gz.age" -print 2>/dev/null | LC_ALL=C sort | tail -n 1)"
    [ -n "$newest_backup" ] || return 1

    printf '%s\n' "$newest_backup"
}

archive_has_valid_extension() {
    local archive_path="$1"
    local allow_partial="${2:-0}"

    case "$archive_path" in
        *.tar.gz.age)
            return 0
            ;;
        *.tar.gz.age.partial)
            if [ "$allow_partial" -eq 1 ]; then
                return 0
            fi
            error "Partial backup archives cannot be used: $(basename -- "$archive_path")"
            return 1
            ;;
        *)
            error "Backup archive must end with .tar.gz.age: $(basename -- "$archive_path")"
            return 1
            ;;
    esac
}

validate_archive_filename() {
    local archive_filename="$1"

    [ -n "$archive_filename" ] || die "Archive filename must not be empty."

    case "$archive_filename" in
        */*|*' '*|*$'\t'*|*\"*|*\'*|*$'\n'*|*$'\r'*)
            die "Archive filename must be a simple filename."
            ;;
        *.partial)
            die "Archive filename must not end with .partial."
            ;;
    esac

    archive_has_valid_extension "$archive_filename" 0 || die "Invalid archive filename: $archive_filename"
    printf '%s\n' "$archive_filename"
}

archive_is_within_backup_directory() {
    path_is_within "$BACKUP_DIRECTORY_ABS" "$1"
}

prompt_for_confirmation() {
    local prompt_message="$1"
    local response

    [ -t 0 ] || die "Confirmation required, but no interactive terminal is available."

    while :; do
        printf '%s [y/N] ' "$prompt_message" > /dev/tty
        read -r response < /dev/tty || return 1

        case "$response" in
            [Yy]|[Yy][Ee][Ss])
                return 0
                ;;
            ""|[Nn]|[Nn][Oo])
                return 1
                ;;
        esac

        printf 'Please answer yes or no.\n' > /dev/tty
    done
}

resolve_archive_argument() {
    local archive_argument="${1:-}"

    if [ -z "$archive_argument" ]; then
        find_newest_completed_backup || die "No completed backup archives found in $BACKUP_DIRECTORY_REL."
        return 0
    fi

    case "$archive_argument" in
        /*)
            die "Archive paths must be relative to the repository root."
            ;;
    esac

    resolve_repo_path "archive path" "$archive_argument"
}

validate_archive_file() {
    local archive_path="$1"
    local allow_partial="${2:-0}"

    archive_is_within_backup_directory "$archive_path" || die "Backup archive must be inside $BACKUP_DIRECTORY_REL."
    [ -e "$archive_path" ] || die "Backup archive not found: $archive_path"
    [ -L "$archive_path" ] && die "Backup archive must not be a symbolic link: $archive_path"
    [ -f "$archive_path" ] || die "Backup archive is not a regular file: $archive_path"
    archive_has_valid_extension "$archive_path" "$allow_partial" || return 1
}

verify_archive_stream() {
    local archive_path="$1"

    age --decrypt "$archive_path" | tar -tzf - >/dev/null
}

normalize_archive_entry() {
    local archive_entry="$1"

    while [ "${archive_entry#./}" != "$archive_entry" ]; do
        archive_entry="${archive_entry#./}"
    done

    printf '%s\n' "$archive_entry"
}

validate_archive_entry_path() {
    local archive_entry="$1"
    local top_level_name

    [ -n "$archive_entry" ] || {
        error "Backup archive contains an empty path entry."
        return 1
    }

    case "$archive_entry" in
        /*)
            error "Backup archive contains an absolute path: $archive_entry"
            return 1
            ;;
        *'//'*)
            error "Backup archive contains repeated path separators: $archive_entry"
            return 1
            ;;
        .|..|./*|../*|*/./*|*/../*|*/.|*/..)
            error "Backup archive contains an unsafe path: $archive_entry"
            return 1
            ;;
    esac

    top_level_name="${archive_entry%%/*}"
    if [ "$top_level_name" != "$VAULT_BASENAME" ]; then
        error "Backup archive contains an unexpected top-level path: $archive_entry"
        return 1
    fi

    return 0
}

validate_archive_listing() {
    local archive_path="$1"
    local archive_listing
    local archive_entry
    local old_ifs

    archive_listing="$(age --decrypt "$archive_path" | tar -tzf -)" || return 1
    [ -n "$archive_listing" ] || die "Backup archive is empty."

    old_ifs="$IFS"
    IFS=$'\n'
    for archive_entry in $archive_listing; do
        archive_entry="$(normalize_archive_entry "$archive_entry")"
        validate_archive_entry_path "$archive_entry" || {
            IFS="$old_ifs"
            return 1
        }
    done
    IFS="$old_ifs"

    return 0
}

directory_is_empty() {
    local directory_path="$1"
    local first_entry

    [ -d "$directory_path" ] || return 1

    first_entry="$(find "$directory_path" -mindepth 1 -print -quit 2>/dev/null)"
    [ -z "$first_entry" ]
}

make_private_temp_dir() {
    local name_prefix="$1"
    local temp_base="${TMPDIR:-/tmp}"
    local temp_directory

    temp_base="${temp_base%/}"
    temp_directory="$(mktemp -d "$temp_base/$name_prefix.XXXXXX")" || return 1
    (
        cd -- "$temp_directory" && pwd -P
    )
}

safe_remove_temp_dir() {
    local target_path="$1"

    [ -n "$target_path" ] || return 0

    case "$target_path" in
        "/"|"")
            error "Refusing to remove an unsafe temporary path."
            return 1
            ;;
    esac

    [ "$target_path" != "$REPO_ROOT" ] || {
        error "Refusing to remove the repository root."
        return 1
    }

    if [ "${VAULT_PATH_ABS:-}" = "$target_path" ] || [ "${BACKUP_DIRECTORY_ABS:-}" = "$target_path" ]; then
        error "Refusing to remove a protected repository path: $target_path"
        return 1
    fi

    case "$target_path" in
        /tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*)
            ;;
        *)
            error "Refusing to remove an unexpected temporary path: $target_path"
            return 1
            ;;
    esac

    [ -e "$target_path" ] || return 0
    rm -rf -- "$target_path"
}

safe_remove_backup_temp_file() {
    local target_path="$1"

    [ -n "$target_path" ] || return 0

    case "$target_path" in
        "/"|"")
            error "Refusing to remove an unsafe backup temporary path."
            return 1
            ;;
    esac

    [ "$target_path" != "$REPO_ROOT" ] || {
        error "Refusing to remove the repository root."
        return 1
    }

    archive_is_within_backup_directory "$target_path" || {
        error "Refusing to remove a file outside the backup directory: $target_path"
        return 1
    }

    case "$target_path" in
        *.partial|*.tmp)
            ;;
        *)
            error "Refusing to remove an unexpected backup temporary path: $target_path"
            return 1
            ;;
    esac

    rm -f -- "$target_path"
}

safe_remove_backup_file() {
    local target_path="$1"

    [ -n "$target_path" ] || return 0

    case "$target_path" in
        "/"|"")
            error "Refusing to remove an unsafe backup path."
            return 1
            ;;
    esac

    [ "$target_path" != "$REPO_ROOT" ] || {
        error "Refusing to remove the repository root."
        return 1
    }

    archive_is_within_backup_directory "$target_path" || {
        error "Refusing to remove a file outside the backup directory: $target_path"
        return 1
    }

    archive_has_valid_extension "$target_path" 0 || return 1
    [ -L "$target_path" ] && {
        error "Refusing to remove a symbolic link backup path: $target_path"
        return 1
    }
    [ -e "$target_path" ] || return 0
    [ -f "$target_path" ] || {
        error "Refusing to remove a non-regular backup path: $target_path"
        return 1
    }

    rm -f -- "$target_path"
}
