import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.telegram import TelegramMessaging
from jarvis.schedule.runner import deliver_due
from jarvis.schedule.store import ScheduledMessageStore
from jarvis.tools.telegram_api import SELF_PEER, TelegramApiError, TelethonBackend


def dialog(id_, name, username=None, kind="user", is_self=False):
    return {"id": id_, "name": name, "username": username, "kind": kind, "is_self": is_self}


DIALOGS = [
    dialog(1, "Joel Chinda", "joelc"),
    dialog(2, "Alice Martin"),
    dialog(3, "Alice Dupont"),
    dialog(4, "Famille", kind="group"),
    dialog(5, "Infos Joel", kind="channel"),
    dialog(6, "Kevin Yankam", "kevin_y", is_self=True),
]


class FakeBackend:
    def __init__(self, dialogs=None, dialogs_error=None, send_error=None, message_id=42):
        self.dialogs = list(DIALOGS if dialogs is None else dialogs)
        self.dialogs_error = dialogs_error
        self.send_error = send_error
        self.message_id = message_id
        self.sent = []

    def list_dialogs(self, limit=300):
        if self.dialogs_error:
            raise self.dialogs_error
        return list(self.dialogs)

    def send_message(self, peer, text):
        if self.send_error:
            raise self.send_error
        self.sent.append((peer, text))
        return self.message_id


class TelegramResolveTest(unittest.TestCase):
    def resolve(self, name, backend=None):
        return TelegramMessaging(backend=backend or FakeBackend()).resolve(name)

    def test_exact_full_name_verifies(self):
        result = self.resolve("joel chinda")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["recipient_verified"])
        self.assertEqual(result.data["target_app"], "Telegram")

    def test_leading_first_name_verifies_when_unique(self):
        self.assertTrue(self.resolve("Joël").ok)

    def test_ambiguous_first_name_refuses(self):
        result = self.resolve("Alice")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "recipient_not_verified")
        self.assertEqual(result.data["reason"], "recipient_ambiguous")
        self.assertEqual(result.data["match_count"], 2)

    def test_full_name_disambiguates(self):
        self.assertTrue(self.resolve("Alice Martin").ok)

    def test_unknown_name_refuses(self):
        result = self.resolve("Bob")

        self.assertFalse(result.ok)
        self.assertEqual(result.data["reason"], "recipient_not_found")

    def test_substring_inside_a_name_never_matches(self):
        # "Chinda" is not a leading word: no fuzzy matching.
        self.assertFalse(self.resolve("Chinda").ok)

    def test_broadcast_channel_is_never_a_target(self):
        # "Infos Joel" is a channel; posting there would be public.
        self.assertFalse(self.resolve("Infos Joel").ok)

    def test_group_is_a_valid_target(self):
        self.assertTrue(self.resolve("Famille").ok)

    def test_username_matches_only_known_chats(self):
        self.assertTrue(self.resolve("@JoelC").ok)
        self.assertFalse(self.resolve("@inconnu").ok)

    def test_saved_messages_aliases_need_no_lookup(self):
        backend = FakeBackend(dialogs_error=AssertionError("no lookup expected"))
        for name in ("Messages enregistrés", "Saved Messages", "moi"):
            self.assertTrue(self.resolve(name, backend).ok, name)

    def test_short_recipient_refuses(self):
        self.assertEqual(self.resolve("K").error_code, "invalid_recipient")
        self.assertEqual(self.resolve("@k").error_code, "invalid_recipient")

    def test_not_configured_refuses(self):
        backend = FakeBackend(dialogs_error=TelegramApiError("pas configure", "telegram_not_configured"))

        result = self.resolve("Joel", backend)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "telegram_not_configured")

    def test_verification_never_exposes_the_peer_id(self):
        backend = FakeBackend(dialogs=[dialog(987654, "Joel Chinda")])
        payload = self.resolve("Joel", backend).to_livekit_dict()

        self.assertNotIn(987654, payload.values())
        self.assertNotIn("Joel Chinda", str(payload))


