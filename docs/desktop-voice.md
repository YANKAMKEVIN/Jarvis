# Vocal Gemini Live dans Jarvis Desktop

## Installation sur le Mac

Depuis le dépôt et son environnement Python 3.13+ :

```bash
git pull --ff-only origin feat/desktop-ui
source .venv/bin/activate
python -m pip install -e '.[desktop,live]'
```

Le SDK utilisé par cette tranche est LiveKit Agents 1.8.x. Le transport audio est
local ; le modèle temps réel est Gemini. Il n’y a ni serveur d’agent à démarrer,
ni salle, ni jeton ou clé LiveKit à créer pour ce mode.
Le POC serveur existant (`python -m jarvis.live.agent`) garde son fonctionnement.

## Clé et configuration

Réutiliser la clé Gemini existante dans le `.env` du projet :

```dotenv
GOOGLE_API_KEY=votre_cle
```

Autre emplacement possible, notamment pour Finder :
`~/Library/Application Support/Jarvis/desktop.env`.

Priorité : variables déjà exportées dans le processus, puis fichier utilisateur,
puis `.env` du projet. Aucune interpolation de variables ni exécution de shell.
Seules la clé Google et les options Gemini de modèle, voix, température et vision
sont lues. Ne pas committer la clé (le `.env` du projet est déjà ignoré par Git).
Après modification d’un fichier de configuration, quitter puis relancer Jarvis.
Ne pas copier la clé dans les logs ou une capture d’écran.

Options conservées : `JARVIS_GEMINI_LIVE_MODEL`, `JARVIS_GEMINI_LIVE_VOICE`,
`JARVIS_GEMINI_LIVE_TEMPERATURE`, `JARVIS_VISION_ENABLED`.
Les valeurs par défaut restent celles du POC. Un modèle indisponible pour la clé
peut nécessiter un changement de configuration.

## Ouvrir et parler

```bash
jarvis-desktop
```

Pour actualiser l’application créée précédemment :

```bash
python scripts/build_desktop_app.py --update
open ~/Applications/Jarvis.app
```

1. Cliquer sur **Activer le vocal**. Cette action ouvre la session externe et le
   microphone après le démarrage de la session, jamais au lancement de l’app.
2. Accorder l’accès Microphone si macOS le demande. Si l’accès est refusé,
   vérifier Réglages Système → Confidentialité et sécurité → Microphone.
3. Parler lorsque l’interface indique **Micro ouvert · voix envoyée à Gemini**.
4. **Couper le micro** arrête la capture et vide le tampon d’entrée local ; le
   bouton permet ensuite de réactiver le micro. L’audio déjà envoyé reste envoyé.
5. **Interrompre** coupe la réponse orale en cours. Cela n’annule pas une action
   système déjà lancée. Les interruptions naturelles par la voix dépendent aussi
   de la détection de parole du modèle.
6. **Arrêter le vocal** ferme les périphériques puis nettoie la session et ses
   tâches. Quitter l’application ou Ctrl+C demande le même arrêt propre avant
   de terminer le processus.

Un casque est conseillé pour éviter que les haut-parleurs ne réinjectent la
voix de Jarvis dans le micro ; cette tranche n’ajoute pas d’annulation d’écho.
Le bundle est toujours un lanceur lié au Python du venv, pas un binaire autonome
signé. L’attribution des permissions macOS au lanceur/Python reste à vérifier sur
le Mac ; le changement d’Info.plist ne garantit pas à lui seul l’accord de TCC.

## Comportement et confidentialité

- Le mode démo ne peut pas activer le micro et ne contacte pas Gemini.
- La voix est transmise à Gemini. Les outils conservent leurs règles existantes
  de confirmation, mémoire, journalisation et accès à l’écran. Vision reste
  soumise à son option d’activation existante.
- L’enregistrement LiveKit est désactivé (`record=False`). L’interface n’ajoute
  aucun fichier audio ni stockage durable de transcriptions.
- Les transcriptions finales s’affichent dans les deux vues, dans l’ordre. Une
  réponse coupée est marquée comme interrompue lorsque le SDK le signale.
- Les confirmations des outils Live se font **vocalement selon le protocole
  prepare → accord explicite → confirm_action existant**. La carte de
  confirmation du moteur texte ne confirme pas les actions de la session Live.
- Le texte est temporairement désactivé pendant le vocal pour éviter deux
  moteurs pilotant le Mac en concurrence. Les échanges texte précédents sont
  visibles mais ne sont pas automatiquement transmis au contexte Gemini.
- Un arrêt coupe d’abord capture et lecture. Le nettoyage peut ensuite attendre
  la fin d’une étape système déjà lancée. Les tâches du planificateur reçoivent
  une demande d’annulation coopérative ; aucun thread d’action n’est tué.
- Les erreurs affichées sont génériques et utiles ; les exceptions brutes du
  fournisseur, chemins et clés ne sont pas recopiés dans l’interface.

## Validation

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_desktop*.py
```

Les tests utilisent des sessions et périphériques simulés : démarrage, arrêt
pendant la connexion, coupure/reprise micro, interruption, transcription,
fermeture sur erreur, absence d’exécution texte concurrente, configuration Finder
et mise à jour du lanceur. Un branchement réel `AgentSession` sans modèle ni
réseau a aussi été vérifié avec les adaptateurs audio.

La connexion Gemini avec une vraie clé, le son et les permissions TCC ne sont
pas validés dans l’environnement Linux de développement. Sur Mac : commencer
par une salutation, couper/réactiver le micro, interrompre une réponse, passer
entre les deux vues, puis arrêter et vérifier que le micro est libéré.

Références SDK : [sessions](https://docs.livekit.io/agents/logic/sessions/),
[événements](https://docs.livekit.io/agents/events/).

Résultat de cette tranche sous Linux/Python 3.13 : 25 tests desktop passants.
Suite complète : 817 tests passants, 149 sous-tests passants et les mêmes
207 échecs de frameworks macOS absents que le snapshot de `main` ; aucun nouvel
identifiant de test en échec. La suite complète n’est pas déclarée verte.

## Si la préparation échoue avant l’ouverture du micro

Depuis le même environnement Python que l’application :

```bash
python scripts/diagnose_desktop_voice.py
```

Ce diagnostic affiche les versions et l’étape en échec (import audio, outils
macOS, modèle Gemini, session LiveKit), avec noms de fichiers/fonctions et lignes.
Il n’ouvre aucun périphérique et ne démarre aucune connexion Gemini. Il ne
recopie ni clé, ni message brut d’exception du fournisseur. Son résultat permet
de distinguer une incompatibilité de SDK d’un problème des outils natifs.

Si le diagnostic passe alors que l’interface échoue, reproduire la préparation
dans le même type de thread que l’interface, sans ouvrir le micro ni Gemini :

```bash
python scripts/diagnose_desktop_voice.py --worker
```

Ce mode utilise une boucle QApplication et un QThread comme le vocal desktop,
puis imprime l’étape et les positions de code en échec avant de se fermer.

### Initialisation du plugin Google

LiveKit exige que l’enregistrement des plugins soit effectué dans le thread
principal. Lors de l’activation du vocal, l’interface importe donc le plugin Google
avant de lancer le worker. La session, l’audio et les outils restent dans le
worker. Aucun micro ni connexion ne s’ouvre pendant ce préchargement.
Un test en processus neuf utilise le vrai plugin puis construit un modèle dans
un QThread, sans démarrer de connexion, pour éviter de masquer ce cas par les
imports préalables des autres tests.
