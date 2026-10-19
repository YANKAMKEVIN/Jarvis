# Jarvis Desktop — assistant vocal

## Installer et ouvrir

Sur le Mac, depuis le dépôt (Python 3.13+) :

```bash
source .venv/bin/activate
python -m pip install -e '.[desktop,live]'
jarvis-desktop
```

Configurer `GOOGLE_API_KEY` dans le `.env` du projet ou dans
`~/Library/Application Support/Jarvis/desktop.env`.
Voir [le guide vocal](desktop-voice.md) pour la configuration et le diagnostic.
Le dialogue vocal utilise Gemini Live ; certaines capacités avancées ci-dessous
utilisent aussi les moteurs locaux existants.
Les modes terminal existants restent indépendants.

## Une interface conçue pour la voix

- Trois vues partagent une seule session vocale : fenêtre complète, compagnon
  compact et orbe seul au premier plan. Changer de vue ne relance ni connexion ni demande.
- Aucun champ de saisie, bouton Envoyer, suggestion textuelle ou fil de messages.
  L’orbe et les libellés indiquent connexion, écoute, réflexion, réponse et erreur.
- **Démarrer Jarvis** ouvre la session puis le micro. Rien n’écoute au lancement.
- **Couper le micro** ferme la capture ; le même bouton permet de la reprendre.
- **Interrompre** coupe la réponse orale. Les actions système déjà lancées peuvent
  continuer. L’entrée audio est suspendue pendant la lecture de Jarvis et une
  courte période après pour limiter les retours de sa propre voix. Pour reprendre
  la parole avant la fin, utiliser ce bouton et attendre le retour de l’écoute.
- **Arrêter** ferme l’audio puis nettoie la session. Les confirmations des outils
  se font vocalement, selon le protocole existant de Gemini Live.
- L’onglet Activité suit les actions et les étapes du planificateur, jamais le
  contenu des phrases prononcées. Les cartes présentent seulement certains
  résultats structurés, sans recréer un fil de conversation.
- L’orbe est peint localement, sans image téléchargée. Le réglage **Réduire les
  animations** et le masquage arrêtent son timer.

Cette protection audio fonctionne en alternant écoute et réponse ; ce n’est pas
une annulation acoustique d’écho permettant de parler simultanément à Jarvis.
Le son réel et les latences des périphériques restent à vérifier sur le Mac.

## Présence holographique

L’orbe combine un cœur lumineux, des filaments, des points et des anneaux de
verre. Le bleu glacier accompagne l’écoute, le violet la réflexion, le rose les
erreurs et le gris le micro coupé. Son mouvement de fond est décoratif ; ses
pulsations supplémentaires dépendent du niveau RMS réellement mesuré dans les
blocs PCM du micro ou de la sortie audio. Aucun échantillon ne traverse le pont
Qt : seuls deux nombres sont émis, au maximum dix fois par seconde. Les niveaux
périmés, coupés ou suspendus sont ramenés à zéro. La démo ne simule pas de voix.

Les commandes restent accessibles et s’estompent légèrement au repos. Le survol
ou le focus clavier rétablit leur contraste. Le réglage **Réduire les animations**
arrête la respiration, les pulsations et les fondus ainsi que le transfert animé
de l’orbe entre les vues. Ce réglage est mémorisé. Les fenêtres partagent toujours
une seule session.

Le compagnon est une capsule sans bordure, au premier plan. Faire glisser la
zone **JARVIS** dans son en-tête pour le déplacer. Sa position est mémorisée dans
les préférences locales à la fin du déplacement, au changement de vue et à la
fermeture ; une position sur un écran débranché est replacée sur l’écran actuel.
La démo ne sauvegarde pas sa position. Le verre utilise de la transparence peinte,
sans flou d’arrière-plan natif macOS.

## Orbe seul

