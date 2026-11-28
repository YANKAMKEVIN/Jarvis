"""Filesystem tools confined to the home folder: list, find, read, open, create, rename and move.

Constants and helpers live in filesystem_common, PathResolver in
filesystem_paths; both are re-exported here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from jarvis.tools.filesystem_common import (  # noqa: F401 -- re-exported
    FileSystemError,
    path_info,
    path_kind,
    is_sensitive_path,
    is_bundle,
    normalize_text,
    BUNDLE_SUFFIXES,
    SENSITIVE_DIRECTORIES,
    SENSITIVE_NESTED_DIRECTORIES,
    SENSITIVE_FILE_NAMES,
    SENSITIVE_SUFFIXES,
    EXECUTABLE_SUFFIXES,
    SCRIPT_SUFFIXES,
    OPEN_TIMEOUT_SECONDS,
    REFERENCE_WORDS,
)
from jarvis.tools.filesystem_paths import (  # noqa: F401 -- re-exported
    PathResolver,
)
from jarvis.tools.filesystem_search import FileSearchMixin
from jarvis.tools.filesystem_reading import FileReadingMixin


@dataclass
class FileSystemTools(
    FileSearchMixin,
    FileReadingMixin,
):
    resolver: PathResolver = field(default_factory=PathResolver)
    list_limit: int = 50
    find_limit: int = 20
    max_find_depth: int = 3
    spotlight_limit: int = 20
    # Injectable argv -> stdout runner, so Spotlight search is testable offline.
    spotlight_runner: Callable[[list[str]], str] | None = None

    def get_file_info(self, path: str | Path) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="get_file_info",
            follow_symlink=False,
        )
        return path_info(resolved)

    def open_file(
        self,
        path: str | Path,
        allow_script: bool = False,
    ) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="open_file",
            expected_kind="file",
            follow_symlink=True,
        )
        self._refuse_executable(resolved)
        if not allow_script:
            self._require_script_confirmation(resolved)
        return self._open_path(resolved, "open_file")

    def open_folder(self, path: str | Path) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="open_folder",
            expected_kind="directory",
            follow_symlink=True,
        )
        self._refuse_executable(resolved)
        return self._open_path(resolved, "open_folder")

    def create_folder(self, path: str | Path) -> dict[str, Any]:
        target = self.resolver.resolve_new_path(path, action="create_folder")

        if target.exists() or target.is_symlink():
            raise FileSystemError("Le dossier existe deja.", "already_exists")

        self.resolver.ensure_inside_home(target)
        target.mkdir()
        state_confirmed = target.exists() and target.is_dir()

        return {
            "path": str(target),
            "command_executed": True,
            "state_confirmed": state_confirmed,
        }

    def rename_file(self, path: str | Path, new_name: str) -> dict[str, Any]:
        source = self.resolver.resolve_existing(
            path,
            action="rename_file",
            follow_symlink=True,
        )
        validated_name = self._validate_new_name(new_name)
        destination = source.with_name(validated_name)

        return self._move_or_rename(
            action="rename_file",
            source=source,
            destination=destination,
        )

    def move_file(self, source: str | Path, destination: str | Path) -> dict[str, Any]:
        resolved_source = self.resolver.resolve_existing(
            source,
            action="move_file",
            follow_symlink=True,
        )
        resolved_destination = self.resolver.resolve_new_path(
            destination,
            action="move_file",
        )

        # "Move X into Documents": an existing folder (not a symlink) as the
        # destination means "inside it", keeping the source name. Collisions
        # inside that folder are still refused by _move_or_rename.
        if resolved_destination.is_dir() and not resolved_destination.is_symlink():
            canonical_source = resolved_source.resolve(strict=False)
            canonical_folder = resolved_destination.resolve(strict=False)

            if canonical_folder == canonical_source.parent:
                raise FileSystemError(
                    "Le fichier ou dossier est deja dans ce dossier.",
                    "same_path",
                )

            if canonical_folder.is_relative_to(canonical_source):
                raise FileSystemError(
                    "Impossible de deplacer un dossier dans lui-meme.",
                    "destination_inside_source",
                )

            resolved_destination = resolved_destination / resolved_source.name

        return self._move_or_rename(
            action="move_file",
            source=resolved_source,
            destination=resolved_destination,
        )

    def _move_or_rename(
        self,
        *,
        action: str,
        source: Path,
        destination: Path,
    ) -> dict[str, Any]:
        self.resolver.ensure_inside_home(source)
        self.resolver.ensure_inside_home(destination.parent)
        self.resolver.ensure_inside_home(destination)

        if source.resolve(strict=False) == destination.resolve(strict=False):
            raise FileSystemError(
                "La source et la destination sont identiques.",
                "same_path",
            )

        if destination.exists() or destination.is_symlink():
            raise FileSystemError(
                "La destination existe deja.",
                "destination_exists",
            )

        previous_path = str(source)
        shutil.move(str(source), str(destination))
        state_confirmed = not source.exists() and destination.exists()

        return {
            "previous_path": previous_path,
            "path": str(destination),
            "destination": str(destination),
            "command_executed": True,
            "state_confirmed": state_confirmed,
        }

    @staticmethod
    def _refuse_executable(path: Path) -> None:
        """Refuse paths that `open` would run, launch or install."""
        candidates = (path, path.resolve(strict=False))
        for candidate in candidates:
            suffix = candidate.suffix.lower()
            # An extensionless executable file is run in Terminal by `open`.
            runnable = (
                not suffix
                and candidate.is_file()
                and os.access(candidate, os.X_OK)
            )
            if suffix in EXECUTABLE_SUFFIXES or runnable:
                raise FileSystemError(
                    "Ce type de fichier lancerait un programme ; "
                    "ouverture refusee.",
                    "executable_refused",
                    {"suffix": suffix},
                )

    @staticmethod
    def _require_script_confirmation(path: Path) -> None:
        """Stop before opening a script until the user has confirmed it."""
        for candidate in (path, path.resolve(strict=False)):
            suffix = candidate.suffix.lower()
            if suffix in SCRIPT_SUFFIXES:
                raise FileSystemError(
                    "Ce fichier est un script qui pourrait s'executer a "
                    "l'ouverture ; confirmation requise.",
                    "script_needs_confirmation",
                    {"suffix": suffix, "path": str(path)},
                )

    def _open_path(self, path: Path, action: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["open", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=OPEN_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise FileSystemError(
                "La commande macOS open est indisponible.",
                "open_command_missing",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise FileSystemError(
                "La commande open n'a pas repondu a temps.",
                "open_timeout",
            ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise FileSystemError(
                detail or "La commande open a echoue.",
                "open_failed",
            )

        return {
            "path": str(path),
            "command_executed": True,
            "state_confirmed": False,
            "open_state_verifiable": False,
            "backend": "macos_open",
        }

    @staticmethod
    def _validate_new_name(new_name: str) -> str:
        if not isinstance(new_name, str):
            raise FileSystemError("Le nouveau nom doit etre du texte.", "invalid_name")

        new_name = new_name.strip()

        if (
            not new_name
            or new_name in {".", ".."}
            or "/" in new_name
            or "\0" in new_name
        ):
            raise FileSystemError("Le nouveau nom est invalide.", "invalid_name")

        return new_name
