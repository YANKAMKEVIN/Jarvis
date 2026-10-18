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
Le desktop utilise Gemini Live ; Ollama n’est pas requis pour cette interface.
Les modes terminal existants restent indépendants.

## Une interface conçue pour la voix

- Deux vues partagent une seule session vocale : fenêtre complète et compagnon
  compact au premier plan. Changer de vue ne relance ni connexion ni demande.
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
- L’onglet Activité affiche seulement l’état de session et le nombre de demandes
  vocales reçues, jamais le contenu des phrases.
- L’orbe est peint localement, sans image téléchargée. Le réglage **Réduire les
  animations** et le masquage arrêtent son timer.

Cette protection audio fonctionne en alternant écoute et réponse ; ce n’est pas
une annulation acoustique d’écho permettant de parler simultanément à Jarvis.
Le son réel et les latences des périphériques restent à vérifier sur le Mac.

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
```

La démo est uniquement visuelle : aucun micro, connexion Gemini ou outil système.

Avec la barre de menus disponible, fermer la fenêtre la masque ; le menu
**Jarvis → Quitter** termine l’app après nettoyage de la session. Sans barre de
menus, fermer la fenêtre demande la fermeture complète. `Ctrl+C` dans le terminal
demande aussi cet arrêt propre, même avec les animations réduites. `Échap` ne
termine pas l’application.

`⌘⇧Espace` sur Mac (`Ctrl+Shift+Space` ailleurs) ouvre le compagnon lorsque
Jarvis est l’application active. Ce n’est pas encore un raccourci global.

## Captures réelles

Mode démo, rendu Qt offscreen sous Linux, sans activation audio :

![Assistant vocal](screenshots/desktop-home.png)
![Compagnon compact](screenshots/compact-idle.png)

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
le changement de vue et l’arrêt. Le rendu Linux ne valide pas le son ou TCC.

Résultat sous Linux/Python 3.13 : **30 tests desktop passants**. Suite complète :
822 tests et 149 sous-tests passants, avec les mêmes 207 échecs de frameworks
macOS absents que le snapshot de référence ; aucun nouvel identifiant en échec.
La suite complète n’est donc pas déclarée verte sur Linux.
