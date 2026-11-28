"""Window actions: focus, minimize, maximize, move."""

from jarvis.tools.macos_base import (
    WINDOW_DEFAULT_MENU_BAR_OFFSET,
    WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS,
)


class WindowActionsMixin:
    """Window actions: focus, minimize, maximize, move. Mixed into MacOSTools."""

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