Le bouton **◉** dans l’en-tête ou le menu Jarvis → **Orbe seul** réduit la présence
à un petit orbe transparent et son état micro. Cliquer ouvre la capsule, faire
glisser l’orbe le déplace. **Entrée**, **Espace** ou **Échap** depuis l’orbe ouvre
également la capsule. Le clic n’active jamais le micro. Le clic droit donne accès
au démarrage/arrêt vocal, au micro, à l’interruption, aux détails et à Quitter.
La position de l’orbe est mémorisée séparément de celle de la capsule et corrigée
si son écran a disparu. Aucune vue n’ouvre une deuxième session.

```bash
jarvis-desktop --orb
jarvis-desktop --demo --orb
```

## Cartes liées aux résultats

Demander vocalement son agenda, ses rappels, le volume du Mac, une recherche web
ou le résumé d’une URL fournie. Si le résultat est compatible, un aperçu apparaît
dans la fenêtre complète ; **Voir les détails** ouvre l’onglet **Cartes**. La
capsule et l’orbe indiquent la présence de cartes sans afficher leurs contenus
personnels sur le bureau miniature.

- Quatre cartes au maximum parmi les catégories web/page, agenda, rappels,
  volume et écran. La plus ancienne est remplacée lorsque cette limite est atteinte.
- Agenda et rappels : six lignes affichées au maximum, avec le nombre total dans
  le résultat. Dates formatées dans le fuseau local lorsque leur format le permet.
- Réponse web : extrait limité et jusqu’à quatre sources. Les liens s’ouvrent
  seulement après un clic, en HTTP(S) ; ni fichier local, script, identifiants ou
  paramètres d’authentification reconnus ne sont transmis aux boutons de source.
- **Masquer les cartes** efface uniquement cette présentation. Aucun rendez-vous,
  rappel ou contexte Gemini n’est supprimé. Les cartes sont aussi vidées à la
  prochaine activation du vocal et ne sont jamais enregistrées sur disque.

Ces cartes peuvent contenir les titres de rendez-vous, textes de rappels et
réponses web ou analyses d’écran demandées : elles sont visibles dans la fenêtre complète. Il n’y a
ni transcription ni collecte supplémentaire en arrière-plan. Les autres outils
continuent de répondre vocalement, avec leur état dans Activité.

## Suivi des actions et tâches

La mission est visible directement dans **Assistant**. Dans la fenêtre complète,
un panneau de verre apparaît à droite de la sphère : objectif, état, outil en
cours et trois dernières étapes affichées. La sphère se décale et adapte sa
taille à la place disponible. Les états demandant une précision ou un accord
vocal gardent le panneau développé. **Annuler la mission** utilise la même
annulation coopérative que dans Activité, indépendamment de l’interruption audio.

À la fin, le panneau devient un petit bilan sous la sphère, avec **Détails** et
**Masquer**. Masquer n’efface ni la mission ni son historique. En mode compact,
deux lignes sous l’orbe indiquent l’objectif court et l’étape ou l’état courant ;
cliquer ce résumé ouvre toujours **Activité**, même si des cartes sont présentes.
Les objectifs longs sont raccourcis à l’affichage et restent lisibles dans
l’infobulle et les détails. Le panneau utilise uniquement les événements de la
session existante : aucune mission ni connexion supplémentaire n’est lancée.

Le fondu d’apparition est désactivé avec **Réduire les animations**. Les commandes
de confirmation restent vocales. L’onglet **Activité** conserve les étapes
détaillées et les missions précédentes.

Captures réelles Qt, avec mission simulée et commandes vocales désactivées :

![Mission à côté de la sphère](screenshots/assistant-mission.png)
![Résumé dans le compagnon compact](screenshots/compact-mission.png)
![Bilan après la mission](screenshots/assistant-mission-bilan.png)

## Plusieurs missions et file d’attente

Le moteur accepte six demandes vivantes au maximum, avec deux exécutions
simultanées. Chaque mission possède son identifiant, ses étapes, son état,
son résultat et son annulation. Une mission **En attente de ressources** n’a
encore lancé aucune action. L’attente ne consomme pas le budget d’exécution
du planificateur. Une septième demande est refusée, sans remplacer les autres.

Deux politiques sont appliquées par le moteur :

