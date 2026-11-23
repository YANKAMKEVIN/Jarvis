# À faire sur le Mac (suite des idées du 23/11)

Branche `claude/idees-50`. Tout ce qui suit demande un Mac, un micro, des comptes ou
des clés : rien n'a pu être lancé depuis le conteneur Linux. Cochez au fur et à mesure.

## Idées prévues pour le Mac

### 1. Groupe smoke « tasks » avec un vrai cerveau
- [ ] Accorder l'Accessibilité au Terminal, lancer Ollama avec `granite4:3b`.
- [ ] `PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --group tasks` (Ollama), puis
      `JARVIS_PLANNER_BACKEND=gemini` (clé Gemini) et, si souhaité, `JARVIS_PLANNER_BACKEND=claude`
      (`pip install -e '.[claude]'`, clé Anthropic ou `ant auth login`).
- [ ] Noter le taux de réussite par tâche dans `docs/architecture-phase3-planification.md` (« À faire »)
      et ajuster `PLANNER_SYSTEM_PROMPT` (planner/engine.py) sur les échecs répétés.
- Attendu : chaque tâche réussie ou échouée avec une raison lisible ; aucun envoi réel.

### 40. Mesurer Ollama, Gemini (et Claude) avec planner_eval.py
- [ ] Étendre `scripts/planner_eval.py` d'une option `--backend` (ollama / gemini / claude) et d'un tableau
      taux de réussite / durée / tokens par backend (non fait : à écrire puis lancer sur le Mac).
- [ ] Lancer les mêmes tâches sur chaque backend, `--runs 3`, et consigner le tableau dans la doc phase 3.
- Attendu : une base chiffrée pour la décision « quel cerveau ? ».

### 50. Endurance vocale de deux heures
- [ ] Écrire le scénario (missions, rappels, micro ouvert, changements de bureau, veille du Mac) et sa grille
      (latence de réponse, mémoire du processus, reconnexions, erreurs audio, toutes les 15 min).
- [ ] Le lancer avec `jarvis-desktop` et une clé Gemini, micro réel, deux heures.
- Attendu : pas de fuite mémoire nette, reconnexions propres, aucun envoi sans accord.

## À vérifier sur ce qui a été codé sans Mac

- [ ] **2 · Confirmer / Annuler** : `jarvis-desktop`, demander « prépare un message WhatsApp pour … ».
      La carte « J'attends votre accord » apparaît sous la sphère ; **Confirmer** envoie (une seule fois),
      **Annuler** n'envoie rien ; le jeton n'apparaît nulle part. Idem avec un rappel d'agenda.
- [ ] **3 · Champ texte** : écrire « quelle heure est-il ? » puis Entrée pendant une session : Gemini répond
      à voix haute ; écrire « oui » après une préparation d'envoi confirme bien.
- [ ] **4 / 28 · Agent launchd** : sans le plist, `set_reminder` doit avertir et le tableau de bord afficher
      « Envois programmés » ; `python -m jarvis.schedule install` puis la commande `launchctl bootstrap
      gui/$(id -u) …` affichée ; `python -m jarvis.schedule status` doit dire « installe » et code 0.
- [ ] **7 · Mode texte** : `python -m jarvis.main`, « verrouille l'écran », « baisse la luminosité à 40 »,
      « mets la musique en pause », « minimise la fenêtre de Safari ».
- [ ] **8 · Mode texte avec outils** : `python -m jarvis.main --outils`, « rappelle-moi dans 5 minutes de boire »,
      puis un envoi WhatsApp : la question « Confirmer ? (oui/non) » doit apparaître avant tout envoi.
- [ ] **9 / 10 · Registre découpé, prompt allégé** : une session vocale normale (volume, apps, rappels, missions,
      danse) ; vérifier que la danse parle toujours, que les mails résumés et les tokens marchent.
- [ ] **16 · AppleScript** : `osascript -e 'return "a“b”c"'` doit rendre `a“b”c` (les guillemets
      typographiques sont gardés tels quels par l'échappement) ; taper un texte avec retour à la ligne
      et guillemets dans TextEdit via Jarvis.
- [ ] **26 · Icône** : `python scripts/build_desktop_app.py --update` puis Finder / Launchpad montrent l'orbe
      (sinon `touch ~/Applications/Jarvis.app` et relancer le Dock).
- [ ] **27** : Réglages affiche « Version 0.9.0 » ; « fais un diagnostic » cite la version.
- [ ] **29 · Rappels manqués** : programmer un rappel dans 2 min, fermer Jarvis, attendre la notification,
      relancer le vocal : Jarvis le mentionne en une phrase.
- [ ] **30 · Minuteur** : « minuteur 3 minutes pour les pâtes », fermer Jarvis : la notification arrive à l'heure.
- [ ] **31 · Serveurs MCP** : Réglages → Serveurs MCP… : tester un vrai serveur (npx), cocher un outil,
      enregistrer ; `mcp.json` reste valide et en 0600.
- [ ] **32 · Ressources MCP** : avec un serveur qui expose des ressources (ex. filesystem), « liste les
      ressources de … » puis lecture, aussi en mode sécurité.
- [ ] **34 · Mot d'éveil** : supprimer les modèles openWakeWord, relancer avec Internet : téléchargement puis
      empreintes vérifiées ; modifier un octet d'un .onnx : le mode doit refuser de démarrer.
- [ ] **35 · Repli du modèle Live** : `JARVIS_GEMINI_LIVE_MODEL=modele-inexistant` : la bannière explique,
      « Reconnecter » essaie le modèle suivant. **À valider** : la liste par défaut
      `JARVIS_GEMINI_LIVE_FALLBACKS` (deux modèles Live connus) existe-t-elle encore sur votre compte ?
- [ ] **36 · Accents** : parcourir quelques cartes (erreurs volume, notes, rappels) : accents corrects.
- [ ] **38 · Budget** : une mission longue affiche « Étape n/25 · x s sur 180 ».
- [ ] **39** : une mission dont un outil reste bloqué continue après 45 s avec une étape en échec.
- [ ] **41 · Claude** : `pip install -e '.[claude]'`, `python -m jarvis.planner --backend claude "Quel est le
      volume actuel ?"` (clé API ou `ant auth login`).
- [ ] **42 · Plan d'abord** : `JARVIS_PLAN_FIRST=1`, « lance une mission : range mes captures » : Jarvis lit le
      plan et attend le oui ou le bouton Confirmer.
- [ ] **43 · Journal** : Tableau de bord → Journal, filtrer « Échecs », effacer « Aujourd'hui ».
- [ ] **44 · Mémoire** : Mémoire → Exporter, puis Importer sur un autre compte macOS.
- [ ] **45 · Raccourcis** : Réglages → Raccourcis, choisir ⌥⇧Espace pour « Maintenir pour parler » :
      le maintien marche depuis une autre app ; choisir la même combinaison pour les deux est refusé.
- [ ] **46 · VoiceOver** : ⌘F5, parcourir la fenêtre au clavier : chaque commande est annoncée.
- [ ] **47 · Texte plus grand** : Jarvis au quotidien → Taille des textes « Très grande », rouvrir le tableau
      de bord : les cartes de chiffres et les listes sont plus grandes.
- [ ] **CI** : vérifier sur GitHub que le job Linux (pip-audit, ruff, tests, captures) puis le job macOS passent
      et regarder l'artefact « desktop-captures ».
