from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vaultlib import (
    ArchiveValidationError,
    OverwriteRequiredError,
    PythonPassphraseBackend,
    SecretValue,
    VaultConfig,
    VaultService,
    VerificationError,
)


class VaultServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)
        subprocess.run(["git", "init"], cwd=self.repo_root, check=True, capture_output=True, text=True)
        (self.repo_root / ".gitignore").write_text("vault/\n", encoding="utf-8")
        self.vault_dir = self.repo_root / "vault"
        self.vault_dir.mkdir()
        (self.vault_dir / "note.md").write_text("# hello\n", encoding="utf-8")
        self.config = VaultConfig.from_env(
            {
                "VAULT_REPO_ROOT": str(self.repo_root),
                "VAULT_PATH": "vault",
                "BACKUP_DIRECTORY": "backups",
                "ARCHIVE_PREFIX": "vault-backup",
            }
        )
        self.service = VaultService(self.config, PythonPassphraseBackend())
        self.passphrase = SecretValue("test-passphrase")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_backup_verify_and_list(self) -> None:
        result = self.service.create_backup(self.passphrase)
        self.assertTrue(result.archive_path.exists())

        verified = self.service.verify_backup(result.archive_path, self.passphrase)
        self.assertEqual(verified.archive_path, result.archive_path)

        backups = self.service.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].archive_path, result.archive_path)

    def test_named_backup_requires_explicit_overwrite(self) -> None:
        result = self.service.create_backup(self.passphrase, archive_name="manual.vaultenc")
        self.assertTrue(result.archive_path.exists())

        with self.assertRaises(OverwriteRequiredError):
            self.service.create_backup(self.passphrase, archive_name="manual.vaultenc")

        overwritten = self.service.create_backup(
            self.passphrase,
            archive_name="manual.vaultenc",
            overwrite=True,
        )
        self.assertTrue(overwritten.archive_path.exists())

    def test_failed_verification_does_not_leave_completed_archive(self) -> None:
        backup_dir = self.config.backup_directory
        backup_dir.mkdir(parents=True, exist_ok=True)
        archive_path = backup_dir / "broken.vaultenc"
        archive_path.write_bytes(b"not-a-vault-container")

        with self.assertRaises(VerificationError):
            self.service.verify_backup(archive_path, self.passphrase)

    def test_restore_requires_replace_existing(self) -> None:
        result = self.service.create_backup(self.passphrase)
        (self.vault_dir / "extra.md").write_text("changed\n", encoding="utf-8")

        with self.assertRaises(OverwriteRequiredError):
            self.service.restore_backup(result.archive_path, self.passphrase)

    def test_restore_replace_existing_preserves_recovery_copy(self) -> None:
        result = self.service.create_backup(self.passphrase)
        (self.vault_dir / "note.md").write_text("modified\n", encoding="utf-8")

        restored = self.service.restore_backup(result.archive_path, self.passphrase, replace_existing=True)
        self.assertIsNotNone(restored.recovered_previous_vault)
        assert restored.recovered_previous_vault is not None
        self.assertTrue(restored.recovered_previous_vault.exists())
        self.assertEqual((self.vault_dir / "note.md").read_text(encoding="utf-8"), "# hello\n")
        self.assertEqual((restored.recovered_previous_vault / "note.md").read_text(encoding="utf-8"), "modified\n")

    def test_vault_symlink_is_rejected(self) -> None:
        nested_dir = self.vault_dir / "linked"
        nested_dir.mkdir()
        target = self.vault_dir / "target.txt"
        target.write_text("hi\n", encoding="utf-8")
        nested_link = nested_dir / "sym.txt"
        nested_link.symlink_to(target)

        with self.assertRaises(ArchiveValidationError):
            self.service.create_backup(self.passphrase)


class NotebookArtifactTests(unittest.TestCase):
    def test_notebook_is_valid_json(self) -> None:
        notebook_path = Path(__file__).resolve().parents[1] / "notebooks" / "vault_demo.ipynb"
        data = json.loads(notebook_path.read_text(encoding="utf-8"))
        self.assertIn("cells", data)
        self.assertGreater(len(data["cells"]), 0)


if __name__ == "__main__":
    unittest.main()
