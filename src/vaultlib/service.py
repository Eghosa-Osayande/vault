from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .backends.base import CryptoBackend
from .config import VaultConfig
from .exceptions import (
    ArchiveValidationError,
    GitProtectionError,
    OverwriteRequiredError,
    RestoreError,
    VerificationError,
)
from .models import BackupInfo, BackupResult, RestoreResult, SecretValue, VerifyResult

DEFAULT_ARCHIVE_EXTENSION = ".vaultenc"


class VaultService:
    def __init__(self, config: VaultConfig, backend: CryptoBackend) -> None:
        self.config = config
        self.backend = backend

    def list_backups(self) -> list[BackupInfo]:
        backup_dir = self.config.backup_directory
        if not backup_dir.is_dir():
            return []

        backups: list[BackupInfo] = []
        for candidate in backup_dir.iterdir():
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.name.endswith(".partial") or not candidate.name.endswith(DEFAULT_ARCHIVE_EXTENSION):
                continue
            stat = candidate.stat()
            backups.append(
                BackupInfo(
                    archive_path=candidate,
                    filename=candidate.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                )
            )

        backups.sort(key=lambda item: item.modified_at, reverse=True)
        return backups

    def create_backup(
        self,
        passphrase: SecretValue,
        archive_name: str | None = None,
        overwrite: bool = False,
    ) -> BackupResult:
        self._validate_git_protection()
        self._validate_vault_directory()

        backup_dir = self.config.backup_directory
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if backup_dir.is_symlink():
            raise ArchiveValidationError(
                f"Backup directory must not be a symbolic link: {backup_dir.relative_to(self.config.repo_root)}"
            )

        if archive_name:
            filename = self._validate_archive_filename(archive_name)
            final_path = backup_dir / filename
            partial_path = final_path.with_suffix(final_path.suffix + ".partial")
            if final_path.exists() or partial_path.exists():
                if not overwrite:
                    raise OverwriteRequiredError(f"Backup already exists and overwrite is required: {final_path.name}")
                self._safe_remove_backup_file(final_path)
                self._safe_remove_backup_temp_file(partial_path)
        else:
            final_path, partial_path = self._next_timestamped_archive_paths()

        try:
            self.backend.create_encrypted_archive(
                source_parent=self.config.vault_path.parent,
                source_name=self.config.vault_basename,
                output_path=partial_path,
                passphrase=passphrase,
            )
            self._verify_archive(partial_path, passphrase)
            partial_path.replace(final_path)
        except Exception:
            self._safe_remove_backup_temp_file(partial_path)
            raise

        stat = final_path.stat()
        return BackupResult(
            archive_path=final_path,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    def verify_backup(self, archive_path: Path, passphrase: SecretValue) -> VerifyResult:
        resolved_archive = self._resolve_archive_path(archive_path)
        self._verify_archive(resolved_archive, passphrase)
        return VerifyResult(archive_path=resolved_archive, verified_at=datetime.now(tz=UTC))

    def restore_backup(
        self,
        archive_path: Path,
        passphrase: SecretValue,
        replace_existing: bool = False,
    ) -> RestoreResult:
        self._validate_git_protection()
        resolved_archive = self._resolve_archive_path(archive_path)
        self._verify_archive(resolved_archive, passphrase)

        temp_restore_directory = Path(tempfile.mkdtemp(prefix="vaultlib-restore-"))
        recovery_path: Path | None = None
        restored_previous_vault = False

        try:
            self.backend.extract_archive(resolved_archive, temp_restore_directory, passphrase)
            self._validate_extracted_tree(temp_restore_directory)

            self.config.vault_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.config.vault_path.is_symlink():
                raise RestoreError(
                    f"Existing vault path must not be a symbolic link: {self.config.vault_path.relative_to(self.config.repo_root)}"
                )
            if self.config.vault_path.exists() and not self.config.vault_path.is_dir():
                raise RestoreError(
                    f"Existing vault path is not a directory: {self.config.vault_path.relative_to(self.config.repo_root)}"
                )

            if self.config.vault_path.is_dir():
                if self._directory_is_empty(self.config.vault_path):
                    self.config.vault_path.rmdir()
                elif replace_existing:
                    recovery_path = self._create_recovery_path()
                    self.config.vault_path.rename(recovery_path)
                    restored_previous_vault = True
                else:
                    raise OverwriteRequiredError("Existing vault is not empty. Re-run with replace_existing=True.")

            restored_source = temp_restore_directory / self.config.vault_basename
            try:
                restored_source.rename(self.config.vault_path)
            except Exception as exc:
                if restored_previous_vault and recovery_path and recovery_path.exists():
                    recovery_path.rename(self.config.vault_path)
                raise RestoreError(
                    f"Failed to place the restored vault at {self.config.vault_path.relative_to(self.config.repo_root)}."
                ) from exc

            return RestoreResult(
                archive_path=resolved_archive,
                restored_to=self.config.vault_path,
                recovered_previous_vault=recovery_path,
                restored_at=datetime.now(tz=UTC),
            )
        finally:
            self._safe_remove_temp_dir(temp_restore_directory)

    def _verify_archive(self, archive_path: Path, passphrase: SecretValue) -> None:
        try:
            entries = self.backend.list_archive_entries(archive_path, passphrase)
        except Exception as exc:
            raise VerificationError("Backup verification failed.") from exc
        self._validate_archive_entries(entries)

    def _validate_vault_directory(self) -> None:
        if not self.config.vault_path.exists():
            raise RestoreError(f"Vault directory not found: {self.config.vault_path.relative_to(self.config.repo_root)}")
        if self.config.vault_path.is_symlink():
            raise RestoreError(
                f"Vault directory must not be a symbolic link: {self.config.vault_path.relative_to(self.config.repo_root)}"
            )
        if not self.config.vault_path.is_dir():
            raise RestoreError(f"Vault path is not a directory: {self.config.vault_path.relative_to(self.config.repo_root)}")

        for root, dirs, files in os.walk(self.config.vault_path):
            current = Path(root)
            for name in dirs + files:
                candidate = current / name
                if candidate.is_symlink():
                    relative = candidate.relative_to(self.config.vault_path)
                    raise ArchiveValidationError(f"Symbolic links inside the vault are not allowed: {relative}")

    def _validate_git_protection(self) -> None:
        git_binary = shutil.which("git")
        if git_binary is None:
            raise GitProtectionError("Missing required command: git")

        repo_root = self.config.repo_root
        rev_parse = subprocess.run(
            [git_binary, "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        if rev_parse.returncode != 0:
            raise GitProtectionError("Repository root is not inside a Git working tree.")

        probe_path = f"{self.config.vault_path.relative_to(repo_root)}/.gitignore-probe"
        ignored = subprocess.run(
            [git_binary, "-C", str(repo_root), "check-ignore", "-q", "--", probe_path],
            capture_output=True,
            text=True,
        )
        if ignored.returncode != 0:
            raise GitProtectionError(
                f"Vault path is not ignored by Git: {self.config.vault_path.relative_to(self.config.repo_root)}"
            )

        tracked = subprocess.run(
            [git_binary, "-C", str(repo_root), "ls-files", "--", str(self.config.vault_path.relative_to(repo_root))],
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_paths = tracked.stdout.strip()
        if tracked_paths:
            raise GitProtectionError(f"Vault files are already tracked by Git.\n{tracked_paths}")

    def _next_timestamped_archive_paths(self) -> tuple[Path, Path]:
        while True:
            timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
            final_path = self.config.backup_directory / f"{self.config.archive_prefix}-{timestamp}{DEFAULT_ARCHIVE_EXTENSION}"
            partial_path = Path(f"{final_path}.partial")
            if not final_path.exists() and not partial_path.exists():
                return final_path, partial_path

    def _resolve_archive_path(self, archive_path: Path) -> Path:
        candidate = archive_path
        if not candidate.is_absolute():
            candidate = (self.config.repo_root / archive_path).resolve(strict=False)
        self._validate_archive_file(candidate)
        return candidate

    def _validate_archive_filename(self, filename: str) -> str:
        if not filename:
            raise ArchiveValidationError("Archive filename must not be empty.")
        if "/" in filename or "\n" in filename or "\r" in filename:
            raise ArchiveValidationError("Archive filename must be a simple filename.")
        if filename.endswith(".partial"):
            raise ArchiveValidationError("Archive filename must not end with .partial.")
        if not filename.endswith(DEFAULT_ARCHIVE_EXTENSION):
            raise ArchiveValidationError(f"Backup archive must end with {DEFAULT_ARCHIVE_EXTENSION}: {filename}")
        return filename

    def _validate_archive_file(self, archive_path: Path) -> None:
        backup_dir = self.config.backup_directory.resolve(strict=False)
        candidate = archive_path.resolve(strict=False)
        if not self._path_is_within(backup_dir, candidate):
            raise ArchiveValidationError(
                f"Backup archive must be inside {self.config.backup_directory.relative_to(self.config.repo_root)}."
            )
        if not candidate.exists():
            raise ArchiveValidationError(f"Backup archive not found: {candidate}")
        if candidate.is_symlink():
            raise ArchiveValidationError(f"Backup archive must not be a symbolic link: {candidate}")
        if not candidate.is_file():
            raise ArchiveValidationError(f"Backup archive is not a regular file: {candidate}")
        if not candidate.name.endswith(DEFAULT_ARCHIVE_EXTENSION):
            raise ArchiveValidationError(
                f"Backup archive must end with {DEFAULT_ARCHIVE_EXTENSION}: {candidate.name}"
            )

    def _validate_archive_entries(self, entries: list[str]) -> None:
        if not entries:
            raise ArchiveValidationError("Backup archive is empty.")

        for entry in entries:
            normalized = entry
            while normalized.startswith("./"):
                normalized = normalized[2:]
            while normalized.endswith("/") and normalized != "/":
                normalized = normalized[:-1]
            if not normalized:
                raise ArchiveValidationError("Backup archive contains an empty path entry.")
            if normalized.startswith("/"):
                raise ArchiveValidationError(f"Backup archive contains an absolute path: {normalized}")
            if "//" in normalized:
                raise ArchiveValidationError(f"Backup archive contains repeated path separators: {normalized}")
            parts = normalized.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                raise ArchiveValidationError(f"Backup archive contains an unsafe path: {normalized}")
            if parts[0] != self.config.vault_basename:
                raise ArchiveValidationError(f"Backup archive contains an unexpected top-level path: {normalized}")

    def _validate_extracted_tree(self, temp_directory: Path) -> None:
        top_level_entries = [entry for entry in temp_directory.iterdir()]
        if not top_level_entries:
            raise RestoreError("Restored data is empty.")
        if len(top_level_entries) != 1:
            raise RestoreError("Backup archive must extract to exactly one top-level directory.")

        top_level_entry = top_level_entries[0]
        if top_level_entry.is_symlink():
            raise RestoreError("Restored vault root must not be a symbolic link.")
        if not top_level_entry.is_dir():
            raise RestoreError("Restored vault root is not a directory.")
        if top_level_entry.name != self.config.vault_basename:
            raise RestoreError("Backup archive restored an unexpected top-level directory.")

        for root, dirs, files in os.walk(temp_directory):
            current = Path(root)
            for name in dirs + files:
                candidate = current / name
                if candidate.is_symlink():
                    raise RestoreError(f"Restored data contains a symbolic link: {candidate}")
                resolved_parent = candidate.parent.resolve()
                resolved_path = resolved_parent / candidate.name
                if not self._path_is_within(temp_directory.resolve(), resolved_path):
                    raise RestoreError(f"Restored data escaped the temporary directory: {candidate}")

    def _create_recovery_path(self) -> Path:
        while True:
            timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
            candidate = self.config.vault_path.parent / f"{self.config.vault_basename}.recovery-{timestamp}"
            if not candidate.exists() and not candidate.is_symlink():
                return candidate

    def _directory_is_empty(self, directory: Path) -> bool:
        return not any(directory.iterdir())

    def _safe_remove_temp_dir(self, target_path: Path) -> None:
        if not target_path:
            return
        target = target_path.resolve(strict=False)
        if str(target) in {"", "/"}:
            raise RestoreError("Refusing to remove an unsafe temporary path.")
        if target == self.config.repo_root:
            raise RestoreError("Refusing to remove the repository root.")
        if target in {self.config.vault_path, self.config.backup_directory}:
            raise RestoreError(f"Refusing to remove a protected repository path: {target}")
        temp_root_prefixes = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
        if not any(str(target).startswith(prefix) for prefix in temp_root_prefixes):
            raise RestoreError(f"Refusing to remove an unexpected temporary path: {target}")
        if target.exists():
            shutil.rmtree(target)

    def _safe_remove_backup_temp_file(self, target_path: Path) -> None:
        if not target_path:
            return
        candidate = target_path.resolve(strict=False)
        if str(candidate) in {"", "/"}:
            raise ArchiveValidationError("Refusing to remove an unsafe backup temporary path.")
        if candidate == self.config.repo_root:
            raise ArchiveValidationError("Refusing to remove the repository root.")
        if not self._path_is_within(self.config.backup_directory.resolve(strict=False), candidate):
            raise ArchiveValidationError(f"Refusing to remove a file outside the backup directory: {candidate}")
        if not (candidate.name.endswith(".partial") or candidate.name.endswith(".tmp")):
            raise ArchiveValidationError(f"Refusing to remove an unexpected backup temporary path: {candidate}")
        candidate.unlink(missing_ok=True)

    def _safe_remove_backup_file(self, target_path: Path) -> None:
        candidate = target_path.resolve(strict=False)
        if str(candidate) in {"", "/"}:
            raise ArchiveValidationError("Refusing to remove an unsafe backup path.")
        if candidate == self.config.repo_root:
            raise ArchiveValidationError("Refusing to remove the repository root.")
        if not self._path_is_within(self.config.backup_directory.resolve(strict=False), candidate):
            raise ArchiveValidationError(f"Refusing to remove a file outside the backup directory: {candidate}")
        if candidate.is_symlink():
            raise ArchiveValidationError(f"Refusing to remove a symbolic link backup path: {candidate}")
        if candidate.exists() and not candidate.is_file():
            raise ArchiveValidationError(f"Refusing to remove a non-regular backup path: {candidate}")
        if not candidate.name.endswith(DEFAULT_ARCHIVE_EXTENSION):
            raise ArchiveValidationError(
                f"Backup archive must end with {DEFAULT_ARCHIVE_EXTENSION}: {candidate.name}"
            )
        candidate.unlink(missing_ok=True)

    @staticmethod
    def _path_is_within(parent_path: Path, child_path: Path) -> bool:
        return child_path == parent_path or parent_path in child_path.parents
