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


## Corrections et campagne de suivi

L’état initial ci-dessus est conservé comme preuve des défauts reproduits. Le
rapport `qa/resilience-after-fixes.json` consigne les quatre sondes après correction.

- Le budget est revérifié après l’inférence, avant tout succès ou action.
- L’attente d’inférence devient annulable, avec un maximum global de deux appels
  physiques. Un fournisseur bloqué conserve sa place jusqu’à son retour ; ses
  résultats tardifs sont ignorés. Les requêtes sont copiées avant transmission.
  Les threads sont isolés de l’exécuteur asyncio et ne retiennent pas sa fermeture.
  Cela ne termine pas une requête HTTP déjà partie : la capacité peut rester
  indisponible jusqu’au timeout du fournisseur. Aucune action native n’est
  abandonnée par ce mécanisme : ses verrous restent nécessaires jusqu’à sa fin.
- Admission atomique : dix commandes desktop, dix routines, 32 alertes et
  32 demandes d’annulation maximum en attente. Une session arrêtée refuse les
  nouvelles demandes. Les refus de routine et d’annulation sont affichés ; une
  alerte refusée retourne `False` pour laisser son appelant utiliser son autre
  canal de notification.
- Les annonces essentielles de missions attendent une place au-delà de dix,
  sans expiration ni suppression. La fermeture interrompt cette attente ; les
  résultats restent dans l’historique des missions.
- La fermeture coupe les périphériques audio avant le nettoyage potentiellement
  lent des commandes desktop et de l’enregistreur. Un test bloque explicitement
  ce nettoyage pour vérifier que le micro est déjà fermé.

La CI exécute désormais les sondes et produit `qa-families.json` à partir du
JUnit réellement exécuté, avec chaque cas et son résultat. `scripts/report_qa.py`
regroupe ces assertions par famille et conserve un groupe transversal pour les
cas sans correspondance. Ce classement n’attribue aucune qualification native
ou sémantique automatique. Les temps pytest ne sont pas des latences utilisateur.
Les modifications caméra en cours restent distinguées dans leur propre famille.

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -m 'not live' --junitxml=/tmp/jarvis-qa-tests.xml
.venv/bin/python scripts/report_qa.py --junit /tmp/jarvis-qa-tests.xml --output /tmp/jarvis-qa-families.json
.venv/bin/python scripts/qa_resilience_probe.py --output /tmp/jarvis-qa-resilience.json
```

Les validations micro/haut-parleurs, comptes de test privés, courses de focus et
endurance de deux heures restent requises avant de qualifier globalement le
produit. Une campagne automatisée hors ligne ne les remplace pas.


La campagne a aussi révélé une faiblesse d’isolation des tests Qt : des fenêtres
masquées survivaient entre les scénarios, et les changements de thème
réappliquaient le style à ces anciennes fenêtres. Le nettoyage automatique
supprime les fenêtres créées par chaque test et traite les suppressions Qt
différées après les autres fixtures. Cette correction concerne le banc de
régression ; elle ne constitue pas une mesure de performance de l’application.
Le traitement des annulations est limité à 32 par passage de boucle pour qu’un
producteur continu ne puisse pas empêcher la prise en compte de la coupure micro.


### Résultats du suivi local

`qa/campaign-summary.json` conserve le bilan par famille : **1 762 tests,
149 sous-tests**, aucun échec ; neuf tests de services réels exécutés séparément
et réussis ; 51 smoke tests locaux et sept smoke tests de services réussis ;
les cinq mutations volontaires détectées. Les quatre sondes de résilience sont
vertes après correction. Le résumé local comprend neuf tests caméra non
commités ; le commit et sa CI les excluent. Les cas JUnit peuvent inclure des
sous-tests séparés : leurs sommes ne représentent pas le nombre d’items pytest.

La suite entière a terminé en 61,13 secondes après le premier nettoyage Qt.
Le nettoyage complémentaire ferme aussi le gestionnaire d’expérience créé par
le test afin de retirer ses filtres d’événements avant suppression des fenêtres.
Les scénarios Qt sont revérifiés avec ce complément. Cette durée reste celle du
banc de tests, pas une promesse de réactivité en utilisation réelle.


## Suite : livraison et reprise

La campagne suivante et ses limites sont détaillées dans [QA livraison et reprise](qa-delivery-recovery.md). Elle ajoute des parcours avec SQLite réel, processus indépendants, notifications simulées et mesure courte de stockage. Elle ne clôt pas les validations matérielles ni l’endurance de deux heures.


## Suite : intégrité des notes

[QA intégrité des notes](qa-note-integrity.md) décrit les fautes d’encodage et d’écriture reproduites, les huit nouveaux cas et les limites de restauration et de concurrence avec des éditeurs externes.


## Suite autonome : planification, documents et effacement

[QA autonome](qa-autonomous-campaign.md) consigne les nouveaux parcours sans intervention, les évaluations documentaires réelles, les défauts reproduits et les limites. L’endurance de deux heures est différée à la fin à la demande de l’utilisateur.
