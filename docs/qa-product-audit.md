# QA produit — état initial du 23 octobre 2026

## Verdict actuel

Jarvis possède un socle commun : résultats structurés, confirmations, mode lecture seule, sérialisation des actions sur le bureau, missions bornées et tests automatiques. Ce socle est réel. Il ne constitue pas une qualification complète du produit : la fluidité en conditions réelles, l’exactitude sémantique de toutes les capacités et l’endurance ne sont pas encore démontrées.

**Qualification globale : non acquise.** Une CI verte atteste les contrats testés ; elle ne doit pas être présentée comme une preuve que toutes les demandes utilisateur réussissent.

Cet état initial ne clôt pas la QA de toutes les capacités. Il inventorie le périmètre, exécute quatre sondes de résilience et définit les preuves manquantes. Aucun nouvel outil produit n’est ajouté et aucun compte privé n’est utilisé.

## Pourquoi le cas WNBA a échappé aux anciens tests

Le smoke test de recherche vérifiait la récupération de résultats sur quelques requêtes fixes. Il ne démontrait pas qu’une formulation conversationnelle conduisait à une réponse pertinente et actuelle. Les fournisseurs et le modèle étaient aussi simulés dans de nombreux tests de fonctions. Des unités correctes pouvaient donc former un parcours insatisfaisant. Les nouveaux tests de parcours et les neuf contrôles réels comblent une partie de cette lacune ; ils ne couvrent pas toutes les capacités et formulations possibles.

## Inventaire systématique

`qa/capability-inventory.json` recense **140 déclarations d’outils** du code commité audité, avec origine, familles et fichiers de tests contenant une référence exacte à leur nom. Cela comprend les outils déclarés pour le vocal, le planificateur et les réglages desktop ; ce nombre n’est pas celui des seuls outils vocaux.

Une référence statique peut être une simple vérification de schéma. Elle ne prouve ni un résultat correct ni une validation réelle. Le statut de qualification réelle de chaque outil reste donc `pending`, et les métriques non mesurées restent nulles. Les modifications caméra locales non commitées sont hors de cet inventaire et doivent recevoir leur propre qualification avant intégration.

```bash
.venv/bin/python scripts/inventory_qa.py --output /tmp/jarvis-inventory.json
```

Le script lit les fichiers de `HEAD` via Git et n’exécute aucun outil. Le champ `base_commit` précise la version inventoriée. Les familles sont des dépendances détectées dans le code, pas un classement exhaustif des intentions utilisateur.

## Sondes exécutées et limites confirmées

```bash
.venv/bin/python scripts/qa_resilience_probe.py --output /tmp/jarvis-qa-resilience.json
```

Les fournisseurs sont simulés, sans réseau, micro, caméra ni action native. Les appels bloqués sont libérés dans les blocs de nettoyage. Les durées du laboratoire ne sont pas des mesures de latence réelle du produit. Le script retourne **1** lorsqu’un critère reste non satisfait ; il ne transforme pas ces limites en tests verts.

| Contrôle | Observation | Conclusion |
|---|---|---|
| QA-BUDGET | Un modèle attend au-delà d’un budget de 30 ms. Après libération à plus de 80 ms, le plan est déclaré `completed`. | Défaut démontré : le budget n’est pas revérifié avant ce succès. La borne actuelle n’est pas un délai maximal strict. |
| QA-CANCEL | Pendant l’appel de modèle bloqué, l’annulation reste en attente ; après libération, le statut est `cancelled`. | Limite de conception : annulation coopérative, pas interruption instantanée. Ne pas promettre l’arrêt immédiat d’une opération déjà partie. |
| QA-QUEUES | Une rafale de 10 000 routines et 10 000 alertes est intégralement mise en file. La file des commandes desktop en accepte seulement dix. | Admission hétérogène : les chemins routines/alertes n’ont pas la même protection contre la surcharge. |
| QA-MISSIONS | Sur 100 demandes, six sont acceptées, 94 refusées, avec au maximum deux appels de modèle simultanés. | La limite de concurrence des missions tient dans ce scénario simulé. Cela ne prouve pas encore l’endurance du produit. |

Résultat conservé dans `qa/resilience-observations.json` : **un critère satisfait, trois non satisfaits**. Ce résultat rouge est distinct de la CI de régression verte.

## Qualification à établir pour chaque famille

Chaque scénario doit préciser intention, préconditions, résultat observable attendu, critères d’échec et nettoyage. Une phrase de succès de Jarvis ne suffit jamais : l’état final est vérifié indépendamment quand c’est possible.

