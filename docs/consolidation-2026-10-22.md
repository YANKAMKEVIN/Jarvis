# Consolidation du 22 octobre 2026

Périmètre : fonctionnement existant de Jarvis, sans nouvelle capacité. Validation sur macOS Apple Silicon, Python 3.13.15, PySide6 6.12.0 et LiveKit Agents/Google 1.8.8.

## Corrections

- Les chemins par défaut des bases de tests, des notes et de la découverte des historiques Claude sont dirigés vers un répertoire temporaire.
- Les tests d’historique de missions injectent leurs propres bases de planification, rappels et checklists. Le test CLI de livraison vide isole aussi les rappels et vérifie qu’aucune notification n’est émise.
- Le test de garde des fenêtres Spaces définit explicitement son moteur Qt. Il vérifie la garde offscreen même lorsqu’on lance les tests depuis Cocoa.

Ces changements concernent les tests ; aucun comportement produit ni capacité n’est ajouté. Les modifications caméra déjà présentes dans le dossier de travail sont testées mais restent séparées du commit de consolidation.

## Vérifications

- Suite complète des tests : **1 425 tests et 149 sous-tests réussis**, sans échec (294,30 secondes).
- Copie propre sans les modifications caméra : 46 tests ciblés réussis sur historique, confidentialité, planification et Spaces.
- Interface macOS native : 25 tests réussis (préférences, réglages vocaux transmis entre threads Qt, vues, Spaces et lanceur).
- Smoke tests réels : 51 vérifications réussies sur système, mode lecture seule, fichiers temporaires, mémoire, missions, calculs, contexte, routines, notes, rappels, planification, confidentialité, minuteurs et checklists.
- Services : 7 vérifications réussies, dont question sur un document, comparaison, extraction d’actions avec Ollama local et recherches web sur des requêtes fixes.
- Gemini Live : connexion, réglage du compagnon confirmé et réponse écrite reçue avec appareils audio simulés ; aucun micro ou haut-parleur matériel ouvert.
- Diagnostic de préparation vocale dans un thread Qt : réussi. Diagnostic natif du compagnon, bulle, Spaces et raccourci : réussi.
- Construction du wheel et installation isolée : réussies ; 16 apparences, 30 voix et ressource SVG accessibles depuis le paquet installé.
- Lanceur `.app` temporaire construit et commande `--help` exécutée. Le lanceur installé de l’utilisateur n’est pas remplacé.
- `pip check` : aucune dépendance incohérente. Compilation Python et contrôle des espaces du diff : réussis.

Les essais réels utilisent des données fictives et des bases temporaires. Aucun message n’est envoyé et aucune mission autonome n’est lancée par ces essais.

## Rejouer les contrôles

Depuis le dépôt, avec les dépendances de développement déjà installées :

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest tests/test_desktop_experience_twenty.py tests/test_desktop_spaces.py tests/test_desktop_launcher.py -q
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/diagnose_desktop_voice.py --worker
.venv/bin/python scripts/diagnose_desktop_experience.py --native
.venv/bin/python scripts/diagnose_experience_live.py --live
.venv/bin/python -m pip check
```

Le dernier diagnostic vocal utilise le quota Gemini configuré. Les diagnostics n’ouvrent pas le micro. Pour les smoke tests système, choisir explicitement les groupes de `scripts/smoke_test.py` : certains groupes non utilisés ici pilotent réellement les applications, le clavier ou le presse-papiers.

## Limites de la validation

Le micro, le rendu sonore physique, la caméra, la lecture VoiceOver et les gestes manuels de changement de bureau restent à essayer par l’utilisateur. Les contrôles de permission du processus de smoke test signalent Accessibilité et Enregistrement de l’écran non accordés : aucune capture réelle ni clic système n’est donc validé ici. Les intégrations privées Agenda et Mail ne sont pas exercées sur les comptes réels ; leurs chemins sont couverts par les tests automatisés.
