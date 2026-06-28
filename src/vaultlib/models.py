from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SecretValue:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("SecretValue must not be empty.")

    def reveal(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"


@dataclass(frozen=True)
class BackupInfo:
    archive_path: Path
    filename: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class BackupResult:
    archive_path: Path
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class VerifyResult:
    archive_path: Path
    verified_at: datetime


@dataclass(frozen=True)
class RestoreResult:
    archive_path: Path
    restored_to: Path
    recovered_previous_vault: Path | None
    restored_at: datetime

