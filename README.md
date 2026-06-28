# Encrypted Obsidian Vault Backups

Private Obsidian notes live in `vault/` on your machine and stay ignored by Git. This repo is for encrypted backup snapshots stored in `backups/`.

## Security

- The vault is plaintext locally.
- Backups are streamed as `tar | gzip | age --passphrase`.
- No plaintext archive is written to disk during backup.
- The passphrase is never stored in config, env vars, arguments, logs, or temp files.
- Restore temporarily writes plaintext into a private temp directory before moving the vault into place.
- Encrypted filenames, sizes, commit times, and backup count remain visible.
- If you lose the passphrase, the backups are unrecoverable.

## Requirements

- Bash 3.2+
- `tar`, `gzip`, `git`, `find`, `mktemp`
- `age`

Install `age` with:

- macOS: `brew install age`
- Debian/Ubuntu: `sudo apt install age`
- Other Linux: install the `age` package from your distro

## Setup

```bash
mkdir -p vault
```

Open `vault/` in Obsidian or copy an existing vault into it. `.obsidian/` is included in backups.

## Python Library

The Python implementation now lives in `src/vaultlib/` and is the shared library intended for notebook, future CLI, and future GUI layers.

Configuration is environment-variable based in this pass, and `VaultConfig.from_env()` will also load the same values from a local `.env` file when present.

```bash
make backup
make list
make verify
make restore
make commit
```

Equivalent `.env` file:

```dotenv
VAULT_REPO_ROOT=/absolute/path/to/your/repo
VAULT_PATH=vault
BACKUP_DIRECTORY=backups
ARCHIVE_PREFIX=vault-backup
```

Library usage:

```bash
make verify ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age'
make restore ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age'
make restore REPLACE_EXISTING=1
make restore ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age' REPLACE_EXISTING=1
make commit MESSAGE='Add encrypted vault backup'
```

## Notebook Demo

The notebook demo lives at `notebooks/vault.ipynb`. It uses `ipywidgets` for passphrase entry, archive selection, overwrite confirmation, and status output while calling `vaultlib` directly for all operations.

## Legacy Shell Commands

The original shell scripts are still present in `scripts/` during this migration, but the Python library is the canonical implementation for new interfaces.

## Typical flow

```bash
make backup
make list
make commit MESSAGE='Add encrypted vault backup'
git push
```

Only encrypted artifacts in `backups/` should be committed. Check occasionally that `vault/` is still ignored and untracked.
