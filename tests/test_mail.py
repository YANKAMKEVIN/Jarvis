import unittest

from jarvis.capabilities.mail import MailCapability
from jarvis.tools.mail import FIELD_SEP, RECORD_SEP, MailError, MailTools


def ok_runner(stdout):
    return lambda script: (0, stdout, "")


def fail_runner(stderr="boom"):
    return lambda script: (1, "", stderr)


def timeout_runner():
    return lambda script: (1, "", "__timeout__")


def record(subject, sender, date):
    return FIELD_SEP.join([subject, sender, date]) + RECORD_SEP


class MailToolsTests(unittest.TestCase):
    def test_parses_unread(self):
        out = (
            record("Facture", "edf@edf.fr", "lundi 09:00")
            + record("Reunion", "boss@work.com", "lundi 10:00")
        )
        state = MailTools(runner=ok_runner(out)).list_unread()
        self.assertEqual(state["unread_count"], 2)
        self.assertEqual(state["emails"][0]["subject"], "Facture")
        self.assertEqual(state["emails"][1]["sender"], "boss@work.com")

    def test_empty_inbox(self):
        self.assertEqual(MailTools(runner=ok_runner("")).list_unread()["unread_count"], 0)

    def test_timeout(self):
        with self.assertRaises(MailError) as ctx:
            MailTools(runner=timeout_runner()).list_unread()
        self.assertEqual(ctx.exception.code, "mail_timeout")

    def test_read_failure(self):
        with self.assertRaises(MailError):
            MailTools(runner=fail_runner()).list_unread()

    def test_create_draft_builds_script(self):
        captured = {}

        def runner(script):
            captured["script"] = script
            return (0, "ok", "")

        state = MailTools(runner=runner).create_draft("a@b.com", "Objet", "Bonjour")
        self.assertTrue(state["command_executed"])
        self.assertIn("outgoing message", captured["script"])
        self.assertIn("a@b.com", captured["script"])
        self.assertIn("Objet", captured["script"])

    def test_create_draft_failure(self):
        with self.assertRaises(MailError):
            MailTools(runner=fail_runner("no mail")).create_draft("a@b.com", "s", "b")


class MailCapabilityTests(unittest.TestCase):
    def test_list_unread_message(self):
        cap = MailCapability(MailTools(runner=ok_runner(record("S", "x@y.z", "d"))))
        result = cap.list_unread()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["unread_count"], 1)

    def test_draft_requires_recipient(self):
        cap = MailCapability(MailTools(runner=ok_runner("ok")))
        result = cap.create_draft("  ", "Objet", "corps")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_recipient")

    def test_draft_requires_body(self):
        cap = MailCapability(MailTools(runner=ok_runner("ok")))
        result = cap.create_draft("a@b.com", "Objet", "   ")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_body")

    def test_draft_success(self):
        cap = MailCapability(MailTools(runner=ok_runner("ok")))
        result = cap.create_draft("a@b.com", "Objet", "Bonjour")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["recipient"], "a@b.com")


if __name__ == "__main__":
    unittest.main()