- `run_task(goal, read_only=true)` réserve une place de recherche. Son jeu
  d’outils est réduit aux lectures autorisées : réponse web, mémoire/activité,
  liste/recherche/métadonnées de fichiers et certains états système. Aucun outil
  de navigateur, presse-papiers, capture, souris, clavier, préparation d’envoi
  ou modification de fichier n’est accessible dans ce mode, même si le modèle
  le réclame. Deux recherches peuvent réellement se chevaucher.
- Le mode par défaut réserve le bureau pendant tout le plan, y compris entre
  deux étapes. Les autres missions de ce mode attendent leur tour. Une recherche
  peut utiliser l’autre place pendant cette attente. Les commandes vocales
  directes qui touchent au bureau partagent ce verrou : si une mission l’utilise,
  elles retournent `desktop_busy` sans exécuter l’action. Elles ne sont pas
  silencieusement rejouées après la mission.

Le verrou concerne la session Jarvis, pas les autres processus ni les actions
manuelles de l’utilisateur. Les verrous internes des outils et les confirmations
vocales existantes restent en place. Une préparation d’envoi termine le plan en
attente d’accord et libère le bureau ; sa confirmation ultérieure garde ses
vérifications habituelles. Une annulation ne revient pas sur les effets passés.

Dans Assistant, deux cartes au maximum restent visibles à droite de la sphère,
avec un format plus court lorsqu’elles sont plusieurs. Le compteur ouvre
**Activité** pour les autres missions. Chaque bouton **Annuler** vise uniquement
l’identifiant de sa carte. En compact, **N missions actives · Suivante** permet
de choisir la mission dont le résumé est affiché. Les attentes de précision ou
d’accord sont incluses dans les missions à suivre, sans occuper une place
d’exécution une fois le plan arrêté.

`task_status()` liste les missions ; `task_status(task_id)` en cible une.
`cancel_task(task_id)` demande son annulation. Sans identifiant et avec plusieurs
missions en cours/en attente, l’annulation est refusée comme ambiguë : Jarvis
doit demander laquelle. Annuler une mission en file l’empêche de démarrer.
Fermer la session annule toutes les missions coopérativement, attend leur
nettoyage et ne laisse pas les missions en file démarrer ensuite.

Le moteur conserve au maximum dix snapshots récents dans la session ; Activité
affiche les missions à suivre et jusqu’à quatre bilans terminés. Une reconnexion
conserve les éléments affichés pour vérification mais crée un moteur neuf,
sans reprise ni relance automatique.

Captures réelles Qt avec missions simulées, sans modèle, micro ni outils natifs :

![Deux missions dans Assistant](screenshots/assistant-missions.png)
![Sélection d’une mission en compact](screenshots/compact-missions.png)
![Missions supplémentaires](screenshots/missions-queue.png)

**Activité** conserve les trente dernières actions de cette session. Les actions
instrumentées du registre annoncent leur début et leur retour ; les lectures
non instrumentées apparaissent après le retour SDK. Le planificateur fournit ses
étapes réelles, consultées quatre fois par seconde sans nouvelle requête modèle.

**En cours**, **Résultat reçu**, **État vérifié**, **Accord vocal attendu** et
**L’outil signale un problème** restent distincts. « État vérifié » exige un
résultat `state_confirmed=true`. Aucun pourcentage, plan ou succès système n’est
inventé. Les noms génériques d’outils sont affichés sans arguments, chemins,
messages d’erreur bruts ou jetons de confirmation.

La carte **Mission actuelle** ajoute l’objectif transmis au planificateur
(300 caractères maximum), l’outil effectivement en cours et un bilan lié à
l’état final. L’objectif est une donnée de mission affichée volontairement,
pas une transcription de la conversation. Aucun résumé libre du modèle,
argument d’outil ou contenu de confirmation n’est copié dans cette carte.
Au maximum 25 étapes sont détaillées, avec le nombre total si la liste est plus longue.
Une fin du planificateur ne transforme pas un simple résultat reçu en effet vérifié.
Le bilan décrit le dernier retour du planificateur : une action préparée puis
confirmée vocalement est suivie séparément dans Activité, sans réécrire
automatiquement ce bilan ni reprendre le plan.

