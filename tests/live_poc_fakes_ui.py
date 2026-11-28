"""Recording fakes of UI accessibility, interaction, browser, screenshot, vision and messaging."""
from jarvis.capabilities.results import ToolResult


class RecordingLiveUIAccessibilityCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append(("inspect_ui", max_depth, max_elements))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="inspect_ui",
            message="1 element Accessibility exploitable a ete trouve.",
            elements=[{"role": "AXButton", "title": "Continuer"}],
            count=1,
            truncated=False,
            max_depth=max_depth,
            max_elements=max_elements,
        )

    def find_ui_elements(self, query, role=None):
        self.calls.append(("find_ui_elements", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="find_ui_elements",
            message="Un element Accessibility correspond a cette recherche.",
            query_length=len(query),
            role=role,
            candidates=[{"role": role or "AXButton", "title": "Continuer"}],
            candidate_count=1,
            truncated=False,
        )

    def focus_ui_element(self, query, role=None):
        self.calls.append(("focus_ui_element", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="focus_ui_element",
            message="Le focus Accessibility a ete confirme.",
            command_executed=True,
            state_confirmed=True,
            candidate={"role": role or "AXTextField"},
            element={"role": role or "AXTextField", "focused": True},
        )

    def activate_ui_element(self, query, role=None):
        self.calls.append(("activate_ui_element", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="activate_ui_element",
            message="La commande Accessibility a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            candidate={"role": role or "AXButton"},
            element={"role": role or "AXButton"},
        )


class RecordingLiveInteractionCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def select_all_and_copy(self):
        self.calls.append(("select_all_and_copy",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="select_all_and_copy",
            message="Les commandes ont ete envoyees dans l'ordre.",
            command_executed=True,
            state_confirmed=False,
            steps=[
                {"name": "hotkey_command_a", "ok": True},
                {"name": "hotkey_command_c", "ok": True},
            ],
        )

    def focus_app_ui_and_type(
        self,
        app_name,
        text,
        query=None,
        role=None,
        press_enter=False,
    ):
        self.calls.append((
            "focus_app_ui_and_type",
            app_name,
            text,
            query,
            role,
            press_enter,
        ))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="focus_app_ui_and_type",
            message="La cible a ete verifiee et la saisie envoyee.",
            command_executed=True,
            state_confirmed=False,
            target_app=app_name,
            query_length=len(query) if isinstance(query, str) else None,
            text_length=len(text) if isinstance(text, str) else None,
            role=role,
            press_enter=press_enter,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "focus_window", "ok": True, "state_confirmed": True},
                {"name": "type_text", "ok": True, "command_executed": True},
            ],
        )

    def select_all_and_delete(self):
        self.calls.append(("select_all_and_delete",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="select_all_and_delete",
            message="La cible a ete verifiee et la suppression a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            deletion_executed=True,
            steps=[
                {"name": "inspect_editable_target", "ok": True},
                {"name": "hotkey_command_a", "ok": True},
                {"name": "delete_selection", "ok": True},
            ],
        )

    def open_app_and_type(self, app_name, text, press_enter=True):
        self.calls.append(("open_app_and_type", app_name, text, press_enter))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="open_app_and_type",
            message="Saisie directe envoyee.",
            command_executed=True,
            state_confirmed=False,
            target_app=app_name,
            text_length=len(text) if isinstance(text, str) else None,
            press_enter=press_enter,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "type_text", "ok": True, "command_executed": True},
            ],
        )

    def open_app_and_focus_ui(self, app_name, query, role=None):
        self.calls.append(("open_app_and_focus_ui", app_name, query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="open_app_and_focus_ui",
            message="La cible Accessibility a ete focalisee.",
            command_executed=True,
            state_confirmed=True,
            target_app=app_name,
            query_length=len(query),
            role=role,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "focus_window", "ok": True, "state_confirmed": True},
                {"name": "focus_ui_element", "ok": True, "state_confirmed": True},
            ],
        )


