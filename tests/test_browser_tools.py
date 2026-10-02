import unittest

from jarvis.tools.browser import BrowserError, BrowserTools


class RecordingRunner:
    """Fake osascript runner returning queued (code, stdout, stderr) tuples."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.scripts = []

    def __call__(self, script):
        self.scripts.append(script)

        if not self.responses:
            raise AssertionError("Appel osascript inattendu : file vide.")

        return self.responses.pop(0)


def make_tools(responses):
    runner = RecordingRunner(responses)
    tools = BrowserTools(runner=runner, sleeper=lambda _seconds: None)
    return tools, runner


class BrowserNormalizationTest(unittest.TestCase):
    def test_normalize_url_prepends_https_when_scheme_absent(self):
        self.assertEqual(BrowserTools.normalize_url("example.com"), "https://example.com")

    def test_normalize_url_keeps_existing_scheme(self):
        self.assertEqual(
            BrowserTools.normalize_url("http://example.com/x"),
            "http://example.com/x",
        )

    def test_normalize_url_rejects_blank(self):
        with self.assertRaises(BrowserError) as context:
            BrowserTools.normalize_url("   ")

        self.assertEqual(context.exception.code, "invalid_url")

    def test_build_search_url_encodes_query_for_default_engine(self):
        url = BrowserTools.build_search_url("meteo paris")

        self.assertEqual(url, "https://www.google.com/search?q=meteo+paris")

    def test_build_search_url_supports_duckduckgo(self):
        url = BrowserTools.build_search_url("chats", engine="duckduckgo")

        self.assertEqual(url, "https://duckduckgo.com/?q=chats")

    def test_build_search_url_rejects_unknown_engine(self):
        with self.assertRaises(BrowserError) as context:
            BrowserTools.build_search_url("x", engine="altavista")

        self.assertEqual(context.exception.code, "invalid_engine")

    def test_build_search_url_rejects_blank_query(self):
        with self.assertRaises(BrowserError) as context:
            BrowserTools.build_search_url("  ")

        self.assertEqual(context.exception.code, "invalid_query")


class BrowserResolutionTest(unittest.TestCase):
    def test_resolve_browser_maps_aliases(self):
        tools, _ = make_tools([])

        self.assertEqual(tools.resolve_browser("chrome"), "Google Chrome")
        self.assertEqual(tools.resolve_browser("Safari"), "Safari")
        self.assertEqual(tools.resolve_browser("Google Chrome"), "Google Chrome")

    def test_resolve_browser_rejects_unsupported(self):
        tools, _ = make_tools([])

        with self.assertRaises(BrowserError) as context:
            tools.resolve_browser("Firefox")

        self.assertEqual(context.exception.code, "invalid_browser")

    def test_auto_browser_picks_the_single_running_one(self):
        # is_running(Safari) -> false, is_running(Google Chrome) -> true
        tools, _ = make_tools([(0, "false", ""), (0, "true", "")])

        self.assertEqual(tools.resolve_browser(None), "Google Chrome")

    def test_auto_browser_prefers_safari_when_ambiguous(self):
        tools, _ = make_tools([(0, "true", ""), (0, "true", "")])

        self.assertEqual(tools.resolve_browser(None), "Safari")

    def test_auto_browser_defaults_to_safari_when_none_running(self):
        tools, _ = make_tools([(0, "false", ""), (0, "false", "")])

        self.assertEqual(tools.resolve_browser(None), "Safari")


class BrowserOpenUrlTest(unittest.TestCase):
    def test_open_url_confirms_when_active_host_matches(self):
        tools, runner = make_tools([
            (0, "", ""),  # open script
            (0, "https://example.com/page\nExample", ""),  # active tab read
        ])

        state = tools.open_url("example.com", browser="Safari", new_tab=True)

        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["browser"], "Safari")
        self.assertEqual(state["requested_url"], "https://example.com")
        self.assertEqual(state["active_url"], "https://example.com/page")
        self.assertEqual(state["active_title"], "Example")
        self.assertIn(
            'make new tab with properties {URL:"https://example.com"}',
            runner.scripts[0],
        )

    def test_open_url_matches_host_despite_www_and_redirect_path(self):
        tools, _ = make_tools([
            (0, "", ""),
            (0, "https://www.example.com/after-redirect\nT", ""),
        ])

        state = tools.open_url("https://example.com", browser="Google Chrome")

        self.assertTrue(state["state_confirmed"])

    def test_open_url_not_confirmed_when_host_never_matches(self):
        tools, runner = make_tools([
            (0, "", ""),       # open
            (0, "", ""),       # read 1 (no window)
            (0, "", ""),       # read 2
            (0, "", ""),       # read 3
        ])

        state = tools.open_url("example.com", browser="Safari")

        self.assertTrue(state["command_executed"])
        self.assertFalse(state["state_confirmed"])
        self.assertIsNone(state["active_url"])
        # open + observe_attempts reads
        self.assertEqual(len(runner.scripts), 4)

    def test_open_url_same_tab_sets_current_tab_url(self):
        tools, runner = make_tools([
            (0, "", ""),
            (0, "https://example.com/\nE", ""),
        ])

        tools.open_url("example.com", browser="Safari", new_tab=False)

        self.assertIn(
            'set URL of current tab of front window to "https://example.com"',
            runner.scripts[0],
        )

    def test_open_url_raises_on_system_error(self):
        tools, _ = make_tools([(1, "", "exec error")])

        with self.assertRaises(BrowserError) as context:
            tools.open_url("example.com", browser="Safari")

        self.assertEqual(context.exception.code, "system_error")


class BrowserActiveTabTest(unittest.TestCase):
    def test_get_active_tab_returns_url_and_title(self):
        tools, _ = make_tools([(0, "https://example.com/\nExample", "")])

        state = tools.get_active_tab(browser="Safari")

        self.assertTrue(state["has_window"])
        self.assertEqual(state["url"], "https://example.com/")
        self.assertEqual(state["title"], "Example")

    def test_get_active_tab_reports_no_window(self):
        tools, _ = make_tools([(0, "", "")])

        state = tools.get_active_tab(browser="Safari")

        self.assertFalse(state["has_window"])
        self.assertIsNone(state["url"])

    def test_active_tab_treats_missing_value_as_none(self):
        tools, _ = make_tools([(0, "missing value\nmissing value", "")])

        state = tools.get_active_tab(browser="Google Chrome")

        self.assertFalse(state["has_window"])


class BrowserListTabsTest(unittest.TestCase):
    def test_list_tabs_parses_records_and_active_index(self):
        output = (
            "2\n"
            "1\nhttps://a.example/\nAlpha\n__JARVIS_TAB__\n"
            "2\nhttps://b.example/\nBeta\n__JARVIS_TAB__\n"
        )
        tools, _ = make_tools([(0, output, "")])

        state = tools.list_tabs(browser="Safari")

        self.assertEqual(state["active_index"], 2)
        self.assertEqual(state["count"], 2)
        self.assertEqual(
            state["tabs"],
            [
                {"index": 1, "url": "https://a.example/", "title": "Alpha"},
                {"index": 2, "url": "https://b.example/", "title": "Beta"},
            ],
        )

    def test_list_tabs_empty_when_no_window(self):
        tools, _ = make_tools([(0, "", "")])

        state = tools.list_tabs(browser="Safari")

        self.assertEqual(state["count"], 0)
        self.assertEqual(state["tabs"], [])


class BrowserActivateTabTest(unittest.TestCase):
    def test_activate_tab_index_confirms_when_active_index_matches(self):
        tools, runner = make_tools([(0, "3\nhttps://x/\nTitle", "")])

        state = tools.activate_tab_index(3, browser="Google Chrome")

        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["active_index"], 3)
        self.assertIn(
            "set active tab index of front window to 3",
            runner.scripts[0],
        )

    def test_activate_tab_index_not_confirmed_on_mismatch(self):
        tools, _ = make_tools([(0, "1\nhttps://x/\nTitle", "")])

        state = tools.activate_tab_index(3, browser="Safari")

        self.assertFalse(state["state_confirmed"])

    def test_activate_tab_index_maps_no_window_error(self):
        tools, _ = make_tools([(1, "", 'script error: no_window')])

        with self.assertRaises(BrowserError) as context:
            tools.activate_tab_index(1, browser="Safari")

        self.assertEqual(context.exception.code, "no_window")

    def test_activate_tab_index_maps_no_tab_error(self):
        tools, _ = make_tools([(1, "", 'script error: no_tab')])

        with self.assertRaises(BrowserError) as context:
            tools.activate_tab_index(9, browser="Safari")

        self.assertEqual(context.exception.code, "no_tab")


if __name__ == "__main__":
    unittest.main()
