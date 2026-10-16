import tempfile
import unittest
from pathlib import Path

from jarvis.capabilities.files import FilesCapability
from jarvis.tools.filesystem import FileSystemError, FileSystemTools, PathResolver


def tools_over(home, runner):
    return FileSystemTools(
        resolver=PathResolver(home=home),
        spotlight_limit=3,
        spotlight_runner=runner,
    )


class SpotlightSearchTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        # Create a couple of real files so path_info succeeds.
        self.a = Path(self.home) / "cv.pdf"
        self.a.write_text("x")
        self.b = Path(self.home) / "budget.txt"
        self.b.write_text("y")

    def test_returns_existing_matches(self):
        runner = lambda argv: f"{self.a}\n{self.b}\n"
        tools = tools_over(self.home, runner)

        result = tools.spotlight_search("budget")

        self.assertEqual(result["result_count"], 2)
        names = {r["name"] for r in result["results"]}
        self.assertEqual(names, {"cv.pdf", "budget.txt"})
        self.assertFalse(result["truncated"])

    def test_scopes_to_home_and_passes_query(self):
        captured = {}

        def runner(argv):
            captured["argv"] = argv
            return ""

        tools_over(self.home, runner).spotlight_search("facture EDF")

        self.assertEqual(captured["argv"][0], "mdfind")
        self.assertIn("-onlyin", captured["argv"])
        self.assertEqual(captured["argv"][-1], "facture EDF")
        self.assertIn(str(Path(self.home).resolve()), captured["argv"])

    def test_truncates_to_limit(self):
        many = "\n".join(str(self.a) for _ in range(10))
        result = tools_over(self.home, lambda argv: many).spotlight_search("x")

        self.assertEqual(result["result_count"], 3)  # spotlight_limit
        self.assertTrue(result["truncated"])

    def test_skips_vanished_paths(self):
        runner = lambda argv: f"{self.a}\n{self.home}/gone.pdf\n"
        result = tools_over(self.home, runner).spotlight_search("x")

        self.assertEqual(result["result_count"], 1)  # the missing one is skipped

    def test_blank_query_rejected(self):
        with self.assertRaises(FileSystemError):
            tools_over(self.home, lambda argv: "").spotlight_search("   ")

    def test_runner_failure_surfaces_as_capability_error(self):
        def boom(argv):
            raise FileSystemError("nope", "spotlight_error")

        capability = FilesCapability(filesystem_tools=tools_over(self.home, boom))
        result = capability.search_content("budget")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "spotlight_error")

    def test_capability_success(self):
        runner = lambda argv: f"{self.a}\n"
        capability = FilesCapability(filesystem_tools=tools_over(self.home, runner))
        result = capability.search_content("cv")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["result_count"], 1)


if __name__ == "__main__":
    unittest.main()
