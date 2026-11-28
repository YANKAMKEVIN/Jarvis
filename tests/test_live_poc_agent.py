"""Live POC: agent entry point, assistant class and tool catalogue."""
import asyncio
import pathlib
import unittest
from livekit.agents import AgentServer
from livekit.agents.cli.discover import ModuleData, get_app_name
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.live import agent
from jarvis.live.config import LiveConfig, debug_live
from jarvis.live.prompts import LIVE_SYSTEM_PROMPT
from jarvis.live.tools import ToolRegistry
from jarvis.voice_mode import VoiceMode
from live_poc_fakes_core import (
    EXPECTED_LIVE_TOOL_NAMES,
    FakeAgentBase,
    FakeGoogle,
    FakeJobContext,
    RecordingAgentSession,
)


class LivePocAgentTest(unittest.TestCase):
    def test_realtime_model_is_created_from_config(self):
        fake_google = FakeGoogle()
        config = LiveConfig(
            model="gemini-test-live",
            voice="Aoede",
            temperature=0.5,
            agent_name="jarvis-test",
        )

        model = agent.create_realtime_model(fake_google, config)

        self.assertEqual(model["type"], "realtime-model")
        self.assertEqual(
            fake_google.realtime.created,
            [
                {
                    "model": "gemini-test-live",
                    "voice": "Aoede",
                    "temperature": 0.5,
                    "instructions": LIVE_SYSTEM_PROMPT,
                }
            ],
        )

    def test_assistant_class_uses_minimal_live_prompt(self):
        assistant_class = agent.create_assistant_class(FakeAgentBase)

        assistant = assistant_class()

        self.assertEqual(assistant.kwargs["instructions"], LIVE_SYSTEM_PROMPT)
        self.assertEqual(
            sorted(tool.info.name for tool in assistant.kwargs["tools"]),
            EXPECTED_LIVE_TOOL_NAMES,
        )

    def test_live_prompt_requires_fresh_state_tools_for_current_state(self):
        self.assertIn("état actuel du Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_media_state pour le média", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_volume pour le volume", LIVE_SYSTEM_PROMPT)
        self.assertIn("is_app_running pour une application", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_battery_status pour la batterie", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_brightness pour la luminosité", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_system_info pour les informations du Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_active_window pour la fenêtre active", LIVE_SYSTEM_PROMPT)
        self.assertIn("appelle uniquement le tool d'action média", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne lance pas get_media_state en parallèle", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour changer la luminosité", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour verrouiller le Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn("locked=null", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais que le Mac est verrouillé", LIVE_SYSTEM_PROMPT)
        self.assertIn("la commande a été envoyée", LIVE_SYSTEM_PROMPT)
        self.assertIn("n'a pas pu être confirmé", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour contrôler les fenêtres", LIVE_SYSTEM_PROMPT)
        self.assertIn("maximize_window agrandit la fenêtre sans plein écran", LIVE_SYSTEM_PROMPT)
        self.assertIn("move_window avec position=fullscreen", LIVE_SYSTEM_PROMPT)
        self.assertIn("tool de fenêtre retourne state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn('Ne dis jamais "je vois"', LIVE_SYSTEM_PROMPT)
        self.assertIn("je confirme visuellement", LIVE_SYSTEM_PROMPT)
        self.assertIn("d'après l'état de la fenêtre", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour les fichiers et dossiers", LIVE_SYSTEM_PROMPT)
        self.assertIn("état actuel du filesystem", LIVE_SYSTEM_PROMPT)
        self.assertIn("chemins absolus retournes par les tools Files", LIVE_SYSTEM_PROMPT)
        self.assertIn("ambiguous_path", LIVE_SYSTEM_PROMPT)
        self.assertIn("contenu ACTUEL du presse-papiers", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_clipboard_text", LIVE_SYSTEM_PROMPT)
        self.assertIn("set_clipboard_text", LIVE_SYSTEM_PROMPT)
        self.assertIn("clear_clipboard", LIVE_SYSTEM_PROMPT)
        self.assertIn("truncated=true", LIVE_SYSTEM_PROMPT)
        self.assertIn("content_type=no_text_detected", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne reponds jamais depuis l'historique", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour les actions clavier", LIVE_SYSTEM_PROMPT)
        self.assertIn("fenetre actuellement active", LIVE_SYSTEM_PROMPT)
        self.assertIn("focus_window d'abord et attends son resultat", LIVE_SYSTEM_PROMPT)
        self.assertIn("type_text n'appuie jamais automatiquement sur Entree", LIVE_SYSTEM_PROMPT)
        self.assertIn("state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn("command_executed=true signifie uniquement", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais que l'effet dans l'application s'est produit", LIVE_SYSTEM_PROMPT)
        self.assertIn("c'est copie", LIVE_SYSTEM_PROMPT)
        self.assertIn("j'ai annule", LIVE_SYSTEM_PROMPT)
        self.assertIn("cela a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("normalement", LIVE_SYSTEM_PROMPT)
        self.assertIn("probablement", LIVE_SYSTEM_PROMPT)
        self.assertIn("ca devrait etre bon", LIVE_SYSTEM_PROMPT)
        self.assertIn("la commande clavier a ete envoyee", LIVE_SYSTEM_PROMPT)
        self.assertIn("texte sensible inutilement", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour la souris", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_mouse_position", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne deduis jamais cette position depuis l'historique", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne devine jamais de coordonnees", LIVE_SYSTEM_PROMPT)
        self.assertIn("MouseCapability ne comprend pas l'interface", LIVE_SYSTEM_PROMPT)
        self.assertIn("attends son resultat", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne lance jamais move_mouse et click en parallele", LIVE_SYSTEM_PROMPT)
        self.assertIn("command_executed=true autorise seulement", LIVE_SYSTEM_PROMPT)
        self.assertIn("executee cote systeme", LIVE_SYSTEM_PROMPT)
        self.assertIn("l'effet applicatif est confirme", LIVE_SYSTEM_PROMPT)
        self.assertIn("c'est fait", LIVE_SYSTEM_PROMPT)
        self.assertIn("le defilement a reussi", LIVE_SYSTEM_PROMPT)
        self.assertIn("le clic a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("le bouton a ete active", LIVE_SYSTEM_PROMPT)
        self.assertIn("D'accord.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Je l'ai envoye.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Voila.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne demande pas systematiquement", LIVE_SYSTEM_PROMPT)
        self.assertIn("est-ce que ca a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("est-ce que ca te convient", LIVE_SYSTEM_PROMPT)
        self.assertIn("qu'est-ce que tu vois", LIVE_SYSTEM_PROMPT)
        self.assertIn("necessaire pour poursuivre une sequence dependante", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pas de spam de clics", LIVE_SYSTEM_PROMPT)
        self.assertIn("pas de drag/drop en V1", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour comprendre l'interface macOS", LIVE_SYSTEM_PROMPT)
        self.assertIn("inspect_ui", LIVE_SYSTEM_PROMPT)
        self.assertIn("find_ui_elements", LIVE_SYSTEM_PROMPT)
        self.assertIn("activate_ui_element", LIVE_SYSTEM_PROMPT)
        self.assertIn("preferes a MouseCapability", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais \"je vois\"", LIVE_SYSTEM_PROMPT)
        self.assertIn("\"je vois que\"", LIVE_SYSTEM_PROMPT)
        self.assertIn("d'apres l'interface accessible", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne reutilise jamais un ancien resultat Accessibility", LIVE_SYSTEM_PROMPT)
        self.assertIn("Si plusieurs elements correspondent", LIVE_SYSTEM_PROMPT)
        self.assertIn("N'invente jamais un bouton absent", LIVE_SYSTEM_PROMPT)
        self.assertIn("AXPress reussi signifie seulement", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne repete jamais automatiquement AXPress", LIVE_SYSTEM_PROMPT)

    def test_live_prompt_defines_multi_step_orchestration_rules(self):
        prompt = LIVE_SYSTEM_PROMPT

        self.assertIn("fournis obligatoirement query", prompt)
        self.assertIn('query="recherche"', prompt)
        self.assertIn('query="Nom"', prompt)
        self.assertIn("editable_target_not_verified", prompt)
        self.assertIn("sans contourner le controle par type_text directement", prompt)

        self.assertIn("demandes naturelles multi-etapes", prompt)
        self.assertIn("strictement sequentielle", prompt)
        self.assertIn("Attends toujours le resultat d'une etape", prompt)
        self.assertIn("utilise select_all_and_copy", prompt)
        self.assertIn("au lieu de lancer separement les hotkeys", prompt)
        self.assertIn("utilise focus_app_ui_and_type", prompt)
        self.assertIn("utilise open_app_and_focus_ui", prompt)

        dependent_sequences = [
            "open_app -> focus_window/get_active_window",
            "focus_window -> inspect_ui/find_ui_elements",
            "focus_ui_element -> type_text",
            "move_mouse -> click",
            "hotkey command+a -> hotkey command+c",
        ]

        for sequence in dependent_sequences:
            with self.subTest(sequence=sequence):
                self.assertIn(sequence, prompt)

        self.assertIn("operations dependantes cross-capability", prompt)
        self.assertIn("Si une etape retourne ok=false", prompt)
        self.assertIn("arrete toutes les etapes qui dependent", prompt)
        self.assertIn("ne substitue pas automatiquement une autre methode", prompt)
        self.assertIn("state_confirmed=false et que l'etape suivante depend", prompt)
        self.assertIn("n'annonce pas de succes applicatif", prompt)
        self.assertIn("n'interdit pas toute action suivante", prompt)
        self.assertIn("Apres open_app, ne suppose pas", prompt)
        self.assertIn("les anciens resultats inspect_ui et find_ui_elements sont obsoletes", prompt)
        self.assertIn("Avant type_text", prompt)
        self.assertIn("verifie ou focalise la bonne cible", prompt)
        self.assertIn("fenetre simplement supposee active", prompt)
        self.assertIn("Pour une cible semantique", prompt)
        self.assertIn("prefere Accessibility", prompt)
        self.assertIn("n'ajoute aucun fallback souris automatique", prompt)
        self.assertIn("ambiguous_ui_element", prompt)
        self.assertIn("ne choisis jamais silencieusement", prompt)
        self.assertIn("Apres une reconnexion", prompt)
        self.assertIn("ne repete jamais automatiquement une mutation", prompt)
        self.assertIn("command_executed=false", prompt)
        self.assertIn("ancien tool call ne prouve pas l'etat actuel", prompt)
        self.assertIn("Ces regles sont internes", prompt)
        self.assertIn("reponds naturellement", prompt)
        self.assertIn("parametres techniques", prompt)

    def test_live_agent_exposes_module_level_server_for_livekit_cli(self):
        self.assertTrue(hasattr(agent, "build_live_server"))
        self.assertTrue(hasattr(agent, "server"))
        self.assertIsInstance(agent.server, AgentServer)

    def test_livekit_cli_discovery_finds_server_variable(self):
        app_name = get_app_name(
            mod_data=ModuleData(
                module_import_str="jarvis.live.agent",
                extra_sys_path=pathlib.Path("src"),
                module_paths=[],
            )
        )

        self.assertEqual(app_name, "server")

    def test_imported_server_is_not_started_before_cli_runs_it(self):
        self.assertFalse(hasattr(agent.server, "_proc_pool"))

    def test_realtime_model_creation_is_deferred_until_session_job(self):
        config = LiveConfig(
            model="gemini-test-live",
            voice="Puck",
            temperature=0.8,
            agent_name="jarvis-test",
        )

        with patch.object(
            agent,
            "create_realtime_model",
            side_effect=AssertionError("Realtime model should be deferred"),
        ):
            built_server = agent.build_live_server(config)

        self.assertIsInstance(built_server, AgentServer)
        self.assertFalse(hasattr(built_server, "_proc_pool"))

    def test_live_session_start_enables_livekit_recording_redaction(self):
        config = LiveConfig(
            model="gemini-test-live",
            voice="Puck",
            temperature=0.8,
            agent_name="jarvis-test",
        )
        RecordingAgentSession.instances.clear()

        with patch("livekit.agents.AgentSession", RecordingAgentSession):
            with patch.object(
                agent,
                "create_realtime_model",
                return_value={"type": "fake-model"},
            ):
                built_server = agent.build_live_server(config)
                asyncio.run(built_server._entrypoint_fnc(FakeJobContext()))

        session = RecordingAgentSession.instances[0]
        self.assertEqual(
            session.start_calls[0]["record"],
            {"redaction": True},
        )
        self.assertIs(session.start_calls[0]["room"], FakeJobContext.room)

    def test_live_session_user_speech_unlocks_confirmation(self):
        from jarvis.live.confirmation import ConfirmationNeedsUserTurn

        config = LiveConfig(
            model="gemini-test-live",
            voice="Puck",
            temperature=0.8,
            agent_name="jarvis-test",
        )
        RecordingAgentSession.instances.clear()

        with patch("livekit.agents.AgentSession", RecordingAgentSession):
            with patch.object(
                agent,
                "create_realtime_model",
                return_value={"type": "fake-model"},
            ):
                built_server = agent.build_live_server(config)
                asyncio.run(built_server._entrypoint_fnc(FakeJobContext()))

        session = RecordingAgentSession.instances[0]
        store = session.start_calls[0]["agent"].registry.pending_actions
        token = store.register("send_message", lambda: "sent")
        with self.assertRaises(ConfirmationNeedsUserTurn):
            store.confirm(token)

        session.handlers["user_input_transcribed"](
            SimpleNamespace(transcript="oui", is_final=False)
        )
        self.assertEqual(store.confirm(token).executor(), "sent")

        typed = store.register("send_message", lambda: "typed")
        session.handlers["conversation_item_added"](
            SimpleNamespace(item=SimpleNamespace(role="user", text_content="oui"))
        )
        self.assertEqual(store.confirm(typed).executor(), "typed")

    def test_voice_mode_still_imports_alongside_live_poc(self):
        self.assertTrue(hasattr(VoiceMode, "run"))

    def test_no_secret_values_are_hardcoded_in_live_modules(self):
        live_source = (
            agent.__loader__.get_source(agent.__name__)
            + "\n"
            + debug_live.__globals__["__loader__"].get_source(
                debug_live.__module__
            )
        )

        forbidden_fragments = (
            "AIza",
            "LIVEKIT_API_SECRET=",
            "GOOGLE_API_KEY=",
        )

        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, live_source)

    def test_tool_registry_exposes_audio_and_app_tools(self):
        registry = ToolRegistry(
            audio_capability=object(),
            app_capability=object(),
        )

        tools = registry.livekit_tools()

        self.assertEqual(
            sorted(tool.info.name for tool in tools),
            EXPECTED_LIVE_TOOL_NAMES,
        )
