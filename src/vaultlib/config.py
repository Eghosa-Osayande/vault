from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .exceptions import ConfigError


def _normalize_relative_path(label: str, raw_path: str, repo_root: Path) -> Path:
    trimmed = raw_path.rstrip("/")
    current_path = repo_root

    if not raw_path:
        raise ConfigError(f"{label} must not be empty.")
    if raw_path.startswith("/"):
        raise ConfigError(f"{label} must be relative to the repository root.")
    if "\n" in raw_path or "\r" in raw_path:
        raise ConfigError(f"{label} must not contain a newline.")
    if "//" in raw_path:
        raise ConfigError(f"{label} must not contain repeated path separators.")
    if not trimmed:
        raise ConfigError(f"{label} must not resolve to the repository root.")

    components = trimmed.split("/")
    for component in components:
        if component in {"", ".", ".."}:
            raise ConfigError(f"{label} contains an unsafe path component: {raw_path}")
        candidate = current_path / component
        if candidate.is_symlink():
            raise ConfigError(f"{label} must not resolve through a symbolic link: {raw_path}")
        current_path = candidate

    return repo_root / trimmed


def _path_is_within(parent_path: Path, child_path: Path) -> bool:
    return child_path == parent_path or parent_path in child_path.parents


@dataclass(frozen=True)
class VaultConfig:
    repo_root: Path
    vault_path: Path
    backup_directory: Path
    archive_prefix: str

    @property
    def vault_basename(self) -> str:
        return self.vault_path.name

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "VaultConfig":
        env_map = dict(os.environ if env is None else env)
        repo_root_raw = env_map.get("VAULT_REPO_ROOT", os.getcwd())
        repo_root = Path(repo_root_raw).expanduser().resolve()

        if not repo_root.exists():
            raise ConfigError(f"VAULT_REPO_ROOT does not exist: {repo_root}")
        if not repo_root.is_dir():
            raise ConfigError(f"VAULT_REPO_ROOT is not a directory: {repo_root}")

        vault_path = _normalize_relative_path("VAULT_PATH", env_map.get("VAULT_PATH", ""), repo_root)
        backup_directory = _normalize_relative_path(
            "BACKUP_DIRECTORY",
            env_map.get("BACKUP_DIRECTORY", ""),
            repo_root,
        )
        archive_prefix = env_map.get("ARCHIVE_PREFIX", "")

        if not archive_prefix:
            raise ConfigError("ARCHIVE_PREFIX must not be empty.")
        if "/" in archive_prefix or "\n" in archive_prefix or "\r" in archive_prefix:
            raise ConfigError("ARCHIVE_PREFIX must be a simple filename prefix.")

        if vault_path == repo_root:
            raise ConfigError("VAULT_PATH must not be the repository root.")
        if vault_path == backup_directory:
            raise ConfigError("VAULT_PATH and BACKUP_DIRECTORY must be different.")
        if _path_is_within(vault_path, backup_directory):
            raise ConfigError("BACKUP_DIRECTORY must not be inside VAULT_PATH.")
        if _path_is_within(backup_directory, vault_path):
            raise ConfigError("VAULT_PATH must not be inside BACKUP_DIRECTORY.")

        if vault_path.exists() and not vault_path.is_dir():
            raise ConfigError(f"VAULT_PATH exists but is not a directory: {vault_path.relative_to(repo_root)}")
        if backup_directory.exists() and not backup_directory.is_dir():
            raise ConfigError(
                f"BACKUP_DIRECTORY exists but is not a directory: {backup_directory.relative_to(repo_root)}"
            )

        return cls(
            repo_root=repo_root,
            vault_path=vault_path,
            backup_directory=backup_directory,
            archive_prefix=archive_prefix,
        )

