# Jarvis

Assistant personnel **local** pour macOS. Jarvis comprend des demandes en
langage naturel et les traduit en actions réelles sur la machine (applications,
fenêtres, fichiers, clavier, souris, presse-papiers, son, média…), via une
couche d'accessibilité native et un ensemble de *capabilities* composables.

Il inclut un POC temps réel **Gemini Live + LiveKit**, isolé du mode texte et du
mode vocal, qui expose ces mêmes capacités comme *tools* à un modèle conversant.

- **Langage** : Python ≥ 3.13
- **Plateforme** : macOS (API Accessibility / ApplicationServices)
- **État** : 0.9.0 — en développement actif

---

## Sommaire

- [Architecture](#architecture)
- [Capacités](#capacités)
- [Les trois modes d'exécution](#les-trois-modes-dexécution)
- [Installation](#installation)
- [Lancer Jarvis](#lancer-jarvis)
- [Le POC Gemini Live](#le-poc-gemini-live)
- [Tests](#tests)
- [Diagnostic Accessibility](#diagnostic-accessibility)
- [Principes de conception](#principes-de-conception)

---

## Architecture

```
src/jarvis/
├── main.py            # Mode texte (REPL)
├── voice_mode.py      # Mode vocal (wake word + parole)
├── wakeword.py        # Détection du mot d'activation
├── speech.py / voice.py
├── executor.py        # Orchestration : routing → intent → sécurité → tools
├── routing.py         # Classe une demande : ACTION / KNOWLEDGE / CONVERSATION
├── intents.py
├── brain.py
├── security.py        # Confirmation des actions sensibles
├── config.py
├── capabilities/      # Briques d'action de haut niveau (composables)
├── tools/             # Implémentations macOS bas niveau
├── knowledge/         # Recherche externe (SearXNG) + benchmark
├── memory/            # Mémoire durable locale (SQLite + FTS5, filtre à secrets)
├── planner/           # Planification : tâches longues en arrière-plan (Ollama local)
└── live/              # POC Gemini Live + LiveKit (isolé)
```

Deux niveaux séparent clairement l'intention et l'exécution :

- **`tools/`** — primitives macOS (accessibility, keyboard, mouse, clipboard,
  filesystem, macos). Elles parlent directement aux API système.
- **`capabilities/`** — couche métier qui enveloppe les primitives, renvoie un
  `ToolResult` structuré (`ok`, `command_executed`, `state_confirmed`,
  `error_code`, `steps`…) et gère la vérification d'état.

## Capacités

| Capability | Rôle |
|---|---|
| `AppCapability` | Ouvrir / activer des applications, tester si une app tourne |
| `BrowserCapability` | Ouvrir une URL / recherche, lire & lister les onglets, activer un onglet (Safari / Chrome), **vérifié** |
| `WindowCapability` | Focaliser une fenêtre, lire la fenêtre active |
| `UIAccessibilityCapability` | Inspecter l'UI, trouver / focaliser / activer un élément via Accessibility |
| `KeyboardCapability` | Saisie texte, raccourcis, touches |
| `MouseCapability` | Déplacer le curseur, cliquer, scroller |
| `ClipboardCapability` | Lire / écrire le presse-papiers |
| `FilesCapability` | Fichiers et Finder |
| `ScreenshotCapability` | Capturer l'écran, une région ou une fenêtre en PNG, **vérifié** |
| `MediaCapability` | Lecture / pause / piste suivante, état de lecture |
| `AudioCapability` | Volume |
| `SystemCapability` | Batterie, luminosité, infos système, verrouillage |
| `InteractionCapability` | **Flux composites** multi-étapes vérifiés (voir ci-dessous) |
| `MemoryCapability` | **Mémoire durable** locale : retenir, retrouver, oublier (voir ci-dessous) |

### InteractionCapability

Couche de haut niveau qui compose plusieurs capacités en séquences **strictement
ordonnées et vérifiées**. Chaque étape s'arrête dès qu'elle échoue, n'a pas
exécuté sa commande, ou n'a pas confirmé son état final — jamais d'étape
dépendante lancée sur un état non vérifié.

- **`select_all_and_copy`** — `⌘A` puis `⌘C`, avec relecture du presse-papiers
  avant/après pour prouver qu'une nouvelle copie a bien eu lieu.
- **`open_app_and_focus_ui`** — ouvre/focalise une app puis focalise une cible
  Accessibility nommée (sans saisie).
- **`focus_app_ui_and_type`** — ouvre/focalise une app, **vérifie** la
  destination éditable (nommée via `query`, ou l'unique champ éditable
  focalisé), puis saisit le texte et, en option, presse Entrée.

### BrowserCapability

Contrôle **tab-aware et vérifié** de Safari / Google Chrome (via AppleScript).
Chaque action de navigation relit l'onglet actif : `state_confirmed` n'est vrai
que si l'onglet observé correspond réellement.

- **`open_url`** / **`search_web`** — ouvrir une URL ou une recherche
  (Google / DuckDuckGo / Bing), puis confirmer le domaine chargé.
- **`get_active_tab`** / **`list_tabs`** — lecture seule de la page affichée et
  des onglets de la fenêtre active.
- **`activate_tab`** — focaliser l'unique onglet dont l'URL/titre correspond à
  une requête ; refuse les correspondances ambiguës au lieu de deviner.

Le navigateur est choisi automatiquement (préfère l'unique navigateur ouvert,
sinon Safari) ou explicitement. En mode Live, ces flux sont exposés comme les
tools `browse_open_url`, `browse_search_web`, `browse_get_active_tab`,
`browse_list_tabs`, `browse_activate_tab`.

### ScreenshotCapability

Capture d'écran **vérifiée** (via `screencapture`). Chaque capture relit le
fichier écrit (existence + taille) : `state_confirmed` n'est vrai que si le PNG
a bien été enregistré. Le résultat ne contient que le chemin et les métadonnées,
jamais l'image — le fichier n'est pas analysé.

- **`capture_screen`** — écran complet (option `display`).
- **`capture_region`** — zone rectangulaire fournie (x, y, largeur, hauteur).
- **`capture_window`** — fenêtre active, ou fenêtre d'une app nommée (mise au
  premier plan et vérifiée avant capture ; refus si l'app active ne correspond
  pas).

Par défaut, les captures sont enregistrées dans `~/Pictures/Jarvis/` avec un nom
horodaté. En mode Live : tools `capture_screen`, `capture_region`,
`capture_window`.

### MemoryCapability

Mémoire durable **locale et privée** : une base SQLite (recherche plein texte
FTS5) dans `~/Library/Application Support/Jarvis/memory.db`, lisible par
l'utilisateur seul (`0600`). Chemin modifiable via `JARVIS_MEMORY_PATH`.

- **Types** : `profile` (l'utilisateur), `person` (surnom ou relation → nom
  exact du contact), `preference`, `fact`. Même type + même sujet = mise à jour,
  jamais de doublon.
- **Écriture** : `remember` uniquement sur demande explicite (« souviens-toi
  que… »). Une information *déduite* passe par `propose_memory` → question à
  l'utilisateur → `confirm_action` ; rien n'est stocké sans son accord.
- **Jamais de secrets** : mots de passe, codes, numéros de carte (Luhn), IBAN,
  clés d'API… sont refusés (`secret_refused`).
- **Rien n'est envoyé d'avance au modèle** : aucun résumé de mémoire dans le
  prompt. Les tools appliquent la mémoire localement — `prepare_send_message`
  traduit « ma mère » en nom de contact sans renvoyer ce nom au modèle. Seuls
  les résultats d'un `recall` explicite remontent au modèle.
- **Oubli** : `forget` par identifiant ou requête ; refuse de deviner si
  plusieurs souvenirs correspondent (`ambiguous_memory`).

- **Journal d'activité** : chaque action notable (ouvrir une app, régler le
  volume, préparer / envoyer un message, ouvrir un site…) est notée avec
  l'heure et le résultat, gardée 30 jours. Jamais de contenu : ni texte de
  message, ni presse-papiers, ni texte tapé, ni chemin de fichier ; pour un
  site, seul l'hôte est gardé. Le tool `recent_activity` répond à « qu'est-ce
  que tu as fait ? » ou « tu as bien envoyé le message ? ».

En mode Live : tools `remember`, `propose_memory`, `recall`, `list_memories`,
`forget`, `recent_activity`. Les tests n'utilisent jamais la vraie base (`tests/conftest.py`).

## Les trois modes d'exécution

1. **Texte** (`main.py`) — un REPL : vous tapez, Jarvis route la demande
   (action / connaissance / conversation), demande confirmation pour les actions
   sensibles, et exécute.
2. **Vocal** (`voice_mode.py`) — écoute un mot d'activation puis traite la
   commande parlée.
3. **Live** (`live/`) — POC Gemini Live + LiveKit : un modèle temps réel
   converse et appelle les capacités exposées comme *tools*.

## Installation

Python 3.13+ requis.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-live.txt   # uniquement pour le POC Live
```

> Le paquet n'est pas installé en editable ; les commandes ci-dessous utilisent
> `PYTHONPATH=src`. Vous pouvez aussi `pip install -e .`.

**Autorisation macOS** : accordez l'accès **Accessibilité** au terminal (ou à
l'app qui lance Jarvis) dans *Réglages Système → Confidentialité et sécurité →
Accessibilité*, sans quoi l'inspection/pilotage de l'UI échoue.

## Lancer Jarvis

Mode texte :

```bash
PYTHONPATH=src .venv/bin/python -m jarvis.main
```

Mode vocal :

```bash
PYTHONPATH=src .venv/bin/python -m jarvis.voice_mode
```

## Le POC Gemini Live

Variables d'environnement requises :

```bash
export GOOGLE_API_KEY=...
export LIVEKIT_URL=...
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
```

Options (valeurs par défaut) :

| Variable | Défaut |
|---|---|
| `JARVIS_GEMINI_LIVE_MODEL` | `gemini-3.1-flash-live-preview` |
| `JARVIS_GEMINI_LIVE_VOICE` | `Puck` |
| `JARVIS_GEMINI_LIVE_TEMPERATURE` | `0.8` |
| `JARVIS_LIVE_AGENT_NAME` | `jarvis-live-poc` |
| `JARVIS_DEBUG_LIVE` | `0` (mettre `1` pour les logs de debug) |

Lancement (via la CLI LiveKit) :

```bash
PYTHONPATH=src .venv/bin/python -m jarvis.live.agent
```

Les logs appliquent un filtre PII et l'enregistrement LiveKit est configuré avec
rédaction.

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

### Smoke test sur la vraie machine

`scripts/smoke_test.py` appelle les tools réellement exposés à Gemini Live
(`create_live_tools`) sur le Mac, puis vérifie chaque effet par une
observation indépendante de Jarvis (`osascript`, `pbpaste`, `lsappinfo`,
disque). Chaque scénario restaure l'état touché (volume, presse-papiers,
souris, apps, fichiers). Rien n'est jamais envoyé : la messagerie est
seulement préparée puis annulée.

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --group safari --group textedit
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --list
```

Il pilote clavier et souris : ne pas utiliser le Mac pendant l'exécution.
Les groupes qui exigent une permission macOS absente (Accessibilité,
Enregistrement de l'écran) ou un écran déverrouillé sont marqués `SKIP`, jamais
`FAIL`. Si une étape de préparation échoue (ex. l'app n'est pas au premier
plan), les étapes dépendantes sont ignorées : le test ne tape jamais à
l'aveugle. La mémoire est testée sur une base temporaire. Code de
sortie non nul en cas d'échec ; `--json` écrit un rapport.

## Diagnostic Accessibility

Outil local **en lecture seule** pour découvrir les cibles (`query` / `role`) à
utiliser avec `InteractionCapability`. Il n'active pas l'app, ne lit aucune
valeur de champ ni texte sélectionné, et n'imprime les métadonnées que sur
stdout (jamais dans les logs) :

```bash
PYTHONPATH=src .venv/bin/python scripts/diagnose_accessibility.py --app Safari
```

## Principes de conception

- **Vérifier, ne pas supposer.** Les capacités renvoient `command_executed` et
  `state_confirmed` ; on ne déclare un succès applicatif que lorsque l'effet réel
  est confirmé. Après un changement d'app/fenêtre, les anciennes inspections UI
  sont considérées obsolètes.
- **Séquentiel et dépendant.** Les étapes dépendantes ne sont jamais lancées en
  parallèle ni sur un état non confirmé ; un échec interrompt la chaîne.
- **Accessibility d'abord.** Les cibles sémantiques (« barre de recherche »,
  « champ Nom », « Continuer ») passent par l'API Accessibility ; la souris reste
  une primitive explicite, sans fallback automatique.
- **Local et sobre en données.** Les valeurs de champs et le texte sélectionné
  ne sont pas lus ; les logs filtrent les PII.


## Interface de bureau (première version)

Trois vues partagent la même session : orbe seul, compagnon compact et fenêtre
complète, entièrement vocales : orbe, état d’écoute et commandes audio.
Orbe réactif au son, capsule déplaçable avec position mémorisée, commandes
discrètes et sons optionnels. Cartes d’agenda, rappels et réponses web, avec un
suivi des actions et une annulation coopérative des tâches. Raccourci global
macOS, choix/tests des périphériques et reconnexion explicite après coupure.
Menu permanent avec état de capture et commandes vocales, même fenêtres masquées. Aucun champ de saisie
ni fil de messages. Les missions présentent leur objectif, l’outil en cours et
leurs bilans ; l’analyse d’écran à la demande dispose d’un indicateur et d’une carte de résultat.
La mission en cours apparaît à côté de la sphère dans Assistant, avec un résumé
cliquable sous l’orbe en mode compact et un petit bilan à la fin.

Installation :

```bash
python -m pip install -e '.[desktop,live]'
jarvis-desktop --demo       # découvrir sans action réelle
jarvis-desktop --demo --orb # découvrir l’orbe seul
jarvis-desktop              # assistant vocal Gemini Live sur macOS
```

Pour ouvrir Jarvis depuis Finder sans terminal au quotidien :

```bash
python scripts/build_desktop_app.py
open ~/Applications/Jarvis.app
```

Ce lanceur de développement reste lié au dépôt et à son environnement Python.
Le bouton **Démarrer Jarvis** connecte Gemini Live aux trois vues, avec micro
coupé/réactivable et interruption de réponse. Configurer
`GOOGLE_API_KEY` dans le `.env` du projet (ou le fichier desktop utilisateur).
Le micro reste fermé jusqu’à l’activation explicite ; la voix est envoyée à
Gemini. Pas de salle ni de clés LiveKit nécessaires pour ce mode desktop.
L’entrée audio est suspendue pendant la lecture de la voix de Jarvis pour limiter
les boucles de retour des haut-parleurs. Pour parler pendant sa réponse, cliquer
sur **Interrompre**, puis attendre la reprise de l’écoute. Les confirmations des
outils restent vocales. Les modes terminal existants restent disponibles.

Pour actualiser un lanceur existant : `python scripts/build_desktop_app.py --update`.
Voir [le guide vocal](docs/desktop-voice.md) et [le guide desktop](docs/desktop-ui.md)
pour les limites, les tests et les prochaines étapes.

