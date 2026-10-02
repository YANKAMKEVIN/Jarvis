from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from typing import Any, Callable


DEFAULT_OUTPUT_DIR = "~/Pictures/Jarvis"
FILENAME_PREFIX = "jarvis-screenshot"

# Command runner contract: a callable taking an argv list and returning a
# (returncode, stdout, stderr) tuple. Injectable so capture flows are testable
# without touching the screen or the filesystem.
CommandRunner = Callable[[list], tuple[int, str, str]]


class ScreenCaptureError(Exception):
    def __init__(self, message: str, code: str | None = None, data: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


class ScreenCaptureTools:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        prober: Callable[[str], dict] | None = None,
        clock: Callable[[], datetime] | None = None,
        dir_maker: Callable[[str], Any] | None = None,
        output_dir: str | None = None,
    ):
        self.runner = runner if runner is not None else self._default_runner
        self.prober = prober if prober is not None else self._default_prober
        self.clock = clock if clock is not None else datetime.now
        self.dir_maker = (
            dir_maker
            if dir_maker is not None
            else (lambda directory: os.makedirs(directory, exist_ok=True))
        )
        self.output_dir = os.path.expanduser(output_dir or DEFAULT_OUTPUT_DIR)

    def capture_screen(
        self,
        path: str | None = None,
        display: int | None = None,
    ) -> dict[str, Any]:
        extra: list[str] = []

        if display is not None:
            extra = ["-D", str(self._validate_display(display))]

        return self._run_capture(extra, path)

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        path: str | None = None,
    ) -> dict[str, Any]:
        x, y, width, height = self.validate_region(x, y, width, height)
        extra = ["-R", f"{x},{y},{width},{height}"]
        result = self._run_capture(extra, path)
        result["region"] = {"x": x, "y": y, "width": width, "height": height}
        return result

    # -- internals --------------------------------------------------------

    def _run_capture(self, extra_args: list[str], path: str | None) -> dict[str, Any]:
        final_path = self._resolve_path(path)
        self.dir_maker(os.path.dirname(final_path))

        argv = ["screencapture", "-x", "-t", "png", *extra_args, final_path]
        code, _out, err = self.runner(argv)

        if code != 0:
            raise ScreenCaptureError(
                err.strip() or "Capture d'ecran impossible.",
                code="capture_failed",
            )

        info = self.prober(final_path)
        exists = bool(info.get("exists"))
        size = int(info.get("bytes") or 0)
        confirmed = exists and size > 0

        result: dict[str, Any] = {
            "path": final_path,
            "bytes": size,
            "command_executed": True,
            "state_confirmed": confirmed,
            "width": None,
            "height": None,
        }

        if confirmed:
            dimensions = self._probe_dimensions(final_path)
            result["width"] = dimensions.get("width")
            result["height"] = dimensions.get("height")

        return result

    def _probe_dimensions(self, path: str) -> dict[str, int]:
        try:
            code, out, _err = self.runner(
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path]
            )
        except Exception:
            return {}

        if code != 0:
            return {}

        dimensions: dict[str, int] = {}
        width = re.search(r"pixelWidth:\s*(\d+)", out)
        height = re.search(r"pixelHeight:\s*(\d+)", out)

        if width:
            dimensions["width"] = int(width.group(1))

        if height:
            dimensions["height"] = int(height.group(1))

        return dimensions

    def _resolve_path(self, path: str | None) -> str:
        if path is None:
            stamp = self.clock().strftime("%Y%m%d-%H%M%S-%f")
            return os.path.join(self.output_dir, f"{FILENAME_PREFIX}-{stamp}.png")

        if not isinstance(path, str) or not path.strip():
            raise ScreenCaptureError(
                "Le chemin de capture est invalide.",
                code="invalid_path",
            )

        candidate = os.path.expanduser(path.strip())

        if not os.path.isabs(candidate):
            candidate = os.path.join(self.output_dir, candidate)

        if not candidate.lower().endswith(".png"):
            candidate += ".png"

        return candidate

    @staticmethod
    def validate_region(x: Any, y: Any, width: Any, height: Any) -> tuple[int, int, int, int]:
        try:
            x = int(x)
            y = int(y)
            width = int(width)
            height = int(height)
        except (TypeError, ValueError) as error:
            raise ScreenCaptureError(
                "La region doit etre definie par des entiers x, y, largeur, hauteur.",
                code="invalid_region",
            ) from error

        if width <= 0 or height <= 0:
            raise ScreenCaptureError(
                "La largeur et la hauteur de la region doivent etre positives.",
                code="invalid_region",
            )

        if x < 0 or y < 0:
            raise ScreenCaptureError(
                "Les coordonnees de la region ne peuvent pas etre negatives.",
                code="invalid_region",
            )

        return x, y, width, height

    @staticmethod
    def _validate_display(display: Any) -> int:
        try:
            display = int(display)
        except (TypeError, ValueError) as error:
            raise ScreenCaptureError(
                "L'indice d'ecran doit etre un entier.",
                code="invalid_display",
            ) from error

        if display < 1:
            raise ScreenCaptureError(
                "L'indice d'ecran doit etre superieur ou egal a 1.",
                code="invalid_display",
            )

        return display

    @staticmethod
    def _default_prober(path: str) -> dict[str, Any]:
        try:
            stat = os.stat(path)
            return {"exists": True, "bytes": stat.st_size}
        except OSError:
            return {"exists": False, "bytes": 0}

    @staticmethod
    def _default_runner(argv: list[str]) -> tuple[int, str, str]:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
