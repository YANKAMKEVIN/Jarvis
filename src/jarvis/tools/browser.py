from __future__ import annotations

import re
import subprocess
import time
from typing import Any, Callable
from urllib.parse import quote_plus, urlparse


SUPPORTED_BROWSERS = ("Safari", "Google Chrome")

BROWSER_ALIASES = {
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "google-chrome": "Google Chrome",
}

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "ddg": "https://duckduckgo.com/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
}
DEFAULT_SEARCH_ENGINE = "google"

TAB_RECORD_SEPARATOR = "__JARVIS_TAB__"

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

# Per-browser AppleScript property names. Safari and Chrome expose the same
# concepts under different nouns (name vs title, current tab vs active tab).
_DIALECT = {
    "Safari": {
        "tab_title": "name",
        "active_tab": "current tab of front window",
        "active_index": "index of current tab of front window",
    },
    "Google Chrome": {
        "tab_title": "title",
        "active_tab": "active tab of front window",
        "active_index": "active tab index of front window",
    },
}

# osascript runner contract: a callable taking the script source and returning
# a (returncode, stdout, stderr) tuple. Injectable so flows are fully testable
# without touching a real browser.
OsascriptRunner = Callable[[str], tuple[int, str, str]]


class BrowserError(Exception):
    def __init__(self, message: str, code: str | None = None, data: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


class BrowserTools:
    DEFAULT_OBSERVE_ATTEMPTS = 3
    DEFAULT_OBSERVE_DELAY_SECONDS = 0.15

    def __init__(
        self,
        runner: OsascriptRunner | None = None,
        observe_attempts: int = DEFAULT_OBSERVE_ATTEMPTS,
        observe_delay_seconds: float = DEFAULT_OBSERVE_DELAY_SECONDS,
        sleeper=None,
    ):
        self.runner = runner if runner is not None else self._default_runner
        self.observe_attempts = max(1, int(observe_attempts))
        self.observe_delay_seconds = max(0.0, float(observe_delay_seconds))
        self.sleeper = sleeper if sleeper is not None else time.sleep

    # -- public API -------------------------------------------------------

    def is_running(self, browser: str) -> bool:
        canonical = self.resolve_browser(browser)
        code, out, _err = self.runner(
            f'application "{self._escape(canonical)}" is running'
        )

        if code != 0:
            return False

        return out.strip().lower() == "true"

    def resolve_browser(self, browser: str | None) -> str:
        if browser is None:
            return self._auto_browser()

        if not isinstance(browser, str) or not browser.strip():
            raise BrowserError(
                "Le navigateur demande est invalide.",
                code="invalid_browser",
            )

        canonical = BROWSER_ALIASES.get(browser.strip().casefold())

        if canonical is None:
            raise BrowserError(
                "Navigateur non supporte. Utilise Safari ou Google Chrome.",
                code="invalid_browser",
                data={"requested_browser": browser},
            )

        return canonical

    def open_url(
        self,
        url: str,
        browser: str | None = None,
        new_tab: bool = True,
    ) -> dict[str, Any]:
        target = self.normalize_url(url)
        canonical = self.resolve_browser(browser)

        self._run_or_raise(self._open_script(canonical, target, new_tab))

        observed = self._observe_active_tab(canonical, self._host(target))
        active_url = observed.get("url")
        confirmed = self._same_host(target, active_url)

        return {
            "browser": canonical,
            "requested_url": target,
            "active_url": active_url,
            "active_title": observed.get("title"),
            "new_tab": bool(new_tab),
            "command_executed": True,
            "state_confirmed": confirmed,
        }

    def get_active_tab(self, browser: str | None = None) -> dict[str, Any]:
        canonical = self.resolve_browser(browser)
        tab = self._read_active_tab(canonical)

        return {
            "browser": canonical,
            "has_window": tab is not None,
            "url": tab.get("url") if tab else None,
            "title": tab.get("title") if tab else None,
        }

    def list_tabs(self, browser: str | None = None) -> dict[str, Any]:
        canonical = self.resolve_browser(browser)
        code, out, err = self.runner(self._list_tabs_script(canonical))

        if code != 0:
            raise BrowserError(
                err.strip() or "Lecture des onglets impossible.",
                code="system_error",
            )

        active_index, tabs = self._parse_tabs(out)

        return {
            "browser": canonical,
            "active_index": active_index,
            "tabs": tabs,
            "count": len(tabs),
        }

    def activate_tab_index(
        self,
        index: int,
        browser: str | None = None,
    ) -> dict[str, Any]:
        canonical = self.resolve_browser(browser)
        code, out, err = self.runner(self._activate_tab_script(canonical, index))

        if code != 0:
            raise BrowserError(
                err.strip() or "Activation de l'onglet impossible.",
                code=self._activate_error_code(err),
                data={"index": index},
            )

        lines = out.splitlines()
        active_index = self._to_int(lines[0]) if lines else None
        active_url = lines[1].strip() if len(lines) > 1 else None
        active_title = lines[2].strip() if len(lines) > 2 else None

        return {
            "browser": canonical,
            "index": index,
            "active_index": active_index,
            "active_url": self._clean(active_url),
            "active_title": self._clean(active_title),
            "command_executed": True,
            "state_confirmed": active_index == index,
        }

    @staticmethod
    def build_search_url(query: str, engine: str | None = None) -> str:
        if not isinstance(query, str) or not query.strip():
            raise BrowserError("Recherche manquante.", code="invalid_query")

        engine_key = (engine or DEFAULT_SEARCH_ENGINE).strip().casefold()
        template = SEARCH_ENGINES.get(engine_key)

        if template is None:
            raise BrowserError(
                "Moteur de recherche non supporte.",
                code="invalid_engine",
                data={"requested_engine": engine},
            )

        return template.format(query=quote_plus(query.strip()))

    @staticmethod
    def normalize_url(url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise BrowserError("URL manquante.", code="invalid_url")

        candidate = url.strip()

        if not _SCHEME_RE.match(candidate):
            candidate = "https://" + candidate

        return candidate

    # -- observation ------------------------------------------------------

    def _observe_active_tab(self, browser: str, expected_host: str) -> dict[str, Any]:
        observed: dict[str, Any] = {}

        for attempt in range(1, self.observe_attempts + 1):
            tab = self._read_active_tab(browser)
            observed = tab or {}

            if tab and self._same_host("//" + expected_host, tab.get("url")):
                return observed

            if attempt < self.observe_attempts:
                self.sleeper(self.observe_delay_seconds)

        return observed

    def _read_active_tab(self, browser: str) -> dict[str, Any] | None:
        code, out, err = self.runner(self._active_tab_script(browser))

        if code != 0:
            raise BrowserError(
                err.strip() or "Lecture de l'onglet actif impossible.",
                code="system_error",
            )

        lines = out.splitlines()

        if not lines or not out.strip():
            return None

        url = self._clean(lines[0].strip())
        title = self._clean(lines[1].strip()) if len(lines) > 1 else None

        if url is None and title is None:
            return None

        return {"url": url, "title": title}

    # -- script builders --------------------------------------------------

    def _open_script(self, browser: str, url: str, new_tab: bool) -> str:
        safe_url = self._escape(url)
        app = self._escape(browser)

        if browser == "Safari":
            if new_tab:
                body = [
                    "if (count of windows) = 0 then",
                    f'make new document with properties {{URL:"{safe_url}"}}',
                    "else",
                    "tell front window to set current tab to "
                    f'(make new tab with properties {{URL:"{safe_url}"}})',
                    "end if",
                ]
            else:
                body = [
                    "if (count of windows) = 0 then",
                    f'make new document with properties {{URL:"{safe_url}"}}',
                    "else",
                    f'set URL of current tab of front window to "{safe_url}"',
                    "end if",
                ]
        else:  # Google Chrome
            if new_tab:
                body = [
                    "if (count of windows) = 0 then",
                    "make new window",
                    f'set URL of active tab of front window to "{safe_url}"',
                    "else",
                    f'tell front window to make new tab with properties {{URL:"{safe_url}"}}',
                    "set active tab index of front window to (count of tabs of front window)",
                    "end if",
                ]
            else:
                body = [
                    "if (count of windows) = 0 then",
                    "make new window",
                    "end if",
                    f'set URL of active tab of front window to "{safe_url}"',
                ]

        return "\n".join([f'tell application "{app}"', "activate", *body, "end tell"])

    def _active_tab_script(self, browser: str) -> str:
        app = self._escape(browser)
        dialect = _DIALECT[browser]
        active = dialect["active_tab"]
        title = dialect["tab_title"]

        return "\n".join([
            f'tell application "{app}"',
            "if (count of windows) = 0 then return \"\"",
            'set u to ""',
            "try",
            f"set u to (URL of {active}) as text",
            "end try",
            'set n to ""',
            "try",
            f"set n to ({title} of {active}) as text",
            "end try",
            "return u & linefeed & n",
            "end tell",
        ])

    def _list_tabs_script(self, browser: str) -> str:
        app = self._escape(browser)
        dialect = _DIALECT[browser]
        title = dialect["tab_title"]
        active_index = dialect["active_index"]

        return "\n".join([
            f'tell application "{app}"',
            "if (count of windows) = 0 then return \"\"",
            "set activeIdx to 0",
            "try",
            f"set activeIdx to {active_index}",
            "end try",
            "set out to (activeIdx as text) & linefeed",
            "set idx to 0",
            "repeat with t in tabs of front window",
            "set idx to idx + 1",
            'set u to ""',
            "try",
            "set u to (URL of t) as text",
            "end try",
            'set n to ""',
            "try",
            f"set n to ({title} of t) as text",
            "end try",
            "set out to out & (idx as text) & linefeed & u & linefeed & n & "
            f'linefeed & "{TAB_RECORD_SEPARATOR}" & linefeed',
            "end repeat",
            "return out",
            "end tell",
        ])

    def _activate_tab_script(self, browser: str, index: int) -> str:
        app = self._escape(browser)
        dialect = _DIALECT[browser]
        active = dialect["active_tab"]
        title = dialect["tab_title"]
        active_index = dialect["active_index"]
        index = int(index)

        if browser == "Safari":
            select = f"tell front window to set current tab to tab {index}"
        else:
            select = f"set active tab index of front window to {index}"

        return "\n".join([
            f'tell application "{app}"',
            'if (count of windows) = 0 then error "no_window"',
            f'if (count of tabs of front window) < {index} then error "no_tab"',
            select,
            "activate",
            'set u to ""',
            "try",
            f"set u to (URL of {active}) as text",
            "end try",
            'set n to ""',
            "try",
            f"set n to ({title} of {active}) as text",
            "end try",
            f"return ({active_index} as text) & linefeed & u & linefeed & n",
            "end tell",
        ])

    # -- parsing / helpers ------------------------------------------------

    def _parse_tabs(self, output: str) -> tuple[int | None, list[dict[str, Any]]]:
        lines = output.splitlines()

        if not lines or not output.strip():
            return None, []

        active_index = self._to_int(lines[0])
        tabs: list[dict[str, Any]] = []
        record: list[str] = []

        for line in lines[1:]:
            if line.strip() == TAB_RECORD_SEPARATOR:
                if len(record) >= 3:
                    tabs.append({
                        "index": self._to_int(record[0]),
                        "url": self._clean(record[1].strip()),
                        "title": self._clean(record[2].strip()),
                    })
                record = []
                continue

            record.append(line)

        return active_index, tabs

    def _run_or_raise(self, script: str) -> str:
        code, out, err = self.runner(script)

        if code != 0:
            raise BrowserError(
                err.strip() or "Commande navigateur impossible.",
                code="system_error",
            )

        return out

    def _auto_browser(self) -> str:
        running = [b for b in SUPPORTED_BROWSERS if self.is_running(b)]

        if len(running) == 1:
            return running[0]

        if "Safari" in running:
            return "Safari"

        if running:
            return running[0]

        return "Safari"

    @classmethod
    def _same_host(cls, target: str, observed: str | None) -> bool:
        if not observed:
            return False

        target_host = cls._host(target)
        observed_host = cls._host(observed)

        return bool(target_host) and target_host == observed_host

    @staticmethod
    def _host(url: str | None) -> str:
        if not url:
            return ""

        netloc = urlparse(url).netloc.casefold()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        return netloc

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value or value == "missing value":
            return None

        return value

    @staticmethod
    def _to_int(value: str) -> int | None:
        try:
            return int(float(value.strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _activate_error_code(stderr: str) -> str:
        text = (stderr or "").lower()

        if "no_window" in text:
            return "no_window"

        if "no_tab" in text:
            return "no_tab"

        return "system_error"

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _default_runner(script: str) -> tuple[int, str, str]:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode, result.stdout, result.stderr
