"""Reading and observing window state through System Events."""
import time

from jarvis.tools.macos_base import (
    AppleScriptRunner,
    WINDOW_READY_STABLE_OBSERVATIONS,
    WINDOW_RECORD_SEPARATOR,
    WINDOW_STATE_OBSERVATION_ATTEMPTS,
    WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS,
)
from jarvis.tools.macos_window_geometry import WindowGeometryMixin


class WindowStateMixin:
    """Reading and observing window state through System Events. Mixed into MacOSTools."""

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
            "frontmost": AppleScriptRunner._parse_applescript_bool(output[1]),
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
            "minimized": AppleScriptRunner._parse_applescript_bool(output[7]),
            "fullscreen": AppleScriptRunner._parse_applescript_bool(output[8]),
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
                "frontmost": AppleScriptRunner._parse_applescript_bool(fields[1]),
                "window_index": int(float(fields[2].strip())),
                "window_role": fields[3].strip() or None,
                "window_subrole": fields[4].strip() or None,
                "window_title": fields[5].strip() or None,
                "window_main": AppleScriptRunner._parse_applescript_bool(fields[6]),
                "window_focused": AppleScriptRunner._parse_applescript_bool(fields[7]),
                "position": {
                    "x": int(float(fields[8].strip())),
                    "y": int(float(fields[9].strip())),
                },
                "size": {
                    "width": int(float(fields[10].strip())),
                    "height": int(float(fields[11].strip())),
                },
                "minimized": AppleScriptRunner._parse_applescript_bool(fields[12]),
                "fullscreen": AppleScriptRunner._parse_applescript_bool(fields[13]),
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
        if not WindowGeometryMixin._window_geometry_complete(candidate):
            return False

        role = candidate.get("window_role")
        subrole = candidate.get("window_subrole")

        if role and role not in {"AXWindow", "AXDialog", "AXSheet"}:
            return False

        if subrole and subrole in {"AXUnknown", "AXSystemDialog"}:
            return False

        return True

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