Les quatre missions précédentes restent consultables dans **Activité**, avec
l’actuelle, uniquement en mémoire pendant la session. **Effacer l’activité**
efface aussi leurs bilans quand aucune action ou mission n’est en cours.
Une reconnexion conserve ce suivi pour vérification, mais ne relance rien.
Un démarrage vocal neuf le vide ; aucune reprise automatique n’est proposée.

![Mission et étape actuelle · données simulées](screenshots/task-progress.png)

**Annuler la tâche** utilise l’annulation coopérative existante du planificateur.
L’interface indique d’abord la demande, puis l’issue réelle ; une action déjà
lancée peut finir. **Interrompre** reste réservé à la réponse audio et n’annule
pas la tâche. Les actions en attente d’accord restent confirmées vocalement :
aucun bouton ne contourne leur protocole. Une fin de session sans résultat laisse
un état « Résultat indisponible », sans faux succès.

## Compréhension de l’écran à la demande

Les outils existants `describe_screen` et `ask_about_screen` sont reliés à
l’interface. Demander par exemple : « Décris ce qui est visible dans Safari »
ou « Que dit l’erreur affichée dans cette fenêtre ? ». Une capture reste une
opération ponctuelle ; aucune surveillance continue n’est ajoutée.

Pendant l’appel d’un outil de capture ou d’analyse, **Observation d’écran en cours**
apparaît dans la fenêtre, le compagnon, l’orbe et la barre de menus. Le signal
couvre l’attente de capture et d’analyse ; il ne prétend pas mesurer la durée
exacte de la capture système. Plusieurs opérations concurrentes restent signalées
jusqu’à leur fin, échec ou annulation. Une fin de session efface cet indicateur.

Une analyse réussie fournit une carte **Analyse de l’écran**, limitée à 1 600
caractères, avec la portée fenêtre/écran. Elle peut contenir des informations
personnelles visibles sur l’écran : seule la fenêtre complète en affiche le
contenu. Aucun fichier image, miniature, chemin local, modèle ou question brute
n’est ajouté à la carte. Une capture seule n’est jamais présentée comme une
analyse. Les captures PNG conservent le stockage du moteur existant ; masquer
la carte ne supprime pas ces fichiers.

La vision doit déjà être activée par `JARVIS_VISION_ENABLED=1`, avec la clé
Gemini et l’autorisation macOS de capture d’écran. L’interface n’active pas cette
option automatiquement. Une vision désactivée ou une permission refusée fournit
une erreur, sans carte de succès. La fenêtre active peut être Jarvis : nommer
l’application souhaitée pour que le moteur cible sa fenêtre vérifiée.
Une observation n’exécute aucune action sur ce qu’elle voit.

![Analyse d’écran · résultat simulé dans la vraie interface Qt](screenshots/screen-analysis.png)
![Indicateur d’observation · simulation sans capture réelle](screenshots/screen-observation.png)

Pour essayer : « Quels sont mes rendez-vous ? », « Liste mes rappels », puis une
demande nécessitant plusieurs étapes. Le moteur de recherche web conserve sa
synthèse locale Ollama. Les tâches utilisent le planificateur existant : Ollama
par défaut, ou Gemini si `JARVIS_PLANNER_BACKEND=gemini` est configuré. Le desktop
charge aussi depuis ses fichiers `.env` les options de modèle/limites du
planificateur et `JARVIS_LLM_MODEL`. Ces capacités peuvent nécessiter un modèle
local disponible ; Gemini Live seul ne remplace pas leur configuration.

Dans **Réglages**, activer les sons discrets pour entendre un court signal au
démarrage de l’écoute et à la coupure/reprise du micro. L’option est désactivée par
défaut et mémorisée. Les sons sont synthétisés localement dans la sortie audio
existante, laissent la priorité à la parole de Jarvis et bénéficient du même
blocage de retour dans le micro. Ils ne nécessitent aucun périphérique ou fichier
supplémentaire. La démo reste silencieuse.

## Finder et Dock

