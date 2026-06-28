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

## Commands

```bash
make backup
make backup FILENAME='my-snapshot.tar.gz.age'
make list
make verify
make restore
make commit
```

Useful options:

```bash
make verify ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age'
make restore ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age'
make restore REPLACE_EXISTING=1
make restore ARCHIVE='backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age' REPLACE_EXISTING=1
make backup FILENAME='my-snapshot.tar.gz.age'
make commit MESSAGE='Add encrypted vault backup'
```

`make backup` will prompt for the passphrase once for encryption and again for verification. If you pass `FILENAME=...`, the file is created inside `backups/`; if that filename already exists, you will be asked to confirm before it is replaced. `make commit` stages `backups/` and creates a Git commit. `make restore REPLACE_EXISTING=1` moves the current vault to `vault.recovery-...` before placing the restored snapshot.

## Typical flow

```bash
make backup
make list
make commit MESSAGE='Add encrypted vault backup'
git push
```

Only encrypted artifacts in `backups/` should be committed. Check occasionally that `vault/` is still ignored and untracked.