class RecordingLiveBrowserCapability:
    def __init__(self):
        self.calls = []

    def open_url(self, url, browser=None, new_tab=True):
        self.calls.append(("open_url", url, browser, new_tab))
        return ToolResult.success(
            action="open_url",
            message="La page est affichee.",
            browser=browser or "Safari",
            requested_url=url,
            active_url="https://example.com/",
            active_title="Example",
            new_tab=new_tab,
            command_executed=True,
            state_confirmed=True,
        )

    def search_web(self, query, browser=None, engine=None):
        self.calls.append(("search_web", query, browser, engine))
        return ToolResult.success(
            action="search_web",
            message="Recherche lancee.",
            browser=browser or "Safari",
            active_url="https://www.google.com/search?q=x",
            query_length=len(query) if isinstance(query, str) else None,
            engine=engine or "google",
            command_executed=True,
            state_confirmed=True,
        )

    def get_active_tab(self, browser=None):
        self.calls.append(("get_active_tab", browser))
        return ToolResult.success(
            action="get_active_tab",
            message="Onglet lu.",
            browser=browser or "Safari",
            has_window=True,
            url="https://example.com/",
            title="Example",
        )

    def list_tabs(self, browser=None):
        self.calls.append(("list_tabs", browser))
        return ToolResult.success(
            action="list_tabs",
            message="2 onglets.",
            browser=browser or "Safari",
            active_index=1,
            tabs=[],
            count=2,
        )

    def activate_tab(self, query=None, index=None, browser=None):
        self.calls.append(("activate_tab", query, index, browser))
        return ToolResult.success(
            action="activate_tab",
            message="Onglet active.",
            browser=browser or "Safari",
            query_length=len(query) if isinstance(query, str) else None,
            active_index=index,
            command_executed=True,
            state_confirmed=True,
        )


class RecordingLiveScreenshotCapability:
    def __init__(self):
        self.calls = []

    def capture_screen(self, path=None, display=None):
        self.calls.append(("capture_screen", path, display))
        return ToolResult.success(
            action="capture_screen",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/jarvis-screenshot-x.png",
            bytes=4096,
            width=1440,
            height=900,
            command_executed=True,
            state_confirmed=True,
        )

    def capture_region(self, x, y, width, height, path=None):
        self.calls.append(("capture_region", x, y, width, height, path))
        return ToolResult.success(
            action="capture_region",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/region.png",
            bytes=1024,
            width=width,
            height=height,
            region={"x": x, "y": y, "width": width, "height": height},
            command_executed=True,
            state_confirmed=True,
        )

    def capture_window(self, app_name=None, path=None):
        self.calls.append(("capture_window", app_name, path))
        return ToolResult.success(
            action="capture_window",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/window.png",
            bytes=2048,
            target_app=app_name or "Safari",
            command_executed=True,
            state_confirmed=True,
        )


class RecordingLiveVisionCapability:
    def __init__(self, analysis="Une page web est affichee.", question_length=None):
        self.analysis = analysis
        self.question_length = question_length
        self.calls = []

    def describe_screen(self, target="window", app_name=None):
        self.calls.append(("describe_screen", target, app_name))
        return ToolResult.success(
            action="describe_screen",
            message=self.analysis,
            analysis=self.analysis,
            source=target,
            model="gemini-2.5-flash",
            image_path="/Users/someone/Pictures/Jarvis/shot.png",
            image_bytes=1234,
            image_width=3024,
            image_height=1964,
            duration_ms=42,
        )

    def ask_about_screen(self, question, target="window", app_name=None):
        self.calls.append(("ask_about_screen", question, target, app_name))
        return ToolResult.success(
            action="ask_about_screen",
            message=self.analysis,
            analysis=self.analysis,
            source=target,
            model="gemini-2.5-flash",
            question_length=len(question) if isinstance(question, str) else None,
            image_path="/Users/someone/Pictures/Jarvis/shot.png",
            image_bytes=1234,
            duration_ms=42,
        )


class RecordingLiveMessagingCapability:
    def __init__(self, verified=True, composer="ChatBar_ComposerTextView"):
        self.verified = verified
        self.composer = composer
        self.calls = []

    def composer_query(self, app_name):
        if isinstance(app_name, str) and app_name.strip().casefold() == "whatsapp":
            return self.composer
        return None

    def supports_composer_send(self, app_name):
        return bool(self.composer_query(app_name))

    def is_api_app(self, app_name):
        return isinstance(app_name, str) and app_name.strip().casefold() == "telegram"

    def supports_verified_send(self, app_name):
        return self.is_api_app(app_name) or self.supports_composer_send(app_name)

    def requires_recipient(self, app_name):
        return self.is_api_app(app_name)

    def send_text(self, app_name, text, recipient=None):
        self.calls.append(("send_text", app_name, text))
        self.last_send_recipient = recipient
        return ToolResult.success(
            action="send_text",
            message="Message envoye.",
            command_executed=True,
            state_confirmed=True,
            app=app_name,
            text_length=len(text),
        )

    def ensure_recipient(self, app_name, expected_recipient):
        self.calls.append(("ensure_recipient", app_name, expected_recipient))
        if self.verified:
            return ToolResult.success(
                action="verify_recipient",
                message="Destinataire verifie.",
                recipient_verified=True,
                target_app=app_name,
                recipient_length=len(expected_recipient),
            )
        return ToolResult(
            ok=False,
            action="verify_recipient",
            message="La conversation ouverte ne correspond pas.",
            data={"recipient_verified": False, "reason": "recipient_not_visible"},
            error_code="recipient_not_verified",
        )
