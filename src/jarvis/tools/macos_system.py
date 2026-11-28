"""Battery, system info, brightness and screen lock."""
import ctypes
import json
import re
import subprocess
from ctypes import util


class SystemToolsMixin:
    """Battery, system info, brightness and screen lock. Mixed into MacOSTools."""

    def get_battery_status(self) -> dict:
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur batterie inconnue."
            raise RuntimeError(error)

        return self._parse_pmset_battery(result.stdout)

    def get_system_info(self) -> dict:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur system_profiler inconnue."
            raise RuntimeError(error)

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("La reponse system_profiler est invalide.") from error

        hardware_items = payload.get("SPHardwareDataType") or []

        if not hardware_items:
            raise RuntimeError("Aucune information materielle disponible.")

        hardware = hardware_items[0]

        return {
            "model_name": hardware.get("machine_name"),
            "model_identifier": hardware.get("machine_model"),
            "chip": hardware.get("chip_type") or hardware.get("cpu_type"),
            "memory": hardware.get("physical_memory"),
            "serial_number": hardware.get("serial_number"),
        }

    def get_brightness(self) -> int:
        brightness = self._get_display_brightness()
        return round(brightness * 100)

    def set_brightness(self, level: int) -> dict:
        level = int(level)

        if not 0 <= level <= 100:
            raise ValueError("La luminosite doit etre comprise entre 0 et 100.")

        self._set_display_brightness(level / 100)
        observed = self.get_brightness()

        return {
            "requested_brightness": level,
            "brightness": observed,
        }

    def lock_screen(self) -> dict:
        script = (
            'tell application "System Events" '
            'to key code 12 using {control down, command down}'
        )
        result = subprocess.run(
            [
                "osascript",
                "-e",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur de verrouillage inconnue."
            raise RuntimeError(error)

        locked = self._read_lock_screen_state()

        return {
            "command_executed": True,
            "state_confirmed": locked is not None,
            "locked": locked,
            "backend": "system_events_control_command_q",
        }

    @staticmethod
    def _read_lock_screen_state() -> bool | None:
        return None

    @staticmethod
    def _parse_pmset_battery(output: str) -> dict:
        percentage_match = re.search(r"(\d+)%", output)

        if percentage_match is None:
            raise RuntimeError("Impossible de lire le pourcentage de batterie.")

        percentage = int(percentage_match.group(1))
        normalized = output.lower()
        charging = bool(re.search(r";\s*charging[;,]", normalized))
        charged = "charged" in normalized
        external_power = "ac power" in normalized

        return {
            "percentage": percentage,
            "charging": charging,
            "charged": charged,
            "external_power": external_power,
            "raw": output.strip(),
        }

    @staticmethod
    def _get_display_services_framework():
        return ctypes.CDLL(
            "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
        )

    @staticmethod
    def _get_core_graphics_framework():
        framework_path = util.find_library("CoreGraphics")

        if framework_path is None:
            raise RuntimeError("CoreGraphics est indisponible.")

        return ctypes.CDLL(framework_path)

    def _main_display_id(self) -> int:
        core_graphics = self._get_core_graphics_framework()
        core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
        return int(core_graphics.CGMainDisplayID())

    def _get_display_brightness(self) -> float:
        display_id = self._main_display_id()
        display_services = self._get_display_services_framework()
        brightness = ctypes.c_float()
        status = display_services.DisplayServicesGetBrightness(
            ctypes.c_uint32(display_id),
            ctypes.byref(brightness),
        )

        if status != 0:
            raise RuntimeError("Lecture de la luminosite indisponible.")

        return float(brightness.value)

    def _set_display_brightness(self, brightness: float) -> None:
        display_id = self._main_display_id()
        display_services = self._get_display_services_framework()
        status = display_services.DisplayServicesSetBrightness(
            ctypes.c_uint32(display_id),
            ctypes.c_float(brightness),
        )

        if status != 0:
            raise RuntimeError("Reglage de la luminosite indisponible.")
