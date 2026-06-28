# Encrypted Obsidian Vault Backups

Private Obsidian notes live in `vault/` on your machine and stay ignored by Git. This repo is for encrypted backup snapshots stored in `backups/`.

## Security

- The vault is plaintext locally.
- Backups are packaged in Python as `tar.gz` and then encrypted with a passphrase-derived key.
- No external encryption CLI is required.
- The passphrase is never stored in config, env vars, arguments, logs, or temp files.
- Restore temporarily writes plaintext into a private temp directory before moving the vault into place.
- Encrypted filenames, sizes, commit times, and backup count remain visible.
- If you lose the passphrase, the backups are unrecoverable.

## Requirements

- Python 3.11+
- `git`
- `ipywidgets` for the notebook demo
- Python dependencies from `requirements.txt`

## Setup

```bash
mkdir -p vault
```

Open `vault/` in Obsidian or copy an existing vault into it. `.obsidian/` is included in backups.

## Python Library

The Python implementation now lives in `src/vaultlib/` and is the shared library intended for notebook, future CLI, and future GUI layers.

Configuration is environment-variable based in this pass:

```bash
export VAULT_REPO_ROOT="$PWD"
export VAULT_PATH="vault"
export BACKUP_DIRECTORY="backups"
export ARCHIVE_PREFIX="vault-backup"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Library usage:

```python
from pathlib import Path

from vaultlib import PythonPassphraseBackend, SecretValue, VaultConfig, VaultService

config = VaultConfig.from_env()
service = VaultService(config, PythonPassphraseBackend())
backup = service.create_backup(SecretValue("correct horse battery staple"))
service.verify_backup(backup.archive_path, SecretValue("correct horse battery staple"))
service.restore_backup(Path(backup.archive_path), SecretValue("correct horse battery staple"), replace_existing=True)
```

## Notebook Demo

The notebook demo lives at `notebooks/vault_demo.ipynb`. It uses `ipywidgets` for passphrase entry, archive selection, overwrite confirmation, and status output while calling `vaultlib` directly for all operations.

## Legacy Shell Commands

The original shell scripts are still present in `scripts/` during this migration, but the Python library is the canonical implementation for new interfaces.

## Typical flow

```bash
export VAULT_REPO_ROOT="$PWD"
export VAULT_PATH="vault"
export BACKUP_DIRECTORY="backups"
export ARCHIVE_PREFIX="vault-backup"
.venv/bin/python -m unittest discover -s tests -v
```

Only encrypted artifacts in `backups/` should be committed. Check occasionally that `vault/` is still ignored and untracked.
