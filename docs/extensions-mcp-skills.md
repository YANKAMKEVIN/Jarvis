# Extensions : serveurs MCP et skills

Jarvis peut utiliser des outils externes sans qu'on modifie son code :

- **MCP** (Model Context Protocol) : un serveur MCP expose des outils (GitHub, Notion,
  Home Assistant, bases de données…). Jarvis en est le client.
- **Skills** : un dossier `SKILL.md` (format [agentskills.io](https://agentskills.io))
  contient des instructions que Jarvis charge quand une demande correspond à sa description.

## Installation

```bash
pip install -e '.[mcp]'
```

Sans le paquet `mcp`, Jarvis démarre normalement. Seul l'appel à un serveur MCP échoue
alors, avec un message clair.

## Configurer des serveurs MCP

Fichier : `~/Library/Application Support/Jarvis/mcp.json` (autre chemin possible avec
`JARVIS_MCP_CONFIG`). C'est le format `mcpServers` de Claude Desktop : un bloc copié de
`claude_desktop_config.json` fonctionne tel quel.

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "..."},
      "autoApprove": ["search_issues", "get_issue"]
    },
    "maison": {
      "url": "http://homeassistant.local:8123/mcp_server/sse",
      "headers": {"Authorization": "Bearer ..."},
      "timeout": 15
    },
    "brouillon": {"command": "uvx", "args": ["mon-serveur"], "disabled": true}
  }
}
```

| Clé | Rôle |
|---|---|
| `command` + `args` + `env` | Serveur local lancé en sous-processus (stdio). |
| `url` + `headers` | Serveur distant (streamable HTTP). |
| `autoApprove` | Outils qui s'exécutent **sans** confirmation orale. À réserver aux lectures. |
| `timeout` | Durée maximale d'un appel, en secondes (30 par défaut, 300 au plus). |
| `disabled` | Garde l'entrée sans jamais démarrer le serveur. |

Les serveurs démarrent au premier usage, puis restent ouverts jusqu'à la fermeture
de Jarvis. Quand l'app est lancée depuis le Finder, son `PATH` est minimal : Jarvis
cherche alors `npx` et `uvx` aussi dans `/opt/homebrew/bin`, `/usr/local/bin` et
`~/.local/bin`.

## Ajouter une skill

Créer un dossier dans `~/Library/Application Support/Jarvis/skills/` (ou dans un
dossier listé par `JARVIS_SKILLS_PATH`, chemins séparés par `:`) :

```
skills/
  revue-hebdo/
    SKILL.md
    modele.md
```

```markdown
---
name: revue-hebdo
description: Fait la revue de la semaine quand l'utilisateur demande son bilan hebdomadaire.
---
1. Liste les rappels et les checklists ouvertes.
2. Résume les missions de la semaine (recent_missions).
3. Propose trois priorités, sans rien créer sans accord.
```

Les noms et descriptions des skills installées sont annoncés au modèle au démarrage de
la session. Les instructions ne sont lues qu'à l'utilisation (`use_skill`), et les
fichiers de référence (`.md`, `.txt`, `.json`, `.yaml`, `.csv`) seulement à la demande.

## Outils vocaux

| Outil | Effet | Mode sécurité |
|---|---|---|
| `list_mcp_tools(server?)` | Liste les serveurs et leurs outils (arguments requis, pré-approbation). | autorisé |
| `call_mcp_tool(server, tool, arguments_json)` | Appelle un outil. Non pré-approuvé → token + `confirm_action`. | **bloqué** |
| `list_skills()` | Liste les skills installées (relit le dossier). | autorisé |
| `use_skill(name, file?)` | Charge les instructions d'une skill ou un fichier de référence. | autorisé |

Les missions (`run_task`) disposent des mêmes outils, avec les mêmes confirmations.

## Sécurité

- **Confirmation par défaut** : tout outil MCP absent de `autoApprove` passe par le flux
  préparer → annoncer → oui explicite → `confirm_action`, comme un envoi de message.
  Les indications `readOnlyHint` d'un serveur sont affichées mais **jamais** prises pour
  une autorisation : elles viennent du serveur, pas de l'utilisateur.
- **Mode sécurité** : `call_mcp_tool` est refusé, même pour un outil pré-approuvé.
  Jarvis ne peut pas savoir ce que fait un outil externe.
- **Secrets** : un serveur stdio reçoit un environnement minimal plus son propre `env`.
  Il n'hérite pas des clés de Jarvis (`GOOGLE_API_KEY`…), ce que le test de bout en bout
  vérifie.
- **Données externes** : un résultat MCP est borné à 4 000 caractères et présenté au
  modèle comme une donnée, jamais comme une consigne. Les arguments et les résultats ne
  sont pas journalisés (seuls le nom de l'outil et le serveur le sont).
- **Skills** : elles sont lues, jamais exécutées. Les scripts qu'elles contiennent ne sont
  pas lancés, et la lecture d'un fichier ne peut pas sortir du dossier de la skill.
  Une skill guide le modèle, qui n'agit qu'avec ses propres outils, toujours gardés.

## Limites (v1)

- Les outils MCP passent par un outil générique (`call_mcp_tool`) au lieu d'être exposés
  un par un. Cela garde la liste d'outils de Gemini Live stable, mais demande un appel
  `list_mcp_tools` avant le premier usage d'un serveur.
- Seuls les *tools* MCP sont pris en charge : ni *resources*, ni *prompts*, ni
  *sampling*, ni OAuth (un jeton passe par `headers` ou `env`).
- Les skills ajoutées pendant une session apparaissent dans `list_skills`, mais la
  description de `use_skill` n'est mise à jour qu'à la session suivante.
- Pas encore d'éditeur de `mcp.json` dans l'interface desktop.

## Tests

- `tests/test_mcp_skills.py` : 30 tests (config, hub avec une fausse session,
  reconnexion, délai dépassé, troncature, confirmation et annulation, mode sécurité,
  skills invalides, sortie du dossier).
- Validation réelle du 2026-10-30 avec le SDK `mcp` 1.30 : serveur FastMCP en stdio
  (liste, appel, arguments manquants, pas de fuite de `GOOGLE_API_KEY`) et en
  streamable HTTP.
