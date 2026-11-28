"""Scheduled messages and reminders tools.

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from jarvis.schedule.reminders import ReminderError
from jarvis.schedule.store import ScheduleError
from jarvis.schedule.store import parse_due_at

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
    @function_tool(
        name="schedule_message",
        description=(
            "PLANIFIE l'envoi d'un message a un destinataire a une date/heure "
            "future, SANS l'envoyer maintenant. Utilise ce tool quand "
            "l'utilisateur dit 'envoie X a Marie demain a 9h', 'programme un "
            "message pour ce soir'. Calcule when comme une date/heure absolue au "
            "format ISO 8601 (par exemple 2026-10-16T09:00) a partir de l'heure "
            "actuelle. Comme tout envoi, ce tool renvoie un token et "
            "requires_confirmation : annonce a l'utilisateur l'application, le "
            "destinataire, le contenu et l'heure, puis attends un oui clair avant "
            "confirm_action(token). Le message partira tout seul a l'heure dite si "
            "le Mac est allume, deverrouille et WhatsApp lance (pour Telegram, "
            "le Mac allume et connecte suffit) ; le destinataire "
            "sera revérifie a ce moment-la. app_name par defaut WhatsApp, ou "
            "Telegram. "
            "repeat : 'none' (defaut), 'daily' ou 'weekly' pour un envoi recurrent."
        ),
    )
    @registry._journaled("schedule_message", "app_name")
    async def schedule_message(
        recipient: str,
        text: str,
        when: str,
        app_name: str = "WhatsApp",
        repeat: str = "none",
    ) -> dict:
        """Register a future send for confirmation; nothing is scheduled yet."""
        debug_live(
            "tool_call",
            tool="schedule_message",
            app_name=app_name,
            text_length=len(text) if isinstance(text, str) else None,
        )
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                action="schedule_message",
                message="Le message a planifier est obligatoire.",
                error_code="invalid_text",
            ).to_livekit_dict()
        if not isinstance(recipient, str) or not recipient.strip():
            return ToolResult.failure(
                action="schedule_message",
                message="Le destinataire est obligatoire.",
                error_code="invalid_recipient",
            ).to_livekit_dict()
        try:
            due_at = parse_due_at(when)
        except ScheduleError as error:
            return ToolResult.failure(
                action="schedule_message",
                message=error.message,
                error_code=error.code,
            ).to_livekit_dict()
        recurrence = (repeat or "none").strip().lower()
        if recurrence not in ("none", "daily", "weekly"):
            return ToolResult.failure(
                action="schedule_message",
                message="La recurrence doit etre none, daily ou weekly.",
                error_code="invalid_recurrence",
            ).to_livekit_dict()

        if not registry._messaging_check("supports_verified_send", app_name):
            return ToolResult.failure(
                action="schedule_message",
                message=(
                    f"Jarvis ne sait pas envoyer de message verifie sur {app_name}. "
                    "Applications prises en charge : WhatsApp et Telegram."
                ),
                error_code="messaging_app_unsupported",
            ).to_livekit_dict()

        # Apply memory locally: "ma mere" -> stored contact name.
        async with registry.memory_lock:
            resolved = await asyncio.to_thread(
                registry.memory.resolve_person, recipient, app_name,
            )
        target_recipient = resolved or recipient.strip()

        def _executor():
            row = registry.schedule_store.add(
                app_name, target_recipient, text, due_at, recurrence,
            )
            return ToolResult.success(
                action="schedule_message",
                message="Message planifie.",
                scheduled_id=row["id"],
                recipient=row["recipient"],
                due_at=row["due_at"],
                app=row["app"],
                recurrence=row["recurrence"],
            )

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("schedule_message", _executor)
        return ToolResult.success(
            action="schedule_message",
            message=(
                "Envoi planifie a confirmer. Annonce le destinataire, le contenu "
                "et l'heure, puis attends la confirmation avant confirm_action."
            ),
            requires_confirmation=True,
            token=token,
            target_app=app_name,
            due_at=due_at,
            text_length=len(text),
            recurrence=recurrence,
            recipient_from_memory=bool(resolved),
        ).to_livekit_dict()

    @function_tool(
        name="list_scheduled_messages",
        description=(
            "Liste les messages planifies en attente d'envoi (id, destinataire, "
            "heure prevue, contenu). Utilise ce tool pour 'quels messages sont "
            "programmes', 'qu'est-ce que tu dois envoyer plus tard'."
        ),
    )
    async def list_scheduled_messages() -> dict:
        """Return pending scheduled messages."""
        debug_live("tool_call", tool="list_scheduled_messages")
        rows = await asyncio.to_thread(registry.schedule_store.list, "pending")
        sending = await asyncio.to_thread(registry.schedule_store.list, "sending")
        failed = await asyncio.to_thread(registry.schedule_store.list, "failed")
        review = sending + [row for row in failed if (row.get("last_error") or "").startswith("envoi incertain")]
        review_items = [{"id": row["id"], "recipient": row["recipient"],
                         "status": row["status"], "reason": row.get("last_error") or "Envoi en cours ou interrompu : resultat a verifier."}
                        for row in review]
        messages = [
            {
                "id": row["id"],
                "app": row["app"],
                "recipient": row["recipient"],
                "due_at": row["due_at"],
                "text": row["text"],
            }
            for row in rows
        ]
        return ToolResult.success(
            action="list_scheduled_messages",
            message=f"{len(messages)} message(s) planifie(s) en attente. {len(review_items)} envoi(s) a verifier ; aucune relance automatique pour ceux-ci.",
            scheduled=messages,
            count=len(messages),
            requires_review=review_items,
            review_count=len(review_items),
        ).to_livekit_dict()

    @function_tool(
        name="cancel_scheduled_message",
        description=(
            "Annule un message planifie par son id (obtenu via "
            "list_scheduled_messages). Utilise ce tool pour 'annule le message "
            "prevu pour Marie', 'ne l'envoie finalement pas'."
        ),
    )
    @registry._journaled("cancel_scheduled_message")
    async def cancel_scheduled_message(message_id: int) -> dict:
        """Cancel a still-pending scheduled message."""
        debug_live("tool_call", tool="cancel_scheduled_message")
        cancelled = await asyncio.to_thread(registry.schedule_store.cancel, message_id)
        if not cancelled:
            return ToolResult.failure(
                action="cancel_scheduled_message",
                message="Aucun message planifie en attente avec cet id.",
                error_code="scheduled_message_not_found",
            ).to_livekit_dict()
        return ToolResult.success(
            action="cancel_scheduled_message",
            message="Message planifie annule.",
            scheduled_id=message_id,
        ).to_livekit_dict()

    @function_tool(
        name="set_reminder",
        description=(
            "Programme un RAPPEL personnel qui declenchera une notification "
            "macOS a l'heure dite ('rappelle-moi dans 20 minutes de sortir le "
            "gateau', 'rappelle-moi demain a 8h d'appeler le dentiste'). Calcule "
            "when comme une date/heure absolue ISO 8601 a partir de l'heure "
            "actuelle. C'est une note a soi-meme (aucun envoi exterieur), donc "
            "pas de confirmation : le rappel est enregistre directement. Il se "
            "declenche si le Mac est allume a ce moment-la. repeat : 'none' "
            "(defaut), 'daily' ou 'weekly' pour un rappel recurrent."
        ),
    )
    @registry._journaled("set_reminder")
    async def set_reminder(text: str, when: str, repeat: str = "none") -> dict:
        """Store a personal reminder that fires a macOS notification."""
        debug_live("tool_call", tool="set_reminder", text_length=len(text) if isinstance(text, str) else None)
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                action="set_reminder",
                message="Le texte du rappel est obligatoire.",
                error_code="invalid_text",
            ).to_livekit_dict()
        try:
            due_at = parse_due_at(when)
        except ScheduleError as error:
            return ToolResult.failure(
                action="set_reminder", message=error.message, error_code=error.code,
            ).to_livekit_dict()
        try:
            row = await asyncio.to_thread(registry.reminder_store.add, text, due_at, repeat)
        except ReminderError as error:
            return ToolResult.failure(
                action="set_reminder", message=error.message, error_code=error.code,
            ).to_livekit_dict()
        return ToolResult.success(
            action="set_reminder",
            message="Rappel enregistre.",
            reminder_id=row["id"],
            due_at=row["due_at"],
            recurrence=row["recurrence"],
        ).to_livekit_dict()

    @function_tool(
        name="list_reminders",
        description=(
            "Liste les rappels personnels en attente (id, heure, texte). Pour "
            "'quels rappels j'ai', 'qu'est-ce que tu dois me rappeler'."
        ),
    )
    async def list_reminders() -> dict:
        """Return pending reminders."""
        debug_live("tool_call", tool="list_reminders")
        rows = await asyncio.to_thread(registry.reminder_store.list, "pending")
        reminders = [
            {"id": r["id"], "due_at": r["due_at"], "text": r["text"]} for r in rows
        ]
        return ToolResult.success(
            action="list_reminders",
            message=f"{len(reminders)} rappel(s) en attente.",
            reminders=reminders,
            count=len(reminders),
        ).to_livekit_dict()

    @function_tool(
        name="cancel_reminder",
        description=(
            "Annule un rappel par son id (obtenu via list_reminders). Pour "
            "'annule le rappel du dentiste', 'oublie ce rappel'."
        ),
    )
    @registry._journaled("cancel_reminder")
    async def cancel_reminder(reminder_id: int) -> dict:
        """Cancel a pending reminder."""
        debug_live("tool_call", tool="cancel_reminder")
        cancelled = await asyncio.to_thread(registry.reminder_store.cancel, reminder_id)
        if not cancelled:
            return ToolResult.failure(
                action="cancel_reminder",
                message="Aucun rappel en attente avec cet id.",
                error_code="reminder_not_found",
            ).to_livekit_dict()
        return ToolResult.success(
            action="cancel_reminder",
            message="Rappel annule.",
            reminder_id=reminder_id,
        ).to_livekit_dict()

    return {
        "schedule_message": schedule_message,
        "list_scheduled_messages": list_scheduled_messages,
        "cancel_scheduled_message": cancel_scheduled_message,
        "set_reminder": set_reminder,
        "list_reminders": list_reminders,
        "cancel_reminder": cancel_reminder,
    }
