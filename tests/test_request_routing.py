import unittest
import os
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.executor import CommandExecutor
from jarvis.knowledge.models import KnowledgeAnswer
from jarvis.routing import RequestRouter, RequestType
from jarvis.security import SecurityDecision


class RequestRouterTest(unittest.TestCase):
    def setUp(self):
        self.router = RequestRouter()

    def assert_route(self, command, request_type):
        decision = self.router.classify(command)

        self.assertEqual(decision.request_type, request_type)

    def test_actions(self):
        self.assert_route("Ouvre Safari", RequestType.ACTION)
        self.assert_route("Mets le volume à 30 %", RequestType.ACTION)

    def test_volume_diagnostic_routes(self):
        cases = {
            "Mets le volume du Mac à 40%.": RequestType.ACTION,
            "Mets le volume à 80%.": RequestType.ACTION,
            "Baisse le volume à 20%.": RequestType.ACTION,
            "Coupe le son.": RequestType.ACTION,
            "Quel est le volume actuel ?": RequestType.KNOWLEDGE,
        }

        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assert_route(command, expected)

    def test_stt_mets_confused_as_mais_does_not_route_to_action(self):
        self.assert_route("Mais le volume a 80%.", RequestType.CONVERSATION)

    def test_conversation(self):
        self.assert_route(
            "Aide-moi à rédiger un message",
            RequestType.CONVERSATION,
        )
        self.assert_route(
            "Donne-moi trois idées de noms",
            RequestType.CONVERSATION,
        )
        self.assert_route(
            "Explique-moi simplement ce qu'est un LLM",
            RequestType.CONVERSATION,
        )

    def test_knowledge(self):
        self.assert_route(
            "Qui est le président actuel de la France ?",
            RequestType.KNOWLEDGE,
        )
        self.assert_route(
            "Quelle météo fera-t-il demain ?",
            RequestType.KNOWLEDGE,
        )
        self.assert_route(
            "Quelles sont les actualités aujourd'hui ?",
            RequestType.KNOWLEDGE,
        )
        self.assert_route(
            "Quel est le prix actuel du Bitcoin ?",
            RequestType.KNOWLEDGE,
        )
        self.assert_route(
            "Qui a gagné le match hier ?",
            RequestType.KNOWLEDGE,
        )
        self.assert_route(
            "Comment dit-on au revoir en japonais ?",
            RequestType.KNOWLEDGE,
        )


class FakeBrain:
    def __init__(
        self,
        route_type=RequestType.CONVERSATION,
        detected=None,
        answer="reponse locale",
    ):
        self.route_type = route_type
        self.detected = detected or {
            "action": "conversation",
            "target": None,
        }
        self.answer = answer
        self.detected_commands = []
        self.thought_commands = []

    def route_request(self, message):
        return self._decision(self.route_type)

    def detect_intent(self, message):
        self.detected_commands.append(message)
        return self.detected

    def think(self, message):
        self.thought_commands.append(message)
        return self.answer

    @staticmethod
    def _decision(request_type):
        return type(
            "Decision",
            (),
            {
                "request_type": request_type,
                "reason": "test",
            },
        )()


class RecordingSecurity:
    def __init__(self):
        self.intents = []

    def evaluate(self, intent):
        self.intents.append(intent)
        return SecurityDecision(
            allowed=False,
            requires_confirmation=False,
            reason="blocked in test",
        )


class AllowingSecurity:
    def __init__(self):
        self.intents = []

    def evaluate(self, intent):
        self.intents.append(intent)
        return SecurityDecision(
            allowed=True,
            requires_confirmation=False,
            reason="allowed in test",
        )


class RecordingTools:
    def __init__(self):
        self.calls = []

    def open_app(self, target):
        self.calls.append(("open_app", target))
        return "opened"

    def set_volume(self, level):
        self.calls.append(("set_volume", level))
        return f"volume {level}"

    def mute(self):
        self.calls.append(("mute", None))
        return "muted"


class FakeKnowledgeService:
    def __init__(self):
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        return KnowledgeAnswer(
            "reponse verifiee",
            external_knowledge_retrieved=True,
        )


