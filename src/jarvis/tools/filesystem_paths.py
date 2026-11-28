"""PathResolver: turns user wording into safe paths inside the home folder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis.tools.filesystem_common import (
    FileSystemError,
    REFERENCE_WORDS,
    normalize_text,
    path_info,
)


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
