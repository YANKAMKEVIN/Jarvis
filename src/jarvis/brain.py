import json
import urllib.request


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:1.7b"

SYSTEM_PROMPT = """
Tu es Jarvis, l'assistant personnel de l'utilisateur sur son Mac.

Règles importantes :
- Tu t'appelles toujours Jarvis.
- Tu fonctionnes sur macOS, jamais sur un téléphone.
- Réponds en français par défaut.
- Sois naturel, concis et direct.
- N'affiche jamais ton raisonnement interne.
- Ne prétends jamais avoir exécuté une action que tu n'as pas exécutée.
- Pour l'instant, tu peux discuter et comprendre des demandes, mais tu ne contrôles pas encore le Mac.
- Les actions sur macOS seront exécutées uniquement par les outils sécurisés de Jarvis.
"""


class LocalBrain:
    def __init__(self):
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    def think(self, message: str) -> str:
        self.messages.append({
            "role": "user",
            "content": message,
        })

        payload = {
            "model": MODEL,
            "messages": self.messages,
            "stream": False,
            "think": False,
        }

        request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))

        answer = data["message"]["content"].strip()

        self.messages.append({
            "role": "assistant",
            "content": answer,
        })

        return answer


Brain = LocalBrain
