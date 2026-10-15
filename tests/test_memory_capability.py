import asyncio
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis.capabilities.memory import MemoryCapability
from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import create_live_tools
from jarvis.memory.store import MemoryStore


class BrokenStore:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise OSError("disk unavailable")
        return fail


class TempMemoryMixin:
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.tempdir.name) / "memory.db")
        self.memory = MemoryCapability(self.store)

    def tearDown(self):
        self.tempdir.cleanup()


class MemoryCapabilityTest(TempMemoryMixin, unittest.TestCase):
    def test_remember_creates_then_updates(self):
        first = self.memory.remember("person", "ma mère", "Maman")
        second = self.memory.remember("person", "ma mere", "Maman ❤️")

        self.assertTrue(first.ok)
        self.assertTrue(first.data["created"])
        self.assertTrue(first.data["state_confirmed"])
        self.assertFalse(second.data["created"])
        self.assertEqual(self.store.count(), 1)

    def test_remember_refuses_secrets_without_storing(self):
        result = self.memory.remember("fact", "banque", "mot de passe: hunter2")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "secret_refused")
        self.assertNotIn("hunter2", result.message)
        self.assertEqual(self.store.count(), 0)

    def test_remember_reports_validation_errors(self):
        result = self.memory.remember("nope", "s", "c")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_kind")

    def test_recall_and_list(self):
        self.memory.remember("fact", "dentiste", "Dr Martin")
        self.memory.remember("preference", "musique", "Spotify")

        recall = self.memory.recall("dentiste")
        empty = self.memory.recall("plombier")
        listing = self.memory.list_memories()

        self.assertEqual(recall.data["count"], 1)
        self.assertEqual(recall.data["memories"][0]["content"], "Dr Martin")
        self.assertEqual(empty.data["count"], 0)
        self.assertTrue(empty.ok)
        self.assertEqual(listing.data["count"], 2)

    def test_forget_by_id(self):
        memory_id = self.memory.remember("fact", "dentiste", "Dr Martin").data["memory"]["id"]

        result = self.memory.forget(memory_id=memory_id)

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(self.store.count(), 0)

    def test_forget_by_unambiguous_query(self):
        self.memory.remember("fact", "dentiste", "Dr Martin")

        result = self.memory.forget(query="dentiste")

        self.assertTrue(result.ok)
        self.assertEqual(self.store.count(), 0)

    def test_forget_never_deletes_on_ambiguity(self):
        self.memory.remember("fact", "dentiste", "Dr Martin")
        self.memory.remember("fact", "medecin", "Dr Martin aussi")

        result = self.memory.forget(query="martin")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous_memory")
        self.assertEqual(len(result.data["candidates"]), 2)
        self.assertEqual(self.store.count(), 2)

    def test_forget_missing_or_without_target(self):
        self.assertEqual(self.memory.forget(memory_id=999).error_code, "memory_not_found")
        self.assertEqual(self.memory.forget(query="rien").error_code, "memory_not_found")
        self.assertEqual(self.memory.forget().error_code, "invalid_forget_target")

    def test_resolve_person(self):
        self.memory.remember("person", "ma mère", "Maman ❤️")

        self.assertEqual(self.memory.resolve_person("Ma Mere"), "Maman ❤️")
        self.assertIsNone(self.memory.resolve_person("Kevin"))

    def test_preferred_media_app(self):
        self.assertIsNone(self.memory.preferred_media_app())

        cases = [
            ("musique", "Spotify", "Spotify"),
            ("musique", "Apple Music", "Music"),
            ("music", "Spotify plutot qu'Apple Music", "Spotify"),
            ("musique", "Apple Music, pas Spotify", "Music"),
            ("musique", "Deezer", None),
        ]
        for subject, content, expected in cases:
            with self.subTest(content=content):
                self.memory.remember("preference", subject, content)
                self.assertEqual(self.memory.preferred_media_app(), expected)
                self.memory.forget(query=subject)

    def test_store_failures_become_clean_results(self):
        memory = MemoryCapability(BrokenStore())

        self.assertEqual(memory.recall("x").error_code, "memory_unavailable")
        self.assertEqual(memory.remember("fact", "a", "b").error_code, "memory_unavailable")
        self.assertIsNone(memory.resolve_person("ma mère"))  # never blocks a send
        self.assertIsNone(memory.preferred_media_app())


class RecordingInteraction:
    def __init__(self):
        self.calls = []

    def focus_app_ui_and_type(self, *args):
        self.calls.append(args)
        return ToolResult.success(action="focus_app_ui_and_type", message="ok")


class RecordingMessaging:
    def __init__(self):
        self.calls = []

    def composer_query(self, app_name):
        return None

    def supports_composer_send(self, app_name):
        return False

    def ensure_recipient(self, app_name, recipient):
        self.calls.append((app_name, recipient))
        return ToolResult.success(action="verify_recipient", message="ok")


