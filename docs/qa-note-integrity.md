# QA — intégrité des notes

Campagne du 23 octobre 2026. Les scénarios utilisent exclusivement des fichiers
temporaires et les vraies opérations du système de fichiers ; aucune note de
l’utilisateur n’est lue ou modifiée.

## Observations et corrections

La première série de cinq cas a reproduit quatre échecs : texte ou titre Unicode
non encodable provoquant une exception, et fichier partiel conservé après une
écriture échouée. Les valeurs Unicode invalides sont désormais refusées avant
la création ou la modification d’un fichier. Un échec de sauvegarde supprime le
fichier qu’elle venait de créer, sans supprimer une note préexistante en cas de
collision `O_EXCL`.

Les ajouts utilisent des écritures non tamponnées, complètent les écritures
courtes et tronquent l’ajout partiel en cas d’erreur. Un verrou de fichier
sérialise les instances Jarvis coopérantes ; la limite de taille est recontrôlée
sur le descripteur verrouillé. Une erreur n’est jamais annoncée comme succès.

Les huit cas de `tests/test_qa_note_failures.py` vérifient :

- refus de texte invalide à la sauvegarde et à l’ajout, sans modifier le disque ;
- refus d’un titre invalide sans fichier créé ;
- suppression d’un fichier réellement partiellement écrit avant erreur de disque ;
- collision réelle de nom, sans altération ni suppression de la note originale ;
- retour au contenu initial après écriture partielle d’un ajout puis erreur ;
- achèvement des écritures courtes ;
- conservation exacte des 100 ajouts réalisés par huit threads utilisant des instances distinctes.

Les deux mutations supplémentaires retirent le nettoyage d’une sauvegarde et le
rollback d’un ajout. Les assertions détectent ces régressions. Le contrôle CI
comporte désormais neuf mutations ciblées ; il ne prétend pas mesurer le taux
de mutation de tout le projet.

Une nouvelle exécution de la sonde de stockage après ces changements est
conservée dans `qa/storage-soak-notes-60s.json`. Son périmètre reste le stockage
local, avec notification simulée et données temporaires. La durée, les cycles,
les ressources et les latences observées figurent dans ce rapport ; aucune
latence de conversation ni endurance vocale de deux heures n’est déduite de ces
mesures.

## Limites

Le verrou de fichier est consultatif : un éditeur extérieur à Jarvis peut
modifier une note sans le respecter. Un arrêt brutal ou une panne matérielle
pendant l’écriture n’est pas couvert par le rollback d’une exception Python.
Aucune garantie de persistance après coupure électrique n’est annoncée. Si le
système refuse aussi le nettoyage ou la troncature, l’opération reste en échec
et le fichier doit être vérifié ; les tests actuels ne démontrent pas sa
restauration dans ce cas.
