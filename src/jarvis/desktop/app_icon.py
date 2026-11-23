"""AppIcon.icns for the Finder / Launchpad, rendered from assets/icons/app.svg.

No macOS tool is needed (iconutil, sips): Qt renders the SVG to PNG and the
.icns container (PNG entries, accepted since OS X 10.7) is written directly.
"""

from __future__ import annotations

import struct
from pathlib import Path

APP_SVG = Path(__file__).resolve().parent / "assets" / "icons" / "app.svg"

# icns entry type -> pixel size (PNG payload).
ICNS_ENTRIES = (
    (b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
    (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
    (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512),
)


def render_png(svg_path: Path, size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # A full QApplication (not QGuiApplication): widgets created later in
        # the same process still work.
        render_png.app = QApplication([])
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"SVG illisible : {svg_path}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def build_icns(pngs: dict[int, bytes]) -> bytes:
    body = b""
    for kind, size in ICNS_ENTRIES:
        payload = pngs[size]
        body += kind + struct.pack(">I", len(payload) + 8) + payload
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def write_icns(destination: Path, svg_path: Path = APP_SVG) -> Path:
    sizes = sorted({size for _, size in ICNS_ENTRIES})
    pngs = {size: render_png(svg_path, size) for size in sizes}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_icns(pngs))
    return destination


def read_icns(data: bytes) -> dict[bytes, bytes]:
    """Entries of an .icns file (used by the tests and the self-check)."""
    if data[:4] != b"icns" or struct.unpack(">I", data[4:8])[0] != len(data):
        raise ValueError("Fichier icns invalide")
    entries, offset = {}, 8
    while offset < len(data):
        kind = data[offset:offset + 4]
        length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        entries[kind] = data[offset + 8:offset + length]
        offset += length
    return entries
