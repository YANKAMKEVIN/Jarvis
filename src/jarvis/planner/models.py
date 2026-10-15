"""Planner model interface and implementations.

The engine never depends on a provider: it talks to a PlannerModel, which
receives neutral messages plus OpenAI-style tool schemas and returns a
ModelTurn (text and/or tool calls). Swapping the brain (local Ollama today,
a cloud model later) is a configuration change, not an engine change.

Neutral message shapes:
    {"role": "system" | "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}
    {"role": "tool", "name": str, "tool_call_id": str, "content": str}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class PlannerModelError(Exception):
    def __init__(self, message: str, code: str = "model_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class PlannerModel(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        """One model turn. Blocking; the engine runs it off the event loop."""


class ScriptedModel:
    """Deterministic model for tests: replays a fixed list of turns.

    Each scripted item is a ModelTurn, or a callable receiving the messages
    so far (to assert on what the engine sent) and returning a ModelTurn.
    """

    name = "scripted"

    def __init__(self, turns: list):
        self._turns = list(turns)
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        self.calls.append([dict(message) for message in messages])
        if not self._turns:
            raise PlannerModelError("Script epuise.", "script_exhausted")
        turn = self._turns.pop(0)
        return turn(messages) if callable(turn) else turn


DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_PLANNER_MODEL = "granite4:3b"
# The planner prompt (rules + ~37 tool schemas) is ~4.3k tokens; Ollama's
# default context is smaller and would silently drop its start. 8k leaves room
# for several steps while staying usable on an 8 GB Mac (16k swapped badly).
DEFAULT_OLLAMA_NUM_CTX = 8192
# First turn on an 8 GB Mac under memory pressure: model load + ~4k prompt
# tokens can take well over a minute.
DEFAULT_OLLAMA_TIMEOUT = 300.0


class OllamaPlannerModel:
    """Local, free and private: Ollama's /api/chat with native tool calling."""

    def __init__(
        self,
        model: str | None = None,
        url: str | None = None,
        num_ctx: int | None = None,
        timeout: float | None = None,
        opener=None,
    ):
        self.name = model or os.environ.get(
            "JARVIS_PLANNER_MODEL", DEFAULT_OLLAMA_PLANNER_MODEL,
        )
        self.url = url or os.environ.get("JARVIS_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        self.num_ctx = int(
            num_ctx or os.environ.get("JARVIS_PLANNER_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX)
        )
        self.timeout = float(
            timeout or os.environ.get("JARVIS_PLANNER_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)
        )
        self._open = opener or urllib.request.urlopen

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        payload = {
            "model": self.name,
            "messages": [self._to_ollama(message) for message in messages],
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise PlannerModelError(
                f"Ollama injoignable ({error}). Lance Ollama puis reessaie.",
                "model_unreachable",
            ) from error
        except (TimeoutError, json.JSONDecodeError) as error:
            raise PlannerModelError(f"Reponse Ollama invalide : {error}") from error

        if "error" in body:
            raise PlannerModelError(f"Erreur Ollama : {body['error']}")

        message = body.get("message") or {}
        calls = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"__invalid_json__": arguments}
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{index}"),
                    name=str(function.get("name") or ""),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return ModelTurn(text=(message.get("content") or "").strip(), tool_calls=calls)

    @staticmethod
    def _to_ollama(message: dict) -> dict:
        role = message["role"]
        if role == "assistant":
            converted = {"role": "assistant", "content": message.get("content", "")}
            if message.get("tool_calls"):
                converted["tool_calls"] = [
                    {"function": {"name": call.name, "arguments": call.arguments}}
                    for call in message["tool_calls"]
                ]
            return converted
        if role == "tool":
            return {
                "role": "tool",
                "content": message["content"],
                "tool_name": message.get("name", ""),
            }
        return {"role": role, "content": message["content"]}


# Google's OpenAI-compatibility endpoint: same request/response shape as OpenAI
# Chat Completions, authenticated with GOOGLE_API_KEY (the key the voice already
# uses). Free tier, no new provider.
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_GEMINI_PLANNER_MODEL = "gemini-3.5-flash"
DEFAULT_OPENAI_TIMEOUT = 120.0


class OpenAIChatPlannerModel:
    """Planner brain over any OpenAI-compatible Chat Completions endpoint.

    The engine already emits OpenAI-style tool schemas and near-OpenAI messages,
    so this adapter is a thin HTTP client (like the Ollama one) with an
    injectable opener for tests. Used for the free Gemini backend via Google's
    OpenAI-compatibility endpoint.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None,
        timeout: float = DEFAULT_OPENAI_TIMEOUT,
        opener=None,
    ):
        self.name = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = float(timeout)
        self._open = opener or urllib.request.urlopen

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        if not self.api_key:
            raise PlannerModelError(
                "Cle API absente pour le planificateur (GOOGLE_API_KEY).",
                "model_api_key_missing",
            )

        payload = {
            "model": self.name,
            "messages": [self._to_openai(message) for message in messages],
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise PlannerModelError(
                f"Erreur HTTP du planificateur ({error.code}).", "model_http_error",
            ) from error
        except urllib.error.URLError as error:
            raise PlannerModelError(
                f"Planificateur injoignable ({error}).", "model_unreachable",
            ) from error
        except (TimeoutError, json.JSONDecodeError) as error:
            raise PlannerModelError(f"Reponse du planificateur invalide : {error}") from error

        if "error" in body:
            raise PlannerModelError(f"Erreur du planificateur : {body['error']}")

        choices = body.get("choices") or []
        if not choices:
            return ModelTurn()
        message = choices[0].get("message") or {}

        calls = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"__invalid_json__": arguments}
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{index}"),
                    name=str(function.get("name") or ""),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return ModelTurn(text=(message.get("content") or "").strip(), tool_calls=calls)

    @staticmethod
    def _to_openai(message: dict) -> dict:
        role = message["role"]
        if role == "assistant":
            converted: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content", "") or "",
            }
            if message.get("tool_calls"):
                converted["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message["tool_calls"]
                ]
            return converted
        if role == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.get("tool_call_id", ""),
                "content": message["content"],
            }
        return {"role": role, "content": message["content"]}


def build_planner_model(backend: str | None = None) -> PlannerModel:
    """Select the planner brain from configuration. Default: local Ollama.

    JARVIS_PLANNER_BACKEND = "ollama" (default, local and free) or "gemini"
    (free via Google's OpenAI-compatible endpoint, reusing GOOGLE_API_KEY).
    """
    choice = (backend or os.environ.get("JARVIS_PLANNER_BACKEND") or "ollama").strip().lower()

    if choice == "gemini":
        return OpenAIChatPlannerModel(
            model=os.environ.get("JARVIS_GEMINI_PLANNER_MODEL", DEFAULT_GEMINI_PLANNER_MODEL),
            base_url=os.environ.get("JARVIS_PLANNER_BASE_URL", GEMINI_OPENAI_BASE),
            api_key=os.environ.get("GOOGLE_API_KEY"),
        )

    return OllamaPlannerModel()
