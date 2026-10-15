from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.memory.guard import contains_secret
from jarvis.memory.store import MemoryError, MemoryStore
from jarvis.tools.accessibility import normalize_text


class MemoryCapability:
    """Long-term memory exposed as tools, plus helpers other tools apply locally.

    Two write paths: remember() for something the user explicitly asked Jarvis
    to keep, and the propose/confirm flow (handled by the registry) for
    anything Jarvis inferred, which is only stored after the user agrees.
    Secrets are always refused.
    """

    def __init__(self, store: MemoryStore | None = None):
        self.store = store if store is not None else MemoryStore()

    def remember(
        self,
        kind: str,
        subject: str,
        content: str,
        source: str = "user",
    ) -> ToolResult:
        refusal = self.check_storable(subject, content, action="remember")
        if refusal is not None:
            return refusal

        try:
            memory, created = self.store.remember(kind, subject, content, source)
        except MemoryError as error:
            return self._memory_failure("remember", error)
        except Exception as error:
            return self._system_error_result("remember", error)

        return ToolResult.success(
            action="remember",
            message=(
                "Souvenir enregistre." if created else "Souvenir existant mis a jour."
            ),
            memory=memory.to_dict(),
            created=created,
            command_executed=True,
            state_confirmed=True,
        )

    def check_storable(self, subject, content, action: str) -> ToolResult | None:
        """Refusal result if the memory must not be stored, else None."""
        if contains_secret(subject, content):
            return ToolResult.failure(
                action=action,
                message=(
                    "Je ne garde jamais de mot de passe, code, numero de carte, "
                    "IBAN ou cle d'acces en memoire. Rien n'a ete enregistre."
                ),
                error_code="secret_refused",
            )
        return None

    def check_proposal(self, kind, subject, content) -> ToolResult | None:
        """Validate an inferred memory before asking the user to confirm it."""
        refusal = self.check_storable(subject, content, action="propose_memory")
        if refusal is not None:
            return refusal
        try:
            MemoryStore.validate(kind, subject, content, "inferred")
        except MemoryError as error:
            return self._memory_failure("propose_memory", error)
        return None

    def recall(self, query: str, kind: str | None = None) -> ToolResult:
        try:
            memories = self.store.search(query, kind)
        except MemoryError as error:
            return self._memory_failure("recall", error)
        except Exception as error:
            return self._system_error_result("recall", error)

        return ToolResult.success(
            action="recall",
            message=(
                f"{len(memories)} souvenir(s) trouve(s)."
                if memories
                else "Aucun souvenir ne correspond."
            ),
            memories=[memory.to_dict() for memory in memories],
            count=len(memories),
        )

    def list_memories(self, kind: str | None = None) -> ToolResult:
        try:
            memories = self.store.list(kind)
        except MemoryError as error:
            return self._memory_failure("list_memories", error)
        except Exception as error:
            return self._system_error_result("list_memories", error)

        return ToolResult.success(
            action="list_memories",
            message=(
                f"{len(memories)} souvenir(s)." if memories else "Aucun souvenir enregistre."
            ),
            memories=[memory.to_dict() for memory in memories],
            count=len(memories),
        )

    def forget(self, memory_id: int | None = None, query: str | None = None) -> ToolResult:
        try:
            if memory_id is not None:
                target = self.store.get(memory_id)
            elif isinstance(query, str) and query.strip():
                matches = self.store.search(query)
                if len(matches) > 1:
                    # Never delete on a guess: let the user pick.
                    return ToolResult(
                        ok=False,
                        action="forget",
                        message=(
                            "Plusieurs souvenirs correspondent. Demande lequel "
                            "oublier puis rappelle forget avec son memory_id."
                        ),
                        data={"candidates": [m.to_dict() for m in matches]},
                        error_code="ambiguous_memory",
                    )
                target = matches[0] if matches else None
            else:
                return ToolResult.failure(
                    action="forget",
                    message="Indique le souvenir a oublier (memory_id ou query).",
                    error_code="invalid_forget_target",
                )

            if target is None:
                return ToolResult.failure(
                    action="forget",
                    message="Aucun souvenir correspondant, rien n'a ete oublie.",
                    error_code="memory_not_found",
                )

            self.store.delete(target.id)
            still_there = self.store.get(target.id) is not None
        except MemoryError as error:
            return self._memory_failure("forget", error)
        except Exception as error:
            return self._system_error_result("forget", error)

        return ToolResult.success(
            action="forget",
            message="Souvenir oublie." if not still_there else "Suppression non confirmee.",
            forgotten=target.to_dict(),
            command_executed=True,
            state_confirmed=not still_there,
        )

    def log_action(self, tool: str, target: str | None, result: dict | None) -> None:
        """Journal one action (never its content). Never raises."""
        try:
            ok = bool(result.get("ok")) if isinstance(result, dict) else False
            error_code = result.get("error_code") if isinstance(result, dict) else None
            self.store.log_episode(tool, target, ok, error_code)
        except Exception:
            pass

    def recent_activity(self, limit: int = 10) -> ToolResult:
        try:
            episodes = self.store.recent_episodes(limit)
        except Exception as error:
            return self._system_error_result("recent_activity", error)

        return ToolResult.success(
            action="recent_activity",
            message=(
                f"{len(episodes)} action(s) recente(s), de la plus recente a la plus ancienne."
                if episodes
                else "Aucune action enregistree dans le journal."
            ),
            episodes=[episode.to_dict() for episode in episodes],
            count=len(episodes),
        )

    def preferred_media_app(self) -> str | None:
        """'Spotify' / 'Music' from a stored music preference, else None.

        When both players are named, the first one mentioned wins
        ("Spotify plutot qu'Apple Music"). Never raises.
        """
        try:
            memories = self.store.search("musique music", kind="preference", limit=5)
        except Exception:
            return None

        for memory in memories:
            text = normalize_text(f"{memory.subject} {memory.content}")
            positions = {
                app: text.find(token)
                for app, token in (("Spotify", "spotify"), ("Music", "apple music"))
                if token in text
            }
            if positions:
                return min(positions, key=positions.get)
        return None

    def resolve_person(self, name: str) -> str | None:
        """Contact name stored for an alias ("ma mere" -> "Maman"), else None.

        Applied locally by messaging so the model never needs the memory.
        Failures are swallowed: memory must never block a send flow.
        """
        try:
            memory = self.store.find_by_subject("person", name)
        except Exception:
            return None
        return memory.content if memory is not None else None

    @staticmethod
    def _memory_failure(action: str, error: MemoryError) -> ToolResult:
        return ToolResult.failure(action=action, message=error.message, error_code=error.code)

    @staticmethod
    def _system_error_result(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec de l'acces a la memoire : {error}",
            error_code="memory_unavailable",
        )
