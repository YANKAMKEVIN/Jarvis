import unittest

from jarvis.capabilities.browser import BrowserCapability
from jarvis.tools.browser import BrowserError


class FakeBrowserTools:
    def __init__(
        self,
        open_result=None,
        active_tab_result=None,
        list_tabs_result=None,
        activate_result=None,
        error=None,
    ):
        self.open_result = open_result
        self.active_tab_result = active_tab_result
        self.list_tabs_result = list_tabs_result
        self.activate_result = activate_result
        self.error = error
        self.calls = []

    def build_search_url(self, query, engine=None):
        self.calls.append(("build_search_url", query, engine))

        if isinstance(self.error, BrowserError) and self.error.code in {
            "invalid_query",
            "invalid_engine",
        }:
            raise self.error

        return f"https://www.google.com/search?q={query}"

    def open_url(self, url, browser=None, new_tab=True):
        self.calls.append(("open_url", url, browser, new_tab))

        if self.error is not None:
            raise self.error

        return dict(self.open_result)

    def get_active_tab(self, browser=None):
        self.calls.append(("get_active_tab", browser))

        if self.error is not None:
            raise self.error

        return dict(self.active_tab_result)

    def list_tabs(self, browser=None):
        self.calls.append(("list_tabs", browser))

        if self.error is not None:
            raise self.error

        return dict(self.list_tabs_result)

    def activate_tab_index(self, index, browser=None):
        self.calls.append(("activate_tab_index", index, browser))

        if self.error is not None:
            raise self.error

        return dict(self.activate_result)


class BrowserOpenUrlCapabilityTest(unittest.TestCase):
    def test_open_url_success_is_confirmed(self):
        tools = FakeBrowserTools(open_result={
            "browser": "Safari",
            "requested_url": "https://example.com",
            "active_url": "https://example.com/",
            "active_title": "Example",
            "new_tab": True,
            "command_executed": True,
            "state_confirmed": True,
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.open_url("example.com")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(tools.calls, [("open_url", "example.com", None, True)])

    def test_open_url_unconfirmed_still_ok_but_flagged(self):
        tools = FakeBrowserTools(open_result={
            "browser": "Safari",
            "active_url": None,
            "command_executed": True,
            "state_confirmed": False,
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.open_url("example.com")

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("n'est pas confirme", result.message)

    def test_open_url_invalid_url_is_tool_failure(self):
        tools = FakeBrowserTools(error=BrowserError("URL manquante.", code="invalid_url"))
        capability = BrowserCapability(browser_tools=tools)

        result = capability.open_url("")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_url")

    def test_open_url_system_error_is_wrapped(self):
        tools = FakeBrowserTools(error=RuntimeError("boom"))
        capability = BrowserCapability(browser_tools=tools)

        result = capability.open_url("example.com")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


class BrowserSearchWebCapabilityTest(unittest.TestCase):
    def test_search_web_builds_url_then_opens_it(self):
        tools = FakeBrowserTools(open_result={
            "browser": "Safari",
            "active_url": "https://www.google.com/search?q=x",
            "command_executed": True,
            "state_confirmed": True,
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.search_web("meteo", engine="google")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["engine"], "google")
        self.assertEqual(result.data["query_length"], len("meteo"))
        self.assertEqual(tools.calls[0][0], "build_search_url")
        self.assertEqual(tools.calls[1][0], "open_url")

    def test_search_web_invalid_engine_fails_before_open(self):
        tools = FakeBrowserTools(error=BrowserError("x", code="invalid_engine"))
        capability = BrowserCapability(browser_tools=tools)

        result = capability.search_web("x", engine="altavista")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_engine")
        self.assertEqual([call[0] for call in tools.calls], ["build_search_url"])


class BrowserReadCapabilityTest(unittest.TestCase):
    def test_get_active_tab_with_window(self):
        tools = FakeBrowserTools(active_tab_result={
            "browser": "Safari",
            "has_window": True,
            "url": "https://example.com/",
            "title": "Example",
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.get_active_tab()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["has_window"])
        self.assertIn("Example", result.message)

    def test_get_active_tab_without_window(self):
        tools = FakeBrowserTools(active_tab_result={
            "browser": "Safari",
            "has_window": False,
            "url": None,
            "title": None,
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.get_active_tab()

        self.assertTrue(result.ok)
        self.assertIn("aucune fenetre", result.message)

    def test_list_tabs_reports_count(self):
        tools = FakeBrowserTools(list_tabs_result={
            "browser": "Google Chrome",
            "active_index": 1,
            "tabs": [
                {"index": 1, "url": "https://a/", "title": "A"},
                {"index": 2, "url": "https://b/", "title": "B"},
            ],
            "count": 2,
        })
        capability = BrowserCapability(browser_tools=tools)

        result = capability.list_tabs("chrome")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 2)


class BrowserActivateTabCapabilityTest(unittest.TestCase):
    def _listing(self):
        return {
            "browser": "Safari",
            "active_index": 1,
            "tabs": [
                {"index": 1, "url": "https://github.com/", "title": "GitHub"},
                {"index": 2, "url": "https://example.com/", "title": "Example Domain"},
            ],
            "count": 2,
        }

    def test_activate_tab_rejects_blank_query(self):
        tools = FakeBrowserTools()
        capability = BrowserCapability(browser_tools=tools)

        result = capability.activate_tab("   ")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_query")
        self.assertEqual(tools.calls, [])

    def test_activate_tab_not_found(self):
        tools = FakeBrowserTools(list_tabs_result=self._listing())
        capability = BrowserCapability(browser_tools=tools)

        result = capability.activate_tab("gitlab")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "tab_not_found")

    def test_activate_tab_ambiguous(self):
        tools = FakeBrowserTools(list_tabs_result=self._listing())
        capability = BrowserCapability(browser_tools=tools)

        # "example" matches both the url and the title of tab 2 only, so make
        # it ambiguous by matching "https" present in both tabs' urls.
        result = capability.activate_tab("https://")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous_tab")

    def test_activate_tab_confirmed(self):
        tools = FakeBrowserTools(
            list_tabs_result=self._listing(),
            activate_result={
                "browser": "Safari",
                "index": 2,
                "active_index": 2,
                "active_url": "https://example.com/",
                "active_title": "Example Domain",
                "command_executed": True,
                "state_confirmed": True,
            },
        )
        capability = BrowserCapability(browser_tools=tools)

        result = capability.activate_tab("example domain")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(tools.calls[-1], ("activate_tab_index", 2, "Safari"))

    def test_activate_tab_not_confirmed_is_failure(self):
        tools = FakeBrowserTools(
            list_tabs_result=self._listing(),
            activate_result={
                "browser": "Safari",
                "index": 2,
                "active_index": 1,
                "active_url": "https://github.com/",
                "active_title": "GitHub",
                "command_executed": True,
                "state_confirmed": False,
            },
        )
        capability = BrowserCapability(browser_tools=tools)

        result = capability.activate_tab("example domain")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "tab_not_activated")


if __name__ == "__main__":
    unittest.main()
