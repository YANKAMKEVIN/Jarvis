# Compagnon : six améliorations de l’expérience

Ces changements sont développés sur `feat/avatar-collection`. Ils ne fusionnent
pas cette branche dans `main`.

## 1. Taille, transparence, position et mode discret

Dans le menu `•••` → **Personnaliser le compagnon** :

- Taille : 240, 320 ou 400 px.
- Opacité : 100 %, 85 % ou 65 %.
- Position libre, ou ancrage dans l’un des quatre coins de l’écran courant.
- Réduction à 180 px après trois minutes au repos, optionnelle.
- Bulles de notification activables/désactivables.

Les préférences sont mémorisées dans QSettings. L’avatar retrouve sa taille au
survol, à l’accès clavier, à une nouvelle interaction ou à une notification.
Les états d’écoute, réflexion, parole et les missions actives/attendant un accord
empêchent la réduction automatique. Les minuteries inutiles s’arrêtent quand la
vue est masquée. Un déplacement manuel remet l’ancrage en position libre.
Les ancrages se réajustent aux changements de géométrie d’écran. Le réglage macOS
« tous les bureaux » et la réduction des animations sont conservés.

## 2. Bouton vocal contextuel

Le premier des deux boutons au survol remplace l’ancien bouton d’agrandissement :

- Vocal arrêté : démarrer/reconnecter.
- Session en écoute : couper le micro.
- Micro coupé : réactiver le micro.
- Jarvis parle : interrompre sa réponse.
- Mode maintien activé : maintenir ce bouton pour parler.

Le menu contient **Ouvrir Jarvis**, les missions, cartes, apparences et réglages.
L’avatar seul reste déplaçable et ne démarre jamais le micro au simple clic.
Les commandes de capture sont désactivées en démo et pendant un test audio local.
La connexion en cours peut être annulée depuis son menu.

## 3. Notifications temporaires

Une bulle apparaît pour une mission terminée, échouée, demandant un accord ou une
précision, et pour une interruption/récupération du vocal. Elle disparaît après
sept secondes, se ferme avec `×` et ouvre les bons détails au clic. Un accord
reste à donner vocalement : cliquer sur une bulle ne confirme aucune action.

La file est bornée à cinq bulles, les doublons proches sont filtrés, et les
notifications de plus d’une minute sont ignorées. Aucune transcription n’entre
dans la bulle. Les bulles ne forcent ni le focus ni l’ouverture de la fenêtre
principale ; elles restent sur les bureaux du compagnon et dans l’écran courant.

## 4. Maintenir pour parler

Activez **Maintenir pour parler · ⌘⌥Espace** dans `•••`.

- Maintenez le bouton vocal du compagnon ; ou
- Maintenez **Espace** lorsque l’avatar a le focus ; ou
- Maintenez **⌘⌥Espace** depuis une autre application sur macOS.

Le premier appui peut établir la session. Vous pouvez aussi démarrer la session
par le menu, puis utiliser le maintien une fois la connexion prête. Le relâchement,
la perte de focus du maintien local, Échap ou le masquage du compagnon ferme la
capture ; une limite de 45 secondes évite un appui bloqué. Désactiver ce mode ne
réouvre pas automatiquement le micro. En cas de conflit du raccourci global,
le bouton et la touche locale restent disponibles et le message l’indique.
Le raccourci existant **⌘⇧Espace** continue d’ouvrir le compagnon.

Le maintien utilise le flux micro existant. Il n’y a ni seconde capture ni
sauvegarde PCM. Un court silence synthétique borné termine l’entrée après les
derniers échantillons capturés ; la détection de tour reste celle de Gemini.
Les annonces de mission attendent la fin du maintien et un état vocal libre.
En mode maintien, la connexion n’émet pas de salutation qui couvrirait le début
de la demande. Les vrais états réflexion/parole restent visibles même micro coupé.

## 5. Routines vocales personnelles

Ouvrez **Routines vocales…** depuis `•••` ou les réglages de la fenêtre complète.
Les exemples **Ma journée** et **Concentration** remplissent une configuration à
adapter (l’exemple Concentration propose un minuteur de 25 minutes) ; ils ne s’enregistrent et ne s’exécutent pas automatiquement.

1. Choisissez un nom et décrivez l’objectif (500 caractères maximum).
2. Enregistrez.
3. Dites « lance la routine [nom] », ou sélectionnez-la et cliquez sur Lancer
   pendant une session vocale active.

Le bouton Lancer exécute la version enregistrée ; les modifications non
sauvegardées doivent d’abord être enregistrées. La configuration n’est pas un
chat écrit. Les routines réutilisent exactement le `MacroStore` local et l’outil
vocal `run_macro` déjà enregistré, sans reconstruire son gestionnaire de tâches.
Le journal, le mode lecture seule, les limites de missions et les confirmations
existantes restent appliqués. Les expressions « prépare ma journée » et « mode
concentration » peuvent retrouver une routine correspondante ; aucune routine
implicite n’est créée si elle n’existe pas.

## 6. Récupération du vocal

