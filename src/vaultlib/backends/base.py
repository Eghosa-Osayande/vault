from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import SecretValue


class CryptoBackend(ABC):
    @abstractmethod
    def create_encrypted_archive(
        self,
        source_parent: Path,
        source_name: str,
        output_path: Path,
        passphrase: SecretValue,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_archive_entries(self, archive_path: Path, passphrase: SecretValue) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def extract_archive(self, archive_path: Path, destination: Path, passphrase: SecretValue) -> None:
        raise NotImplementedError

