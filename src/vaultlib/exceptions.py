class VaultError(Exception):
    """Base exception for vault operations."""


class ConfigError(VaultError):
    """Raised when configuration is missing or invalid."""


class GitProtectionError(VaultError):
    """Raised when Git protection checks fail."""


class ArchiveValidationError(VaultError):
    """Raised when an archive path or listing is unsafe."""


class BackendError(VaultError):
    """Raised when a backend command fails."""


class VerificationError(VaultError):
    """Raised when archive verification fails."""


class RestoreError(VaultError):
    """Raised when restore placement or cleanup fails."""


class OverwriteRequiredError(VaultError):
    """Raised when a destructive overwrite requires explicit confirmation."""

