"""Text mode over the full tool registry through the planner (idea 8)."""
from livekit.agents import function_tool

from jarvis.planner import PLANNER_TOOL_NAMES, ModelTurn, ScriptedModel, ToolCall
from jarvis.text_agent import TEXT_MODE_TOOL_NAMES, TextAgent, start_text_agent


class Registry:
    def __init__(self):
        self.turns = 0
        self.calls = []
        self.confirm_turns = None

        @function_tool(name="set_reminder", description="Rappel.")
        async def set_reminder(text: str, when: str) -> dict:
            self.calls.append(("set_reminder", text, when))
            return {"ok": True, "message": "Rappel enregistre."}

        @function_tool(name="prepare_send_message", description="Prepare.")
        async def prepare_send_message(app_name: str, recipient: str, text: str) -> dict:
            self.calls.append(("prepare_send_message", recipient))
            return {"ok": True, "requires_confirmation": True, "token": "tok", "target_app": app_name}

        @function_tool(name="confirm_action", description="Confirme.")
        async def confirm_action(token: str) -> dict:
            self.calls.append(("confirm_action", token))
            self.confirm_turns = self.turns
            return {"ok": True, "message": "Message envoye."}

        @function_tool(name="cancel_action", description="Annule.")
        async def cancel_action(token: str) -> dict:
            self.calls.append(("cancel_action", token))
            return {"ok": True}

        @function_tool(name="clear_personal_data", description="Efface tout.")
        async def clear_personal_data() -> dict:
            self.calls.append(("clear_personal_data",))
            return {"ok": True}

        self.tools = [set_reminder, prepare_send_message, confirm_action, cancel_action, clear_personal_data]

    def livekit_tools(self):
        return self.tools

    def note_user_turn(self):
        self.turns += 1


def call(name, **arguments):
    return ToolCall(id=f"c_{name}", name=name, arguments=arguments)


def test_allowlist_extends_the_planner_with_local_tools_only():
    assert set(PLANNER_TOOL_NAMES) <= set(TEXT_MODE_TOOL_NAMES)
    for name in ("set_reminder", "remember", "save_note"):
        assert name in TEXT_MODE_TOOL_NAMES
    for name in ("confirm_action", "cancel_action", "clear_personal_data", "disable_safe_mode", "call_mcp_tool"):
        assert name not in TEXT_MODE_TOOL_NAMES


def test_reminder_request_reaches_the_registry_tool():
    registry = Registry()
    model = ScriptedModel([ModelTurn(tool_calls=[call("set_reminder", text="dentiste", when="demain 9h")]),
                           ModelTurn(text="Rappel cree pour demain 9 h.")])
    agent = TextAgent(registry=registry, model=model)
    try:
        assert agent.respond("Rappelle-moi le dentiste demain 9h") == "Rappel cree pour demain 9 h."
        assert registry.calls == [("set_reminder", "dentiste", "demain 9h")]
        assert registry.turns == 1
    finally:
        agent.close()


def test_outward_action_needs_a_typed_yes_before_confirm_action():
    registry = Registry()
    turn = ModelTurn(tool_calls=[call("prepare_send_message", app_name="WhatsApp", recipient="Maman", text="Coucou")])
    agent = TextAgent(registry=registry, model=ScriptedModel([turn, turn]))
    try:
        prompts = []
        assert agent.respond("Ecris coucou a maman", ask=lambda p: prompts.append(p) or "oui") == "Message envoye."
        assert "prepare_send_message" in prompts[0] and "Maman" in prompts[0]
        assert ("confirm_action", "tok") in registry.calls
        assert registry.confirm_turns == 2  # the request, then the typed « oui »
        assert agent.respond("Ecris coucou a maman", ask=lambda p: "non") == "Action annulee, rien n'a ete envoye."
        assert registry.calls[-1] == ("cancel_action", "tok")
    finally:
        agent.close()


def test_a_tool_outside_the_allowlist_is_never_run():
    registry = Registry()
    model = ScriptedModel([ModelTurn(tool_calls=[call("clear_personal_data")]), ModelTurn(text="Impossible.")])
    agent = TextAgent(registry=registry, model=model)
    try:
        agent.respond("Efface tout")
        assert ("clear_personal_data",) not in registry.calls
    finally:
        agent.close()


def test_clarification_answer_resumes_the_same_objective():
    registry = Registry()
    seen = []
    model = ScriptedModel([
        ModelTurn(tool_calls=[call("ask_clarification", question="Quelle heure ?")]),
        lambda messages: seen.append(messages[1]["content"]) or ModelTurn(text="C'est note."),
    ])
    agent = TextAgent(registry=registry, model=model)
    try:
        assert agent.respond("Rappelle-moi le dentiste") == "Quelle heure ?"
        assert agent.respond("9 h") == "C'est note."
        assert "Rappelle-moi le dentiste" in seen[0] and "Reponse de l'utilisateur : 9 h" in seen[0]
    finally:
        agent.close()


def test_loop_quits_and_closes():
    registry = Registry()
    agent = TextAgent(registry=registry, model=ScriptedModel([ModelTurn(text="Bonjour !")]))
    inputs = iter(["salut", "quit"])
    out = []
    start_text_agent(agent, read=lambda prompt: next(inputs), write=out.append)
    assert any("Bonjour !" in line for line in out) and agent.loop.is_closed()
