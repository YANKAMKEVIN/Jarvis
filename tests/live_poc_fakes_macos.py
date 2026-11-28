"""Recording fake of MacOSTools for the Live POC tests."""


class RecordingLiveMacOSTools:
    def __init__(
        self,
        error=None,
        volume=40,
        get_error=None,
        app_running=True,
        open_error=None,
        close_error=None,
        running_error=None,
        media_state=None,
        media_error=None,
        battery=None,
        system_info=None,
        brightness=50,
        system_error=None,
        lock_state=None,
        window_state=None,
        window_error=None,
    ):
        self.error = error
        self.volume = volume
        self.get_error = get_error
        self.app_running = app_running
        self.open_error = open_error
        self.close_error = close_error
        self.running_error = running_error
        self.media_state = media_state or {
            "media_available": True,
            "playing": True,
            "title": "Song",
            "artist": "Artist",
            "app": "Music",
        }
        self.media_error = media_error
        self.battery = battery or {
            "percentage": 74,
            "charging": True,
            "charged": False,
            "external_power": True,
            "raw": "test battery",
        }
        self.system_info = system_info or {
            "model_name": "MacBook Pro",
            "model_identifier": "Mac15,3",
            "chip": "Apple M3",
            "memory": "8 GB",
            "serial_number": "TEST123",
        }
        self.brightness = brightness
        self.system_error = system_error
        self.lock_state = lock_state or {
            "command_executed": True,
            "state_confirmed": False,
            "locked": None,
            "backend": "test_backend",
        }
        self.window_state = window_state or {
            "target_app": "Safari",
            "frontmost": True,
            "window_title": "Example",
            "position": {"x": 0, "y": 25},
            "size": {"width": 800, "height": 600},
            "minimized": False,
            "fullscreen": False,
            "command_executed": True,
            "state_confirmed": True,
            "previous_position": {"x": 100, "y": 100},
            "previous_size": {"width": 600, "height": 400},
        }
        self.window_error = window_error
        self.calls = []
        self.get_calls = 0
        self.open_calls = []
        self.close_calls = []
        self.running_calls = []
        self.play_calls = 0
        self.next_calls = 0
        self.previous_calls = 0
        self.media_state_calls = 0
        self.battery_calls = 0
        self.system_info_calls = 0
        self.get_brightness_calls = 0
        self.set_brightness_calls = []
        self.lock_calls = 0
        self.active_window_calls = 0
        self.focus_window_calls = []
        self.minimize_window_calls = []
        self.maximize_window_calls = []
        self.move_window_calls = []

    def set_volume(self, level):
        self.calls.append(level)

        if self.error is not None:
            raise self.error

        return f"Volume regle a {level} %."

    def get_volume(self):
        self.get_calls += 1

        if self.get_error is not None:
            raise self.get_error

        return self.volume

    def open_app(self, app_name):
        self.open_calls.append(app_name)

        if self.open_error is not None:
            raise self.open_error

        return f"{app_name} a ete ouvert."

    def close_app(self, app_name):
        self.close_calls.append(app_name)

        if self.close_error is not None:
            raise self.close_error

        return f"{app_name} a ete ferme."

    def is_app_running(self, app_name):
        self.running_calls.append(app_name)

        if self.running_error is not None:
            raise self.running_error

        return self.app_running

    def play_pause(self):
        self.play_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def next_track(self):
        self.next_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def previous_track(self):
        self.previous_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def get_media_state(self):
        self.media_state_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def get_battery_status(self):
        self.battery_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.battery)

    def get_system_info(self):
        self.system_info_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.system_info)

    def get_brightness(self):
        self.get_brightness_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return self.brightness

    def set_brightness(self, level):
        self.set_brightness_calls.append(level)

        if self.system_error is not None:
            raise self.system_error

        return {
            "requested_brightness": level,
            "brightness": level,
        }

    def lock_screen(self):
        self.lock_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.lock_state)

    def get_active_window(self):
        self.active_window_calls += 1

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def focus_window(self, app_name):
        self.focus_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def minimize_window(self, app_name=None):
        self.minimize_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def maximize_window(self, app_name=None):
        self.maximize_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def move_window(self, position, app_name=None):
        self.move_window_calls.append((position, app_name))

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)
