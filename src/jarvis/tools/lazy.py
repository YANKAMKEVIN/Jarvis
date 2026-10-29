from collections.abc import Callable
from typing import Any


class LazyBackend:
    """Builds the real backend on first use, not at construction.

    Loading a macOS framework (CoreGraphics, ApplicationServices) fails off
    macOS; deferring it lets tool registries be built anywhere, and the error
    surfaces only when a tool actually needs the framework.
    """

    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._backend = None

    def __getattr__(self, name: str) -> Any:
        if self._backend is None:
            self._backend = self._factory()

        return getattr(self._backend, name)
