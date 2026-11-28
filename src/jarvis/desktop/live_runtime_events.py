"""LiveKit session event handlers and state reporting to the UI."""
from __future__ import annotations

import uuid

from jarvis.desktop.presentation import project_activity, project_task
from jarvis.live.confirmation import note_user_turn_from_text


class LiveRuntimeEventsMixin:
    """LiveKit session event handlers and state reporting to the UI. Mixed into LiveRuntime."""

    def state(self, state):
        audio = self.components.audio if self.components else None
        self.emit({"type": "state", "state": state, "mic_open": bool(audio and audio.mic_open),
                   "input_suppressed": bool(audio and getattr(audio, "input_suppressed", False)),
                   "standby": self._standby()})

    def _standby(self):
        audio = self.components.audio if self.components else None
        return bool(audio and audio.mic_open and getattr(audio, "asleep", False))

    def presentation_state(self):
        if self.agent_state in {'speaking','thinking'}:return self.agent_state
        # Standby looks like a muted avatar; the "standby" flag tells the UI why.
        return 'muted' if self.mute_requested.is_set() or self._standby() else self.agent_state

    def _agent_changed(self, event):
        self.agent_state = event.new_state
        if self.agent_state in {"thinking","speaking"}:self.turn_progress.response()
        if self.ready and not self.stop_requested.is_set():
            self.state(self.presentation_state())

    def _user_changed(self, event):
        previous = self.user_state
        self.user_state = event.new_state
        if previous == "speaking" and self.user_state != "speaking":
            self.emit(self.turn_progress.received())
        echo_free = self.profile.get("headphones") or getattr(self.components and self.components.audio, "echo_cancelled", False) is True
        if self.user_state == "speaking" and self.agent_state == "speaking" and echo_free:
            self.interrupt_requested.set()

    def _can_announce(self):
        """Idle agent, user not mid-sentence, push-to-talk key released."""
        return (self.agent_state == "listening" and self.user_state != "speaking"
                and (not self.ptt_mode_requested.is_set() or self.mute_requested.is_set()))

    def _conversation(self, event):
        item = event.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", "")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            item_id = getattr(item, "id", None)
            if item_id:
                if item_id in self.seen_items:
                    return
                self.seen_items.append(item_id)
            if role == "user":
                self._note_user_turn(text)
                self.emit(self.turn_progress.received())
            else:
                self.turn_progress.response()
                if self.profile.get("quiet"):
                    self.emit({"type":"assistant_text", "text":text[:4000]})
            # Conversation words stay private except opt-in quiet replies in RAM.
            self.emit({"type": "transcript", "role": role,
                       "interrupted": bool(getattr(item, "interrupted", False))})

    def _note_user_turn(self, text):
        registry = getattr(getattr(self.components, "assistant", None), "registry", None)
        note_user_turn_from_text(registry, text)

    def _user_transcribed(self, event):
        # Partial transcripts count: the final one only arrives after the model
        # has answered, i.e. after a confirm_action in the same generation.
        self._note_user_turn(getattr(event, "transcript", ""))

    def _error(self, event):
        if not self.closing and not self.stop_requested.is_set() and not getattr(event.error, "recoverable", False):
            self.failed = True
            self.stop_requested.set()

    def _tools_executed(self, event):
        for call, output in zip(event.function_calls, event.function_call_outputs):
            if call.name in self.observed_tools:
                continue  # Already received directly from the registry, including planner tools.
            activity_id = getattr(call, 'call_id', None) or uuid.uuid4().hex
            self.emit(project_activity(call.name, output.output, activity_id,
                                       'error' if output.is_error else 'result'))

    def _task_progress(self):
        registry = self.components.assistant.registry
        tasks = getattr(registry, 'tasks', None)
        if tasks is not None and (hasattr(tasks, 'progress') or hasattr(tasks, 'presentations')):
            if hasattr(tasks, 'presentations'):
                snapshot = {'type': 'missions', 'missions': [project_task(item) for item in tasks.presentations()]}
            else:
                snapshot = project_task(tasks.presentation() if hasattr(tasks, 'presentation') else tasks.progress())
            if snapshot is not None and snapshot != self.last_task_snapshot:
                self.last_task_snapshot = snapshot
                self.emit(snapshot)

    def _closed(self, event):
        if not self.closing and not self.stop_requested.is_set():
            self.failed = True
            self.stop_requested.set()

    @staticmethod
    def _consume_interruption(task):
        if not task.cancelled():
            task.exception()  # Consume races with a speech that already ended.
