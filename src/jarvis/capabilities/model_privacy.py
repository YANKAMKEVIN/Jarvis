"""Shared helper: keep sensitive content on-device unless opted in.

Several capabilities ship user content (document text, mail bodies) to the
planner model. By default that model must be local (Ollama on a loopback
address), so private content never leaves the machine; a per-category
environment variable lets the user opt in to a remote backend.

A model with no network endpoint (e.g. an injected test model) counts as local.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_TRUE_VALUES = {"1", "true", "yes", "oui", "on"}


def endpoint_is_local(endpoint: str) -> bool:
    host = (urlparse(endpoint).hostname or "").lower()
    return not host or host in _LOOPBACK_HOSTS or host.endswith(".localhost")


def model_is_local(model) -> bool:
    endpoint = getattr(model, "url", None) or getattr(model, "base_url", None)
    return endpoint is None or endpoint_is_local(endpoint)


def remote_allowed(env_var: str) -> bool:
    return os.environ.get(env_var, "").strip().lower() in _TRUE_VALUES
