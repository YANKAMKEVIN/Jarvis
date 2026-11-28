"""Filesystem constants, error type and pure path helpers."""
from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


BUNDLE_SUFFIXES = {".app", ".bundle", ".pkg"}
# read_text never returns secrets: credential folders and files anywhere in
# the home folder are refused, whatever the path or symlink used to reach them.
SENSITIVE_DIRECTORIES = frozenset({
    ".ssh", ".aws", ".gnupg", ".gpg", ".kube", ".docker", ".azure",
    ".password-store", ".1password",
})
SENSITIVE_NESTED_DIRECTORIES = (
    (".config", "gcloud"),
    (".config", "gh"),
    (".config", "op"),
    ("library", "keychains"),
    ("library", "cookies"),
    (".local", "share", "keyrings"),
)
SENSITIVE_FILE_NAMES = frozenset({
    ".env", ".netrc", ".npmrc", ".pypirc", ".git-credentials", ".pgpass",
    ".my.cnf", ".htpasswd", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.json", "service-account.json",
})
SENSITIVE_SUFFIXES = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".keychain", ".keychain-db", ".kdbx",
    ".ovpn", ".mobileprovision",
})
# Opening these with macOS `open` launches, runs or installs something rather
# than displaying a document, so open_file/open_folder refuse them.
EXECUTABLE_SUFFIXES = frozenset({
    ".app", ".command", ".terminal", ".tool", ".sh", ".bash", ".zsh", ".csh",
    ".ksh", ".fish", ".pkg", ".mpkg",
    ".scpt", ".scptd", ".applescript", ".workflow", ".action", ".shortcut",
    ".prefpane", ".mobileconfig", ".fileloc", ".bundle", ".plugin", ".kext",
    ".osax", ".saver", ".qlgenerator", ".dylib", ".xpc", ".appex",
})
# Interpreted scripts and Java archives: depending on the default app, `open`
# shows them in an editor or runs them (Python Launcher, Jar Launcher...).
# open_file only opens them once the user has confirmed (allow_script=True).
SCRIPT_SUFFIXES = frozenset({".py", ".pl", ".rb", ".php", ".jar"})
OPEN_TIMEOUT_SECONDS = 15
REFERENCE_WORDS = {
    "ce fichier",
    "ce dossier",
    "celui-la",
    "celui-là",
    "celle-la",
    "celle-là",
    "le premier",
    "la premiere",
    "la première",
}


class FileSystemError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


def path_info(path: Path) -> dict[str, Any]:
    try:
        stat_result = path.lstat()
    except FileNotFoundError:
        raise FileSystemError("Le chemin n'existe pas.", "path_not_found") from None
    except PermissionError as exc:
        raise FileSystemError("Permission refusee.", "permission_denied") from exc

    kind = path_kind(path)

    return {
        "path": str(path),
        "name": path.name,
        "parent": str(path.parent),
        "kind": kind,
        "size_bytes": stat_result.st_size,
        "modified_at": datetime.fromtimestamp(stat_result.st_mtime).isoformat(
            timespec="seconds",
        ),
        "is_hidden": path.name.startswith("."),
        "is_symlink": path.is_symlink(),
    }


def path_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"

    if is_bundle(path):
        return "bundle"

    if path.is_dir():
        return "directory"

    if path.is_file():
        return "file"

    return "other"


def is_sensitive_path(parts: tuple[str, ...]) -> bool:
    """True for credential folders/files (parts are relative to home)."""
    lowered = [part.casefold() for part in parts]
    if not lowered:
        return False
    if any(part in SENSITIVE_DIRECTORIES for part in lowered[:-1]):
        return True
    folders = lowered[:-1]
    for nested in SENSITIVE_NESTED_DIRECTORIES:
        size = len(nested)
        for index in range(len(folders) - size + 1):
            if tuple(folders[index:index + size]) == nested:
                return True
    name = lowered[-1]
    if name in SENSITIVE_FILE_NAMES or name.startswith(".env."):
        return True
    return Path(name).suffix in SENSITIVE_SUFFIXES


def is_bundle(path: Path) -> bool:
    return path.is_dir() and path.suffix.lower() in BUNDLE_SUFFIXES


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().strip().split())