Créer une fois le lanceur depuis l’environnement activé :

```bash
python scripts/build_desktop_app.py
open ~/Applications/Jarvis.app
```

Ensuite, double-cliquer sur `Jarvis.app` depuis Finder ou la garder dans le Dock.
Ce lanceur de développement référence le chemin absolu du dépôt et du Python
actuel : conserver le dépôt et `.venv` à leur place. Ce n’est pas une application
encore autonome et signée pour distribution sur d’autres Macs.

Pour actualiser un lanceur existant :

```bash
python scripts/build_desktop_app.py --update
```

Finder ne reprend pas les exports du terminal. Le vocal charge la configuration
utilisateur puis celle du projet, sans remplacer les variables déjà exportées.

## Démo et fermeture

```bash
jarvis-desktop --demo
jarvis-desktop --demo --compact
jarvis-desktop --demo --orb
```

La démo est uniquement visuelle : aucun micro, connexion Gemini ou outil système.

Avec la barre de menus disponible, fermer la fenêtre la masque ; le menu
**Jarvis → Quitter Jarvis** termine l’app après nettoyage de la session. Sans barre de
menus, fermer la fenêtre demande la fermeture complète. `Ctrl+C` dans le terminal
demande aussi cet arrêt propre, même avec les animations réduites. `Échap` ne
termine pas l’application.

## Contrôles depuis la barre de menus

Le menu permanent partage le contrôleur des trois fenêtres : il permet de
démarrer, arrêter ou reconnecter le vocal, couper/réactiver le micro et
interrompre une réponse. Les commandes sont désactivées pendant la connexion,
l’arrêt et le nettoyage d’une session en erreur. Les tests audio bloquent le
démarrage du vocal ; **Arrêter le test audio local** reste accessible dans le menu.
La démo ne permet aucune capture ou connexion.

Deux lignes séparent l’état de Jarvis de l’état de capture. **Écoute suspendue**
pendant la réponse ne signifie pas que le périphérique micro est fermé : la
ligne **Capture micro ouverte** continue de l’indiquer. Le test du micro porte
explicitement la mention **local**. L’icône est barrée quand la capture est
fermée ; sa couleur reflète repos, écoute, réflexion/réponse ou erreur. Ces
indications suivent les événements du contrôleur, sans transcription, erreur
brute ou résultat d’outil dans le menu ni l’infobulle.

**Masquer les fenêtres** garde la session dans son état actuel. Cette commande
n’est effective que si la barre de menus est disponible. **Réglages audio** ouvre
directement les réglages ; les cartes, le compagnon et l’orbe restent accessibles.
Ouvrir le menu ne force plus l’apparition du compagnon. Quitter attend toujours
la fermeture du worker vocal ou du test audio local.

Capture réelle du menu Qt en démo, sans barre native ni micro. Sur Mac, le menu
utilisera l’apparence native du système ; cette image ne valide pas son intégration.

![Contrôles du menu en démonstration](screenshots/menu-controls.png)

