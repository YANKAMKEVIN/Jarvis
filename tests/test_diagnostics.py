import unittest

from jarvis.capabilities.diagnostics import DiagnosticsCapability


class DiagnosticsTests(unittest.TestCase):
    def test_all_ok(self):
        cap = DiagnosticsCapability(checks={
            "a": lambda: (True, "ok"),
            "b": lambda: (True, "ok"),
        })
        result = cap.self_check()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["missing"], [])
        self.assertEqual(sorted(result.data["available"]), ["a", "b"])
        self.assertIn("operationnel", result.message)

    def test_some_missing(self):
        cap = DiagnosticsCapability(checks={
            "accessibility": lambda: (True, "accorde"),
            "vision": lambda: (False, "desactivee"),
        })
        result = cap.self_check()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["missing"], ["vision"])
        self.assertEqual(result.data["checks"]["vision"]["detail"], "desactivee")

    def test_check_exception_counts_as_missing(self):
        def boom():
            raise RuntimeError("down")

        cap = DiagnosticsCapability(checks={"x": boom})
        result = cap.self_check()
        self.assertEqual(result.data["missing"], ["x"])
        self.assertFalse(result.data["checks"]["x"]["ok"])
        self.assertIn("erreur", result.data["checks"]["x"]["detail"])

    def test_real_checks_run_without_crashing(self):
        # Default real checks must at least produce a well-formed report.
        result = DiagnosticsCapability().self_check()
        self.assertTrue(result.ok)
        for name in ("accessibility", "vision", "local_model", "imap_mail"):
            self.assertIn(name, result.data["checks"])
            self.assertIn("ok", result.data["checks"][name])


if __name__ == "__main__":
    unittest.main()
