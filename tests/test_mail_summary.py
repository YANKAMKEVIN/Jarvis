import email.message
import json
import unittest

from jarvis.capabilities.mail import MailCapability
from jarvis.tools.imap_mail import ImapMailReader


# --- fakes ------------------------------------------------------------------


class FakeBodyClient:
    """IMAP client returning full MIME messages for BODY.PEEK[] fetches."""

    def __init__(self, unseen, messages):
        self.unseen = unseen            # list[bytes]
        self.messages = messages        # {bytes id: bytes raw}
        self.fetch_specs = []
        self.logged_out = False

    def login(self, user, password):
        pass

    def select(self, mailbox):
        pass

    def search(self, charset, criterion):
        return "OK", [b" ".join(self.unseen)]

    def fetch(self, message_id, spec):
        self.fetch_specs.append(spec)
        return "OK", [(message_id + b" (body)", self.messages[message_id])]

    def logout(self):
        self.logged_out = True


def plain_message(subject, sender, body):
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = "Mon, 19 Oct 2026 09:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


def html_message(subject, sender, html):
    raw = (
        f"Subject: {subject}\r\nFrom: {sender}\r\n"
        "Date: Mon, 19 Oct 2026 09:00:00 +0000\r\n"
        "MIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        f"{html}\r\n"
    )
    return raw.encode("utf-8")


def reader_with(client):
    return ImapMailReader(
        host="imap.example.com", username="me@example.com",
        connector=lambda h, p: client, password_lookup=lambda: "pw",
    )


class Turn:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, text="[]", url=None, base_url=None):
        self.text = text
        self.calls = []
        if url is not None:
            self.url = url
        if base_url is not None:
            self.base_url = base_url

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return Turn(self.text)


class FakeReader:
    def __init__(self, emails, configured=True):
        self.emails = emails
        self._configured = configured
        self.calls = []

    def configured(self):
        return self._configured

    def list_unread_with_bodies(self, limit, max_body_chars):
        self.calls.append((limit, max_body_chars))
        rows = self.emails[:limit]
        return {"emails": rows, "unread_count": len(rows)}


# --- IMAP body fetch --------------------------------------------------------


class ImapBodyTests(unittest.TestCase):
    def test_peek_does_not_mark_read_and_parses_plain(self):
        client = FakeBodyClient(
            unseen=[b"1"],
            messages={b"1": plain_message("Facture", "edf@x.com", "Votre facture de 42 euros est disponible.")},
        )
        state = reader_with(client).list_unread_with_bodies(limit=5)
        # BODY.PEEK[] keeps the message unread.
        self.assertTrue(all("PEEK" in spec for spec in client.fetch_specs))
        self.assertEqual(state["emails"][0]["subject"], "Facture")
        self.assertIn("42 euros", state["emails"][0]["body"])

    def test_html_body_is_stripped(self):
        client = FakeBodyClient(
            unseen=[b"1"],
            messages={b"1": html_message("Promo", "shop@x.com", "<p>Soldes <b>-50%</b></p><script>x()</script>")},
        )
        body = reader_with(client).list_unread_with_bodies(limit=5)["emails"][0]["body"]
        self.assertIn("Soldes", body)
        self.assertIn("-50%", body)
        self.assertNotIn("<", body)
        self.assertNotIn("x()", body)


# --- summarize_unread -------------------------------------------------------


class SummarizeUnreadTests(unittest.TestCase):
    def _emails(self):
        return [
            {"sender": "edf@x.com", "subject": "Facture", "body": "Facture 42 euros."},
            {"sender": "rh@x.com", "subject": "Entretien", "body": "Entretien lundi 10h."},
        ]

    def test_summarizes_and_anchors_to_real_headers(self):
        model = FakeModel(json.dumps([
            {"index": 0, "summary": "Facture de 42 euros disponible."},
            {"index": 1, "summary": "Entretien propose lundi a 10h."},
        ]))
        cap = MailCapability(imap_reader=FakeReader(self._emails()), model=model)
        result = cap.summarize_unread(limit=5)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 2)
        first = result.data["items"][0]
        # Sender/subject come from headers, not the model.
        self.assertEqual(first["sender"], "edf@x.com")
        self.assertEqual(first["subject"], "Facture")
        self.assertIn("42 euros", first["summary"])

    def test_missing_index_leaves_empty_summary(self):
        model = FakeModel(json.dumps([{"index": 0, "summary": "Seulement le premier."}]))
        cap = MailCapability(imap_reader=FakeReader(self._emails()), model=model)
        result = cap.summarize_unread()
        self.assertEqual(result.data["items"][1]["summary"], "")

    def test_remote_model_is_blocked_and_nothing_is_read(self):
        reader = FakeReader(self._emails())
        model = FakeModel(base_url="https://generativelanguage.googleapis.com/v1beta/openai")
        cap = MailCapability(imap_reader=reader, model=model)
        result = cap.summarize_unread()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "remote_model_blocked")
        self.assertEqual(reader.calls, [])   # bodies never fetched
        self.assertEqual(model.calls, [])    # nothing sent

    def test_opt_in_allows_remote(self):
        reader = FakeReader(self._emails())
        model = FakeModel(json.dumps([{"index": 0, "summary": "ok"}]),
                          base_url="https://generativelanguage.googleapis.com/v1beta/openai")
        cap = MailCapability(imap_reader=reader, model=model)
        import os
        os.environ["JARVIS_MAIL_ALLOW_REMOTE"] = "1"
        try:
            result = cap.summarize_unread()
        finally:
            del os.environ["JARVIS_MAIL_ALLOW_REMOTE"]
        self.assertTrue(result.ok)
        self.assertTrue(model.calls)

    def test_imap_not_configured(self):
        cap = MailCapability(imap_reader=FakeReader([], configured=False), model=FakeModel())
        result = cap.summarize_unread()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "imap_not_configured")

    def test_no_unread_is_ok(self):
        cap = MailCapability(imap_reader=FakeReader([]), model=FakeModel())
        result = cap.summarize_unread()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 0)

    def test_invalid_model_output_is_refused(self):
        cap = MailCapability(imap_reader=FakeReader(self._emails()), model=FakeModel("not json"))
        result = cap.summarize_unread()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_summary")

    def test_out_of_range_index_is_refused(self):
        model = FakeModel(json.dumps([{"index": 9, "summary": "fantome"}]))
        cap = MailCapability(imap_reader=FakeReader(self._emails()), model=model)
        result = cap.summarize_unread()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_summary")


if __name__ == "__main__":
    unittest.main()