**Reconnecter automatiquement après coupure** est activé par défaut en usage
natif, et désactivé par défaut dans les tests/rendus hors écran. Ce choix est
persistant. Il ne démarre jamais une session après un simple lancement de Jarvis.

Après une erreur déclarée réessayable, trois reconnexions au maximum sont
proposées à 2, 5 puis 10 secondes, seulement après fermeture de l’ancien worker.
Le menu indique l’avancement et permet **Annuler la reconnexion**. Un arrêt
volontaire et la fermeture de Jarvis annulent les essais. Dix secondes de connexion
stable réinitialisent le compteur. Les erreurs de configuration non réessayables
ne déclenchent pas cette boucle.

La mise en veille demande l’arrêt de la capture et de la session. Le réveil
rétablit une session demandée précédemment, si l’option est active et si
l’utilisateur ne l’a pas arrêtée. Le mode muet reste conservé et le mode maintien
revient micro fermé. Un changement de périphérique audio système par défaut ou
un arrêt de flux déclenche la récupération ; un périphérique explicitement choisi
n’est jamais remplacé silencieusement par un autre choix.

Les cartes et les états des missions restent consultables, mais les actions ne
sont pas rejouées. Une reconnexion crée une nouvelle conversation ; une ancienne
mission interrompue n’est pas présentée comme réussie ou reprise automatiquement.

## Installation et essais

Quitter complètement Jarvis avant la mise à jour :

```sh
cd ~/dev/Jarvis
git switch feat/avatar-collection
git pull --ff-only origin feat/avatar-collection
source .venv/bin/activate
python -m pip install -e '.[desktop,live]'
jarvis-desktop --demo --compact
```

La démo permet de tester la présentation et la configuration, avec le vocal et
le lancement des routines désactivés. Pour les interactions audio réelles :

```sh
jarvis-desktop --compact
```

Diagnostic natif sans micro ni Gemini, et captures reproductibles :

```sh
python scripts/diagnose_desktop_experience.py --native
QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_experience.py
```

Les [captures réelles Qt](screenshots/experience/) utilisent des préférences et
un stockage de routines temporaires. La notification est simulée ; le fond du
comparatif sert uniquement à rendre la transparence lisible. Aucun visuel
conceptuel n’est présenté comme une capture de l’application.

Tests pertinents :

```sh
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_desktop*.py tests/test_macros.py tests/test_live_poc.py tests/test_read_only_mode.py tests/test_multi_missions.py -q
```

La vérification native a enregistré le raccourci Carbon, les deux observateurs
macOS de veille/réveil, les réglages de taille/ancrage/opacité et les propriétés
Spaces du compagnon et de la bulle, sans ouvrir de micro. Les tests utilisent des
workers et périphériques simulés pour les coupures, reprises, relâchements et
routines. Restent à essayer manuellement : une conversation Gemini réelle, une
veille/réveil réelle, le changement d’un périphérique physique et les passages
entre écrans/bureaux pendant ces interactions.

### Résultats de livraison

- 412 tests pertinents et 8 sous-tests réussis, avec sortie normale du processus.
- Diagnostic natif Cocoa réussi : raccourci de maintien enregistré, deux
  observateurs de veille/réveil, ancrage/taille/opacité et fenêtres Spaces.
- Roue Python construite puis installée dans un répertoire isolé : préférences,
  maintien, bulles, configuration des routines et les 16 assets vérifiés.
- Aucun micro ni appel Gemini pendant les diagnostics et les captures.

## Danse des personnages

Dans les commandes du compagnon (`•••` ou clic droit), **Faire danser** lance une
chorégraphie de huit secondes, y compris dans `jarvis-desktop --demo --compact`.
En session vocale, demander « Danse », « Tu sais danser ? » ou « Montre-moi une
danse » utilise la commande de présentation dédiée. « Arrête de danser » arrête
la danse sans fermer le vocal ni les missions. Jarvis lance la danse avec une courte
phrase joueuse, différente à chaque fois, sans décrire l'animation qu'il ne voit pas. La reconnaissance réelle par
Gemini reste à essayer avec un micro.

NovaBot, Neo Guide, Kitsune, Digital Avatar, Synth Companion et Holo Face
utilisent leurs poses 2D existantes : balancements, petits bonds, poses alternées
et inclinaisons adaptées au personnage. Holo Face garde une amplitude réduite.
Ces images ne possèdent pas de squelette articulé : il ne s'agit pas encore de
nouveaux mouvements de jambes dessinés ou d'une danse 3D.

En mode compact, la fenêtre accompagne le mouvement sur 32 pixels au maximum
horizontalement et 7 verticalement, dans la surface disponible du même écran.
Elle reprend sa place à la fin ; ce déplacement temporaire n'est pas enregistré
comme position préférée. Glisser le personnage, appuyer sur Échap, masquer le
compagnon, changer son apparence ou ses préférences interrompt la danse. Les
animations réduites et les apparences abstraites désactivent cette commande.
Les missions déléguées ne disposent pas de cet outil de présentation.

![Danse 2D : véritable capture Qt, sans micro](screenshots/experience/avatar-dance.gif)

