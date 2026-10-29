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
- La voix reste l’entrée principale. La palette permet une mission saisie et le
  mode discret affiche les réponses de Jarvis en mémoire seulement. Les paroles
  de l’utilisateur restent dans le contexte SDK/Gemini sans copie dans l’interface. Le pont transmet des notifications de tour pour le
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
de début élevée, sensibilité de fin basse, 300 ms de contexte avant parole et
1 100 ms de silence pour terminer un tour. Ce délai laisse l'utilisateur
reprendre son souffle ou chercher ses mots au milieu d'une longue phrase sans
que Jarvis prenne la parole ; en contrepartie, une commande courte attend
environ 0,4 s de plus qu'avec l'ancien réglage (700 ms, fin élevée). La variable
`JARVIS_TURN_SILENCE_MS` ajuste ce silence sur le terrain (bornée entre 400 et
3 000 ms). La réponse ajoute ensuite la latence réseau et la génération. Le CLI conserve ses réglages
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

## Mot d’éveil « Jarvis » (veille locale)

Option désactivée par défaut : **Réglages → Réveiller Jarvis en disant « Jarvis »
(détection locale)**, ou menu du compagnon → **Réveil par « Jarvis »**. Elle
remplace le maintien pour parler (activer l’un désactive l’autre).

Installation du détecteur local, une fois :

```bash
python -m pip install -e '.[desktop,live,wake]'
```

Au premier démarrage du mode, openWakeWord télécharge ses modèles (quelques Mo,
depuis la page des versions GitHub d’openWakeWord). Ce téléchargement porte sur
des fichiers de modèle, jamais sur de l’audio. Ensuite tout fonctionne hors ligne.

### Fonctionnement

1. Le mode activé, Jarvis démarre la session vocale au lancement de l’app, sans
   salutation, **en veille** : l’orbe affiche « En veille » et l’indication
   « Veille locale · rien n’est envoyé à Gemini avant « Jarvis » ».
2. Le micro capte en local. Chaque bloc de 20 ms part vers le détecteur
   (rééchantillonné de 24 à 16 kHz, file bornée à 1 s, thread dédié) et **pas**
   vers Gemini : le flux d’entrée de la session ne reçoit aucune trame.
3. Dire « hey Jarvis » (ou « Jarvis » seul, avec un taux de détection plus
   faible) : un court bip aigu confirme, puis le micro s’ouvre vers Gemini dans
   la **même** session. Jarvis ne reparle pas et ne se présente pas : on
   enchaîne directement la demande. La parole qui suit le mot sans pause est
   conservée : les blocs captés après la détection sont transmis en premier.
4. Après `JARVIS_WAKE_IDLE_SECONDS` (45 s par défaut, borné entre 15 et 300 s)
   sans parole de l’utilisateur ni réponse ou réflexion de Jarvis, retour en
   veille locale (son « micro coupé » si les sons discrets sont activés).

Règles conservées :

- **Couper le micro** reste prioritaire : il ferme la capture, y compris la
  détection locale. Une détection arrivée juste après la coupure est ignorée.
  **Réactiver le micro** revient en veille, pas directement vers Gemini.
- Pendant que Jarvis parle, la protection en alternance s’applique aussi au
  détecteur : Jarvis ne peut pas se réveiller en prononçant son propre nom. Le
  bip de réveil, lui, ne déclenche pas cette protection, pour ne pas couper la
  phrase qui suit.
- Si le détecteur est absent ou s’arrête, la session échoue **fermée** avec un
  message (aucun repli vers un micro ouvert en continu).
- Une alerte proactive peut encore être dite pendant la veille ; pour y
  répondre, redire « Jarvis ».
- Changer l’option pendant une session s’applique au prochain démarrage du vocal.

`JARVIS_WAKE_THRESHOLD` (0,5 par défaut, borné entre 0,2 et 0,95) règle le seuil
de score : plus haut, moins de faux réveils mais plus de « Jarvis » manqués. Un
réveil est suivi de 2 s pendant lesquelles un second réveil est ignoré.

### Session longue et contexte

La session reste ouverte micro fermé plutôt que d’être recréée à chaque réveil,
pour garder le contexte de la conversation. Comme une session Gemini Live audio
est limitée (environ 15 min sans compression, connexions réinitialisées par le
serveur), le mode mot d’éveil active la compression du contexte par fenêtre
glissante et la reprise de session (`session_resumption`) du plugin LiveKit
Google ; le plugin se reconnecte de lui-même sur un `GoAway`. Les autres modes
ne changent pas. Une session inactive n’envoie aucun audio et ne consomme donc
pas de jetons audio.

### Choix du moteur : openWakeWord plutôt que Porcupine

| Critère | openWakeWord 0.6 (retenu) | Porcupine (Picovoice) |
|---|---|---|
| Local | Oui, ONNX Runtime (déjà présent via LiveKit) | Oui |
| Mot | `hey_jarvis` pré-entraîné ; « Jarvis » seul détecté moins souvent | `jarvis` intégré |
| Compte / clé | Aucun | Clé d’accès Picovoice obligatoire, validée en ligne, offre gratuite limitée à un usage personnel |
| Licence | Apache-2.0 (modèles pré-entraînés : CC BY-NC-SA 4.0, usage non commercial) | Propriétaire |
| CPU (estimé, à mesurer) | Quelques % d’un cœur (spectrogramme + embedding par pas de 80 ms) | Très faible |
| Personnalisation | Entraînement possible d’un modèle « Jarvis » seul | Console Picovoice |

openWakeWord est retenu : aucune clé ni compte tiers, tout reste local sans
dépendance à un service de licence, et le moteur s’insère derrière une petite
interface (`score`, `reset`, `frame_samples`) dans
`src/jarvis/desktop/wake_word.py`. Porcupine resterait l’alternative si le CPU
ou le taux de détection de « Jarvis » seul se révélaient insuffisants : il
suffirait d’un second adaptateur de moteur.

### Tests et ce qui reste à valider sur le Mac

`tests/test_desktop_wake_word.py` couvre, avec des moteurs, listeners et
périphériques simulés (aucun modèle ni matériel) : rééchantillonnage, détection
unique et période réfractaire, transmission de la parole qui suit le mot, file
bornée, panne du détecteur, porte audio (rien vers Gemini en veille, mute
prioritaire, bip sans protection en alternance), démarrage en veille sans
salutation, réveil avec bip seul, retour en veille après inactivité, réactivation
du micro en veille, échec fermé, priorité du maintien pour parler.

À valider sur le Mac (non mesurable ici) :

- Taux de faux réveils sur une heure de bruit ambiant, de vidéo et de
  conversation ; ajuster `JARVIS_WAKE_THRESHOLD`.
- Taux de détection de « hey Jarvis » et de « Jarvis » seul, avec l’accent de
  l’utilisateur, à 1 m et à 3 m.
- CPU du processus en veille (Moniteur d’activité) et effet sur la batterie.
- Premier téléchargement du modèle, puis fonctionnement hors ligne.
- Tenue d’une session en veille plus de 15 min, puis réveil avec contexte
  conservé (« de quoi parlions-nous ? »).
- Enchaînement « Jarvis, quelle heure est-il » sans pause.
