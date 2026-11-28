"""Listing, bounded search and Spotlight search."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from jarvis.tools.filesystem_common import (
    FileSystemError,
    is_bundle,
    normalize_text,
    path_info,
)


class FileSearchMixin:
    """Listing, bounded search and Spotlight search. Mixed into FileSystemTools."""

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

    def spotlight_search(
        self,
        query: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Content/metadata search via macOS Spotlight (mdfind), scoped to home.

        Complements find_files (name-only, slow walk): Spotlight searches file
        contents and metadata across the home folder, instantly.
        """
        query = self._validate_query(query)
        cap = self.spotlight_limit if limit is None else max(1, min(int(limit), 100))
        home = str(self.resolver.home)
        output = self._run_spotlight(["mdfind", "-onlyin", home, query])

        results: list[dict[str, Any]] = []
        total = 0
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            total += 1
            if len(results) >= cap:
                continue
            candidate = Path(line)
            try:
                results.append(path_info(candidate))
            except Exception:
                continue

        return {
            "query": query,
            "path": home,
            "results": results,
            "result_count": len(results),
            "truncated": total > len(results),
        }

    def _run_spotlight(self, argv: list[str]) -> str:
        if self.spotlight_runner is not None:
            return self.spotlight_runner(argv)
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=10,
            )
        except Exception as error:
            raise FileSystemError(
                f"Recherche Spotlight impossible : {error}", "spotlight_error"
            )
        if completed.returncode != 0:
            raise FileSystemError(
                "La recherche Spotlight a echoue.", "spotlight_error"
            )
        return completed.stdout

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
