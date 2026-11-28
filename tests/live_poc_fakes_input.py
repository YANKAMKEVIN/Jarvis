"""Recording fakes of filesystem, clipboard, keyboard and mouse for the Live POC tests."""
from jarvis.capabilities.results import ToolResult


class RecordingLiveFileSystemTools:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def list_files(self, path=None):
        self.calls.append(("list_files", path))
        self._raise_if_needed()
        return {
            "path": "/Users/test",
            "results": [],
            "result_count": 0,
            "truncated": False,
        }

    def find_files(self, query, path=None):
        self.calls.append(("find_files", query, path))
        self._raise_if_needed()
        return {
            "query": query,
            "path": "/Users/test",
            "results": [{"path": "/Users/test/report.pdf", "name": "report.pdf"}],
            "result_count": 1,
            "truncated": False,
        }

    def get_file_info(self, path):
        self.calls.append(("get_file_info", path))
        self._raise_if_needed()
        return {
            "path": path,
            "name": "report.pdf",
            "kind": "file",
            "size_bytes": 42,
            "modified_at": "2026-09-23T12:00:00",
            "is_hidden": False,
            "is_symlink": False,
        }

    def open_file(self, path):
        self.calls.append(("open_file", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def open_folder(self, path):
        self.calls.append(("open_folder", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def create_folder(self, path):
        self.calls.append(("create_folder", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": True,
        }

    def rename_file(self, path, new_name):
        self.calls.append(("rename_file", path, new_name))
        self._raise_if_needed()
        return {
            "previous_path": path,
            "path": f"/Users/test/{new_name}",
            "destination": f"/Users/test/{new_name}",
            "command_executed": True,
            "state_confirmed": True,
        }

    def move_file(self, source, destination):
        self.calls.append(("move_file", source, destination))
        self._raise_if_needed()
        return {
            "previous_path": source,
            "path": destination,
            "destination": destination,
            "command_executed": True,
            "state_confirmed": True,
        }


class RecordingLiveClipboardTools:
    def __init__(self, error=None, text_state=None, set_state=None, clear_state=None):
        self.error = error
        self.text_state = text_state or {
            "has_text": True,
            "text": "Bonjour",
            "length": 7,
            "returned_length": 7,
            "truncated": False,
            "content_type": "text",
        }
        self.set_state = set_state or {
            "command_executed": True,
            "state_confirmed": True,
            "length": 7,
            "has_text": True,
            "content_type": "text",
        }
        self.clear_state = clear_state or {
            "command_executed": True,
            "state_confirmed": True,
            "length": 0,
            "has_text": False,
            "content_type": "no_text_detected",
        }
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def get_text(self):
        self.calls.append(("get_text",))
        self._raise_if_needed()
        return dict(self.text_state)

    def set_text(self, text):
        self.calls.append(("set_text", text))
        self._raise_if_needed()
        return dict(self.set_state)

    def clear(self):
        self.calls.append(("clear",))
        self._raise_if_needed()
        return dict(self.clear_state)


class RecordingLiveKeyboardCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def type_text(self, text):
        self.calls.append(("type_text", text))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="type_text",
            message=(
                "La commande de saisie a ete envoyee, mais Jarvis ne peut "
                "pas confirmer que le texte a ete applique."
            ),
            command_executed=True,
            state_confirmed=False,
            length=len(text),
            target_app="Safari",
            target_window="Example",
        )

    def press_key(self, key):
        self.calls.append(("press_key", key))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="press_key",
            message="La touche a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            key=key,
            target_app="Safari",
            target_window="Example",
        )

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="hotkey",
            message="Le raccourci clavier a ete envoye.",
            command_executed=True,
            state_confirmed=False,
            keys=list(keys),
            target_app="Safari",
            target_window="Example",
        )


class RecordingLiveMouseCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def get_mouse_position(self):
        self.calls.append(("get_mouse_position",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="get_mouse_position",
            message="La souris est en position x=10, y=20.",
            x=10,
            y=20,
            screen_index=0,
        )

    def move_mouse(self, x, y):
        self.calls.append(("move_mouse", x, y))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="move_mouse",
            message="Le pointeur a ete deplace.",
            command_executed=True,
            state_confirmed=True,
            previous_x=1,
            previous_y=2,
            target_x=x,
            target_y=y,
            x=x,
            y=y,
            screen_index=0,
        )

    def click(self):
        self.calls.append(("click",))
        return self._click_result("click", "left", 1)

    def double_click(self):
        self.calls.append(("double_click",))
        return self._click_result("double_click", "left", 2)

    def right_click(self):
        self.calls.append(("right_click",))
        return self._click_result("right_click", "right", 1)

    def scroll(self, direction, amount=3):
        self.calls.append(("scroll", direction, amount))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="scroll",
            message="La commande de scroll a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            direction=direction,
            amount=amount,
            x=10,
            y=20,
            screen_index=0,
        )

    def _click_result(self, action, button, click_count):
        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action=action,
            message="La commande de clic a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            button=button,
            click_count=click_count,
            x=10,
            y=20,
            screen_index=0,
        )
