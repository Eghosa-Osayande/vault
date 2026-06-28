from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..exceptions import ArchiveValidationError, BackendError
from ..models import SecretValue
from .base import CryptoBackend

MAGIC = b"VLT1"
VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
DEFAULT_EXTENSION = ".vaultenc"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class PythonPassphraseBackend(CryptoBackend):
    archive_extension = DEFAULT_EXTENSION

    def create_encrypted_archive(
        self,
        source_parent: Path,
        source_name: str,
        output_path: Path,
        passphrase: SecretValue,
    ) -> None:
        archive_bytes = self._build_archive_bytes(source_parent, source_name)
        encrypted_bytes = self._encrypt_bytes(archive_bytes, passphrase)
        output_path.write_bytes(encrypted_bytes)

    def list_archive_entries(self, archive_path: Path, passphrase: SecretValue) -> list[str]:
        archive_bytes = self._decrypt_bytes(archive_path.read_bytes(), passphrase)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
                return tar.getnames()
        except tarfile.TarError as exc:
            raise BackendError("Failed to read decrypted archive contents.") from exc

    def extract_archive(self, archive_path: Path, destination: Path, passphrase: SecretValue) -> None:
        archive_bytes = self._decrypt_bytes(archive_path.read_bytes(), passphrase)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
                tar.extractall(path=destination, filter="data")
        except TypeError:
            # Python <3.12 compatibility fallback without filter support.
            try:
                with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
                    tar.extractall(path=destination)
            except tarfile.TarError as exc:
                raise BackendError("Failed to extract decrypted archive.") from exc
        except tarfile.TarError as exc:
            raise BackendError("Failed to extract decrypted archive.") from exc

    def _build_archive_bytes(self, source_parent: Path, source_name: str) -> bytes:
        archive_buffer = io.BytesIO()
        try:
            with gzip.GzipFile(fileobj=archive_buffer, mode="wb") as gzip_file:
                with tarfile.open(fileobj=gzip_file, mode="w|") as tar:
                    tar.add(source_parent / source_name, arcname=source_name, recursive=True)
        except (OSError, tarfile.TarError) as exc:
            raise BackendError("Failed to build compressed archive.") from exc
        return archive_buffer.getvalue()

    def _encrypt_bytes(self, plaintext: bytes, passphrase: SecretValue) -> bytes:
        salt = os.urandom(SALT_BYTES)
        nonce = os.urandom(NONCE_BYTES)
        key = self._derive_key(passphrase, salt)
        header = {
            "version": VERSION,
            "algorithm": "AES-256-GCM",
            "kdf": {
                "name": "scrypt",
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
                "dklen": KEY_BYTES,
            },
            "salt": salt.hex(),
            "nonce": nonce.hex(),
        }
        header_bytes = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, header_bytes)
        return MAGIC + len(header_bytes).to_bytes(4, "big") + header_bytes + ciphertext

    def _decrypt_bytes(self, payload: bytes, passphrase: SecretValue) -> bytes:
        try:
            magic = payload[:4]
            if magic != MAGIC:
                raise ArchiveValidationError("Archive is not a supported vaultlib encrypted container.")
            header_length = int.from_bytes(payload[4:8], "big")
            header_start = 8
            header_end = header_start + header_length
            header = json.loads(payload[header_start:header_end].decode("utf-8"))
            ciphertext = payload[header_end:]
            salt = bytes.fromhex(header["salt"])
            nonce = bytes.fromhex(header["nonce"])
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ArchiveValidationError("Archive header is invalid or corrupted.") from exc

        key = self._derive_key(passphrase, salt)
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, payload[8:header_end])
        except Exception as exc:
            raise BackendError("Failed to decrypt archive. The passphrase may be incorrect or the file may be tampered with.") from exc

    def _derive_key(self, passphrase: SecretValue, salt: bytes) -> bytes:
        return hashlib.scrypt(
            passphrase.reveal().encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=KEY_BYTES,
            maxmem=0,
        )
