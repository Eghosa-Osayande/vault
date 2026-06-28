from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vaultlib.config import VaultConfig
from vaultlib.exceptions import ConfigError


class VaultConfigTests(unittest.TestCase):
    def test_from_env_requires_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ConfigError):
                VaultConfig.from_env({"VAULT_REPO_ROOT": temp_dir})

    def test_from_env_rejects_overlapping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ConfigError):
                VaultConfig.from_env(
                    {
                        "VAULT_REPO_ROOT": temp_dir,
                        "VAULT_PATH": "vault",
                        "BACKUP_DIRECTORY": "vault/backups",
                        "ARCHIVE_PREFIX": "vault-backup",
                    }
                )

    def test_from_env_rejects_symlink_path_components(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            real_dir = repo_root / "real"
            real_dir.mkdir()
            os.symlink(real_dir, repo_root / "vault-link")
            with self.assertRaises(ConfigError):
                VaultConfig.from_env(
                    {
                        "VAULT_REPO_ROOT": temp_dir,
                        "VAULT_PATH": "vault-link",
                        "BACKUP_DIRECTORY": "backups",
                        "ARCHIVE_PREFIX": "vault-backup",
                    }
                )

    def test_from_env_uses_current_working_directory_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            previous = os.getcwd()
            os.chdir(temp_dir)
            try:
                config = VaultConfig.from_env(
                    {
                        "VAULT_PATH": "vault",
                        "BACKUP_DIRECTORY": "backups",
                        "ARCHIVE_PREFIX": "vault-backup",
                    }
                )
            finally:
                os.chdir(previous)

        self.assertEqual(config.repo_root, Path(temp_dir).resolve())
        self.assertEqual(config.vault_path, Path(temp_dir).resolve() / "vault")

    def test_from_env_loads_values_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / ".env").write_text(
                "\n".join(
                    [
                        f"VAULT_REPO_ROOT={repo_root}",
                        "VAULT_PATH=vault",
                        "BACKUP_DIRECTORY=backups",
                        "ARCHIVE_PREFIX=vault-backup",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            previous = os.getcwd()
            os.chdir(temp_dir)
            try:
                config = VaultConfig.from_env()
            finally:
                os.chdir(previous)

        self.assertEqual(config.repo_root, repo_root.resolve())
        self.assertEqual(config.vault_path, repo_root.resolve() / "vault")
        self.assertEqual(config.backup_directory, repo_root.resolve() / "backups")


if __name__ == "__main__":
    unittest.main()