class CommandExecutorRoutingTest(unittest.TestCase):
    def test_knowledge_returns_structured_external_signal(self):
        brain = FakeBrain(route_type=RequestType.KNOWLEDGE)
        knowledge = FakeKnowledgeService()
        executor = CommandExecutor(
            brain=brain,
            security=RecordingSecurity(),
            tools=RecordingTools(),
            knowledge_service=knowledge,
        )

        result = executor.execute("Comment dit-on au revoir en japonais ?")

        self.assertEqual(result.request_type, RequestType.KNOWLEDGE)
        self.assertTrue(result.requires_external_knowledge)
        self.assertTrue(result.external_knowledge_retrieved)
        self.assertEqual(knowledge.questions, [
            "Comment dit-on au revoir en japonais ?",
        ])
        self.assertEqual(brain.detected_commands, [])
        self.assertEqual(brain.thought_commands, [])

    def test_conversation_uses_local_brain_without_intent_detection(self):
        brain = FakeBrain(route_type=RequestType.CONVERSATION)
        executor = CommandExecutor(
            brain=brain,
            security=RecordingSecurity(),
            tools=RecordingTools(),
            knowledge_service=FakeKnowledgeService(),
        )

        result = executor.execute("Aide-moi à rédiger un message")

        self.assertEqual(result.request_type, RequestType.CONVERSATION)
        self.assertEqual(result.message, "reponse locale")
        self.assertEqual(brain.thought_commands, [
            "Aide-moi à rédiger un message",
        ])
        self.assertEqual(brain.detected_commands, [])

    def test_unknown_dangerous_action_still_goes_through_security(self):
        brain = FakeBrain(
            route_type=RequestType.ACTION,
            detected={
                "action": "delete_everything",
                "target": "/",
            },
        )
        security = RecordingSecurity()
        tools = RecordingTools()
        executor = CommandExecutor(
            brain=brain,
            security=security,
            tools=tools,
            knowledge_service=FakeKnowledgeService(),
        )

        result = executor.execute("Supprime tout")

        self.assertEqual(result.request_type, RequestType.ACTION)
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "delete_everything")
        self.assertEqual(tools.calls, [])
        self.assertIn("pas autorisee", result.message)

    def test_volume_action_executes_only_after_action_intent(self):
        brain = FakeBrain(
            route_type=RequestType.ACTION,
            detected={
                "action": "set_volume",
                "target": "80",
            },
        )
        tools = RecordingTools()
        executor = CommandExecutor(
            brain=brain,
            security=AllowingSecurity(),
            tools=tools,
            knowledge_service=FakeKnowledgeService(),
        )

        result = executor.execute("Mets le volume du Mac à 80%.")

        self.assertEqual(result.request_type, RequestType.ACTION)
        self.assertEqual(result.intent.action, "set_volume")
        self.assertEqual(result.intent.target, "80")
        self.assertEqual(tools.calls, [("set_volume", 80)])

    def test_action_route_can_fallback_to_llm_without_system_action(self):
        brain = FakeBrain(
            route_type=RequestType.ACTION,
            detected={
                "action": "conversation",
                "target": None,
            },
            answer="Le volume est à 80%.",
        )
        tools = RecordingTools()
        executor = CommandExecutor(
            brain=brain,
            security=AllowingSecurity(),
            tools=tools,
            knowledge_service=FakeKnowledgeService(),
        )

        result = executor.execute("Mets le volume du Mac à 80%.")

        self.assertEqual(result.request_type, RequestType.CONVERSATION)
        self.assertEqual(result.message, "Le volume est à 80%.")
        self.assertEqual(brain.thought_commands, [
            "Mets le volume du Mac à 80%.",
        ])
        self.assertEqual(tools.calls, [])

    def test_routing_debug_disabled_outputs_nothing(self):
        brain = FakeBrain(route_type=RequestType.CONVERSATION)
        executor = CommandExecutor(
            brain=brain,
            security=AllowingSecurity(),
            tools=RecordingTools(),
            knowledge_service=FakeKnowledgeService(),
        )

        with patch.dict(os.environ, {}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                executor.execute("Mais le volume a 80%.")

        self.assertEqual(output.getvalue(), "")

    def test_routing_debug_shows_fallback_to_llm_without_system_action(self):
        brain = FakeBrain(
            route_type=RequestType.CONVERSATION,
            answer="Le volume est à 80%.",
        )
        executor = CommandExecutor(
            brain=brain,
            security=AllowingSecurity(),
            tools=RecordingTools(),
            knowledge_service=FakeKnowledgeService(),
        )

        with patch.dict(os.environ, {"JARVIS_DEBUG_ROUTING": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                executor.execute("Mais le volume a 80%.")

        debug_output = output.getvalue()

        self.assertIn("JARVIS ROUTING DEBUG", debug_output)
        self.assertIn("text: Mais le volume a 80%.", debug_output)
        self.assertIn("request_type: conversation", debug_output)
        self.assertIn("system_action_executed: False", debug_output)
        self.assertIn("fallback_to_llm: True", debug_output)

    def test_routing_debug_shows_detected_volume_action(self):
        brain = FakeBrain(
            route_type=RequestType.ACTION,
            detected={
                "action": "set_volume",
                "target": "80",
            },
        )
        executor = CommandExecutor(
            brain=brain,
            security=AllowingSecurity(),
            tools=RecordingTools(),
            knowledge_service=FakeKnowledgeService(),
        )

        with patch.dict(os.environ, {"JARVIS_DEBUG_ROUTING": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                executor.execute("Mets le volume du Mac à 80%.")

        debug_output = output.getvalue()

        self.assertIn("request_type: action", debug_output)
        self.assertIn("action: set_volume", debug_output)
        self.assertIn("target: 80", debug_output)
        self.assertIn("system_action_executed: True", debug_output)
        self.assertIn("fallback_to_llm: False", debug_output)


if __name__ == "__main__":
    unittest.main()
