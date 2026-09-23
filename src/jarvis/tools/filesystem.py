from __future__ import annotations

import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


BUNDLE_SUFFIXES = {".app", ".bundle", ".pkg"}
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


@dataclass(frozen=True)
class PathResolver:
    home: Path | None = None
    search_roots: tuple[Path, ...] | None = None
    max_candidates: int = 10

    def __post_init__(self):
        home = Path.home() if self.home is None else Path(self.home)
        object.__setattr__(self, "home", home.expanduser().resolve())

        if self.search_roots is None:
            roots = (
                self.home,
                self.home / "Desktop",
                self.home / "Downloads",
                self.home / "Documents",
            )
        else:
            roots = tuple(Path(root) for root in self.search_roots)

        object.__setattr__(
            self,
            "search_roots",
            tuple(self._normalize_inside_home(root) for root in roots),
        )

    def resolve_existing(
        self,
        value: str | Path | None,
        *,
        action: str,
        expected_kind: str | None = None,
        follow_symlink: bool = True,
    ) -> Path:
        if value is None:
            raise FileSystemError(
                "Aucun chemin n'a ete fourni.",
                "unresolved_path",
            )

        text = self._clean_text(value)

        if self._is_unresolved_reference(text):
            raise FileSystemError(
                "La reference conversationnelle ne contient pas de chemin exact.",
                "unresolved_reference",
            )

        path = self._path_from_text(text)

        if path is not None:
            checked = self._ensure_existing_path(
                path,
                expected_kind=expected_kind,
                follow_symlink=follow_symlink,
            )
            return checked

        candidates = self._find_candidates(text)

        if not candidates:
            raise FileSystemError(
                f"Aucun chemin ne correspond a {text}.",
                "unresolved_path",
            )

        if len(candidates) > 1:
            raise FileSystemError(
                f"Plusieurs chemins correspondent a {text}.",
                "ambiguous_path",
                {"candidates": [path_info(candidate) for candidate in candidates]},
            )

        return self._ensure_existing_path(
            candidates[0],
            expected_kind=expected_kind,
            follow_symlink=follow_symlink,
        )

    def resolve_directory_or_home(self, value: str | Path | None) -> Path:
        if value is None:
            return self.home

        return self.resolve_existing(
            value,
            action="list_files",
            expected_kind="directory",
            follow_symlink=True,
        )

    def resolve_new_path(self, value: str | Path, *, action: str) -> Path:
        text = self._clean_text(value)

        if self._is_unresolved_reference(text):
            raise FileSystemError(
                "La reference conversationnelle ne contient pas de chemin exact.",
                "unresolved_reference",
            )

        path = self._path_from_text(text)

        if path is None:
            path = self.home / text

        parent = path.parent

        if not parent.exists():
            raise FileSystemError(
                "Le dossier parent de destination n'existe pas.",
                "destination_parent_missing",
            )

        if not parent.is_dir():
            raise FileSystemError(
                "Le parent de destination n'est pas un dossier.",
                "not_a_directory",
            )

        self.ensure_inside_home(parent)

        return path

    def ensure_inside_home(self, path: Path) -> None:
        canonical = path.resolve(strict=False)
        try:
            canonical.relative_to(self.home)
        except ValueError as exc:
            raise FileSystemError(
                "Le chemin sort du dossier home autorise.",
                "outside_home",
            ) from exc

    def _ensure_existing_path(
        self,
        path: Path,
        *,
        expected_kind: str | None,
        follow_symlink: bool,
    ) -> Path:
        if not path.exists() and not path.is_symlink():
            raise FileSystemError("Le chemin n'existe pas.", "path_not_found")

        if follow_symlink or not path.is_symlink():
            self.ensure_inside_home(path)
        else:
            self.ensure_inside_home(path.parent)

        if expected_kind == "file" and not path.is_file():
            raise FileSystemError("Le chemin n'est pas un fichier.", "not_a_file")

        if expected_kind == "directory" and not path.is_dir():
            raise FileSystemError("Le chemin n'est pas un dossier.", "not_a_directory")

        return path

    def _path_from_text(self, text: str) -> Path | None:
        alias = self._alias_to_path(text)

        if alias is not None:
            return alias

        expanded = Path(text).expanduser()

        if expanded.is_absolute():
            return expanded

        if "/" in text:
            first, rest = text.split("/", 1)
            alias_root = self._alias_to_path(first)

            if alias_root is not None:
                return alias_root / rest

            return self.home / text

        return None

    def _alias_to_path(self, value: str) -> Path | None:
        normalized = normalize_text(value)
        aliases = {
            "bureau": self.home / "Desktop",
            "desktop": self.home / "Desktop",
            "telechargements": self.home / "Downloads",
            "downloads": self.home / "Downloads",
            "documents": self.home / "Documents",
            "home": self.home,
            "maison": self.home,
            "dossier personnel": self.home,
        }
        return aliases.get(normalized)

    def _find_candidates(self, text: str) -> list[Path]:
        needle = normalize_text(text)
        candidates: list[Path] = []

        for root in self.search_roots:
            if not root.exists() or not root.is_dir():
                continue

            for child in root.iterdir():
                if child.name.startswith("."):
                    continue

                if normalize_text(child.name) == needle:
                    candidates.append(child)

                if len(candidates) >= self.max_candidates:
                    return candidates

        return candidates

    def _normalize_inside_home(self, path: Path) -> Path:
        path = path.expanduser()

        if not path.is_absolute():
            path = self.home / path

        self.ensure_inside_home(path)
        return path

    @staticmethod
    def _clean_text(value: str | Path) -> str:
        if isinstance(value, Path):
            value = str(value)

        if not isinstance(value, str):
            raise FileSystemError("Le chemin doit etre du texte.", "invalid_path")

        value = value.strip()

        if not value:
            raise FileSystemError("Le chemin est vide.", "unresolved_path")

        return value

    @staticmethod
    def _is_unresolved_reference(value: str) -> bool:
        return normalize_text(value) in REFERENCE_WORDS


