"""MacOSTools keeps its full API after being split into mixins."""
import inspect

from jarvis.tools import macos
from jarvis.tools.macos import MacOSTools

# Members of MacOSTools before the split, with their kind.
MEMBERS = (
    "_active_media_app", "_active_media_context", "_escape_applescript",
    "_get_core_graphics_framework", "_get_display_brightness",
    "_get_display_services_framework", "_main_display_id",
    "_main_screen_usable_frame", "_media_state_after_command",
    "_observe_window_ready_for_action", "_observe_window_state_until",
    "_observe_window_transition", "_parse_applescript_bool",
    "_parse_legacy_window_state", "_parse_pmset_battery",
    "_parse_window_candidates", "_prepare_window_for_geometry_action",
    "_read_lock_screen_state", "_read_window_candidates",
    "_read_window_state", "_run_osa_javascript", "_run_osascript",
    "_select_window_candidate", "_set_display_brightness",
    "_set_window_fullscreen", "_set_window_minimized", "_set_window_rect",
    "_target_window_rect", "_validate_window_app_name",
    "_validate_window_position", "_window_action_state",
    "_window_candidate_consistent", "_window_candidate_manipulable",
    "_window_geometry_complete", "_window_geometry_stable",
    "_window_rect_matches", "close_app", "focus_window",
    "get_active_window", "get_battery_status", "get_brightness", "get_date",
    "get_media_state", "get_system_info", "get_volume", "is_app_running",
    "lock_screen", "maximize_window", "minimize_window", "move_window",
    "mute", "next_track", "open_app", "open_url", "play_pause",
    "previous_track", "set_brightness", "set_volume", "unmute",
    "web_search",
)
STATIC = {'_escape_applescript', '_get_core_graphics_framework', '_get_display_services_framework', '_parse_applescript_bool', '_parse_legacy_window_state', '_parse_pmset_battery', '_parse_window_candidates', '_read_lock_screen_state', '_run_osa_javascript', '_run_osascript', '_validate_window_app_name', '_validate_window_position', '_window_action_state', '_window_candidate_consistent', '_window_candidate_manipulable', '_window_geometry_complete', '_window_geometry_stable', '_window_rect_matches'}
CLASS = {'_select_window_candidate'}


def test_every_member_is_still_there_with_its_kind():
    for name in MEMBERS:
        member = inspect.getattr_static(MacOSTools, name)
        if name in STATIC:
            assert isinstance(member, staticmethod), name
        elif name in CLASS:
            assert isinstance(member, classmethod), name
        else:
            assert inspect.isfunction(member), name


def test_no_member_is_defined_twice_across_mixins():
    seen = {}
    for klass in MacOSTools.__mro__[1:-1]:
        for name in vars(klass):
            if not name.startswith("__"):
                assert name not in seen, (name, klass, seen.get(name))
                seen[name] = klass


def test_constants_are_still_exported_from_macos():
    assert macos.WINDOW_RECORD_SEPARATOR == "__JARVIS_WINDOW__"
    assert macos.SUPPORTED_MEDIA_APPS == ("Music", "Spotify")