class TelegramSendTest(unittest.TestCase):
    def test_send_is_confirmed_by_message_id(self):
        backend = FakeBackend()

        result = TelegramMessaging(backend=backend).send("Joel", "Salut")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(result.data["message_id"], 42)
        self.assertEqual(backend.sent, [(1, "Salut")])

    def test_self_chat_sends_to_me(self):
        backend = FakeBackend()

        TelegramMessaging(backend=backend).send("Messages enregistrés", "test")
        TelegramMessaging(backend=backend).send("Kevin Yankam", "test")

        self.assertEqual([peer for peer, _ in backend.sent], [SELF_PEER, SELF_PEER])

    def test_send_re_resolves_and_refuses_if_now_ambiguous(self):
        backend = FakeBackend()
        messaging = TelegramMessaging(backend=backend)
        self.assertTrue(messaging.resolve("Joel").ok)

        backend.dialogs.append(dialog(7, "Joel Martin"))
        result = messaging.send("Joel", "Salut")

        self.assertFalse(result.ok)
        self.assertEqual(result.data["reason"], "recipient_ambiguous")
        self.assertEqual(backend.sent, [])

    def test_empty_text_sends_nothing(self):
        backend = FakeBackend()

        result = TelegramMessaging(backend=backend).send("Joel", "  ")

        self.assertEqual(result.error_code, "invalid_text")
        self.assertEqual(backend.sent, [])

    def test_failure_after_request_is_reported_uncertain(self):
        backend = FakeBackend(send_error=TelegramApiError("timeout", "telegram_send_failed", may_have_sent=True))

        result = TelegramMessaging(backend=backend).send("Joel", "Salut")

        self.assertFalse(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])

    def test_failure_before_request_is_a_clean_refusal(self):
        backend = FakeBackend(send_error=TelegramApiError("pas connecte", "telegram_not_authorized"))

        result = TelegramMessaging(backend=backend).send("Joel", "Salut")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "telegram_not_authorized")
        self.assertNotIn("command_executed", result.data)


class FakeUI:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"UI must not be used for Telegram ({name})")
        return record


class MessagingRoutingTest(unittest.TestCase):
    def make(self, backend=None):
        self.ui = FakeUI()
        self.backend = backend or FakeBackend()
        return MessagingCapability(
            windows=FakeUI(), ui_accessibility=self.ui, apps=FakeUI(), keyboard=FakeUI(),
            sleeper=lambda _s: None, telegram=TelegramMessaging(backend=self.backend),
        )

    def test_telegram_is_an_api_app(self):
        messaging = self.make()

        self.assertTrue(messaging.is_api_app("Telegram"))
        self.assertTrue(messaging.supports_verified_send("telegram"))
        self.assertTrue(messaging.requires_recipient("Telegram"))
        self.assertFalse(messaging.requires_unlocked_screen("Telegram"))
        self.assertFalse(messaging.is_api_app("WhatsApp"))
        self.assertTrue(messaging.requires_unlocked_screen("WhatsApp"))

    def test_verify_and_ensure_use_the_api_never_the_screen(self):
        messaging = self.make()

        self.assertTrue(messaging.verify_recipient("Telegram", "Joel").ok)
        self.assertTrue(messaging.ensure_recipient("Telegram", "Joel").ok)
        self.assertFalse(messaging.ensure_recipient("Telegram", "Alice").ok)
        self.assertEqual(self.ui.calls, [])

    def test_send_text_requires_a_recipient(self):
        messaging = self.make()

        result = messaging.send_text("Telegram", "Salut")

        self.assertEqual(result.error_code, "invalid_recipient")
        self.assertEqual(self.backend.sent, [])

    def test_send_text_routes_to_the_api(self):
        messaging = self.make()

        result = messaging.send_text("Telegram", "Salut", recipient="Joel Chinda")

        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(self.backend.sent, [(1, "Salut")])
        self.assertEqual(self.ui.calls, [])


class ScheduledTelegramTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ScheduledMessageStore(Path(self.tmp.name) / "schedule.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def messaging(self, backend):
        return MessagingCapability(
            windows=FakeUI(), ui_accessibility=FakeUI(), apps=FakeUI(), keyboard=FakeUI(),
            sleeper=lambda _s: None, telegram=TelegramMessaging(backend=backend),
        )

    def test_delivers_with_screen_locked_and_confirms(self):
        backend = FakeBackend()
        self.store.add("Telegram", "Joel Chinda", "Bonjour", 100, "none")

        result = deliver_due(self.store, self.messaging(backend), screen_unlocked=lambda: False, now=110)

        self.assertEqual(len(result["sent"]), 1)
        self.assertEqual(backend.sent, [(1, "Bonjour")])

    def test_ambiguous_recipient_is_deferred_never_sent(self):
        backend = FakeBackend()
        self.store.add("Telegram", "Alice", "Bonjour", 100, "none")

        result = deliver_due(self.store, self.messaging(backend), screen_unlocked=lambda: True, now=110)

        self.assertEqual(result["sent"], [])
        self.assertEqual(backend.sent, [])

    def test_whatsapp_still_waits_for_an_unlocked_screen(self):
        self.store.add("WhatsApp", "Joel", "Bonjour", 100, "none")

        result = deliver_due(self.store, self.messaging(FakeBackend()), screen_unlocked=lambda: False, now=110)

        self.assertEqual(result["sent"], [])
        self.assertEqual(len(result["deferred"]), 1)


class FakeDialog:
    def __init__(self, id_, name, entity, is_user=True, is_group=False):
        self.id, self.name, self.entity = id_, name, entity
        self.is_user, self.is_group = is_user, is_group


class FakeTelethonClient:
    def __init__(self, authorized=True, dialogs=()):
        self.authorized = authorized
        self.dialogs = list(dialogs)
        self.sent = []

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def is_user_authorized(self):
        return self.authorized

    async def iter_dialogs(self, limit=None):
        for item in self.dialogs[:limit]:
            yield item

    async def send_message(self, peer, text):
        self.sent.append((peer, text))
        return SimpleNamespace(id=99)


class TelethonBackendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Path(self.tmp.name) / "jarvis.session"

    def tearDown(self):
        self.tmp.cleanup()

    def backend(self, client):
        self.session.write_bytes(b"")
        backend = TelethonBackend(
            api_id=1, api_hash="h", session_path=self.session,
            client_factory=lambda *args: client,
        )
        self.addCleanup(backend.close)
        return backend

    def test_lists_dialogs_with_kinds(self):
        me = SimpleNamespace(username="kevin", bot=False, is_self=True)
        bot = SimpleNamespace(username="robot", bot=True, is_self=False)
        group = SimpleNamespace(username=None)
        client = FakeTelethonClient(dialogs=[
            FakeDialog(6, "Kevin", me),
            FakeDialog(8, "Robot", bot),
            FakeDialog(4, "Famille", group, is_user=False, is_group=True),
            FakeDialog(5, "Infos", group, is_user=False),
        ])

        dialogs = self.backend(client).list_dialogs()

        self.assertEqual([d["kind"] for d in dialogs], ["user", "bot", "group", "channel"])
        self.assertTrue(dialogs[0]["is_self"])

    def test_send_returns_message_id(self):
        client = FakeTelethonClient()

        self.assertEqual(self.backend(client).send_message(SELF_PEER, "hi"), 99)
        self.assertEqual(client.sent, [(SELF_PEER, "hi")])

    def test_unauthorized_session_is_refused(self):
        backend = self.backend(FakeTelethonClient(authorized=False))

        with self.assertRaises(TelegramApiError) as caught:
            backend.list_dialogs()
        self.assertEqual(caught.exception.code, "telegram_not_authorized")

    def test_missing_session_or_credentials_is_not_configured(self):
        no_session = TelethonBackend(api_id=1, api_hash="h", session_path=self.session)
        no_creds = TelethonBackend(api_id=None, api_hash="", session_path=self.session)
        self.session.write_bytes(b"")

        for backend in (no_session, no_creds):
            if backend is no_session:
                self.session.unlink()
            self.assertFalse(backend.configured())
            with self.assertRaises(TelegramApiError) as caught:
                backend.list_dialogs()
            self.assertEqual(caught.exception.code, "telegram_not_configured")

    def test_session_file_is_private(self):
        self.backend(FakeTelethonClient()).list_dialogs()

        self.assertEqual(self.session.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
