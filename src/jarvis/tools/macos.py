import ctypes
import json
import re
import subprocess
import time
import urllib.parse
import webbrowser
from ctypes import util
from datetime import datetime


SUPPORTED_MEDIA_APPS = ("Music", "Spotify")
MEDIA_OBSERVATION_ATTEMPTS = 3
MEDIA_OBSERVATION_INTERVAL_SECONDS = 0.15
WINDOW_GEOMETRY_TOLERANCE_PIXELS = 8
WINDOW_DEFAULT_MENU_BAR_OFFSET = 25
WINDOW_STATE_OBSERVATION_ATTEMPTS = 3
WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS = 0.15
WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS = 8
WINDOW_READY_STABLE_OBSERVATIONS = 2
WINDOW_RECORD_SEPARATOR = "__JARVIS_WINDOW__"


class MacOSTools:
    def open_app(self, app_name: str) -> str:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return f"{app_name} a ete ouvert."

    def close_app(self, app_name: str) -> str:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        safe_name = app_name.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "{safe_name}" to quit'

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return f"{app_name} a ete ferme."

    def is_app_running(self, app_name: str) -> bool:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        safe_name = app_name.replace("\\", "\\\\").replace('"', '\\"')
        script = f'application "{safe_name}" is running'

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result.stdout.strip().lower() == "true"

    def open_url(self, url: str) -> str:
        if not url or not url.strip():
            raise ValueError("URL manquante.")

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        webbrowser.open(url)
        return f"J'ai ouvert {url}."

    def web_search(self, query: str) -> str:
        if not query or not query.strip():
            raise ValueError("Recherche manquante.")

        encoded_query = urllib.parse.quote_plus(query.strip())
        url = f"https://www.google.com/search?q={encoded_query}"

        webbrowser.open(url)
        return f"Recherche lancee pour : {query}."

    def get_date(self) -> str:
        return datetime.now().strftime("%d/%m/%Y")

    def set_volume(self, level: int) -> str:
        level = int(level)

        if not 0 <= level <= 100:
            raise ValueError("Le volume doit etre compris entre 0 et 100.")

        script = f"set volume output volume {level}"

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return f"Volume regle a {level} %."

    def get_volume(self) -> int:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                "output volume of (get volume settings)",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return int(result.stdout.strip())

    def mute(self) -> str:
        subprocess.run(
            ["osascript", "-e", "set volume output muted true"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return "Son coupe."

    def unmute(self) -> str:
        subprocess.run(
            ["osascript", "-e", "set volume output muted false"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return "Son reactive."

    def get_active_window(self) -> dict:
        return self._read_window_state()

    def focus_window(self, app_name: str) -> dict:
        app_name = self._validate_window_app_name(app_name)
        before_state = self._read_window_state(app_name)
        safe_name = self._escape_applescript(app_name)
        script = "\n".join([
            'tell application "System Events"',
            f'if not (exists application process "{safe_name}") then error "Application introuvable: {safe_name}"',
            f'set frontmost of application process "{safe_name}" to true',
            "end tell",
        ])

        self._run_osascript(script)
        after_state = self._read_window_state(app_name)
        confirmed = after_state.get("target_app") == app_name and after_state.get("frontmost")

        return self._window_action_state(
            action_state=after_state,
            before_state=before_state,
            command_executed=True,
            state_confirmed=bool(confirmed),
        )

    def minimize_window(self, app_name: str | None = None) -> dict:
        before_state = self._read_window_state(app_name)
        target_app = before_state["target_app"]

        prepared_state = self._prepare_window_for_geometry_action(
            target_app,
            before_state,
            restore_minimized=False,
        )

        if not prepared_state["ready"]:
            return self._window_action_state(
                action_state=prepared_state["state"],
                before_state=before_state,
                command_executed=False,
                state_confirmed=False,
                diagnostics=prepared_state["diagnostics"],
            )

        action_before_state = prepared_state["state"]

        self._set_window_minimized(
            target_app,
            action_before_state["window_index"],
            True,
        )
        after_state = self._read_window_state(target_app)
        confirmed = after_state.get("minimized") is True

        return self._window_action_state(
            action_state=after_state,
            before_state=action_before_state,
            command_executed=True,
            state_confirmed=confirmed,
            diagnostics=prepared_state["diagnostics"],
        )

    def maximize_window(self, app_name: str | None = None) -> dict:
        before_state = self._read_window_state(app_name)
        target_app = before_state["target_app"]

        prepared_state = self._prepare_window_for_geometry_action(
            target_app,
            before_state,
            restore_minimized=True,
        )

        if not prepared_state["ready"]:
            return self._window_action_state(
                action_state=prepared_state["state"],
                before_state=before_state,
                command_executed=False,
                state_confirmed=False,
                requested_position="maximize",
                diagnostics=prepared_state["diagnostics"],
            )

        action_before_state = prepared_state["state"]
        target_rect = self._target_window_rect("maximize")

        self._set_window_rect(
            target_app,
            action_before_state["window_index"],
            target_rect,
        )
        after_state = self._read_window_state(target_app)
        confirmed = self._window_rect_matches(after_state, target_rect)

        return self._window_action_state(
            action_state=after_state,
            before_state=action_before_state,
            command_executed=True,
            state_confirmed=confirmed,
            requested_position="maximize",
            target_position=target_rect["position"],
            target_size=target_rect["size"],
            diagnostics=prepared_state["diagnostics"],
        )

    def move_window(self, position: str, app_name: str | None = None) -> dict:
        normalized_position = self._validate_window_position(position)
        before_state = self._read_window_state(app_name)
        target_app = before_state["target_app"]

        if normalized_position == "fullscreen":
            self._set_window_fullscreen(
                target_app,
                before_state["window_index"],
                True,
            )
            observed = self._observe_window_transition(
                target_app,
                predicate=lambda current, previous: current.get("fullscreen") is True,
                max_attempts=WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS,
            )
            after_state = observed["state"] or before_state
            confirmed = after_state.get("fullscreen") is True
            return self._window_action_state(
                action_state=after_state,
                before_state=before_state,
                command_executed=True,
                state_confirmed=confirmed,
                requested_position=normalized_position,
                diagnostics={
                    "entered_fullscreen": True,
                    "fullscreen_enter_confirmed": confirmed,
                    "fullscreen_transition_observations": observed["attempts"],
                    "window_geometry_stable": observed["geometry_stable"],
                },
            )

        prepared_state = self._prepare_window_for_geometry_action(
            target_app,
            before_state,
            restore_minimized=False,
        )

        if not prepared_state["ready"]:
            return self._window_action_state(
                action_state=prepared_state["state"],
                before_state=before_state,
                command_executed=False,
                state_confirmed=False,
                requested_position=normalized_position,
                diagnostics=prepared_state["diagnostics"],
            )

        action_before_state = prepared_state["state"]
        target_rect = self._target_window_rect(normalized_position)

        self._set_window_rect(
            target_app,
            action_before_state["window_index"],
            target_rect,
        )
        after_state = self._read_window_state(target_app)
        confirmed = self._window_rect_matches(after_state, target_rect)

        return self._window_action_state(
            action_state=after_state,
            before_state=action_before_state,
            command_executed=True,
            state_confirmed=confirmed,
            requested_position=normalized_position,
            target_position=target_rect["position"],
            target_size=target_rect["size"],
            diagnostics=prepared_state["diagnostics"],
        )

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

    def _read_window_state(self, app_name: str | None = None) -> dict:
        candidates = self._read_window_candidates(app_name)
        selected = self._select_window_candidate(candidates)

        if selected is None:
            raise RuntimeError("Aucune fenetre manipulable.")

        return selected

    def _read_window_candidates(self, app_name: str | None = None) -> list[dict]:
        if app_name is not None:
            app_name = self._validate_window_app_name(app_name)
            safe_name = self._escape_applescript(app_name)
            process_selector = f'application process "{safe_name}"'
            missing_process_check = (
                f'if not (exists {process_selector}) then error "Application introuvable: {safe_name}"'
            )
        else:
            process_selector = "first application process whose frontmost is true"
            missing_process_check = ""

        script = "\n".join([
            'tell application "System Events"',
            missing_process_check,
            f"set target_process to {process_selector}",
            'if not (exists windows of target_process) then error "Aucune fenetre manipulable."',
            'set output_text to ""',
            'set window_index to 0',
            'repeat with candidate_window in windows of target_process',
            'set window_index to window_index + 1',
            'set role_value to ""',
            'try',
            'set role_value to value of attribute "AXRole" of candidate_window as text',
            'end try',
            'set subrole_value to ""',
            'try',
            'set subrole_value to value of attribute "AXSubrole" of candidate_window as text',
            'end try',
            'set title_value to ""',
            'try',
            'set title_value to name of candidate_window as text',
            'end try',
            'set main_value to false',
            'try',
            'set main_value to value of attribute "AXMain" of candidate_window',
            'end try',
            'set focused_value to false',
            'try',
            'set focused_value to value of attribute "AXFocused" of candidate_window',
            'end try',
            'set window_position to {0, 0}',
            'try',
            'set window_position to position of candidate_window',
            'end try',
            'set window_size to {0, 0}',
            'try',
            'set window_size to size of candidate_window',
            'end try',
            'set minimized_value to false',
            'try',
            'set minimized_value to value of attribute "AXMinimized" of candidate_window',
            'end try',
            'set fullscreen_value to false',
            'try',
            'set fullscreen_value to value of attribute "AXFullScreen" of candidate_window',
            'end try',
            f'set output_text to output_text & "{WINDOW_RECORD_SEPARATOR}" & linefeed & '
            'name of target_process & linefeed & '
            'frontmost of target_process & linefeed & '
            'window_index & linefeed & '
            'role_value & linefeed & '
            'subrole_value & linefeed & '
            'title_value & linefeed & '
            'main_value & linefeed & '
            'focused_value & linefeed & '
            'item 1 of window_position & linefeed & '
            'item 2 of window_position & linefeed & '
            'item 1 of window_size & linefeed & '
            'item 2 of window_size & linefeed & '
            'minimized_value & linefeed & fullscreen_value & linefeed',
            'end repeat',
            'return output_text',
            "end tell",
        ])
        output = self._run_osascript(script).stdout.splitlines()

        if output and output[0] != WINDOW_RECORD_SEPARATOR:
            return [self._parse_legacy_window_state(output)]

        return self._parse_window_candidates(output)

    @staticmethod
    def _parse_legacy_window_state(output: list[str]) -> dict:
        if len(output) < 9:
            raise RuntimeError("Etat de fenetre macOS incomplet.")

        return {
            "target_app": output[0].strip() or None,
            "frontmost": MacOSTools._parse_applescript_bool(output[1]),
            "window_title": output[2].strip() or None,
            "window_index": 1,
            "window_role": None,
            "window_subrole": None,
            "window_main": False,
            "window_focused": False,
            "window_candidate_count": 1,
            "position": {
                "x": int(float(output[3].strip())),
                "y": int(float(output[4].strip())),
            },
            "size": {
                "width": int(float(output[5].strip())),
                "height": int(float(output[6].strip())),
            },
            "minimized": MacOSTools._parse_applescript_bool(output[7]),
            "fullscreen": MacOSTools._parse_applescript_bool(output[8]),
        }

    @staticmethod
    def _parse_window_candidates(output: list[str]) -> list[dict]:
        candidates = []
        index = 0

        while index < len(output):
            if output[index] != WINDOW_RECORD_SEPARATOR:
                index += 1
                continue

            fields = output[index + 1:index + 15]

            if len(fields) < 14:
                break

            candidate = {
                "target_app": fields[0].strip() or None,
                "frontmost": MacOSTools._parse_applescript_bool(fields[1]),
                "window_index": int(float(fields[2].strip())),
                "window_role": fields[3].strip() or None,
                "window_subrole": fields[4].strip() or None,
                "window_title": fields[5].strip() or None,
                "window_main": MacOSTools._parse_applescript_bool(fields[6]),
                "window_focused": MacOSTools._parse_applescript_bool(fields[7]),
                "position": {
                    "x": int(float(fields[8].strip())),
                    "y": int(float(fields[9].strip())),
                },
                "size": {
                    "width": int(float(fields[10].strip())),
                    "height": int(float(fields[11].strip())),
                },
                "minimized": MacOSTools._parse_applescript_bool(fields[12]),
                "fullscreen": MacOSTools._parse_applescript_bool(fields[13]),
            }
            candidates.append(candidate)
            index += 15

        candidate_count = len(candidates)

        for candidate in candidates:
            candidate["window_candidate_count"] = candidate_count

        return candidates

    @classmethod
    def _select_window_candidate(cls, candidates: list[dict]) -> dict | None:
        compatible = [
            candidate
            for candidate in candidates
            if cls._window_candidate_manipulable(candidate)
        ]

        if not compatible:
            return None

        def sort_key(candidate):
            area = candidate["size"]["width"] * candidate["size"]["height"]
            return (
                1 if candidate.get("window_main") else 0,
                1 if candidate.get("window_focused") else 0,
                1 if candidate.get("window_subrole") == "AXStandardWindow" else 0,
                area,
                -candidate.get("window_index", 0),
            )

        return max(compatible, key=sort_key)

    @staticmethod
    def _window_candidate_manipulable(candidate: dict) -> bool:
        if not MacOSTools._window_geometry_complete(candidate):
            return False

        role = candidate.get("window_role")
        subrole = candidate.get("window_subrole")

        if role and role not in {"AXWindow", "AXDialog", "AXSheet"}:
            return False

        if subrole and subrole in {"AXUnknown", "AXSystemDialog"}:
            return False

        return True

    def _set_window_rect(self, app_name: str, window_index: int, rect: dict) -> None:
        safe_name = self._escape_applescript(app_name)
        x = rect["position"]["x"]
        y = rect["position"]["y"]
        width = rect["size"]["width"]
        height = rect["size"]["height"]
        script = "\n".join([
            'tell application "System Events"',
            f'tell application process "{safe_name}"',
            f'if not (exists window {window_index}) then error "Aucune fenetre manipulable."',
            f"set target_window to window {window_index}",
            f"set position of target_window to {{{x}, {y}}}",
            f"set size of target_window to {{{width}, {height}}}",
            "end tell",
            "end tell",
        ])
        self._run_osascript(script)

    def _set_window_fullscreen(
        self,
        app_name: str,
        window_index: int,
        fullscreen: bool,
    ) -> None:
        safe_name = self._escape_applescript(app_name)
        value = "true" if fullscreen else "false"
        script = "\n".join([
            'tell application "System Events"',
            f'tell application process "{safe_name}"',
            f'if not (exists window {window_index}) then error "Aucune fenetre manipulable."',
            f'set value of attribute "AXFullScreen" of window {window_index} to {value}',
            "end tell",
            "end tell",
        ])
        self._run_osascript(script)

    def _set_window_minimized(
        self,
        app_name: str,
        window_index: int,
        minimized: bool,
    ) -> None:
        safe_name = self._escape_applescript(app_name)
        value = "true" if minimized else "false"
        script = "\n".join([
            'tell application "System Events"',
            f'tell application process "{safe_name}"',
            f'if not (exists window {window_index}) then error "Aucune fenetre manipulable."',
            f'set value of attribute "AXMinimized" of window {window_index} to {value}',
            "end tell",
            "end tell",
        ])
        self._run_osascript(script)

    def _target_window_rect(self, position: str) -> dict:
        frame = self._main_screen_usable_frame()
        x = frame["x"]
        y = frame["y"]
        width = frame["width"]
        height = frame["height"]

        if position == "left":
            return {
                "position": {"x": x, "y": y},
                "size": {"width": width // 2, "height": height},
            }

        if position == "right":
            half_width = width // 2
            return {
                "position": {"x": x + half_width, "y": y},
                "size": {"width": width - half_width, "height": height},
            }

        if position == "center":
            target_width = int(width * 0.7)
            target_height = int(height * 0.8)
            return {
                "position": {
                    "x": x + (width - target_width) // 2,
                    "y": y + (height - target_height) // 2,
                },
                "size": {
                    "width": target_width,
                    "height": target_height,
                },
            }

        if position == "maximize":
            return {
                "position": {"x": x, "y": y},
                "size": {"width": width, "height": height},
            }

        raise ValueError("Position de fenetre non supportee.")

    def _main_screen_usable_frame(self) -> dict:
        script = "\n".join([
            "ObjC.import('AppKit');",
            "const screen = $.NSScreen.mainScreen;",
            "if (!screen) { throw new Error('Aucun ecran principal.'); }",
            "const frame = screen.frame;",
            "const visible = screen.visibleFrame;",
            "const x = Math.round(visible.origin.x);",
            "const y = Math.round(frame.size.height - visible.origin.y - visible.size.height);",
            "const width = Math.round(visible.size.width);",
            "const height = Math.round(visible.size.height);",
            "[x, y, width, height].join('\\n');",
        ])
        output = self._run_osa_javascript(script).stdout.splitlines()

        if len(output) != 4:
            raise RuntimeError("Cadre d'ecran macOS indisponible.")

        x, y, width, height = [int(float(part.strip())) for part in output]

        return {
            "x": x,
            "y": max(y, WINDOW_DEFAULT_MENU_BAR_OFFSET),
            "width": width,
            "height": height,
        }

    def _prepare_window_for_geometry_action(
        self,
        app_name: str,
        before_state: dict,
        restore_minimized: bool,
    ) -> dict:
        diagnostics = {
            "entered_fullscreen": False,
            "fullscreen_enter_confirmed": None,
            "exited_fullscreen": False,
            "fullscreen_exit_confirmed": None,
            "fullscreen_transition_observations": 0,
            "fullscreen_settle_observations": 0,
            "window_geometry_stable": None,
            "window_ready_for_action": None,
            "restored_minimized": False,
            "minimized_restore_confirmed": None,
        }
        state = before_state

        if before_state.get("fullscreen"):
            self._set_window_fullscreen(
                app_name,
                before_state["window_index"],
                False,
            )
            observed = self._observe_window_ready_for_action(
                app_name,
                max_attempts=WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS,
            )
            state = observed["state"] or before_state
            diagnostics["exited_fullscreen"] = True
            diagnostics["fullscreen_exit_confirmed"] = (
                state.get("fullscreen") is False and observed["ready"]
            )
            diagnostics["fullscreen_transition_observations"] = observed["attempts"]
            diagnostics["fullscreen_settle_observations"] = observed["stable_observations"]
            diagnostics["window_geometry_stable"] = observed["geometry_stable"]
            diagnostics["window_ready_for_action"] = observed["ready"]

            if not diagnostics["fullscreen_exit_confirmed"]:
                return {
                    "ready": False,
                    "state": state,
                    "diagnostics": diagnostics,
                }

        if restore_minimized and state.get("minimized"):
            self._set_window_minimized(
                app_name,
                state["window_index"],
                False,
            )
            state = self._observe_window_state_until(
                app_name,
                predicate=lambda observed: observed.get("minimized") is False,
            )
            diagnostics["restored_minimized"] = True
            diagnostics["minimized_restore_confirmed"] = state.get("minimized") is False

            if not diagnostics["minimized_restore_confirmed"]:
                return {
                    "ready": False,
                    "state": state,
                    "diagnostics": diagnostics,
                }

        return {
            "ready": True,
            "state": state,
            "diagnostics": diagnostics,
        }

    def _observe_window_state_until(self, app_name: str, predicate) -> dict:
        state = None

        for attempt in range(1, WINDOW_STATE_OBSERVATION_ATTEMPTS + 1):
            state = self._read_window_state(app_name)

            if predicate(state):
                break

            if attempt < WINDOW_STATE_OBSERVATION_ATTEMPTS:
                time.sleep(WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS)

        return state

    def _observe_window_transition(
        self,
        app_name: str,
        predicate,
        max_attempts: int = WINDOW_STATE_OBSERVATION_ATTEMPTS,
    ) -> dict:
        state = None
        previous_state = None
        attempts = 0
        geometry_stable = False

        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                state = self._read_window_state(app_name)
            except RuntimeError:
                state = previous_state

                if attempt < max_attempts:
                    time.sleep(WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS)

                continue

            geometry_stable = self._window_geometry_stable(state, previous_state)

            if predicate(state, previous_state):
                break

            previous_state = state

            if attempt < max_attempts:
                time.sleep(WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS)

        return {
            "state": state,
            "attempts": attempts,
            "geometry_stable": geometry_stable,
        }

    def _observe_window_ready_for_action(
        self,
        app_name: str,
        max_attempts: int,
    ) -> dict:
        state = None
        previous_state = None
        attempts = 0
        stable_observations = 0
        geometry_stable = False
        ready = False

        for attempt in range(1, max_attempts + 1):
            attempts = attempt

            try:
                state = self._read_window_state(app_name)
            except RuntimeError:
                state = previous_state
                stable_observations = 0

                if attempt < max_attempts:
                    time.sleep(WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS)

                continue

            geometry_stable = (
                state.get("fullscreen") is False
                and self._window_geometry_stable(state, previous_state)
                and self._window_candidate_consistent(state, previous_state)
            )

            if geometry_stable:
                stable_observations += 1
            else:
                stable_observations = 0

            ready = stable_observations >= WINDOW_READY_STABLE_OBSERVATIONS

            if ready:
                break

            previous_state = state

            if attempt < max_attempts:
                time.sleep(WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS)

        return {
            "state": state,
            "attempts": attempts,
            "stable_observations": stable_observations,
            "geometry_stable": geometry_stable,
            "ready": ready,
        }

    @staticmethod
    def _window_action_state(
        action_state: dict,
        before_state: dict,
        command_executed: bool,
        state_confirmed: bool,
        requested_position: str | None = None,
        target_position: dict | None = None,
        target_size: dict | None = None,
        diagnostics: dict | None = None,
    ) -> dict:
        state = dict(action_state)
        state["command_executed"] = command_executed
        state["state_confirmed"] = state_confirmed
        state["previous_position"] = before_state.get("position")
        state["previous_size"] = before_state.get("size")
        state["previous_fullscreen"] = before_state.get("fullscreen")
        state["previous_minimized"] = before_state.get("minimized")

        if requested_position is not None:
            state["requested_position"] = requested_position

        if target_position is not None:
            state["target_position"] = target_position

        if target_size is not None:
            state["target_size"] = target_size

        if diagnostics is not None:
            state.update(diagnostics)

        return state

    @staticmethod
    def _window_rect_matches(state: dict, rect: dict) -> bool:
        position = state.get("position") or {}
        size = state.get("size") or {}
        target_position = rect["position"]
        target_size = rect["size"]

        pairs = (
            (position.get("x"), target_position["x"]),
            (position.get("y"), target_position["y"]),
            (size.get("width"), target_size["width"]),
            (size.get("height"), target_size["height"]),
        )

        if any(observed is None for observed, _expected in pairs):
            return False

        return all(
            abs(observed - expected) <= WINDOW_GEOMETRY_TOLERANCE_PIXELS
            for observed, expected in pairs
        )

    @staticmethod
    def _window_geometry_complete(state: dict | None) -> bool:
        if state is None:
            return False

        position = state.get("position") or {}
        size = state.get("size") or {}

        x = position.get("x")
        y = position.get("y")
        width = size.get("width")
        height = size.get("height")

        return (
            isinstance(x, int | float)
            and isinstance(y, int | float)
            and isinstance(width, int | float)
            and isinstance(height, int | float)
            and x >= 0
            and y >= 0
            and width > 0
            and height > 0
        )

    @staticmethod
    def _window_geometry_stable(current: dict | None, previous: dict | None) -> bool:
        if current is None or previous is None:
            return False

        if not (
            MacOSTools._window_geometry_complete(current)
            and MacOSTools._window_geometry_complete(previous)
        ):
            return False

        current_position = current["position"]
        previous_position = previous["position"]
        current_size = current["size"]
        previous_size = previous["size"]
        pairs = (
            (current_position["x"], previous_position["x"]),
            (current_position["y"], previous_position["y"]),
            (current_size["width"], previous_size["width"]),
            (current_size["height"], previous_size["height"]),
        )

        return all(
            abs(current_value - previous_value) <= WINDOW_GEOMETRY_TOLERANCE_PIXELS
            for current_value, previous_value in pairs
        )

    @staticmethod
    def _window_candidate_consistent(
        current: dict | None,
        previous: dict | None,
    ) -> bool:
        if current is None or previous is None:
            return False

        if current.get("target_app") != previous.get("target_app"):
            return False

        if current.get("window_role") != previous.get("window_role"):
            return False

        if current.get("window_subrole") != previous.get("window_subrole"):
            return False

        current_title = current.get("window_title")
        previous_title = previous.get("window_title")

        if current_title and previous_title and current_title != previous_title:
            return False

        return True

    @staticmethod
    def _validate_window_app_name(app_name: str) -> str:
        if not isinstance(app_name, str) or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        return app_name.strip()

    @staticmethod
    def _validate_window_position(position: str) -> str:
        if not isinstance(position, str):
            raise ValueError("Position de fenetre non supportee.")

        normalized = position.strip().lower()

        if normalized not in {"left", "right", "center", "fullscreen"}:
            raise ValueError("Position de fenetre non supportee.")

        return normalized

    @staticmethod
    def _parse_applescript_bool(value: str) -> bool:
        return value.strip().lower() == "true"

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

    def play_pause(self, preferred_app: str | None = None) -> dict:
        app_name = self._active_media_app(preferred_app)

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to playpause'
        )
        state = self.get_media_state(app_name)
        state["app"] = app_name

        return state

    def next_track(self, preferred_app: str | None = None) -> dict:
        app_name, before_state = self._active_media_context(preferred_app)

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to next track'
        )
        state = self._media_state_after_command(
            app_name,
            before_state,
            command_attempts=1,
        )

        return state

    def previous_track(self, preferred_app: str | None = None) -> dict:
        app_name, before_state = self._active_media_context(preferred_app)

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to previous track'
        )
        state = self._media_state_after_command(
            app_name,
            before_state,
            command_attempts=1,
        )

        if state["track_changed"]:
            return state

        if not state["command_executed"] or not state["media_observed"]:
            return state

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to previous track'
        )
        state = self._media_state_after_command(
            app_name,
            state,
            command_attempts=2,
        )

        return state

    def get_media_state(self, app_name: str | None = None) -> dict:
        if app_name is None:
            app_name, state = self._active_media_context()

            if app_name is not None:
                return state

        if app_name is None:
            return {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            }

        safe_name = self._escape_applescript(app_name)
        script = "\n".join([
            f'tell application "{safe_name}"',
            'set track_name to ""',
            'set artist_name to ""',
            "try",
            "set track_name to name of current track",
            "end try",
            "try",
            "set artist_name to artist of current track",
            "end try",
            "set playback_state to player state as text",
            "return playback_state & linefeed & track_name & linefeed & artist_name",
            "end tell",
        ])
        output = self._run_osascript(script).stdout.splitlines()
        playback_state = output[0].strip().lower() if output else ""
        title = output[1].strip() if len(output) > 1 and output[1].strip() else None
        artist = output[2].strip() if len(output) > 2 and output[2].strip() else None
        media_available = bool(playback_state or title or artist)

        return {
            "media_available": media_available,
            "playing": playback_state == "playing",
            "title": title,
            "artist": artist,
            "app": app_name,
        }

    def _active_media_app(self, preferred_app: str | None = None) -> str | None:
        app_name, _state = self._active_media_context(preferred_app)
        return app_name

    def _active_media_context(
        self,
        preferred_app: str | None = None,
    ) -> tuple[str | None, dict | None]:
        # The user's preferred player (from memory) is tried first when
        # several supported players are running; otherwise the fixed order.
        order = list(SUPPORTED_MEDIA_APPS)
        if preferred_app in order:
            order.remove(preferred_app)
            order.insert(0, preferred_app)

        for app_name in order:
            if not self.is_app_running(app_name):
                continue

            try:
                state = self.get_media_state(app_name)
            except Exception:
                continue

            if state["media_available"]:
                return app_name, state

        return None, None

    def _media_state_after_command(
        self,
        app_name: str,
        before_state: dict | None,
        command_attempts: int,
    ) -> dict:
        before_title = before_state.get("title") if before_state else None
        before_artist = before_state.get("artist") if before_state else None
        after_state = None
        attempts = 0

        for attempt in range(1, MEDIA_OBSERVATION_ATTEMPTS + 1):
            attempts = attempt
            after_state = self.get_media_state(app_name)
            after_title = after_state.get("title")
            after_artist = after_state.get("artist")
            track_changed = after_state.get("media_available", False) and (
                (before_title, before_artist) != (after_title, after_artist)
            )

            if track_changed or not after_state.get("media_available", False):
                break

            if attempt < MEDIA_OBSERVATION_ATTEMPTS:
                time.sleep(MEDIA_OBSERVATION_INTERVAL_SECONDS)

        if after_state is None:
            after_state = {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": app_name,
            }

        after_state["app"] = app_name
        after_state["command_executed"] = True
        after_state["media_observed"] = after_state.get("media_available", False)
        after_title = after_state.get("title")
        after_artist = after_state.get("artist")
        after_state["previous_title"] = before_title
        after_state["previous_artist"] = before_artist
        after_state["track_changed"] = after_state["media_observed"] and (
            (before_title, before_artist) != (after_title, after_artist)
        )
        after_state["observation_attempts"] = attempts
        after_state["command_attempts"] = command_attempts

        return after_state

    @staticmethod
    def _escape_applescript(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _run_osascript(script: str):
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result

    @staticmethod
    def _run_osa_javascript(script: str):
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result
