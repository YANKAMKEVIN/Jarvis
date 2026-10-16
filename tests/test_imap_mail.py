import unittest

from jarvis.capabilities.mail import MailCapability
from jarvis.tools.imap_mail import ImapMailReader, _decode
from jarvis.tools.mail import MailError, MailTools


class FakeImapClient:
    def __init__(self, unseen, headers):
        self.unseen = unseen          # list[bytes]
        self.headers = headers        # {bytes id: bytes raw header}
        self.logged_in = None
        self.selected = None
        self.logged_out = False

    def login(self, user, password):
        self.logged_in = (user, password)

    def select(self, mailbox):
        self.selected = mailbox

    def search(self, charset, criterion):
        return "OK", [b" ".join(self.unseen)]

    def fetch(self, message_id, spec):
        return "OK", [(message_id + b" (headers)", self.headers[message_id])]

    def logout(self):
        self.logged_out = True


def header(subject, sender, date="Mon, 16 Oct 2026 09:00:00 +0000"):
    return (f"Subject: {subject}\r\nFrom: {sender}\r\nDate: {date}\r\n\r\n").encode("utf-8")


def reader_with(client, **kw):
    return ImapMailReader(
        host="imap.example.com", username="me@example.com",
        connector=lambda h, p: client, password_lookup=lambda: "app-pw", **kw,
    )


class ImapReaderTests(unittest.TestCase):
    def test_reads_unread_most_recent_first(self):
        client = FakeImapClient(
            unseen=[b"1", b"2", b"3"],
            headers={
                b"1": header("Ancien", "a@x.com"),
                b"2": header("Milieu", "b@x.com"),
                b"3": header("Recent", "c@x.com"),
            },
        )
        state = reader_with(client).list_unread(limit=2)

        self.assertEqual(state["unread_count"], 2)
        self.assertEqual(state["emails"][0]["subject"], "Recent")  # most recent first
        self.assertEqual(state["emails"][0]["sender"], "c@x.com")
        self.assertTrue(client.logged_out)

    def test_not_configured_raises(self):
        reader = ImapMailReader(host=None, username=None)
        with self.assertRaises(MailError) as ctx:
            reader.list_unread()
        self.assertEqual(ctx.exception.code, "imap_not_configured")

    def test_no_password_raises(self):
        reader = ImapMailReader(
            host="imap.x", username="me@x",
            connector=lambda h, p: FakeImapClient([], {}),
            password_lookup=lambda: None,
        )
        with self.assertRaises(MailError) as ctx:
            reader.list_unread()
        self.assertEqual(ctx.exception.code, "imap_no_password")

    def test_connect_failure_raises(self):
        def boom(host, port):
            raise OSError("refused")

        reader = ImapMailReader(
            host="imap.x", username="me@x",
            connector=boom, password_lookup=lambda: "pw",
        )
        with self.assertRaises(MailError) as ctx:
            reader.list_unread()
        self.assertEqual(ctx.exception.code, "imap_connect_failed")

    def test_configured(self):
        self.assertTrue(reader_with(FakeImapClient([], {})).configured())
        self.assertFalse(ImapMailReader(host=None, username="x").configured())

    def test_decode_encoded_subject(self):
        self.assertEqual(_decode("=?utf-8?q?Caf=C3=A9?="), "Café")


class MailImapFallbackTests(unittest.TestCase):
    def test_uses_imap_when_configured(self):
        client = FakeImapClient([b"1"], {b"1": header("IMAP", "x@y.z")})

        def boom_runner(script):
            raise AssertionError("AppleScript must not run when IMAP is configured")

        cap = MailCapability(
            mail_tools=MailTools(runner=boom_runner),
            imap_reader=reader_with(client),
        )
        result = cap.list_unread()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["emails"][0]["subject"], "IMAP")

    def test_falls_back_to_applescript_when_imap_not_configured(self):
        from jarvis.tools.mail import FIELD_SEP, RECORD_SEP

        rec = FIELD_SEP.join(["AS", "x@y.z", "d"]) + RECORD_SEP
        cap = MailCapability(
            mail_tools=MailTools(runner=lambda s: (0, rec, "")),
            imap_reader=ImapMailReader(host=None, username=None),  # not configured
        )
        result = cap.list_unread()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["emails"][0]["subject"], "AS")

    def test_imap_bad_credentials_surface_not_silent_fallback(self):
        def bad_login_client(host, port):
            c = FakeImapClient([b"1"], {b"1": header("x", "y")})
            def fail_login(u, p):
                raise OSError("auth failed")
            c.login = fail_login
            return c

        cap = MailCapability(
            mail_tools=MailTools(runner=lambda s: (0, "", "")),
            imap_reader=ImapMailReader(
                host="imap.x", username="me@x",
                connector=bad_login_client, password_lookup=lambda: "pw",
            ),
        )
        result = cap.list_unread()
        self.assertFalse(result.ok)  # surfaced, not fell back
        self.assertEqual(result.error_code, "imap_read_failed")


if __name__ == "__main__":
    unittest.main()