`QT_QPA_PLATFORM=offscreen python scripts/capture_avatar_dance.py` produit les
81 images PNG de cet aperçu dans un dossier temporaire affiché en sortie. Elles
peuvent être assemblées en GIF avec Pillow, sans dépendance supplémentaire pour
l'application. `tests/test_desktop_dance.py` vérifie les limites, l'arrêt, le
retour, la persistance, la conservation des missions et les refus ; le test du
runtime vérifie le branchement et le nettoyage de la commande vocale sans appel
réseau ni ouverture du micro.

## Voix par avatar et aperçus intégrés

**Voix des avatars…** est accessible dans les réglages, le menu du compagnon et
la barre de menus macOS. Les 16 avatars conservent leurs associations de voix.
Le catalogue contient désormais 30 voix standard, dont les cinq choix initiaux,
Zephyr, Leda, Orus, Sulafat et Gacrux. Une recherche par nom ou description filtre
la liste ; la voix actuellement attribuée reste visible. Les étoiles marquent
les favoris, placés en tête de liste et mémorisés entre les démarrages.

Le catalogue provient de la [liste officielle des voix standard Google](https://ai.google.dev/gemini-api/docs/speech-generation#voice-options).
Le [guide Live](https://ai.google.dev/gemini-api/docs/live-api/capabilities#change-voice-and-language)
décrit leur utilisation avec les modèles audio natifs. Les voix personnalisées
et le catalogue étendu au-delà de ces 30 noms ne sont pas proposés ici.

Choisir un avatar dans cette fenêtre édite sa voix sans changer l'apparence
active. Chaque choix est enregistré automatiquement et indépendamment des autres
avatars. **Rétablir la voix initiale de cet avatar** ne modifie que ce personnage.
Les préférences invalides reviennent à sa voix initiale. Les favoris ne changent
ni les associations ni les sessions. Les associations sont stockées dans
QSettings sous `voice/avatars/<avatar>` et les favoris sous `voice/favorites`.

### Écouter et comparer

Lancer `jarvis-desktop --compact`, arrêter le vocal s'il est actif, puis ouvrir
**••• → Voix des avatars…**. Choisir une voix et cliquer **Écouter un aperçu**.
La même phrase est prononcée en français : « Bonjour, je suis Jarvis. Je peux
vous aider à organiser votre journée. Quelle est votre prochaine idée ? »
**Arrêter l’aperçu**, fermer la fenêtre, changer de voix ou changer d'avatar
interrompt l'aperçu. Aucun navigateur ni connexion à AI Studio n'est requis.

L'aperçu est une requête Gemini Live distincte, avec le modèle configuré et la
voix choisie. Seule cette phrase fixe est transmise : aucun contexte de session,
outil ou audio d'entrée n'est joint. Le microphone n'est jamais ouvert. Il faut
une clé Gemini valide et un accès réseau ; la génération utilise le quota API
habituel. Les données PCM sont conservées uniquement en mémoire, limitées à 15
secondes, puis jouées sur la sortie audio choisie dans les réglages. Aucune
nouvelle capture ni aucun fichier audio n'est créé. La génération expire après
30 secondes, les erreurs du fournisseur sont reformulées sans contenu privé.

Les aperçus et les autres opérations audio s'excluent : aucun aperçu ne démarre
pendant une conversation ou un test audio, et le démarrage du vocal attend la
fin de l'aperçu. À la fermeture de Jarvis, la génération ou la lecture est
interrompue et le worker est nettoyé avant de quitter. En démo, le catalogue,
la recherche et les favoris fonctionnent, mais l'écoute reste désactivée.

### Quand le choix est-il appliqué ?

Changer d'apparence sélectionne sa voix enregistrée pour le prochain démarrage
vocal. Une session déjà ouverte garde sa voix ; la fenêtre indique la voix en
cours et celle de la prochaine connexion. Aucun changement n'arrête une
conversation ou ses missions. Arrêter puis redémarrer le vocal applique le choix.
Une reconnexion automatique utilise aussi la voix de l'avatar actif.

Dans le desktop, les associations prennent la priorité sur
`JARVIS_GEMINI_LIVE_VOICE`, sans modifier l'environnement. Le mode CLI garde sa
configuration habituelle. La voix est transmise au modèle à la création de la
session, après chargement de l'environnement.

![Catalogue et aperçus : capture réelle Qt en mode démo](screenshots/experience/avatar-voices.png)

`QT_QPA_PLATFORM=offscreen python scripts/capture_avatar_voices.py` reproduit la
capture avec des préférences temporaires. `tests/test_desktop_voices.py` et
`tests/test_desktop_voice_preview.py` vérifient les associations, les favoris,
le filtrage, la transmission de voix, le format et les limites PCM, l'arrêt,
la fermeture des clients, la sortie audio seule et les exclusions de session.
Des générations réelles Puck et Sulafat ont fourni du PCM 24 kHz sans microphone.
Les tests de lecture utilisent une sortie simulée ; l'écoute au haut-parleur
et la comparaison subjective des 30 timbres restent des essais manuels.