Pour reproduire cette capture :

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_menu.py
```

## Raccourci global

Sur macOS, **⌘⇧Espace** fait apparaître le compagnon depuis une autre application,
sans démarrer le vocal ni ouvrir le micro. Dans **Réglages**, l’option permet de
l’activer ou le désactiver ; son état est mémorisé. Le message indique si
l’enregistrement natif a réussi. Si la combinaison est réservée ou indisponible,
vérifier les raccourcis macOS/autres applications puis utiliser **Réessayer le
raccourci**. Le raccourci local reste disponible lorsque l’enregistrement global
est inactif. Le raccourci est libéré à la fermeture.

L’implémentation utilise une seule combinaison Carbon enregistrée exclusivement,
avec filtrage de son identifiant ; elle ne lit pas les autres frappes. Les appels
UI passent par un signal Qt en file d’attente. La démo et Qt offscreen n’installent
aucun raccourci système ; hors macOS, seul le raccourci local est proposé.
Le fonctionnement natif depuis une autre application doit être vérifié sur Mac.

Référence des signatures/constantes : [en-tête Carbon du SDK Apple macOS](https://github.com/phracker/MacOSX-SDKs/blob/master/MacOSX10.15.sdk/System/Library/Frameworks/Carbon.framework/Versions/A/Frameworks/HIToolbox.framework/Versions/A/Headers/CarbonEvents.h).

## Choix et tests audio

Dans **Réglages**, arrêter le vocal puis utiliser **Actualiser** pour lire la
liste des périphériques. Choisir le microphone et la sortie souhaités. Le choix
est mémorisé par nom et système audio, puis résolu à chaque démarrage ; les indices
PortAudio changeants ne sont pas enregistrés. Un périphérique absent ou ambigu
ne bascule jamais silencieusement sur un autre. **Utiliser les périphériques
système** rétablit explicitement le choix par défaut.

- **Tester le micro** ouvre seulement l’entrée, montre son niveau réel et la ferme
  au bout de cinq secondes ou avec **Arrêter le test**. Rien n’est enregistré ou
  envoyé à Gemini.
- **Tester la sortie** ouvre seulement la sortie et joue un bref signal local à
  faible amplitude, puis ferme le périphérique. Le micro n’est pas ouvert.
- Le niveau d’entrée peut aussi être consulté pendant la session vocale existante,
  sans deuxième capture. Le réglage et les tests sont verrouillés pendant le vocal.
- Les tests et le vocal sont exclusifs : démarrer l’un bloque l’autre jusqu’à la
  fermeture du worker. Quitter pendant un test attend sa fermeture normale.
- Pendant un test micro, la capsule et l’orbe indiquent **Test micro local**, et
  distinguent cette capture de la voix transmise à Gemini.
- Le format reste mono PCM16 à 24 kHz. Les tests détectent l’indisponibilité ou le
  format non pris en charge. Un flux arrêté en cours de session est signalé au
  lieu de laisser croire que Jarvis écoute encore.

La recherche de périphériques et les tests sont exécutés hors du thread UI. La
démo n’énumère et n’ouvre aucun périphérique. Les changements de périphériques
se font session arrêtée, puis sont appliqués au prochain démarrage.

## Reconnexion après coupure

Une fermeture imprévue ou une erreur de connexion met fin à la session et ferme
l’audio. Le bouton **Reconnecter** devient disponible après la fin du nettoyage.
Il ouvre une nouvelle session après une action explicite ; aucune demande, action,
transcription ou approbation de la session interrompue n’est renvoyée. Les cartes
et l’activité précédentes restent consultables pour vérifier ce qui a déjà été
fait. Les tâches sans résultat final restent marquées comme telles.

Le micro coupé par l’utilisateur reste coupé à la reconnexion : même le démarrage
du nouveau flux n’ouvre pas brièvement l’entrée. Les périphériques choisis sont
à nouveau vérifiés. Une erreur de préparation ou de configuration propose
**Réessayer**, avec son message utile. Un arrêt demandé ne déclenche pas de
reconnexion automatique. Le SDK conserve sa gestion interne des erreurs
récupérables ; le bouton traite la fin effective de la session desktop.

La nouvelle conversation n’efface pas la mémoire durable existante de Jarvis ;
elle ne rejoue pas le contexte conversationnel de la session interrompue.

## Captures réelles

Mode démo, rendu Qt offscreen sous Linux, sans activation audio :

![Assistant vocal](screenshots/desktop-home.png)
![Compagnon compact](screenshots/compact-idle.png)
![Réglages audio en démo](screenshots/audio-settings.png)

L’orbe capturé par Qt est présenté sur un fond sombre uni pour rendre sa
transparence lisible dans les lecteurs d’images :

![Orbe seul](screenshots/orb-only.png)

Captures des cartes et du suivi avec des **données simulées explicitement
signalées**, sans lecture d’agenda, recherche web ou tâche réelle :

![Cartes simulées](screenshots/context-cards.png)
![Suivi simulé](screenshots/task-progress.png)

Pour reproduire ces captures sans audio, connexion ou lecture des préférences :

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_preview.py --samples
```

