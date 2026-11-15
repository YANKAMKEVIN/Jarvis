import unittest

from types import SimpleNamespace

from jarvis.live.confirmation import (
    ConfirmationNeedsUserTurn,
    PendingActionStore,
    note_user_turn_from_text,
)


class SequenceClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def token_sequence():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return f"tok{counter['n']}"

    return factory


class PendingActionStoreTest(unittest.TestCase):
    def make_store(self, ttl_seconds=300.0, max_pending=8):
        self.clock = SequenceClock()
        return PendingActionStore(
            clock=self.clock,
            token_factory=token_sequence(),
            ttl_seconds=ttl_seconds,
            max_pending=max_pending,
        )

    def test_register_then_confirm_runs_executor_once(self):
        store = self.make_store()
        runs = []
        token = store.register("send_message", lambda: runs.append("ran") or "result")

        self.assertEqual(token, "tok1")
        self.assertTrue(store.has_pending())

        store.note_user_turn()
        pending = store.confirm(token)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.action, "send_message")
        self.assertEqual(pending.executor(), "result")
        self.assertEqual(runs, ["ran"])

    def test_confirm_is_single_use(self):
        store = self.make_store()
        token = store.register("send_message", lambda: "x")

        store.note_user_turn()
        self.assertIsNotNone(store.confirm(token))
        store.note_user_turn()
        self.assertIsNone(store.confirm(token))  # already consumed
        self.assertFalse(store.has_pending())

    def test_unknown_token_returns_none(self):
        store = self.make_store()
        store.register("send_message", lambda: "x")

        self.assertIsNone(store.confirm("nope"))
        self.assertIsNone(store.confirm(None))

    def test_cancel_removes_without_running(self):
        store = self.make_store()
        runs = []
        token = store.register("send_message", lambda: runs.append("ran"))

        cancelled = store.cancel(token)
        self.assertIsNotNone(cancelled)
        self.assertEqual(runs, [])  # never executed
        self.assertIsNone(store.confirm(token))  # gone

    def test_expired_token_cannot_be_confirmed(self):
        store = self.make_store(ttl_seconds=10.0)
        token = store.register("send_message", lambda: "x")

        self.clock.advance(11.0)
        store.note_user_turn()

        self.assertIsNone(store.confirm(token))
        self.assertFalse(store.has_pending())

    def test_not_yet_expired_token_still_confirms(self):
        store = self.make_store(ttl_seconds=10.0)
        token = store.register("send_message", lambda: "x")

        self.clock.advance(9.0)
        store.note_user_turn()

        self.assertIsNotNone(store.confirm(token))

    def test_pending_count_is_bounded(self):
        store = self.make_store(max_pending=2)
        t1 = store.register("a", lambda: 1)
        self.clock.advance(1)
        store.register("b", lambda: 2)
        self.clock.advance(1)
        store.register("c", lambda: 3)  # evicts the oldest (t1)

        store.note_user_turn()
        self.assertIsNone(store.confirm(t1))

    def test_confirm_without_user_turn_is_refused_and_keeps_the_token(self):
        store = self.make_store()
        runs = []
        token = store.register("send_message", lambda: runs.append("ran"))

        with self.assertRaises(ConfirmationNeedsUserTurn):
            store.confirm(token)

        self.assertTrue(store.has_pending())  # still valid, not consumed
        self.assertEqual(runs, [])
        store.note_user_turn()
        self.assertIsNotNone(store.confirm(token))

    def test_user_turn_after_preparation_allows_confirmation(self):
        store = self.make_store()
        token = store.register("send_message", lambda: "x")

        store.note_user_turn()

        self.assertEqual(store.confirm(token).action, "send_message")

    def test_user_turn_before_preparation_does_not_count(self):
        store = self.make_store()
        store.note_user_turn()  # "envoie Salut a Paul" triggers the preparation
        token = store.register("send_message", lambda: "x")

        with self.assertRaises(ConfirmationNeedsUserTurn):
            store.confirm(token)

    def test_double_confirm_after_one_turn_runs_once(self):
        store = self.make_store()
        token = store.register("send_message", lambda: "x")
        store.note_user_turn()

        self.assertIsNotNone(store.confirm(token))
        self.assertIsNone(store.confirm(token))

    def test_each_action_needs_a_turn_after_its_own_preparation(self):
        store = self.make_store()
        first = store.register("a", lambda: 1)
        store.note_user_turn()
        second = store.register("b", lambda: 2)

        self.assertIsNotNone(store.confirm(first))
        with self.assertRaises(ConfirmationNeedsUserTurn):
            store.confirm(second)

    def test_expiration_still_applies_after_a_user_turn(self):
        store = self.make_store(ttl_seconds=10.0)
        token = store.register("send_message", lambda: "x")
        store.note_user_turn()

        self.clock.advance(11.0)

        self.assertIsNone(store.confirm(token))
        self.assertFalse(store.has_pending())

    def test_unknown_token_without_turn_is_none_not_an_error(self):
        store = self.make_store()
        store.register("send_message", lambda: "x")

        self.assertIsNone(store.confirm("nope"))


class NoteUserTurnFromTextTest(unittest.TestCase):
    def test_only_non_empty_text_notes_a_turn(self):
        calls = []
        registry = SimpleNamespace(note_user_turn=lambda: calls.append(1))

        self.assertFalse(note_user_turn_from_text(registry, ""))
        self.assertFalse(note_user_turn_from_text(registry, "   "))
        self.assertFalse(note_user_turn_from_text(registry, None))
        self.assertTrue(note_user_turn_from_text(registry, "oui"))
        self.assertEqual(calls, [1])

    def test_registry_without_support_is_ignored(self):
        self.assertFalse(note_user_turn_from_text(None, "oui"))
        self.assertFalse(note_user_turn_from_text(object(), "oui"))


if __name__ == "__main__":
    unittest.main()
