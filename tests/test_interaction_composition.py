"""InteractionCapability keeps its full API after being split into mixins."""
import inspect

from jarvis.capabilities.interaction import InteractionCapability

METHODS = (
    "__init__", "_candidate_label", "_clipboard_changed", "_clipboard_step",
    "_failure", "_focus_window_with_readiness",
    "_observe_clipboard_after_copy", "_open_focus_and_verify_app",
    "_recover_ui_focus", "_recovery_candidates",
    "_require_command_executed", "_require_confirmed", "_require_ok",
    "_safe_len", "_same_app", "_step", "_verify_focused_editable_target",
    "focus_app_ui_and_type", "open_app_and_focus_ui", "open_app_and_type",
    "select_all_and_copy", "select_all_and_delete",
)
STATIC = {'_clipboard_changed', '_safe_len', '_step', '_same_app', '_failure', '_clipboard_step', '_candidate_label'}
ATTRIBUTES = ('DEFAULT_CLIPBOARD_READ_ATTEMPTS', 'DEFAULT_CLIPBOARD_READ_DELAY_SECONDS', 'DEFAULT_READINESS_ATTEMPTS', 'DEFAULT_READINESS_DELAY_SECONDS', 'READINESS_RETRYABLE_ERRORS', 'RECOVERY_TEXT_ROLES', 'SEARCH_TOKENS')


def test_every_method_is_still_there_with_its_kind():
    for name in METHODS:
        member = inspect.getattr_static(InteractionCapability, name)
        if name in STATIC:
            assert isinstance(member, staticmethod), name
        else:
            assert inspect.isfunction(member), name


def test_tuning_attributes_stay_on_the_capability():
    for name in ATTRIBUTES:
        assert name in vars(InteractionCapability), name


def test_no_member_is_defined_twice_across_mixins():
    seen = {}
    for klass in InteractionCapability.__mro__[:-1]:
        for name in vars(klass):
            if not name.startswith("__"):
                assert name not in seen, (name, klass, seen.get(name))
                seen[name] = klass
