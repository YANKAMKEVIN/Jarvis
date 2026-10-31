import asyncio
import unittest

from jarvis.capabilities.knowledge import KnowledgeCapability, web_announcement_for
from jarvis.capabilities.results import ToolResult
from jarvis.knowledge.models import KnowledgeAnswer, SourceReference
from jarvis.live.registry import create_live_registry


class FakeService:
    def __init__(self, answer=None, error=None):
        self.answer_value = answer
        self.error = error
        self.calls = []

    def answer(self, question):
        self.calls.append(question)
        if self.error is not None:
            raise self.error
        return self.answer_value


class KnowledgeCapabilityTests(unittest.TestCase):
    def test_answer_with_sources_is_confirmed(self):
        answer = KnowledgeAnswer(
            message="Trois titres à la une aujourd'hui.",
            sources=[
                SourceReference(title="Le Monde", url="https://lemonde.fr/a"),
                SourceReference(title="France 24", url="https://france24.com/b"),
            ],
            external_knowledge_retrieved=True,
        )
        capability = KnowledgeCapability(FakeService(answer=answer))

        result = capability.answer("les nouvelles")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "web_answer")
        self.assertEqual(result.data["source_count"], 2)
        self.assertTrue(result.data["external_knowledge_retrieved"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(result.data["sources"][0]["url"], "https://lemonde.fr/a")

    def test_answer_without_retrieval_is_unconfirmed(self):
        answer = KnowledgeAnswer(
            message="Je n'arrive pas à accéder à ma source de recherche.",
            sources=[],
            external_knowledge_retrieved=False,
        )
        capability = KnowledgeCapability(FakeService(answer=answer))

        result = capability.answer("meteo demain")

        self.assertTrue(result.ok)
        self.assertFalse(result.data["external_knowledge_retrieved"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(result.data["source_count"], 0)

    def test_blank_question_rejected(self):
        capability = KnowledgeCapability(FakeService())
        result = capability.answer("   ")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_question")

    def test_service_exception_becomes_failure(self):
        capability = KnowledgeCapability(FakeService(error=RuntimeError("boom")))
        result = capability.answer("prix du bitcoin")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


class WebAnnouncementTests(unittest.TestCase):
    def test_retrieved_announcement_carries_message_and_offer(self):
        result = ToolResult.success(
            action="web_answer",
            message="Voici les grands titres.",
            sources=[{"title": "x", "url": "https://x"}],
            source_count=1,
            external_knowledge_retrieved=True,
            state_confirmed=True,
        )
        text = web_announcement_for(result)
        self.assertIn("Voici les grands titres.", text)
        self.assertIn("source", text.lower())

    def test_unretrieved_announcement_says_it_failed(self):
        result = ToolResult.success(
            action="web_answer",
            message="Pas de source.",
            sources=[],
            source_count=0,
            external_knowledge_retrieved=False,
            state_confirmed=False,
        )
        text = web_announcement_for(result)
        self.assertIn("n'a pas abouti", text)


class FakeKnowledge:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def answer(self, question):
        self.calls.append(question)
        return self.result


class SearchTheWebToolTests(unittest.TestCase):
    def _registry_with(self, knowledge):
        registry = create_live_registry(knowledge_capability=knowledge)
        return registry

    def test_background_search_acks_then_announces(self):
        result = ToolResult.success(
            action="web_answer",
            message="Trois nouvelles ce matin.",
            sources=[{"title": "Le Monde", "url": "https://lemonde.fr/a"}],
            source_count=1,
            external_knowledge_retrieved=True,
            state_confirmed=True,
        )
        knowledge = FakeKnowledge(result)

        async def scenario():
            registry = self._registry_with(knowledge)
            spoken = []

            async def notifier(instructions):
                spoken.append(instructions)

            registry.set_task_notifier(notifier)
            tools = {tool.info.name: tool for tool in registry.livekit_tools()}
            ack = await tools["search_the_web"]("les nouvelles")
            await registry._web_task
            return ack, spoken

        ack, spoken = asyncio.run(scenario())

        self.assertTrue(ack["ok"])
        self.assertTrue(ack["search_started"])
        self.assertEqual(knowledge.calls, ["les nouvelles"])
        self.assertEqual(len(spoken), 1)
        self.assertIn("Trois nouvelles ce matin.", spoken[0])

    def test_blank_question_rejected(self):
        knowledge = FakeKnowledge(None)

        async def scenario():
            registry = self._registry_with(knowledge)
            tools = {tool.info.name: tool for tool in registry.livekit_tools()}
            return await tools["search_the_web"]("  ")

        ack = asyncio.run(scenario())
        self.assertFalse(ack["ok"])
        self.assertEqual(ack["error_code"], "invalid_question")
        self.assertEqual(knowledge.calls, [])

    def test_refuses_when_a_search_is_already_running(self):
        knowledge = FakeKnowledge(
            ToolResult.success(
                action="web_answer",
                message="x",
                sources=[],
                source_count=0,
                external_knowledge_retrieved=True,
                state_confirmed=True,
            )
        )

        async def scenario():
            registry = self._registry_with(knowledge)
            tools = {tool.info.name: tool for tool in registry.livekit_tools()}

            async def busy():
                await asyncio.sleep(0.2)

            registry._web_task = asyncio.get_running_loop().create_task(busy())
            ack = await tools["search_the_web"]("les nouvelles")
            registry._web_task.cancel()
            return ack

        ack = asyncio.run(scenario())
        self.assertFalse(ack["ok"])
        self.assertEqual(ack["error_code"], "web_search_running")
        self.assertEqual(knowledge.calls, [])


class FakeMemory:
    """Minimal memory so journaling in the registry is a no-op in tests."""

    def log_action(self, *args, **kwargs):
        return None

    def resolve_person(self, name, app_name=None):
        return None


class SendLastWebResultTests(unittest.TestCase):
    def _result(self):
        return ToolResult.success(
            action="web_answer",
            message="Trois nouvelles ce matin.",
            sources=[
                {"title": "Le Monde", "url": "https://lemonde.fr/a"},
                {"title": "AFP", "url": "https://afp.com/b"},
            ],
            source_count=2,
            external_knowledge_retrieved=True,
            state_confirmed=True,
        )

    def test_no_recent_result_is_rejected(self):
        async def scenario():
            registry = create_live_registry(
                knowledge_capability=FakeKnowledge(self._result()),
                memory_capability=FakeMemory(),
            )
            tools = {tool.info.name: tool for tool in registry.livekit_tools()}
            return await tools["send_last_web_result"]("WhatsApp")

        ack = asyncio.run(scenario())
        self.assertFalse(ack["ok"])
        self.assertEqual(ack["error_code"], "no_recent_web_result")

    def test_sends_last_result_verbatim_through_confirmation_flow(self):
        async def scenario():
            registry = create_live_registry(
                knowledge_capability=FakeKnowledge(self._result()),
                memory_capability=FakeMemory(),
            )

            async def notifier(_instructions):
                return None

            registry.set_task_notifier(notifier)
            tools = {tool.info.name: tool for tool in registry.livekit_tools()}
            await tools["search_the_web"]("les nouvelles")
            await registry._web_task
            # recipient=None skips UI verification; no Mac is touched.
            prepared = await tools["send_last_web_result"]("WhatsApp")
            return registry._last_web_result_text, prepared

        text, prepared = asyncio.run(scenario())

        self.assertIn("Trois nouvelles ce matin.", text)
        self.assertIn("https://lemonde.fr/a", text)  # source appended verbatim
        self.assertTrue(prepared["ok"])
        self.assertTrue(prepared["requires_confirmation"])
        self.assertTrue(prepared["token"])
        self.assertEqual(prepared["target_app"], "WhatsApp")


if __name__ == "__main__":
    unittest.main()