@dataclass
class FileSystemTools:
    resolver: PathResolver = field(default_factory=PathResolver)
    list_limit: int = 50
    find_limit: int = 20
    max_find_depth: int = 3

    def list_files(self, path: str | Path | None = None) -> dict[str, Any]:
        directory = self.resolver.resolve_directory_or_home(path)
        results = []
        truncated = False

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except PermissionError as exc:
            raise FileSystemError("Permission refusee.", "permission_denied") from exc
        except NotADirectoryError as exc:
            raise FileSystemError("Le chemin n'est pas un dossier.", "not_a_directory") from exc

        for child in children:
            if child.name.startswith("."):
                continue

            if len(results) >= self.list_limit:
                truncated = True
                break

            results.append(path_info(child))

        return {
            "path": str(directory),
            "results": results,
            "result_count": len(results),
            "truncated": truncated,
        }

    def find_files(
        self,
        query: str,
        path: str | Path | None = None,
    ) -> dict[str, Any]:
        query = self._validate_query(query)
        root = self.resolver.resolve_directory_or_home(path)
        matches: list[dict[str, Any]] = []
        truncated = False

        for item, depth in self._walk_bounded(root):
            if depth > self.max_find_depth:
                continue

            if item.name.startswith("."):
                continue

            if is_bundle(item) and depth >= self.max_find_depth:
                continue

            if self._matches_query(item, query):
                matches.append(path_info(item))

                if len(matches) >= self.find_limit:
                    truncated = True
                    break

        return {
            "query": query,
            "path": str(root),
            "results": matches,
            "result_count": len(matches),
            "truncated": truncated,
        }

    def get_file_info(self, path: str | Path) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="get_file_info",
            follow_symlink=False,
        )
        return path_info(resolved)

    def open_file(self, path: str | Path) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="open_file",
            expected_kind="file",
            follow_symlink=True,
        )
        return self._open_path(resolved, "open_file")

    def open_folder(self, path: str | Path) -> dict[str, Any]:
        resolved = self.resolver.resolve_existing(
            path,
            action="open_folder",
            expected_kind="directory",
            follow_symlink=True,
        )
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

    def _open_path(self, path: Path, action: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["open", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise FileSystemError(
                "La commande macOS open est indisponible.",
                "open_command_missing",
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

    def _walk_bounded(self, root: Path):
        stack = [(root, 0)]

        while stack:
            current, depth = stack.pop()

            try:
                children = sorted(
                    current.iterdir(),
                    key=lambda item: item.name.casefold(),
                    reverse=True,
                )
            except (PermissionError, NotADirectoryError):
                continue

            for child in children:
                yield child, depth

                if (
                    depth < self.max_find_depth
                    and child.is_dir()
                    and not child.is_symlink()
                    and not is_bundle(child)
                    and not child.name.startswith(".")
                ):
                    stack.append((child, depth + 1))

    @staticmethod
    def _validate_query(query: str) -> str:
        if not isinstance(query, str):
            raise FileSystemError("La requete doit etre du texte.", "invalid_query")

        query = query.strip()

        if not query:
            raise FileSystemError("La requete est vide.", "invalid_query")

        return query

    @staticmethod
    def _matches_query(path: Path, query: str) -> bool:
        normalized_name = normalize_text(path.name)
        normalized_query = normalize_text(query)

        if normalized_query in normalized_name:
            return True

        if normalized_query.startswith("."):
            return normalize_text(path.suffix) == normalized_query

        extension = path.suffix.lstrip(".")

        if extension and normalized_query == normalize_text(extension):
            return True

        return False

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


def is_bundle(path: Path) -> bool:
    return path.is_dir() and path.suffix.lower() in BUNDLE_SUFFIXES


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().strip().split())
