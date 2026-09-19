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
- Les actions macOS sont exécutées uniquement par les outils sécurisés de Jarvis.
"""


class LocalBrain:
    def __init__(self):
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    def detect_intent(self, message: str) -> dict:
        intent_prompt = f"""
Tu es le routeur d'intentions d'un assistant macOS.

Tu dois déterminer si le message demande une action sur le Mac
ou s'il s'agit simplement d'une conversation.

Actions disponibles :

open_app
→ ouvrir une application macOS

conversation
→ aucune action à exécuter

Réponds UNIQUEMENT avec un objet JSON valide.
Aucun commentaire.
Aucune explication.

Exemples :

Message : Ouvre Safari
Réponse :
{{"action":"open_app","target":"Safari"}}

Message : Lance Spotify
Réponse :
{{"action":"open_app","target":"Spotify"}}

Message : Peux-tu ouvrir Notes ?
Réponse :
{{"action":"open_app","target":"Notes"}}

Message : Explique-moi ce qu'est Spotify
Réponse :
{{"action":"conversation","target":null}}

Message : Comment vas-tu ?
Réponse :
{{"action":"conversation","target":null}}

Message utilisateur :
{message}
"""

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": intent_prompt,
                }
            ],
            "stream": False,
            "think": False,
            "format": "json",
        }

        request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))

        return json.loads(data["message"]["content"])

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