## Vérifications

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_desktop*.py
```

Les tests vérifient notamment l’absence d’interface textuelle, le partage d’un
seul worker, le contrôle micro/interruption, le filtrage du retour audio et le
nettoyage à la fermeture. Les périphériques et sessions réseau sont simulés.
Le test de préchargement utilise le vrai plugin Google, sans démarrer de connexion.

Sur Mac, vérifier Finder/Dock, permissions Microphone, une salutation, la pause
micro pendant une réponse sur haut-parleurs, l’interruption, la reprise d’écoute,
le changement de vue et l’arrêt. Vérifier aussi ⌘⇧Espace depuis Safari,
le choix d’un micro/casque, les tests locaux et une reconnexion après coupure
avec le micro préalablement coupé. Le rendu Linux ne valide pas le son ou TCC.
Vérifier aussi les commandes vocales depuis le menu avec toutes les fenêtres
masquées, la distinction capture/écoute, l’accès aux réglages et Quitter pendant
un test micro local.
Tester aussi une observation de fenêtre nommée, une vision désactivée, un refus
de capture macOS, une mission en cours puis terminée et ses bilans après reconnexion.
Pour les missions multiples, tester deux recherches indépendantes, deux missions
qui pilotent le bureau (la seconde attend), l’annulation ciblée de celle en
attente, une demande vocale ambiguë d’annulation et Quitter avec plusieurs missions.

Pour le lot multi-missions : **90 tests ciblés passants** (83 desktop et 7 tests
de concurrence/ressources). Les scénarios vérifient le chevauchement réel de
recherches simulées, le verrou du bureau, l’absence d’interférence d’une commande
directe, le refus d’outils hors lecture, la limite de file, l’annulation ciblée,
la fermeture globale, les identifiants transmis au worker et les deux cartes.
Suite complète dans cet environnement : **879 tests et 149 sous-tests passants**,
avec exactement les mêmes **210 échecs** que le snapshot avant modification
(207 liés aux frameworks macOS absents, 3 à la dépendance PDF `pypdf` absente).
Aucun nouvel identifiant en échec. L’audio, les effets réels sur le Mac et les
permissions restent à valider sur macOS ; la suite complète Linux n’est pas verte.

Pour le lot précédent du panneau intégré à Assistant : **29 tests UI, menu et présentation
passants**, dont 4 nouveaux contrôlant le placement, le bilan, la navigation,
l’annulation et la petite fenêtre. Vérification visuelle hors écran des captures
complète et compacte ; l’audio et l’intégration native macOS ne sont pas testés
par ces contrôles.

Résultat du lot précédent sous Linux/Python 3.13 : **75 tests desktop passants**. Suite complète
exécutée pendant ce lot, avant le dernier test de rendu Qt :
866 tests et 149 sous-tests passants, avec les mêmes 207 échecs de frameworks
macOS absents que le snapshot de référence ; aucun nouvel identifiant en échec.
La suite complète n’est donc pas déclarée verte sur Linux.


### Dix capacités vocales supplémentaires

Le [guide des capacités](capabilities-v2.md) décrit les dix ajouts, leurs exemples
vocaux et leurs limites. Les missions dépendantes et en pause restent visibles
près de la sphère ; les résultats de checklists, minuteurs, documents et agenda
utilisent la vue Cartes. Aucun champ de saisie n’est ajouté.
Les captures suivantes sont des rendus Qt réels alimentés par des données simulées :

![Checklists, minuteurs et documents simulés](screenshots/productivity-cards.png)

![Missions simulées en pause et dépendantes](screenshots/mission-dependencies.png)

Validation de ce lot : **134 tests ciblés passants** (capacités, notes, agenda,
concurrence et desktop). Suite complète : **902 tests et 149 sous-tests passants**,
avec les mêmes **210 échecs préexistants** que le snapshot de référence Linux
(207 liés aux frameworks macOS absents et 3 à `pypdf` absent). Aucun nouvel
identifiant de test en échec. Les derniers ajustements de stockage ont été
revérifiés par la suite ciblée ; la validation native reste à faire sur Mac.
