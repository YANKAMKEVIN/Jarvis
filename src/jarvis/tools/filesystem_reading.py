"""Bounded text extraction from text, DOCX and PDF files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.tools.filesystem_common import FileSystemError, is_sensitive_path


class FileReadingMixin:
    """Bounded text extraction from text, DOCX and PDF files. Mixed into FileSystemTools."""

    def read_text(self, path: str | Path, max_chars: int = 12000) -> dict[str, Any]:
        """Read a local text file's content (bounded), refusing binary files."""
        resolved = self.resolver.resolve_existing(
            path,
            action="read_text",
            expected_kind="file",
            follow_symlink=True,
        )
        self._refuse_sensitive(resolved)
        cap = max(200, min(int(max_chars), 40000))
        pages_truncated = False
        if resolved.suffix.lower() == ".pdf":
            text, pages_truncated = self._read_pdf_text(resolved, max_chars=cap, _metadata=True)
        elif resolved.suffix.lower() == ".docx":
            text = self._read_docx_text(resolved)
        else:
            try:
                with resolved.open("rb") as stream:
                    raw = stream.read(cap * 4 + 1)  # a char is up to 4 UTF-8 bytes
            except OSError as error:
                raise FileSystemError(f"Lecture impossible : {error}", "read_failed")
            if b"\x00" in raw[:4096]:
                raise FileSystemError(
                    "Ce fichier ne semble pas etre du texte lisible.", "binary_file"
                )
            text = raw.decode("utf-8", errors="replace")
        truncated = pages_truncated or len(text) > cap
        return {
            "path": str(resolved),
            "name": resolved.name,
            "text": text[:cap],
            "char_count": min(len(text), cap),
            "truncated": truncated,
        }

    def _refuse_sensitive(self, path: Path) -> None:
        home = self.resolver.home
        for candidate in (path, path.resolve(strict=False)):
            try:
                parts = candidate.relative_to(home).parts
            except ValueError:
                parts = candidate.parts
            if is_sensitive_path(parts):
                raise FileSystemError(
                    "Ce fichier peut contenir des secrets ; lecture refusee.",
                    "sensitive_path_refused",
                )

    @staticmethod
    def _read_docx_text(path: Path) -> str:
        import zipfile
        import xml.etree.ElementTree as ET
        try:
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > 10 * 1024 * 1024:
                    raise ValueError('Document XML trop volumineux')
                with archive.open(info) as stream:xml = stream.read(10 * 1024 * 1024 + 1)
                if len(xml) > 10 * 1024 * 1024:raise ValueError('Document XML trop volumineux')
            if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                raise ValueError('Entites XML refusees')
            root = ET.fromstring(xml)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            return '\n'.join(''.join(node.text or '' for node in paragraph.iter(ns+'t')) for paragraph in root.iter(ns+'p'))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError, RuntimeError):
            raise FileSystemError('Document DOCX illisible ou trop volumineux.', 'docx_unreadable') from None

    @staticmethod
    def _read_pdf_text(path: Path, max_pages: int = 50, *, max_chars: int | None = None, _metadata: bool = False) -> str | tuple[str, bool]:
        try:
            from pypdf import PdfReader
        except Exception:
            raise FileSystemError(
                "La lecture des PDF n'est pas disponible (pypdf absent).",
                "pdf_unsupported",
            )
        try:
            reader = PdfReader(str(path))
            parts = []
            length = 0
            for page in reader.pages[:max_pages]:
                part = page.extract_text() or ""
                parts.append(part)
                length += len(part) + (1 if len(parts) > 1 else 0)
                if max_chars is not None and length > max_chars:
                    break
            pages_truncated = len(parts) < len(reader.pages)
        except Exception as error:
            raise FileSystemError(f"PDF illisible : {error}", "pdf_unreadable")
        text = "\n".join(parts)
        return (text, pages_truncated) if _metadata else text
