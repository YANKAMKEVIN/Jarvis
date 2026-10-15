import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.memory import store as memory_store
from jarvis.memory.guard import contains_secret
from jarvis.memory.store import MemoryError, MemoryStore


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "nested" / "memory.db"
        self.clock = FakeClock()
        self.store = MemoryStore(self.path, clock=self.clock)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_construction_touches_nothing_on_disk(self):
        MemoryStore(self.path)

        self.assertFalse(self.path.exists())

    def test_database_and_folder_are_private(self):
        self.store.remember("fact", "dentiste", "Dr Martin")

        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_remember_then_get(self):
        memory, created = self.store.remember("person", "ma mère", "Maman")

        self.assertTrue(created)
        self.assertEqual(self.store.get(memory.id).content, "Maman")
        self.assertEqual(memory.source, "user")

    def test_same_kind_and_subject_updates_instead_of_duplicating(self):
        first, _ = self.store.remember("person", "Ma Mère", "Maman")
        second, created = self.store.remember("person", "ma mere", "Maman ❤️")

        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.content, "Maman ❤️")
        self.assertEqual(self.store.count(), 1)

    def test_same_subject_in_another_kind_is_separate(self):
        self.store.remember("person", "musique", "x")
        self.store.remember("preference", "musique", "Spotify")

        self.assertEqual(self.store.count(), 2)

    def test_find_by_subject_ignores_case_accents_and_spaces(self):
        self.store.remember("person", "ma mère", "Maman")

        found = self.store.find_by_subject("person", "  MA   MERE ")

        self.assertEqual(found.content, "Maman")
        self.assertIsNone(self.store.find_by_subject("person", "mon père"))
        self.assertIsNone(self.store.find_by_subject("fact", "ma mère"))

    def test_search_matches_words_prefixes_and_accents(self):
        self.store.remember("fact", "dentiste", "Mon dentiste est le Dr Martin à Lyon")
        self.store.remember("preference", "musique", "Spotify plutôt que Musique")

        self.assertEqual(self.store.search("dentiste")[0].subject, "dentiste")
        self.assertEqual(self.store.search("dent")[0].subject, "dentiste")
        self.assertEqual(self.store.search("plutot")[0].subject, "musique")
        self.assertEqual(self.store.search("lyon martin")[0].subject, "dentiste")

    def test_search_falls_back_to_any_word(self):
        self.store.remember("fact", "dentiste", "Dr Martin")

        results = self.store.search("comment s'appelle mon dentiste")

        self.assertEqual([m.subject for m in results], ["dentiste"])

    def test_search_filters_by_kind(self):
        self.store.remember("fact", "spotify", "abonnement famille")
        self.store.remember("preference", "musique", "Spotify")

        results = self.store.search("spotify", kind="preference")

        self.assertEqual([m.kind for m in results], ["preference"])

    def test_search_reflects_updates_and_deletes(self):
        memory, _ = self.store.remember("fact", "voiture", "Clio rouge")
        self.store.remember("fact", "voiture", "Tesla bleue")

        self.assertEqual(self.store.search("clio"), [])
        self.assertEqual(self.store.search("tesla")[0].id, memory.id)

        self.store.delete(memory.id)
        self.assertEqual(self.store.search("tesla"), [])

    def test_empty_search_is_refused(self):
        with self.assertRaises(MemoryError) as context:
            self.store.search("  ?! ")

        self.assertEqual(context.exception.code, "invalid_query")

    def test_list_and_delete(self):
        a, _ = self.store.remember("fact", "a", "1")
        self.store.remember("profile", "prenom", "Kevin")

        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual([m.kind for m in self.store.list("profile")], ["profile"])
        self.assertEqual(self.store.delete(a.id).id, a.id)
        self.assertIsNone(self.store.get(a.id))
        self.assertIsNone(self.store.delete(a.id))

    def test_validation(self):
        cases = [
            (("episode", "s", "c"), "invalid_kind"),
            (("fact", "  ", "c"), "invalid_subject"),
            (("fact", "s", ""), "invalid_content"),
            (("fact", "s" * 121, "c"), "subject_too_long"),
            (("fact", "s", "c" * 501), "content_too_long"),
        ]
        for args, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(MemoryError) as context:
                    self.store.remember(*args)
                self.assertEqual(context.exception.code, code)

        with self.assertRaises(MemoryError) as context:
            self.store.remember("fact", "s", "c", source="guess")
        self.assertEqual(context.exception.code, "invalid_source")

    def test_data_survives_a_new_store_instance(self):
        self.store.remember("fact", "dentiste", "Dr Martin")

        reopened = MemoryStore(self.path)

        self.assertEqual(reopened.search("martin")[0].subject, "dentiste")

    def test_default_path_is_in_application_support_and_overridable(self):
        real = memory_store.real_default_memory_path

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                real(),
                Path.home() / "Library/Application Support/Jarvis/memory.db",
            )
        with patch.dict(os.environ, {"JARVIS_MEMORY_PATH": "~/x/m.db"}):
            self.assertEqual(real(), Path.home() / "x/m.db")


class EpisodeJournalTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.clock = FakeClock(now=1_700_000_000.0)
        self.store = MemoryStore(Path(self.tempdir.name) / "memory.db", clock=self.clock)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_recent_episodes_newest_first(self):
        self.store.log_episode("open_app", "Safari", True)
        self.clock.now += 60
        self.store.log_episode("set_volume", None, False, "system_error")

        episodes = self.store.recent_episodes()

        self.assertEqual([e.tool for e in episodes], ["set_volume", "open_app"])
        self.assertEqual(episodes[0].to_dict()["error_code"], "system_error")
        self.assertNotIn("target", episodes[0].to_dict())
        self.assertEqual(episodes[1].to_dict()["target"], "Safari")
        self.assertRegex(episodes[1].to_dict()["at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_episodes_expire_after_30_days(self):
        self.store.log_episode("open_app", "Safari")
        self.clock.now += 31 * 24 * 3600
        self.store.log_episode("close_app", "Safari")

        self.assertEqual([e.tool for e in self.store.recent_episodes()], ["close_app"])

    def test_fields_are_clipped_and_tool_required(self):
        self.store.log_episode("open_app", "x" * 500)

        self.assertEqual(len(self.store.recent_episodes()[0].target), 80)
        with self.assertRaises(MemoryError):
            self.store.log_episode("  ")

    def test_limit_is_bounded(self):
        for index in range(5):
            self.store.log_episode(f"t{index}")

        self.assertEqual(len(self.store.recent_episodes(limit=2)), 2)
        self.assertEqual(len(self.store.recent_episodes(limit=0)), 1)


class SecretGuardTest(unittest.TestCase):
    def test_refuses_secrets(self):
        secrets = [
            "mon mot de passe est hunter2",
            "MDP wifi : abc",
            "le code PIN de ma carte",
            "IBAN FR76 3000 6000 0112 3456 7890 189",
            "ma carte 4111 1111 1111 1111",
            "4111-1111-1111-1111",
            "clé API sk-abcdefghijklmnopqrstuvwx",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "token: a1b2c3d4e5f6g7h8i9j0k1l2m3n4",
            "numéro de sécurité sociale",
            "mon passeport",
        ]
        for text in secrets:
            with self.subTest(text=text):
                self.assertTrue(contains_secret(text))

    def test_allows_ordinary_memories(self):
        ordinary = [
            "ma mère s'appelle Maman sur WhatsApp",
            "Spotify pour la musique",
            "mon dentiste est le Dr Martin, 04 78 12 34 56",
            "anniversaire de Paul le 12 mars 1990",
            "j'habite au 12 rue de la Paix",
            "la réunion d'équipe est le mardi à 10h",
        ]
        for text in ordinary:
            with self.subTest(text=text):
                self.assertFalse(contains_secret(text))

    def test_checks_every_value(self):
        self.assertTrue(contains_secret("banque", "mot de passe: x"))
        self.assertFalse(contains_secret(None, ""))


if __name__ == "__main__":
    unittest.main()
