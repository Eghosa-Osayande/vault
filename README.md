# Encrypted Obsidian Vault Backups

This repository stores encrypted snapshots of a private Obsidian vault while the plaintext vault stays local in `vault/` and is ignored by Git.

## Purpose

The scripts create a compressed TAR stream of the vault, encrypt that stream directly with `age --passphrase`, and write only the encrypted artifact to `backups/`. The plaintext vault is never meant to be committed.

## Security model

- The local `vault/` directory is plaintext on the current device.
- The TAR stream is gzip-compressed and encrypted directly by `age`.
- Internal filenames and directory structure stay hidden because the whole TAR stream is encrypted.
- Backup creation does not write a plaintext `.tar` or `.tar.gz` file to disk.
- Restore temporarily writes plaintext files into a private temporary directory before moving the restored vault into place.
- The encrypted filename, file size, commit history, commit times, and number of backups are still visible.
- The scripts never store, log, or accept the passphrase as an argument, environment variable, config value, or temporary file.
- Use a long, unique passphrase and store it in a password manager as well as your memory.
- If the passphrase is lost, the encrypted backups cannot be recovered.
- Anyone with both the encrypted artifact and the passphrase can restore the vault.
- Local full-disk encryption is strongly recommended.
- `.gitignore` does not remove files that were already committed to Git history.
- Temporary-file cleanup reduces exposure but does not guarantee physical erasure on SSDs or copy-on-write filesystems.

## Prerequisites

- Bash 3.2 or later
- `tar`
- `gzip`
- `git`
- `find`
- `mktemp`
- `age`

Install `age` with:

- macOS (Homebrew): `brew install age`
- Debian/Ubuntu: `sudo apt install age`
- Other Linux distributions: install the `age` package from your system package manager or the official release instructions at [age-encryption.org](https://age-encryption.org/)

## Initial setup

Create the local vault directory:

```bash
mkdir -p vault
```

Open `vault/` as an Obsidian vault or copy an existing vault into it. The backup includes hidden files and directories, including `.obsidian/`.

## Backup

Run:

```bash
./scripts/backup.sh
```

`age` will prompt for the passphrase and confirmation during encryption, then prompt again during verification before the final `.tar.gz.age` file is renamed into place.

## Listing

Run:

```bash
./scripts/list.sh
```

## Verification

Verify the newest completed backup:

```bash
./scripts/verify.sh
```

Verify a selected artifact:

```bash
./scripts/verify.sh backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age
```

## Fresh-clone restoration

1. Clone the repository.
2. Install `age` and the other required tools.
3. Run:

```bash
./scripts/restore.sh
```

4. Enter the same passphrase used to create the backup.
5. Open the restored `vault/` directory in Obsidian.

## Replacement restore

To replace an existing non-empty vault with the newest backup snapshot:

```bash
./scripts/restore.sh --replace-existing
```

You can also restore a specific archive:

```bash
./scripts/restore.sh backups/vault-backup-2026-06-28T15-30-00Z.tar.gz.age --replace-existing
```

When replacing a non-empty vault, the old plaintext vault is moved to a sibling recovery directory such as `vault.recovery-2026-06-28T15-30-00Z`. That recovery directory is kept and is never deleted automatically.

## Git workflow

Only add encrypted artifacts:

```bash
git add backups/
git commit -m "Add encrypted vault backup"
git push
```

Always confirm that `vault/` and any `vault.recovery-*` directories remain ignored and untracked.

## Testing backups

Periodically restore a backup into a clean clone or a separate test location to confirm the passphrase and workflow still work.
