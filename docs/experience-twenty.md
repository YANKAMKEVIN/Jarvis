# Jarvis au quotidien : vingt améliorations

Première version fonctionnelle. Ouvrir le menu du compagnon → **Jarvis au quotidien…**, ou **⌘K** lorsque l’une des fenêtres Jarvis est active. Démarrer explicitement le vocal avant de lancer les actions qui utilisent le service. La palette ne démarre jamais le micro à votre place.

| # | Amélioration | Utilisation |
|---|---|---|
| 1 | Briefing personnalisé | Choisir ses sujets dans les préférences puis lancer le briefing depuis la palette. Le briefing utilise une mission en lecture seule. |
| 2 | Compréhension de l’écran | « Comprendre mon écran » : vérifier l’application proposée, poser une question puis autoriser cette analyse explicite. |
| 3 | Mémoire contrôlable | Ouvrir Mémoire pour ajouter, modifier ou supprimer un souvenir ou un élément de contexte local. |
| 4 | Déclencheurs | Associer une routine existante à une heure quotidienne ou au lancement d’une application. |
| 5 | Apprentissage | Après une réussite, « Retenir la dernière réussite… » permet de nommer une procédure. Son lancement reste explicite. |
| 6 | Demande reçue | Indication de réception à la fin de la parole et libellé de l’action comprise. |
| 7 | Attentes visibles | Une attente prolongée affiche un état ; les erreurs et commandes de reprise restent accessibles. |
| 8 | Interruption | Activer le mode casque pour interrompre oralement Jarvis. Avec les haut-parleurs, utiliser Interrompre. |
| 9 | Mode discret | La réponse audio devient silencieuse ; les cinq dernières réponses écrites restent accessibles dans le panneau, uniquement en mémoire. |
| 10 | Personnalité | Régler ton, longueur des réponses et niveau d’initiative sans changer de session. |
| 11 | Premier lancement guidé | Guide clé API, permissions, périphériques, voix et essai. La clé est enregistrée dans le fichier privé de configuration desktop. |
| 12 | Palette | ⌘K : rechercher une action, valider avec Entrée, fermer avec Échap. |
| 13 | Historique utile | Chercher missions et procédures, relancer un objectif, exporter un bilan ou révéler un fichier produit. L’archive des résultats est facultative. |
| 14 | Annulation | Annuler un déplacement/renommage de fichier vérifié ou un rappel local encore en attente, après confirmation. |
| 15 | Documents déposés | Déposer un ou deux documents puis choisir résumé, actions ou comparaison ; consentement séparé pour l’analyse distante. |
| 16 | Humanoïdes articulés | Option de dessin 2D articulé pour Nova Bot, Neo Guide, Digital Avatar, Synth Companion et Holo Face. |
| 17 | Réactions au curseur | Regard discret vers le pointeur ; cliquer sans déplacer le compagnon déclenche un salut. |
| 18 | Expressions | Attente, réflexion, réussite et danse influencent la pose du compagnon. |
| 19 | Thèmes | Nuit, aube et contraste élevé depuis les préférences. |
| 20 | Accessibilité | Taille de texte, réduction des mouvements, noms accessibles, navigation clavier et annonces d’état. |

## Limites et confidentialité

Les déclencheurs nécessitent Jarvis ouvert. Ils ne démarrent pas le micro. Une routine attend une session disponible pendant dix minutes au maximum ; un déclencheur quotidien ne se rejoue pas automatiquement après un arrêt. Les outils conservent leurs confirmations et leurs limites habituelles.

Le contexte d’application contient seulement le dernier nom d’application en mémoire. L’analyse d’écran est explicite et envoie l’image de la fenêtre désignée au service configuré. Déposer un document n’envoie pas son contenu : l’envoi éventuel dépend de l’action et de son consentement.

L’historique facultatif conserve des résultats d’outils locaux pendant trente jours, au maximum mille entrées. Il ne conserve aucune conversation ni audio. Les réponses du mode discret restent en mémoire. La suppression des résultats archivés est disponible lorsque la session vocale est arrêtée.

L’annulation refuse un fichier modifié ou un emplacement déjà occupé. Elle ne couvre pas les dossiers, les courriels envoyés ou toutes les actions système. Les rappels doivent être locaux, inchangés et suffisamment éloignés de leur échéance.

Les humanoïdes articulés sont une option de dessin 2D ; les illustrations d’origine restent disponibles. Les apparences abstraites et Kitsune gardent leur animation existante. Réduire les mouvements désactive danse, suivi et salut animés.

Les tests automatisés couvrent préférences, consentement, mémoire, déclencheurs, annulation, commandes, archive et rendu Qt. Le confort au micro, la lecture VoiceOver réelle et les routines propres à chaque utilisateur nécessitent également un essai sur son Mac.
