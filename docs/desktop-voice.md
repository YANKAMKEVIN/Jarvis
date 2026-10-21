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
Seules la clé Google, les options Gemini de modèle/voix/température/vision, les
options de backend/modèle/limites du planificateur et le modèle local de synthèse
sont lus ; aucun endpoint arbitraire n’est chargé depuis ces fichiers. Ne pas committer la clé (le `.env` du projet est déjà ignoré par Git).
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

1. Cliquer sur **Démarrer Jarvis**. Cette action ouvre la session externe et le
   microphone après le démarrage de la session, jamais au lancement de l’app.
2. Accorder l’accès Microphone si macOS le demande. Si l’accès est refusé,
   vérifier Réglages Système → Confidentialité et sécurité → Microphone.
3. Parler lorsque l’interface indique **Micro ouvert · voix envoyée à Gemini**.
4. **Couper le micro** arrête la capture et vide le tampon d’entrée local ; le
   bouton permet ensuite de réactiver le micro. L’audio déjà envoyé reste envoyé.
5. **Interrompre** coupe la réponse orale en cours. Cela n’annule pas une action
   système déjà lancée. Attendre ensuite la reprise de l’écoute avant de parler.
6. Dans **Réglages**, choisir et tester les périphériques lorsque le vocal est
   arrêté. Les tests sont locaux et n’ouvrent aucune connexion Gemini.
7. Après une coupure, **Reconnecter** ouvre une nouvelle conversation sans rejouer
   les demandes précédentes. Le micro coupé reste coupé ; vérifier les actions
   déjà effectuées dans Activité avant de les redemander.
8. **Arrêter** ferme les périphériques puis nettoie la session et ses
   tâches. Quitter l’application ou Ctrl+C demande le même arrêt propre avant
   de terminer le processus.

Pendant la lecture d’un bloc audio non silencieux, l’entrée micro n’est plus
transmise à Gemini. Le délai matériel de sortie et une marge de 250 ms sont
inclus pour limiter le retour de la voix de Jarvis. Les anciens échantillons
d’entrée encore dans le tampon local sont supprimés. Le micro matériel reste
ouvert sauf si vous le coupez explicitement ; la pause automatique ne réactive
jamais un micro coupé. Cette protection fonctionne en alternance, sans annulation
acoustique d’écho : parler par-dessus Jarvis est volontairement suspendu. Utiliser
**Interrompre**, puis attendre le retour de l’écoute. Un casque reste utile en
cas de réverbération importante ou de latence inhabituelle du périphérique.
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
- L’interface est entièrement vocale, sans saisie ni fil de messages. Les mots
  transcrits restent dans le contexte de la session SDK/Gemini ; ils ne sont pas
  recopiés vers l’interface. Le pont transmet des notifications de tour pour le
  compteur, des niveaux audio numériques pour l’orbe et des libellés génériques
  d’outils sans arguments pour le suivi. Les cartes sélectionnées d’agenda,
  rappels et web transmettent aussi les champs utiles à leur affichage, en mémoire
  seulement : voir [le guide desktop](desktop-ui.md). Elles ne recopient pas les
  phrases de la conversation ni les arguments ou jetons des outils. Un même identifiant de message SDK n’est compté qu’une
  fois (fenêtre de 512 identifiants). Deux demandes identiques avec des
  identifiants différents restent deux demandes légitimes.
- Les confirmations des outils Live se font **vocalement selon le protocole
  prepare → accord explicite → confirm_action existant**. Aucune transcription
  n’est soumise à un second moteur d’exécution par l’interface.
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
pendant la connexion, coupure/reprise micro, interruption, suppression du retour
audio pendant la lecture et son délai matériel, absence de texte transmis à
l’interface, fermeture sur erreur, configuration Finder
et mise à jour du lanceur. Un branchement réel `AgentSession` sans modèle ni
réseau a aussi été vérifié avec les adaptateurs audio.

La connexion Gemini avec une vraie clé, le son et les permissions TCC ne sont
pas validés dans l’environnement Linux de développement. Sur Mac : commencer
par une salutation, couper/réactiver le micro, interrompre une réponse, passer
entre les deux vues, puis arrêter et vérifier que le micro est libéré.

Les sons optionnels d’activation et de changement du micro utilisent la même
sortie et la même protection de capture que les réponses. Ils sont désactivés
par défaut et activables dans Réglages ; le mode démo reste silencieux.

Références SDK : [sessions](https://docs.livekit.io/agents/logic/sessions/),
[événements](https://docs.livekit.io/agents/events/).

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

## Fin de parole et écoute qui semble bloquée

Le desktop configure explicitement la détection de parole Gemini : sensibilité
de début et de fin élevée, 300 ms de contexte avant parole et 700 ms de silence
pour terminer un tour. Ce délai préserve les petites pauses ; la réponse ajoute
ensuite la latence réseau et la génération. Le CLI conserve ses réglages
habituels. Les valeurs suivent les possibilités de la
[configuration VAD Gemini](https://ai.google.dev/gemini-api/docs/live-api/capabilities#voice-activity-detection-vad).

Pendant la lecture du haut-parleur et sa courte réverbération, Jarvis continue
à bloquer le véritable son du micro pour éviter de s'entendre lui-même. Le flux
vers Gemini fournit alors des trames silencieuses synthétiques, au lieu d'un
trou de transmission. Couper explicitement le micro arrête toujours ce flux ;
le maintien pour parler garde sa fin de parole silencieuse bornée existante.
Aucune transcription ni aucun enregistrement n'est ajouté.

Les callbacks audio sont aussi surveillés : un flux déclaré actif mais qui ne
fournit plus de callbacks pendant plus de trois secondes devient une erreur
audio récupérable. Si la reconnexion automatique est activée, elle suit sa
procédure habituelle après nettoyage de l'ancienne session. Le silence réel ne
déclenche pas cette récupération : ses callbacks continuent à arriver. Un micro
volontairement coupé n'est pas considéré comme bloqué. Aucun objectif ou outil
n'est rejoué automatiquement pour forcer une réponse.

`tests/test_desktop_turn_detection.py` vérifie les paramètres, les trames
silencieuses pendant l'anti-écho, la reprise du vrai PCM, le respect du micro
coupé et les périphériques actifs mais sans callbacks. Les nouveaux paramètres
ont également été acceptés par une session Gemini réelle avec une phrase fixe,
sans microphone. Le blocage intermittent décrit par l'utilisateur n'a pas été
reproduit avec son environnement sonore ; le test en conversation reste requis.

Pour essayer après redémarrage de Jarvis : prononcer une question courte, laisser
un silence, puis recommencer après une réponse complète de Jarvis. Vérifier aussi
une phrase avec une petite pause au milieu et le fonctionnement du micro coupé.
Si le délai persiste, comparer casque et haut-parleurs permet de distinguer la
protection anti-écho d'un problème de détection ou de connexion.