| Famille | Preuve de résultat et cas à pousser |
|---|---|
| Recherche, lecture web | Réponse factuelle pertinente et datée ; sources absentes, moteur bloqué, extrait partiel, contradiction, changement de page et injection d’instructions. |
| Documents | Résumé fidèle, citations ou éléments vérifiables, refus d’inventer ; PDF/DOCX, fichier vide/corrompu/volumineux, consentement et panne du modèle. |
| Calculs, conversions | Comparaison à un oracle déterministe ; bornes, précision, unité incorrecte, division par zéro et saisie mal formée. |
| Fichiers | Vérifier le disque ; ambiguïté, collision, liens symboliques, droits insuffisants, disque plein, fichier modifié entre lecture et action, annulation et redémarrage. |
| Notes, mémoire, contexte, checklists | Relire depuis un nouveau processus ; isoler les éléments, préserver le contenu, contrôler effacement, corruption, données sensibles et concurrence. |
| Applications, fenêtres | Vérifier l’application et la fenêtre ciblées ; nom ambigu, application absente, focus volé, plein écran et changement de bureau. |
| Clavier, souris, Accessibilité, interaction | Exécuter sur une application de test ; bonne cible, bon état final, permission refusée, élément disparu et changement de focus pendant l’action. |
| Navigateur | Vérifier URL, onglet et résultat ; plusieurs fenêtres, titres identiques, redirection, délai, fermeture d’onglet et page inaccessible. |
| Système, volume, luminosité, média | Comparer à une observation système ; périphérique absent/changé, erreur native, valeur limite et restauration de l’état initial. |
| Presse-papiers, reformulation | Vérifier intégrité, langue et résultat réellement copiable ; texte long, presse-papiers non textuel, erreur de modèle et absence d’écrasement en échec. |
| Agenda, disponibilités, conflits | Vérifier dates et événements sur un calendrier de test ; fuseaux, heure d’été/hiver, chevauchements, récurrence et autorisations. |
| Mail, messagerie, confirmations | Vérifier destinataire/contenu exacts avec données de test ; ambiguïté, annulation, expiration, double confirmation et panne après envoi. Aucun envoi réel sans instruction explicite. |
| Planification, rappels, minuteurs | Une seule livraison attendue ; échéance passée, réveil/sommeil, redémarrage, annulation, doublons et panne de notification. |
| Missions, dépendances, routines, procédures | Résultat utile, pas seulement plan terminé ; refus de surcharge, sérialisation du bureau, pauses, échecs partiels, budget, dépendances et annulation en cours d’appel. |
| Sessions Claude | État réel et bonne session ; confirmation, échec du CLI, dossier inaccessible, session interrompue et absence de doublon. |
| Statistiques, métriques, alertes | Comparaison aux données de référence ; historique absent/corrompu, horloge modifiée, coût du sampling et rafales d’alertes. |
| Vision, captures | Vérifier la bonne fenêtre, le contenu analysé et les limites de lecture ; permission refusée, image vide, mauvais écran et suppression des fichiers temporaires. |
| Confidentialité, historique | Vérifier les données réellement persistées et effacées ; redémarrage, rétention, informations sensibles, erreurs de stockage et archives incomplètes. |
| Vocal, voix, interface, avatars | Compréhension jusqu’au résultat ; silence, bruit, interruptions, casque/haut-parleur, reconnexion, changement de périphérique, VoiceOver, lisibilité et état affiché fidèle. |
| Caméra en cours de développement | Une capture explicite, fermeture et suppression même en échec ; permission refusée, périphérique absent, pilote bloqué et confidentialité. Non qualifiée en réel ici. |

## Ce que signifient solide, efficace, fluide et évolutif

- **Solide** : résultat exact ou échec explicite, absence d’action sur une mauvaise cible, état final vérifiable et reprise sans doublon.
- **Efficace** : temps, appels de modèles, réseau, CPU et mémoire mesurés pour un résultat utile. Aucun coût global n’est certifié par cet audit initial.
- **Fluide** : accusé de réception rapide, états honnêtes, micro et arrêt accessibles pendant les attentes, interruptions et retours d’erreur compréhensibles.
- **Évolutif pour un assistant local** : refuser proprement une surcharge, borner les ressources et maintenir la réactivité pendant plusieurs heures. Il ne s’agit pas de faire piloter le même bureau par cent tâches concurrentes.

Objectifs de qualification **proposés**, à traiter comme des critères et non des résultats acquis : commandes locales d’arrêt/coupure micro prises en compte en moins d’une seconde sous panne réseau ; latences médianes et p95 mesurées par famille ; scénarios critiques sans erreur de cible ni double effet ; session d’endurance de deux heures avec suivi mémoire, files et récupération. Les valeurs de latence des services externes doivent avoir un budget par famille plutôt qu’une promesse unique.

## Priorités

1. Traiter le budget dépassé déclaré réussi ; préciser le contrat d’annulation et l’état d’une action en vol avant toute tentative d’interruption forcée.
2. Définir la pression d’entrée, la taille maximale et le retour utilisateur pour toutes les files. Les résultats de missions essentiels ne doivent pas être jetés silencieusement.
3. Qualifier les parcours critiques par famille sur des données et applications de test, puis consigner chaque outil et scénario dans l’inventaire.
4. Mesurer latences et taux de succès sur des séries répétées, puis réaliser l’endurance. Garder les résultats réels distincts des simulations.
5. N’annoncer une capacité « qualifiée » qu’après ces preuves. La CI reste nécessaire, mais elle ne remplace pas ce bilan produit.

Aucun envoi réel, accès à des comptes privés, changement de réglage utilisateur ou test matériel n’a été effectué dans cet état initial. Les contrôles manquants ne sont pas comptés comme réussis.
