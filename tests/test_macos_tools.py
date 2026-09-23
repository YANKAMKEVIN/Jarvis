import unittest
from unittest.mock import patch

from jarvis.tools.macos import MacOSTools


class FakeCompletedProcess:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class MacOSToolsTest(unittest.TestCase):
    @staticmethod
    def window_state_output(
        app="Safari",
        frontmost=True,
        title="Example",
        x=0,
        y=25,
        width=800,
        height=600,
        minimized=False,
        fullscreen=False,
    ):
        return "\n".join([
            app,
            "true" if frontmost else "false",
            title,
            str(x),
            str(y),
            str(width),
            str(height),
            "true" if minimized else "false",
            "true" if fullscreen else "false",
            "",
        ])

    @staticmethod
    def visible_frame_output(x=0, y=33, width=1512, height=878):
        return f"{x}\n{y}\n{width}\n{height}\n"

    @staticmethod
    def window_candidates_output(*candidates):
        chunks = []

        for index, candidate in enumerate(candidates, start=1):
            chunks.extend([
                "__JARVIS_WINDOW__",
                candidate.get("app", "Safari"),
                "true" if candidate.get("frontmost", True) else "false",
                str(candidate.get("index", index)),
                candidate.get("role", "AXWindow"),
                candidate.get("subrole", "AXStandardWindow"),
                candidate.get("title", "Example"),
                "true" if candidate.get("main", False) else "false",
                "true" if candidate.get("focused", False) else "false",
                str(candidate.get("x", 0)),
                str(candidate.get("y", 33)),
                str(candidate.get("width", 800)),
                str(candidate.get("height", 600)),
                "true" if candidate.get("minimized", False) else "false",
                "true" if candidate.get("fullscreen", False) else "false",
            ])

        return "\n".join(chunks) + "\n"

    def test_get_volume_reads_output_volume_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="42\n"),
        ) as run:
            volume = MacOSTools().get_volume()

        self.assertEqual(volume, 42)
        run.assert_called_once_with(
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

    def test_open_app_uses_open_with_argument_list_for_names_with_spaces(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(),
        ) as run:
            message = MacOSTools().open_app("Visual Studio Code")

        self.assertEqual(message, "Visual Studio Code a ete ouvert.")
        run.assert_called_once_with(
            ["open", "-a", "Visual Studio Code"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_open_app_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Application introuvable",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Application introuvable"):
                MacOSTools().open_app("Missing App")

    def test_close_app_uses_osascript_with_escaped_name(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(),
        ) as run:
            message = MacOSTools().close_app("Google Chrome")

        self.assertEqual(message, "Google Chrome a ete ferme.")
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'tell application "Google Chrome" to quit',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_close_app_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Quit failed",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Quit failed"):
                MacOSTools().close_app("Spotify")

    def test_is_app_running_reads_boolean_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="true\n"),
        ) as run:
            running = MacOSTools().is_app_running("Visual Studio Code")

        self.assertTrue(running)
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'application "Visual Studio Code" is running',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_is_app_running_returns_false_for_false_output(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            running = MacOSTools().is_app_running("Spotify")

        self.assertFalse(running)

    def test_is_app_running_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="State check failed",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "State check failed"):
                MacOSTools().is_app_running("Spotify")

    def test_get_battery_status_parses_charging_battery(self):
        output = (
            "Now drawing from 'AC Power'\n"
            " -InternalBattery-0 (id=1234567)\t74%; charging; 1:20 remaining present: true\n"
        )

        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout=output),
        ) as run:
            status = MacOSTools().get_battery_status()

        self.assertEqual(status["percentage"], 74)
        self.assertTrue(status["charging"])
        self.assertTrue(status["external_power"])
        run.assert_called_once_with(
            ["pmset", "-g", "batt"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_get_battery_status_parses_non_charging_battery(self):
        output = (
            "Now drawing from 'Battery Power'\n"
            " -InternalBattery-0 (id=1234567)\t42%; discharging; 4:00 remaining present: true\n"
        )

        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout=output),
        ):
            status = MacOSTools().get_battery_status()

        self.assertEqual(status["percentage"], 42)
        self.assertFalse(status["charging"])
        self.assertFalse(status["external_power"])

    def test_get_battery_status_raises_on_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(returncode=1, stderr="pmset failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pmset failed"):
                MacOSTools().get_battery_status()

    def test_get_system_info_parses_system_profiler_json(self):
        payload = (
            '{"SPHardwareDataType":[{"machine_name":"MacBook Pro",'
            '"machine_model":"Mac15,3","chip_type":"Apple M3",'
            '"physical_memory":"8 GB","serial_number":"TEST123"}]}'
        )

        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout=payload),
        ) as run:
            info = MacOSTools().get_system_info()

        self.assertEqual(info["model_name"], "MacBook Pro")
        self.assertEqual(info["model_identifier"], "Mac15,3")
        self.assertEqual(info["chip"], "Apple M3")
        self.assertEqual(info["memory"], "8 GB")
        run.assert_called_once_with(
            ["system_profiler", "SPHardwareDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_get_brightness_reads_display_brightness(self):
        tools = MacOSTools()

        with patch.object(tools, "_get_display_brightness", return_value=0.42):
            brightness = tools.get_brightness()

        self.assertEqual(brightness, 42)

    def test_set_brightness_sets_and_reads_observed_value(self):
        tools = MacOSTools()

        with patch.object(tools, "_set_display_brightness") as set_brightness:
            with patch.object(tools, "get_brightness", return_value=31):
                state = tools.set_brightness(30)

        set_brightness.assert_called_once_with(0.3)
        self.assertEqual(
            state,
            {
                "requested_brightness": 30,
                "brightness": 31,
            },
        )

    def test_set_brightness_rejects_out_of_range_before_backend(self):
        tools = MacOSTools()

        with patch.object(tools, "_set_display_brightness") as set_brightness:
            with self.assertRaisesRegex(ValueError, "0 et 100"):
                tools.set_brightness(101)

        set_brightness.assert_not_called()

    def test_lock_screen_uses_system_events_shortcut_without_real_lock(self):
        with patch.object(MacOSTools, "_read_lock_screen_state", return_value=None):
            with patch(
                "jarvis.tools.macos.subprocess.run",
                return_value=FakeCompletedProcess(),
            ) as run:
                state = MacOSTools().lock_screen()

        self.assertEqual(
            state,
            {
                "command_executed": True,
                "state_confirmed": False,
                "locked": None,
                "backend": "system_events_control_command_q",
            },
        )
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                (
                    'tell application "System Events" '
                    'to key code 12 using {control down, command down}'
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_lock_screen_can_return_confirmed_state_when_backend_confirms_it(self):
        with patch.object(MacOSTools, "_read_lock_screen_state", return_value=True):
            with patch(
                "jarvis.tools.macos.subprocess.run",
                return_value=FakeCompletedProcess(),
            ):
                state = MacOSTools().lock_screen()

        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertTrue(state["locked"])

    def test_lock_screen_raises_on_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(returncode=1, stderr="lock failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "lock failed"):
                MacOSTools().lock_screen()

    def test_get_active_window_reads_frontmost_window_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                stdout=self.window_state_output(
                    app="Visual Studio Code",
                    title="main.py",
                    x=10,
                    y=40,
                    width=900,
                    height=700,
                )
            ),
        ) as run:
            state = MacOSTools().get_active_window()

        self.assertEqual(state["target_app"], "Visual Studio Code")
        self.assertEqual(state["window_title"], "main.py")
        self.assertEqual(state["position"], {"x": 10, "y": 40})
        self.assertEqual(state["size"], {"width": 900, "height": 700})
        self.assertFalse(state["fullscreen"])
        self.assertIn(
            "first application process whose frontmost is true",
            run.call_args.args[0][2],
        )

    def test_window_selector_skips_transition_window_and_selects_real_candidate(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                stdout=self.window_candidates_output(
                    {
                        "index": 1,
                        "role": "AXGroup",
                        "subrole": "AXUnknown",
                        "title": "Transition",
                        "x": 0,
                        "y": 0,
                        "width": 1512,
                        "height": 33,
                    },
                    {
                        "index": 2,
                        "role": "AXWindow",
                        "subrole": "AXStandardWindow",
                        "title": "JARVIS",
                        "main": True,
                        "x": 227,
                        "y": 121,
                        "width": 1058,
                        "height": 703,
                    },
                )
            ),
        ):
            state = MacOSTools().get_active_window()

        self.assertEqual(state["window_index"], 2)
        self.assertEqual(state["window_title"], "JARVIS")
        self.assertTrue(state["window_main"])
        self.assertEqual(state["window_candidate_count"], 2)
        self.assertEqual(state["window_role"], "AXWindow")

    def test_window_selector_prioritizes_axmain_candidate(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                stdout=self.window_candidates_output(
                    {
                        "index": 1,
                        "title": "Focused",
                        "focused": True,
                        "width": 1200,
                        "height": 800,
                    },
                    {
                        "index": 2,
                        "title": "Main",
                        "main": True,
                        "width": 600,
                        "height": 400,
                    },
                )
            ),
        ):
            state = MacOSTools().get_active_window()

        self.assertEqual(state["window_index"], 2)
        self.assertEqual(state["window_title"], "Main")

    def test_window_selector_falls_back_to_axfocused_candidate(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                stdout=self.window_candidates_output(
                    {
                        "index": 1,
                        "title": "Other",
                        "width": 1200,
                        "height": 800,
                    },
                    {
                        "index": 2,
                        "title": "Focused",
                        "focused": True,
                        "width": 600,
                        "height": 400,
                    },
                )
            ),
        ):
            state = MacOSTools().get_active_window()

        self.assertEqual(state["window_index"], 2)
        self.assertTrue(state["window_focused"])

    def test_window_selector_is_deterministic_for_multiple_valid_windows(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                stdout=self.window_candidates_output(
                    {
                        "index": 1,
                        "title": "Large",
                        "width": 900,
                        "height": 700,
                    },
                    {
                        "index": 2,
                        "title": "Small",
                        "width": 600,
                        "height": 400,
                    },
                )
            ),
        ):
            state = MacOSTools().get_active_window()

        self.assertEqual(state["window_index"], 1)
        self.assertEqual(state["window_title"], "Large")

    def test_get_active_window_raises_explicit_no_window_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Aucune fenetre manipulable.",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Aucune fenetre"):
                MacOSTools().get_active_window()

    def test_focus_window_sets_frontmost_and_confirms_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(app="Safari")),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(app="Safari")),
            ],
        ) as run:
            state = MacOSTools().focus_window("Safari")

        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["target_app"], "Safari")
        self.assertIn("set frontmost", run.call_args_list[1].args[0][2])

    def test_minimize_window_sets_axminimized_and_confirms_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(minimized=False)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(minimized=True)),
            ],
        ) as run:
            state = MacOSTools().minimize_window()

        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertTrue(state["minimized"])
        self.assertIn('AXMinimized', run.call_args_list[1].args[0][2])

    def test_maximize_window_uses_bounds_without_axfullscreen(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(app="Safari")),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_state_output(
                        app="Safari",
                        x=0,
                        y=33,
                        width=1512,
                        height=878,
                        fullscreen=False,
                    )
                ),
            ],
        ) as run:
            state = MacOSTools().maximize_window("Safari")

        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["requested_position"], "maximize")
        self.assertFalse(state["fullscreen"])
        script = run.call_args_list[2].args[0][2]
        self.assertIn("set size of target_window to {1512, 878}", script)
        self.assertNotIn("to true", script)

    def test_move_window_left_confirms_real_1512_half_screen_geometry(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(app="Safari")),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_state_output(
                        app="Safari",
                        x=0,
                        y=33,
                        width=756,
                        height=878,
                    )
                ),
            ],
        ) as run:
            state = MacOSTools().move_window("left", "Safari")

        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["requested_position"], "left")
        self.assertEqual(state["target_position"], {"x": 0, "y": 33})
        self.assertEqual(state["target_size"], {"width": 756, "height": 878})
        self.assertIn("set position of target_window to {0, 33}", run.call_args_list[2].args[0][2])

    def test_move_window_right_confirms_real_1512_half_screen_geometry(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(app="Safari")),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_state_output(
                        app="Safari",
                        x=756,
                        y=33,
                        width=756,
                        height=878,
                    )
                ),
            ],
        ):
            state = MacOSTools().move_window("right", "Safari")

        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["target_position"], {"x": 756, "y": 33})
        self.assertEqual(state["target_size"], {"width": 756, "height": 878})

    def test_move_window_fullscreen_uses_axfullscreen_and_requires_confirmed_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
            ],
        ) as run:
            state = MacOSTools().move_window("fullscreen")

        self.assertTrue(state["state_confirmed"])
        self.assertTrue(state["fullscreen"])
        self.assertEqual(state["requested_position"], "fullscreen")
        self.assertIn('AXFullScreen', run.call_args_list[1].args[0][2])

    def test_move_window_fullscreen_observes_delayed_axfullscreen_confirmation(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                ],
            ):
                state = MacOSTools().move_window("fullscreen")

        self.assertTrue(state["state_confirmed"])
        self.assertTrue(state["fullscreen"])
        self.assertTrue(state["entered_fullscreen"])
        self.assertTrue(state["fullscreen_enter_confirmed"])
        self.assertEqual(state["fullscreen_transition_observations"], 2)
        self.assertEqual(sleep.call_count, 1)

    def test_move_window_fullscreen_confirms_candidate_that_is_not_first_window(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(
                    stdout=self.window_candidates_output(
                        {
                            "index": 1,
                            "role": "AXGroup",
                            "subrole": "AXUnknown",
                            "title": "Transition",
                            "width": 1512,
                            "height": 33,
                        },
                        {
                            "index": 2,
                            "title": "JARVIS",
                            "main": True,
                            "width": 1058,
                            "height": 703,
                        },
                    )
                ),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_candidates_output(
                        {
                            "index": 1,
                            "role": "AXGroup",
                            "subrole": "AXUnknown",
                            "title": "Transition",
                            "width": 1512,
                            "height": 33,
                        },
                        {
                            "index": 2,
                            "title": "JARVIS",
                            "main": True,
                            "width": 1512,
                            "height": 982,
                            "fullscreen": True,
                        },
                    )
                ),
            ],
        ) as run:
            state = MacOSTools().move_window("fullscreen", "Safari")

        self.assertTrue(state["state_confirmed"])
        self.assertTrue(state["fullscreen"])
        self.assertEqual(state["window_index"], 2)
        self.assertIn('AXFullScreen" of window 2 to true', run.call_args_list[1].args[0][2])

    def test_move_window_fullscreen_waits_through_transition_candidates(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1058,
                                "height": 703,
                            },
                        )
                    ),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 1,
                                "role": "AXGroup",
                                "subrole": "AXUnknown",
                                "title": "Transition",
                                "width": 1512,
                                "height": 33,
                            },
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1512,
                                "height": 982,
                                "fullscreen": True,
                            },
                        )
                    ),
                ],
            ):
                state = MacOSTools().move_window("fullscreen", "Safari")

        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["window_index"], 2)
        self.assertEqual(state["fullscreen_transition_observations"], 2)
        self.assertEqual(sleep.call_count, 1)

    def test_move_window_fullscreen_does_not_confirm_without_axfullscreen_state(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=""),
                    *[
                        FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False))
                        for _ in range(8)
                    ],
                ],
            ):
                state = MacOSTools().move_window("fullscreen")

        self.assertTrue(state["command_executed"])
        self.assertFalse(state["state_confirmed"])
        self.assertFalse(state["fullscreen"])
        self.assertEqual(state["fullscreen_transition_observations"], 8)
        self.assertEqual(sleep.call_count, 7)

    def test_move_window_rejects_invalid_position_before_macos_command(self):
        with patch("jarvis.tools.macos.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "Position"):
                MacOSTools().move_window("top", "Safari")

        run.assert_not_called()

    def test_window_action_reports_unconfirmed_state_after_exit_zero(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(x=100, y=100)),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(x=100, y=100)),
            ],
        ):
            state = MacOSTools().move_window("left")

        self.assertTrue(state["command_executed"])
        self.assertFalse(state["state_confirmed"])

    def test_move_window_center_exits_fullscreen_before_resize(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=0,
                            y=33,
                            width=1512,
                            height=123,
                            fullscreen=False,
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=0,
                            y=33,
                            width=1512,
                            height=878,
                            fullscreen=False,
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=0,
                            y=33,
                            width=1512,
                            height=878,
                            fullscreen=False,
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=0,
                            y=33,
                            width=1512,
                            height=878,
                            fullscreen=False,
                        )
                    ),
                    FakeCompletedProcess(stdout=self.visible_frame_output()),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=227,
                            y=121,
                            width=1058,
                            height=702,
                            fullscreen=False,
                        )
                    ),
                ],
            ) as run:
                state = MacOSTools().move_window("center", "Safari")

        self.assertTrue(state["exited_fullscreen"])
        self.assertTrue(state["fullscreen_exit_confirmed"])
        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["fullscreen_transition_observations"], 4)
        self.assertEqual(state["fullscreen_settle_observations"], 2)
        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["window_geometry_stable"])
        self.assertEqual(sleep.call_count, 3)
        self.assertIn('AXFullScreen" of window 1 to false', run.call_args_list[1].args[0][2])
        self.assertIn("set position of target_window", run.call_args_list[7].args[0][2])

    def test_fullscreen_exit_ignores_transition_candidate_until_real_window_is_stable(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1512,
                                "height": 982,
                                "fullscreen": True,
                            },
                        )
                    ),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 1,
                                "role": "AXGroup",
                                "subrole": "AXUnknown",
                                "title": "Transition",
                                "width": 1512,
                                "height": 33,
                            },
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1058,
                                "height": 703,
                                "fullscreen": False,
                            },
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1058,
                                "height": 703,
                                "fullscreen": False,
                            },
                        )
                    ),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "width": 1058,
                                "height": 703,
                                "fullscreen": False,
                            },
                        )
                    ),
                    FakeCompletedProcess(stdout=self.visible_frame_output()),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_candidates_output(
                            {
                                "index": 2,
                                "title": "JARVIS",
                                "main": True,
                                "x": 0,
                                "y": 33,
                                "width": 756,
                                "height": 878,
                            },
                        )
                    ),
                ],
            ) as run:
                state = MacOSTools().move_window("left", "Safari")

        self.assertTrue(state["fullscreen_exit_confirmed"])
        self.assertTrue(state["window_geometry_stable"])
        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["window_index"], 2)
        self.assertEqual(sleep.call_count, 3)
        self.assertIn('AXFullScreen" of window 2 to false', run.call_args_list[1].args[0][2])
        self.assertIn("window 2", run.call_args_list[7].args[0][2])

    def test_move_window_left_exits_fullscreen_before_resize(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_state_output(
                        x=0,
                        y=33,
                        width=756,
                        height=878,
                        fullscreen=False,
                    )
                ),
            ],
        ):
            state = MacOSTools().move_window("left", "Safari")

        self.assertTrue(state["fullscreen_exit_confirmed"])
        self.assertTrue(state["window_geometry_stable"])
        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["state_confirmed"])

    def test_move_window_right_waits_until_fullscreen_exit_ready_before_resize(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.visible_frame_output()),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=756,
                            y=33,
                            width=756,
                            height=878,
                            fullscreen=False,
                        )
                    ),
                ],
            ):
                state = MacOSTools().move_window("right", "Safari")

        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["fullscreen_settle_observations"], 2)
        self.assertEqual(sleep.call_count, 2)

    def test_minimize_window_exits_fullscreen_before_minimizing(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(minimized=True)),
            ],
        ) as run:
            state = MacOSTools().minimize_window("Safari")

        self.assertTrue(state["exited_fullscreen"])
        self.assertTrue(state["fullscreen_exit_confirmed"])
        self.assertTrue(state["window_geometry_stable"])
        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["minimized"])
        self.assertTrue(state["state_confirmed"])
        self.assertIn('AXMinimized', run.call_args_list[5].args[0][2])

    def test_maximize_window_exits_fullscreen_before_maximizing(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=False)),
                    FakeCompletedProcess(stdout=self.visible_frame_output()),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(
                        stdout=self.window_state_output(
                            x=0,
                            y=33,
                            width=1512,
                            height=878,
                            fullscreen=False,
                        )
                    ),
                ],
            ):
                state = MacOSTools().maximize_window("Safari")

        self.assertTrue(state["window_ready_for_action"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["requested_position"], "maximize")
        self.assertEqual(sleep.call_count, 2)

    def test_maximize_window_restores_minimized_window_before_maximizing(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout=self.window_state_output(minimized=True)),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout=self.window_state_output(minimized=False)),
                FakeCompletedProcess(stdout=self.visible_frame_output()),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(
                    stdout=self.window_state_output(
                        x=0,
                        y=33,
                        width=1512,
                        height=878,
                        minimized=False,
                    )
                ),
            ],
        ) as run:
            state = MacOSTools().maximize_window("Safari")

        self.assertTrue(state["restored_minimized"])
        self.assertTrue(state["minimized_restore_confirmed"])
        self.assertTrue(state["state_confirmed"])
        self.assertFalse(state["minimized"])
        self.assertIn('AXMinimized" of window 1 to false', run.call_args_list[1].args[0][2])

    def test_fullscreen_exit_failure_does_not_attempt_resize(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True)),
                    FakeCompletedProcess(stdout=""),
                    *[
                        FakeCompletedProcess(stdout=self.window_state_output(fullscreen=True))
                        for _ in range(8)
                    ],
                ],
            ) as run:
                state = MacOSTools().move_window("left", "Safari")

        self.assertTrue(state["exited_fullscreen"])
        self.assertFalse(state["fullscreen_exit_confirmed"])
        self.assertFalse(state["window_ready_for_action"])
        self.assertFalse(state["command_executed"])
        self.assertFalse(state["state_confirmed"])
        self.assertEqual(sleep.call_count, 7)
        self.assertEqual(run.call_count, 10)
        self.assertFalse(
            any(
                "set position of target_window" in call.args[0][2]
                for call in run.call_args_list
            )
        )

    def test_process_present_without_window_reports_no_window(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Aucune fenetre manipulable.",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Aucune fenetre"):
                MacOSTools().move_window("right", "Codex")

    def test_get_media_state_reads_music_metadata_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
        ) as run:
            state = MacOSTools().get_media_state("Music")

        self.assertEqual(
            state,
            {
                "media_available": True,
                "playing": True,
                "title": "Song",
                "artist": "Artist",
                "app": "Music",
            },
        )
        args = run.call_args.args[0]
        self.assertEqual(args[0:2], ["osascript", "-e"])
        self.assertIn('tell application "Music"', args[2])
        self.assertIn("player state as text", args[2])

    def test_get_media_state_returns_no_media_when_no_supported_app_is_running(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            state = MacOSTools().get_media_state()

        self.assertEqual(
            state,
            {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            },
        )

    def test_play_pause_uses_active_supported_media_app_and_confirms_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="paused\nSong\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().play_pause()

        self.assertTrue(state["playing"])
        self.assertEqual(state["title"], "Song")
        self.assertEqual(state["app"], "Music")
        self.assertIn('application "Music" is running', run.call_args_list[0].args[0][2])
        self.assertIn('tell application "Music"', run.call_args_list[2].args[0][2])
        self.assertIn("playpause", run.call_args_list[2].args[0][2])

    def test_next_track_uses_active_supported_media_app(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nNew Song\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().next_track()

        self.assertEqual(state["title"], "New Song")
        self.assertTrue(state["command_executed"])
        self.assertTrue(state["media_observed"])
        self.assertEqual(state["previous_title"], "Old Song")
        self.assertEqual(state["previous_artist"], "Artist")
        self.assertTrue(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 1)
        self.assertEqual(state["command_attempts"], 1)
        self.assertIn("next track", run.call_args_list[2].args[0][2])

    def test_next_track_reports_no_observed_track_change_without_retry(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().next_track()

        self.assertEqual(state["title"], "Same Song")
        self.assertEqual(state["previous_title"], "Same Song")
        self.assertFalse(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 3)
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(run.call_count, 6)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            sum(
                "next track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_next_track_observes_delayed_metadata_change_with_bounded_check(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nNew Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().next_track()

        self.assertTrue(state["track_changed"])
        self.assertEqual(state["title"], "New Song")
        self.assertEqual(state["previous_title"], "Old Song")
        self.assertEqual(state["observation_attempts"], 2)
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(
            sum(
                "next track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_previous_track_uses_active_supported_media_app(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nPrevious Song\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().previous_track()

        self.assertEqual(state["title"], "Previous Song")
        self.assertTrue(state["track_changed"])
        self.assertEqual(state["command_attempts"], 1)
        self.assertIn("previous track", run.call_args_list[2].args[0][2])

    def test_previous_track_sends_second_command_when_first_does_not_change_track(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nPrevious Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertTrue(state["track_changed"])
        self.assertEqual(state["title"], "Previous Song")
        self.assertEqual(state["previous_title"], "Current Song")
        self.assertEqual(state["command_attempts"], 2)
        self.assertEqual(state["observation_attempts"], 1)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            2,
        )

    def test_previous_track_sends_at_most_two_commands_when_track_stays_same(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertFalse(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 3)
        self.assertEqual(state["command_attempts"], 2)
        self.assertEqual(sleep.call_count, 4)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            2,
        )

    def test_previous_track_does_not_send_second_command_when_media_disappears(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="\n\n\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertFalse(state["media_observed"])
        self.assertFalse(state["track_changed"])
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(sleep.call_count, 0)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_previous_track_does_not_send_second_command_after_system_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                FakeCompletedProcess(returncode=1, stderr="previous failed"),
            ],
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "previous failed"):
                MacOSTools().previous_track()

        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_media_action_raises_when_no_supported_app_is_active(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Aucune application media"):
                MacOSTools().next_track()

    def test_media_action_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
                FakeCompletedProcess(returncode=1, stderr="media command failed"),
            ],
        ):
            with self.assertRaisesRegex(RuntimeError, "media command failed"):
                MacOSTools().play_pause()


if __name__ == "__main__":
    unittest.main()