class LiveMemoryToolsTest(TempMemoryMixin, unittest.TestCase):
    def make_tools(self):
        self.interaction = RecordingInteraction()
        self.messaging = RecordingMessaging()
        tools = create_live_tools(
            interaction_capability=self.interaction,
            messaging_capability=self.messaging,
            memory_capability=self.memory,
        )
        return {tool.info.name: tool for tool in tools}

    def test_memory_tools_are_exposed(self):
        tools = self.make_tools()

        for name in ("remember", "propose_memory", "recall", "list_memories", "forget"):
            self.assertIn(name, tools)
        self.assertIn("explicitement", tools["remember"].info.description)
        self.assertIn("DEDUITE", tools["propose_memory"].info.description)

    def test_remember_recall_forget_round_trip(self):
        tools = self.make_tools()

        saved = asyncio.run(tools["remember"]("fact", "dentiste", "Dr Martin"))
        found = asyncio.run(tools["recall"]("dentiste"))
        listed = asyncio.run(tools["list_memories"]())
        forgotten = asyncio.run(tools["forget"](saved["memory"]["id"]))

        self.assertTrue(saved["ok"])
        self.assertEqual(found["memories"][0]["content"], "Dr Martin")
        self.assertEqual(listed["count"], 1)
        self.assertTrue(forgotten["state_confirmed"])
        self.assertEqual(self.store.count(), 0)

    def test_proposed_memory_is_stored_only_after_confirmation(self):
        tools = self.make_tools()

        proposed = asyncio.run(tools["propose_memory"]("person", "Marie", "Marie Dupont"))

        self.assertTrue(proposed["requires_confirmation"])
        self.assertEqual(self.store.count(), 0)  # nothing stored yet

        confirmed = asyncio.run(tools["confirm_action"](proposed["token"]))

        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["memory"]["source"], "inferred")
        self.assertEqual(self.store.count(), 1)

    def test_cancelled_proposal_stores_nothing(self):
        tools = self.make_tools()

        proposed = asyncio.run(tools["propose_memory"]("person", "Marie", "Marie Dupont"))
        asyncio.run(tools["cancel_action"](proposed["token"]))
        late = asyncio.run(tools["confirm_action"](proposed["token"]))

        self.assertEqual(late["error_code"], "no_pending_action")
        self.assertEqual(self.store.count(), 0)

    def test_proposal_is_validated_before_asking(self):
        tools = self.make_tools()

        secret = asyncio.run(tools["propose_memory"]("fact", "wifi", "mot de passe abc"))
        invalid = asyncio.run(tools["propose_memory"]("nope", "a", "b"))

        self.assertEqual(secret["error_code"], "secret_refused")
        self.assertEqual(invalid["error_code"], "invalid_kind")
        self.assertNotIn("token", secret)
        self.assertNotIn("token", invalid)

    def test_messaging_resolves_alias_from_memory_locally(self):
        tools = self.make_tools()
        self.memory.remember("person", "ma mère", "Maman ❤️")

        result = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "J'arrive", "ma mere")
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["recipient_from_memory"])
        self.assertEqual(self.messaging.calls, [("WhatsApp", "Maman ❤️")])
        # The stored contact name is applied locally, not returned to the model.
        self.assertNotIn("Maman", repr(result))
        self.assertEqual(self.interaction.calls, [])  # still not sent

    def test_messaging_without_alias_keeps_recipient(self):
        tools = self.make_tools()

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut", "Paul"))

        self.assertFalse(result["recipient_from_memory"])
        self.assertEqual(self.messaging.calls, [("WhatsApp", "Paul")])

    def test_actions_are_journaled_without_content(self):
        tools = self.make_tools()

        prepared = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "TEXTE_PRIVE", "Paul")
        )
        asyncio.run(tools["confirm_action"](prepared["token"]))
        activity = asyncio.run(tools["recent_activity"]())

        self.assertEqual(
            [(e["tool"], e.get("target"), e["ok"]) for e in activity["episodes"]],
            [("confirm_send_message", None, True), ("prepare_send_message", "WhatsApp", True)],
        )
        journal = repr(self.store.recent_episodes())
        self.assertNotIn("TEXTE_PRIVE", journal)
        self.assertNotIn("Paul", journal)

    def test_browse_journal_keeps_only_the_host(self):
        class FakeBrowser:
            def open_url(self, url, browser=None, new_tab=True):
                return ToolResult.success(action="browse_open_url", message="ok")

        tools = {
            tool.info.name: tool
            for tool in create_live_tools(
                browser_capability=FakeBrowser(), memory_capability=self.memory,
            )
        }

        asyncio.run(tools["browse_open_url"]("https://www.example.com/compte?id=42"))

        episode = self.store.recent_episodes()[0]
        self.assertEqual((episode.tool, episode.target), ("browse_open_url", "example.com"))

    def test_journal_host_drops_credentials_port_path_and_query(self):
        from jarvis.live.registry import ToolRegistry

        host = ToolRegistry._journal_host
        self.assertEqual(host("https://user:pw@www.site.fr:8443/a?b=c#d"), "site.fr")
        self.assertEqual(host("lemonde.fr/article"), "lemonde.fr")
        self.assertIsNone(host(""))
        self.assertIsNone(host(None))

    def test_failed_actions_are_journaled_as_failed(self):
        tools = self.make_tools()

        asyncio.run(tools["prepare_send_message"]("WhatsApp", "   "))

        episode = self.store.recent_episodes()[0]
        self.assertFalse(episode.ok)
        self.assertEqual(episode.error_code, "invalid_text")

    def test_journal_failure_never_breaks_a_tool(self):
        tools = {
            tool.info.name: tool
            for tool in create_live_tools(
                interaction_capability=RecordingInteraction(),
                messaging_capability=RecordingMessaging(),
                memory_capability=MemoryCapability(BrokenStore()),
            )
        }

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))

        self.assertTrue(result["ok"])

    def test_media_tools_apply_music_preference_locally(self):
        class RecordingMedia:
            def __init__(self):
                self.calls = []

            def play_pause(self, *args):
                self.calls.append(("play_pause", args))
                return ToolResult.success(action="play_pause", message="ok")

        media = RecordingMedia()
        tools = {
            tool.info.name: tool
            for tool in create_live_tools(media_capability=media, memory_capability=self.memory)
        }

        asyncio.run(tools["play_pause"]())
        self.memory.remember("preference", "musique", "Spotify")
        result = asyncio.run(tools["play_pause"]())

        self.assertEqual(media.calls, [("play_pause", ()), ("play_pause", ("Spotify",))])
        self.assertNotIn("Spotify", repr(result))

    def test_debug_never_logs_memory_content(self):
        tools = self.make_tools()

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}):
            output = StringIO()
            with redirect_stdout(output):
                asyncio.run(tools["remember"]("fact", "SECRET_SUBJECT", "SECRET_CONTENT"))
                asyncio.run(tools["recall"]("SECRET_SUBJECT"))

        self.assertNotIn("SECRET_SUBJECT", output.getvalue())
        self.assertNotIn("SECRET_CONTENT", output.getvalue())


