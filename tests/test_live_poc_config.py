"""Live POC: configuration and logging privacy."""
import logging
import os
import pathlib
import tomllib
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.live.config import (
    DEFAULT_GEMINI_LIVE_MODEL,
    debug_live,
    get_live_config,
    get_required_runtime_env_names,
)
from jarvis.live.logging import REDACTED_PII_VALUE, install_livekit_pii_log_filter


class LivePocConfigTest(unittest.TestCase):
    def test_pyproject_marks_repository_as_agent_project_for_livekit_cli(self):
        pyproject_path = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"

        self.assertTrue(pyproject_path.exists())

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "jarvis")
        self.assertEqual(data["project"]["requires-python"], ">=3.13")

    def test_default_live_model_is_centralized(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_live_config()

        self.assertEqual(config.model, DEFAULT_GEMINI_LIVE_MODEL)
        self.assertEqual(config.voice, "Puck")
        self.assertEqual(config.agent_name, "jarvis-live-poc")

    def test_live_model_can_be_overridden(self):
        with patch.dict(
            os.environ,
            {
                "JARVIS_GEMINI_LIVE_MODEL": "gemini-test-live",
                "JARVIS_GEMINI_LIVE_VOICE": "Aoede",
                "JARVIS_GEMINI_LIVE_TEMPERATURE": "0.4",
                "JARVIS_LIVE_AGENT_NAME": "jarvis-test",
            },
            clear=True,
        ):
            config = get_live_config()

        self.assertEqual(config.model, "gemini-test-live")
        self.assertEqual(config.voice, "Aoede")
        self.assertEqual(config.temperature, 0.4)
        self.assertEqual(config.agent_name, "jarvis-test")

    def test_required_runtime_env_names_are_documented_by_code(self):
        self.assertEqual(
            get_required_runtime_env_names(),
            (
                "GOOGLE_API_KEY",
                "LIVEKIT_URL",
                "LIVEKIT_API_KEY",
                "LIVEKIT_API_SECRET",
            ),
        )

    def test_debug_live_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                debug_live("event", model="gemini")

        self.assertEqual(output.getvalue(), "")

    def test_debug_live_outputs_non_secret_fields_when_enabled(self):
        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                debug_live("event", model="gemini")

        debug_output = output.getvalue()

        self.assertIn("JARVIS LIVE DEBUG", debug_output)
        self.assertIn("EVENT: event", debug_output)
        self.assertIn("model: gemini", debug_output)


class LiveLoggingPrivacyTest(unittest.TestCase):
    def emit_livekit_log(self, **extra):
        logger = logging.getLogger("livekit.agents")
        old_level = logger.level
        old_propagate = logger.propagate
        records = []

        class RecordingHandler(logging.Handler):
            def emit(self, record):
                records.append(dict(record.__dict__))

        handler = RecordingHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        try:
            install_livekit_pii_log_filter()
            logger.debug("executing tool", extra=extra)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        self.assertEqual(len(records), 1)
        return records[0]

    def test_livekit_pii_arguments_are_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_ARGUMENT_SENTINEL_2ef6"

        record = self.emit_livekit_log(
            function="set_clipboard_text",
            **{"lk.pii.arguments": f'{{"text": "{secret}"}}'},
        )

        self.assertEqual(record["function"], "set_clipboard_text")
        self.assertEqual(record["lk.pii.arguments"], REDACTED_PII_VALUE)
        self.assertNotIn(secret, str(record))

    def test_livekit_pii_text_is_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_TEXT_SENTINEL_9b03"

        record = self.emit_livekit_log(
            role="user",
            **{"lk.pii.text": secret},
        )

        self.assertEqual(record["role"], "user")
        self.assertEqual(record["lk.pii.text"], REDACTED_PII_VALUE)
        self.assertNotIn(secret, str(record))

    def test_livekit_nested_pii_fields_are_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_OUTPUT_SENTINEL_b75c"

        record = self.emit_livekit_log(
            function="get_clipboard_text",
            **{"lk.pii.function_tool.output": f'{{"text": "{secret}"}}'},
        )

        self.assertEqual(
            record["lk.pii.function_tool.output"],
            REDACTED_PII_VALUE,
        )
        self.assertNotIn(secret, str(record))

    def test_livekit_non_pii_log_fields_are_unchanged(self):
        record = self.emit_livekit_log(
            function="get_volume",
            safe_field="visible diagnostic",
        )

        self.assertEqual(record["function"], "get_volume")
        self.assertEqual(record["safe_field"], "visible diagnostic")

    def test_livekit_pii_filter_installation_is_idempotent(self):
        logger = logging.getLogger("livekit.agents")

        install_livekit_pii_log_filter()
        install_livekit_pii_log_filter()

        filters = [
            item
            for item in logger.filters
            if item.__class__.__name__ == "LiveKitPIILogFilter"
        ]
        self.assertEqual(len(filters), 1)
