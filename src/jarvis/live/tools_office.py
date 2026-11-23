"""Live tools, family « office » : Calculs, notes, agenda et mails.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def office_tools(self) -> dict:
    @function_tool(
        name="calculate",
        description=(
            "Calcule une expression arithmetique en local (de maniere sure) : "
            "'combien font 15% de 240', '(12+8)*3', 'racine de 2'. expression : "
            "l'expression mathematique (nombres, + - * / %, puissance **, "
            "parentheses, fonctions sqrt/log/sin/cos/min/max, constantes pi/e)."
        ),
    )
    async def calculate(expression: str) -> dict:
        """Evaluate a safe arithmetic expression locally."""
        debug_live("tool_call", tool="calculate")
        result = await asyncio.to_thread(self.compute.calculate, expression)
        self._debug_tool_result("calculate", result)
        return result.to_livekit_dict()

    @function_tool(
        name="convert_units",
        description=(
            "Convertit une valeur entre unites (longueur, masse, volume, "
            "temperature) en local : 'convertis 10 km en miles', '180 livres en "
            "kg', '72 F en C'. value : le nombre ; from_unit et to_unit : les "
            "unites (km, mi, kg, lb, l, gal, C, F, K...). Pas de devises."
        ),
    )
    async def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert a value between units locally."""
        debug_live("tool_call", tool="convert_units")
        result = await asyncio.to_thread(
            self.compute.convert_units, value, from_unit, to_unit,
        )
        self._debug_tool_result("convert_units", result)
        return result.to_livekit_dict()

    @function_tool(
        name="save_note",
        description=(
            "Enregistre une note dictee par l'utilisateur dans un fichier local "
            "('prends une note : ...', 'note que ...'). text : le contenu de la "
            "note ; title : un titre court optionnel. La note est sauvegardee "
            "dans le dossier Notes de Jarvis ; rien n'est envoye."
        ),
    )
    @self._journaled("save_note")
    async def save_note(text: str, title: str | None = None) -> dict:
        """Save a dictated note to a local Markdown file."""
        debug_live("tool_call", tool="save_note",
                   char_count=len(text) if isinstance(text, str) else None)
        result = await asyncio.to_thread(self.notes.save_note, text, title)
        self._debug_tool_result("save_note", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_notes",
        description=(
            "Liste les notes recemment enregistrees (nom, chemin). Pour 'mes "
            "notes', 'qu'est-ce que j'ai note'."
        ),
    )
    async def list_notes(limit: int = 10) -> dict:
        """List recent saved notes."""
        debug_live("tool_call", tool="list_notes")
        result = await asyncio.to_thread(self.notes.list_notes, limit)
        self._debug_tool_result("list_notes", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_calendar_events",
        description=(
            "Lit les evenements de l'agenda Apple pour un jour : "
            "'qu'est-ce que j'ai aujourd'hui', 'mon agenda de demain'. "
            "day_offset : 0 aujourd'hui, 1 demain, -1 hier."
        ),
    )
    async def list_calendar_events(day_offset: int = 0) -> dict:
        """Read Apple Calendar events for a day."""
        debug_live("tool_call", tool="list_calendar_events", day_offset=day_offset)
        result = await asyncio.to_thread(self.calendar.list_today, day_offset)
        self._debug_tool_result("list_calendar_events", result)
        return result.to_livekit_dict()

    @function_tool(
        name="create_calendar_event",
        description=(
            "PREPARE la creation d'un evenement dans l'agenda Apple, sans le "
            "creer tout de suite. Utilise ce tool pour 'ajoute un rendez-vous', "
            "'cree un evenement'. start et end sont des date/heure ISO 8601 "
            "absolues calculees depuis l'heure actuelle. Renvoie un token et "
            "requires_confirmation : annonce le titre, le jour et l'heure, puis "
            "confirm_action seulement sur un oui clair."
        ),
    )
    @self._journaled("create_calendar_event")
    async def create_calendar_event(title: str, start: str, end: str) -> dict:
        """Prepare an Apple Calendar event for confirmation."""
        debug_live("tool_call", tool="create_calendar_event")
        # Validate eagerly so the user is not asked to confirm a bad event.
        if not isinstance(title, str) or not title.strip():
            return ToolResult.failure(
                action="create_calendar_event",
                message="Le titre de l'evenement est obligatoire.",
                error_code="invalid_title",
            ).to_livekit_dict()
        from jarvis.capabilities.calendar import _parse_iso
        try:
            start_dt = _parse_iso(start)
            end_dt = _parse_iso(end)
        except ValueError:
            return ToolResult.failure(
                action="create_calendar_event",
                message="Les dates doivent etre au format ISO 8601.",
                error_code="invalid_datetime",
            ).to_livekit_dict()
        if end_dt <= start_dt:
            return ToolResult.failure(
                action="create_calendar_event",
                message="La fin doit etre apres le debut.",
                error_code="invalid_range",
            ).to_livekit_dict()

        def _executor():
            return self.calendar.create_event(title, start, end)

        async with self.confirmation_lock:
            token = self.pending_actions.register("create_calendar_event", _executor)
        return ToolResult.success(
            action="create_calendar_event",
            message=(
                "Evenement a confirmer. Annonce le titre, le jour et l'heure, "
                "puis attends la confirmation avant confirm_action."
            ),
            requires_confirmation=True,
            token=token,
            title=title.strip(),
            start=start_dt.isoformat(timespec="minutes"),
            end=end_dt.isoformat(timespec="minutes"),
        ).to_livekit_dict()

    @function_tool(
        name="list_unread_emails",
        description=(
            "Lit les mails non lus de la boite de reception Apple Mail (sujet, "
            "expediteur, date) : 'mes mails non lus', 'qu'est-ce que j'ai recu'. "
            "limit : nombre maximum a remonter."
        ),
    )
    async def list_unread_emails(limit: int = 10) -> dict:
        """Read unread Apple Mail messages."""
        debug_live("tool_call", tool="list_unread_emails")
        result = await asyncio.to_thread(self.mail.list_unread, limit)
        self._debug_tool_result("list_unread_emails", result)
        return result.to_livekit_dict()

    @function_tool(
        name="summarize_unread_emails",
        description=(
            "Resume les mails NON LUS de la boite de reception en une phrase "
            "par mail, en local : 'resume mes mails', 'qu'est-ce que j'ai recu "
            "d'important'. Lit le corps des messages sans les marquer comme lus, "
            "et s'appuie uniquement sur leur contenu. Necessite IMAP configure. "
            "Le resume est genere et doit etre verifie ; aucun mail n'est envoye "
            "ni modifie. limit : nombre maximum de mails a resumer."
        ),
    )
    @self._journaled("summarize_unread_emails")
    async def summarize_unread_emails(limit: int = 5) -> dict:
        """Summarize unread Apple Mail messages with the local model."""
        debug_live("tool_call", tool="summarize_unread_emails", limit=limit)
        result = await asyncio.to_thread(self.mail.summarize_unread, limit)
        self._debug_tool_result("summarize_unread_emails", result)
        return result.to_livekit_dict()

    return {
        "calculate": calculate,
        "convert_units": convert_units,
        "save_note": save_note,
        "list_notes": list_notes,
        "list_calendar_events": list_calendar_events,
        "create_calendar_event": create_calendar_event,
        "list_unread_emails": list_unread_emails,
        "summarize_unread_emails": summarize_unread_emails,
    }