class ProcedureTest(TempMemoryMixin, unittest.TestCase):
    STEPS = [
        {"tool": "open_app", "target": "Safari"},
        {"tool": "browse_open_url", "target": "example.com"},
        {"tool": "capture_screen", "target": None},
    ]

    def test_save_then_get_roundtrip(self):
        saved = self.memory.save_procedure("préparer réunion", self.STEPS)
        self.assertTrue(saved.ok)
        self.assertTrue(saved.data["created"])
        self.assertEqual(len(saved.data["procedure"]["steps"]), 3)

        # Accent/case-insensitive subject lookup.
        got = self.memory.get_procedure("preparer reunion")
        self.assertTrue(got.ok)
        self.assertEqual(got.data["procedure"]["steps"], self.STEPS)

    def test_resaving_updates(self):
        self.memory.save_procedure("ma tache", self.STEPS)
        again = self.memory.save_procedure("ma tache", self.STEPS[:1])

        self.assertFalse(again.data["created"])
        got = self.memory.get_procedure("ma tache")
        self.assertEqual(len(got.data["procedure"]["steps"]), 1)

    def test_steps_are_reduced_to_tool_and_target_only(self):
        saved = self.memory.save_procedure("fuite", [
            {"tool": "type_text", "target": "champ", "text": "SECRET_BODY"},
            "pas un dict",
            {"target": "sans tool"},
        ])
        self.assertTrue(saved.ok)
        steps = saved.data["procedure"]["steps"]
        self.assertEqual(steps, [{"tool": "type_text", "target": "champ"}])
        self.assertNotIn("SECRET_BODY", repr(self.store.get(saved.data["procedure"]["id"]).content))

    def test_empty_procedure_is_rejected(self):
        result = self.memory.save_procedure("vide", [])
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_procedure")

    def test_secret_in_step_is_refused(self):
        result = self.memory.save_procedure("login", [
            {"tool": "type_text", "target": "mot de passe hunter2"},
        ])
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "secret_refused")
        self.assertEqual(self.store.count(), 0)

    def test_get_unknown_procedure(self):
        result = self.memory.get_procedure("inconnue")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "memory_not_found")

    def test_procedure_is_a_memory_kind(self):
        self.memory.save_procedure("ma tache", self.STEPS)
        recalled = self.memory.recall("tache", kind="procedure")
        self.assertTrue(recalled.ok)
        self.assertEqual(recalled.data["count"], 1)


if __name__ == "__main__":
    unittest.main()
