"""One in-memory session shared by the compact and full desktop windows.

The UI owns this state on the main thread. Workers only return results; they
never modify the session. Conversation contents are not persisted or logged.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Job:
    id: int
    command: str
    intent: Any = None


@dataclass
class Turn:
    id: int
    command: str
    time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))
    status: str = "running"
    reply: str = ""
    action: str = ""
    target: str = ""
    channel: str = "text"
    interrupted: bool = False


class DesktopSession:
    def __init__(self):
        self.turns: list[Turn] = []
        self.draft = ""
        self.busy = False
        self.pending: Job | None = None
        self._next_id = 0
        self._active: Job | None = None

    def begin(self, command: str) -> Job:
        command = command.strip()
        if not command:
            raise ValueError("Écrivez une demande.")
        if self.busy or self.pending:
            raise ValueError("Terminez ou annulez la demande en cours.")
        self._next_id += 1
        job = Job(self._next_id, command)
        self.turns.append(Turn(job.id, command))
        self.draft = ""
        self.busy = True
        self._active = job
        return job

    def finish(self, job: Job, result=None, error: str | None = None) -> bool:
        if self._active is not job:
            return False  # Ignore stale deliveries; never alter another request.
        turn = self.turns[-1]
        self.busy = False
        self._active = None
        if error:
            turn.status, turn.reply = "error", error
        elif result.needs_confirmation:
            if result.intent is None or job.intent is not None:
                turn.status = "error"
                turn.reply = "Confirmation indisponible. Aucune nouvelle action lancée."
            else:
                intent = deepcopy(result.intent)
                self.pending = Job(job.id, job.command, intent)
                turn.action = intent.action
                turn.target = str(intent.target or "")
                turn.status, turn.reply = "confirmation", result.message
        else:
            # ExecutionResult does not expose ok/state_confirmed. A response is
            # NOT proof of success: never manufacture a green verified badge.
            turn.status, turn.reply = "response", result.message
            if result.intent is not None:
                turn.action = result.intent.action
                turn.target = str(result.intent.target or "")
        return True

    def confirm(self) -> Job:
        if self.busy or self.pending is None:
            raise ValueError("Aucune action à confirmer.")
        job = self.pending
        self.pending = None  # Consume approval once, before dispatch.
        self.busy = True
        self._active = job
        self.turns[-1].status = "running"
        return job

    def cancel(self):
        if self.busy:
            raise ValueError("Une action en cours ne peut pas encore être interrompue.")
        if self.pending:
            self.turns[-1].status = "cancelled"
            self.turns[-1].reply = "Action annulée avant exécution."
            self.pending = None

    def record_voice(self, role, text, interrupted=False):
        """Append final transcripts in chronological order, without executing text."""
        if self.busy or self.pending:
            raise ValueError("Le moteur texte doit être au repos avant le vocal.")
        if role not in {"user", "assistant"} or not text.strip():
            return
        if (role == "assistant" and self.turns and self.turns[-1].channel == "voice"
                and self.turns[-1].command and not self.turns[-1].reply):
            self.turns[-1].reply = text
            self.turns[-1].interrupted = interrupted
        else:
            self._next_id += 1
            self.turns.append(Turn(self._next_id, text if role == "user" else "",
                status="response", reply=text if role == "assistant" else "",
                channel="voice", interrupted=interrupted))

    def clear(self):
        if self.busy or self.pending:
            raise ValueError("Terminez la demande avant d’effacer cette session.")
        self.turns.clear()
        self.draft = ""
