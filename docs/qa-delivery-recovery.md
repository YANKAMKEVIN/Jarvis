# QA — livraison, reprise et stockage local

Campagne du 23 octobre 2026, sur la branche `codex/qa-audit`.

## Défauts reproduits et corrections

La première exécution des douze scénarios initiaux a donné onze échecs et un
succès. Les rappels étaient consommés malgré une notification en erreur, absente
ou refusée ; deux passages observant la même échéance pouvaient la livrer deux
fois ; la création de la récurrence n’était pas atomique avec la clôture du rappel.
Des dates non finies ou booléennes étaient aussi acceptées. Le texte de la
notification était interpolé dans le programme AppleScript.

La livraison recontrôle maintenant l’état sous transaction SQLite d’écriture,
prépare les écritures de clôture/récurrence avant l’effet externe, et annule la
transaction si le notificateur échoue ou retourne `False`. Sans notificateur,
aucun rappel n’est déclaré livré. La récurrence rattrape les échéances manquées
par calcul direct. Les entrées invalides sont rejetées avant écriture.

Le notificateur macOS retourne l’acceptation du processus `osascript`. Le texte
reste un argument, sans être interprété comme programme. Un aller-retour réel
avec `osascript` a vérifié la conservation des guillemets, barres obliques et
sauts de ligne, sans afficher de notification ni lancer de commande incluse dans
le texte. L’acceptation du processus ne prouve pas que l’utilisateur a vu une
notification : permissions et réglages macOS restent à tester sur le matériel.

## Parcours exécutables

`tests/test_qa_delivery_journeys.py` contient 19 cas, sans compte privé ni envoi :

| Parcours | Observation indépendante |
|---|---|
| Notification en panne puis reprise | Réouverture de la base, état encore `pending`, puis une livraison réussie et aucun nouvel effet au passage suivant. |
| Notification absente ou refusée | Aucun identifiant livré et rappel toujours en attente. |
| Deux threads ayant lu la même échéance | Une seule notification et une seule prochaine occurrence. |
| Deux processus indépendants ayant lu la même échéance | Barrière sur disque, journal de notifications unique et relecture SQLite finale. |
| Erreur SQL avant création de la récurrence | Rappel encore en attente et aucun appel au notificateur. |
| Échec de notification récurrente | Aucune occurrence supplémentaire ; une reprise réussie crée exactement la prochaine échéance. |
| Redémarrage d’interpréteur | Texte de note et ajout conservés ; contenu et état du rappel retrouvés par un nouveau processus Python. |
| Dates et récurrences mal typées | Échec explicite, aucune ligne créée. |
| Texte contenant du code apparent | Texte absent du programme AppleScript ; retour d’échec du sous-processus observable. |

Deux mutations supplémentaires sont exécutées en CI : consommer une notification
refusée et supprimer le recontrôle `pending`. Les sept mutations ciblées sont
détectées par des assertions, sans compter les erreurs d’import comme preuves.

## Endurance courte mesurée

`qa/storage-soak-60s.json` conserve une exécution de 60,045 secondes :
**1 011 cycles réels de stockage**, avec **102 rejets de notification injectés
et récupérés**. Chaque cycle ajoute du texte à une note, contrôle le fichier,
crée un rappel, vérifie sa livraison et sa non-répétition, puis observe l’état
avec une connexion SQL distincte. Les notifications sont des callbacks simulés.

Les descripteurs restent à quatre et le nombre de threads à un. La croissance
de mémoire Python retenue après échauffement est de 55 051 octets. La médiane
d’un cycle est de 2,784 ms et le p95 de 14,584 ms, hors temporisation volontaire.
Ces valeurs concernent exclusivement ce laboratoire local, sans audio, réseau
ou modèle. Elles ne mesurent pas la latence d’une demande vocale. Les seuils
techniques de la sonde sont dix Mo de croissance Python retenue, au plus quatre
descripteurs supplémentaires et deux threads supplémentaires ; ce ne sont pas
des objectifs de performance produit.

La première version de la sonde retenait ses propres connexions d’observation
SQLite (un context manager SQLite seul ne ferme pas la connexion). Ce problème
du banc a été corrigé par fermeture explicite ; la mesure conservée provient de
la nouvelle exécution. La CI exécute cinq secondes de cette sonde et publie son
rapport ; cela constitue un smoke d’endurance, pas une qualification de deux heures.

```bash
.venv/bin/python -m pytest tests/test_qa_delivery_journeys.py -q
.venv/bin/python scripts/qa_persistence_soak.py --seconds 60 --output /tmp/jarvis-storage-qa.json
# Campagne longue de stockage uniquement, à distinguer d’une session vocale :
.venv/bin/python scripts/qa_persistence_soak.py --seconds 7200 --output /tmp/jarvis-storage-2h.json
```

## Limites ouvertes

Une notification système et une transaction SQLite ne partagent pas de commit.
Un arrêt brutal après acceptation macOS mais avant commit peut conduire à une
nouvelle notification après redémarrage. La garantie est une reprise avec risque
de répétition dans cette fenêtre, pas « exactement une fois » après tout crash.
Les tests couvrent les fautes SQL avant l’effet, les refus et la concurrence ;
ils ne suppriment pas cette limite distribuée.

L’endurance de deux heures n’a pas été exécutée. Le stockage local n’est qu’une
partie de Jarvis : micro, haut-parleurs, interruptions, changements de bureau et
périphériques, comptes de test et parcours complets avec services réels restent
à qualifier. Les modifications caméra locales restent hors de cette campagne.
