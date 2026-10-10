import unittest

from jarvis.live.confirmation import PendingActionStore


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

        pending = store.confirm(token)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.action, "send_message")
        self.assertEqual(pending.executor(), "result")
        self.assertEqual(runs, ["ran"])

    def test_confirm_is_single_use(self):
        store = self.make_store()
        token = store.register("send_message", lambda: "x")

        self.assertIsNotNone(store.confirm(token))
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

        self.assertIsNone(store.confirm(token))
        self.assertFalse(store.has_pending())

    def test_not_yet_expired_token_still_confirms(self):
        store = self.make_store(ttl_seconds=10.0)
        token = store.register("send_message", lambda: "x")

        self.clock.advance(9.0)

        self.assertIsNotNone(store.confirm(token))

    def test_pending_count_is_bounded(self):
        store = self.make_store(max_pending=2)
        t1 = store.register("a", lambda: 1)
        self.clock.advance(1)
        store.register("b", lambda: 2)
        self.clock.advance(1)
        store.register("c", lambda: 3)  # evicts the oldest (t1)

        self.assertIsNone(store.confirm(t1))


if __name__ == "__main__":
    unittest.main()
