# Vérifier l’expérience utilisateur de Jarvis

Le nombre de tests ne suffit pas : un moteur peut renvoyer dix liens et donner une mauvaise réponse. Les nouveaux tests suivent aussi la récupération des sources, leur sélection, la synthèse et l’annonce finale. Les demandes réelles signalées deviennent des cas de régression, dont « donne des infos sur la finale des playoffs WNBA ».

## Nouveaux contrôles

| Fichier | Tests hors ligne | Ce qui est vérifié |
|---|---:|---|
| `test_search_resilience.py` | 56 | Trente formulations récentes/historiques/explicatives, reprise après panne ou résultat vide, limite des tentatives, absence de synthèse sans preuve, synthèse vide et annonce vocale réelle via le registre. |
| `test_protection_contracts.py` | 189 | Refus des outils mutateurs sur les surfaces vocal et planificateur, 72 combinaisons de consentement documentaire, concurrence des consentements et refus d’annuler un fichier différent ou modifié. |
| `test_generated_invariants.py` | 17 | Données générées pour sources, notes et préférences ; séquences de préparation, expiration, confirmation et annulation. |
| `test_voice_resilience_contracts.py` | 25 | Mode discret, casque/haut-parleur et latences, commandes disponibles pendant un outil bloqué, interruption, arrêt et absence de rejeu d’audio fermé. |
| `test_search_transport_contracts.py` | 17 | Réponses HTTP/JSON/RSS mal formées, extraits HTML imbriqués et distinction entre moteur cassé et vraie recherche vide. |
| `test_search_and_trigger_boundaries.py` | 24 | Configuration corrompue, heures limites, limite de déclencheurs, lecture web bornée et erreurs de secours. |
| **Total ajouté hors ligne** | **328** | Les sous-tests et exemples générés ne sont pas comptés comme des tests supplémentaires. |

`test_live_answer_quality.py` ajoute **9 contrôles réels**, activés séparément : six synthèses par Ollama, puis trois recherches jusqu’à la réponse finale, dont la WNBA. Ils vérifient des faits attendus et des sources pertinentes, pas uniquement un statut de succès. Les données fictives ne servent pas à prétendre connaître de vrais résultats sportifs ; le cas sportif à source unique vérifie le format des finales depuis une source officielle datée du corpus.

Hypothesis explore cent exemples de listes de sources, cinquante couples de notes, cent configurations JSON et quarante séquences de confirmation pouvant comporter trente-cinq étapes. Ces exemples complètent les assertions des tests, sans gonfler artificiellement le nombre affiché par pytest.

## Défauts révélés et corrigés

- Des demandes sportives récentes étaient routées en recherche générale. Les demandes historiques ou explicatives restent générales.
- Après une panne ou un résultat inexploitable, aucune seconde stratégie n’était essayée. La reprise utilise désormais au maximum trois requêtes distinctes : demande originale, formulation simplifiée et autre catégorie. Elle s’arrête dès qu’elle récupère des sources exploitables.
- Une panne DuckDuckGo, une page de blocage ou un flux RSS incorrect pouvait être confondu avec l’absence d’informations. Les erreurs de fournisseur et les vrais résultats vides sont distingués ; le message n’affirme plus avoir évalué la fiabilité de sources inexistantes.
- Une synthèse vide pouvait être annoncée comme terminée. Son échec est désormais explicite, sans perdre les références récupérées.
- Une balise HTML imbriquée pouvait couper la fin d’un extrait, notamment le score. Les extraits restent complets.
- Une URL mal formée ou un type JSON incorrect dans un déclencheur pouvait faire échouer le parcours. Ces entrées sont ignorées proprement.
- Les détails d’une exception inattendue du service de recherche ne sont plus recopiés dans la réponse utilisateur.

Le prompt de synthèse précise aussi qu’un fait explicite peut être rapporté depuis une seule source et qu’un détail manquant ne justifie pas de rejeter tous les faits établis.

## Vérifier que les tests détectent les régressions

```bash
.venv/bin/python scripts/check_regression_sensitivity.py --json /tmp/jarvis-mutations.json
```

Ce script vérifie d’abord que les tests sélectionnés passent, puis introduit cinq régressions dans une copie temporaire : suppression des reprises de recherche, consentement ignoré, son réactivé en mode discret, confirmations expirées acceptées et mode lecture seule contourné. Les cinq doivent être détectées par des assertions. Une erreur d’import ou de collecte n’est pas considérée comme une détection. Le dépôt n’est jamais modifié. Il s’agit d’un contrôle ciblé, pas d’un score de mutation global.

## Exécution et CI

```bash
.venv/bin/python -m pip install -e '.[desktop,live,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -m 'not live' -q
JARVIS_RUN_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live_answer_quality.py -q
```

Les tests réels nécessitent le modèle Ollama configuré et Internet. Après activation explicite, une indisponibilité compte comme un échec : elle n’est pas transformée silencieusement en test ignoré. Aucun micro ni caméra ne s’ouvre. Aucun compte privé, message personnel ou document utilisateur n’est utilisé.

La CI macOS lance les tests hors ligne avec couverture des branches, applique un seuil de **90 % sur le service de recherche, ses fournisseurs sans clé et son adaptateur vocal**, puis vérifie les cinq régressions injectées. Elle conserve les rapports pytest, couverture et mutations. Les essais réels sont séparés de la CI pour distinguer une panne externe d’une régression déterministe.

Les mesures ciblées après ajout des tests donnent **94 %** sur ces trois modules de recherche. Ce pourcentage ne concerne pas tout Jarvis. Les résultats de l’exécution complète figurent dans le bilan ci-dessous.

## Bilan du 22 octobre 2026

- Neuf contrôles de qualité réels réussis, dont la recherche WNBA jusqu’à sa synthèse.
- Cinq régressions injectées sur cinq détectées après une exécution de référence réussie.
- Copie propre sans modifications caméra en cours : 511 tests ciblés et huit sous-tests réussis.
- Suite complète finale dans le dossier de travail : **1 753 tests hors ligne et 149 sous-tests réussis**, neuf contrôles réels exclus de cette commande puis exécutés séparément avec succès. Durée : 186,74 secondes. Les neuf tests caméra déjà présents localement restent hors du commit.

Les tests augmentent la capacité à détecter un défaut, sans garantir l’absence de bugs ni l’exactitude permanente d’une source distante. Les essais physiques du micro, du son, de VoiceOver et des permissions macOS restent complémentaires.
