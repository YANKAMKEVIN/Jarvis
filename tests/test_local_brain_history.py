"""LocalBrain keeps a bounded conversation history (idea 11)."""
from jarvis.brain import MAX_HISTORY_EXCHANGES, LocalBrain


def test_history_keeps_system_prompt_and_last_exchanges():
    brain = LocalBrain(max_history_exchanges=3)
    sent = []
    brain._chat = lambda messages, response_format=None: sent.append(list(messages)) or f"r{len(sent)}"
    for index in range(10):
        brain.think(f"q{index}")
    assert brain.messages[0]["role"] == "system"
    assert len(brain.messages) == 1 + 2 * 3
    assert [m["content"] for m in brain.messages[1:]] == ["q7", "r8", "q8", "r9", "q9", "r10"]
    assert len(sent[-1]) <= 1 + 2 * 3 + 1  # plus the new question


def test_default_bound():
    assert LocalBrain().max_history_exchanges == MAX_HISTORY_EXCHANGES >= 4
