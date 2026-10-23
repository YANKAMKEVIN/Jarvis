# QA autonome — planification, documents et confidentialité

Campagne du 23 octobre 2026. L’endurance de deux heures est **différée à la fin,
à la demande de l’utilisateur**. Aucun envoi réel, accès à un compte privé,
effacement de données utilisateur ou ouverture de micro n’est effectué ici.

## Périmètre et preuves

47 nouveaux cas hors ligne utilisent de vrais fichiers, bases SQLite et
processus, avec des interfaces de messagerie simulées. Quatre évaluations
supplémentaires utilisent le modèle Ollama réel, exclusivement sur des faits et
documents fictifs. Les tests de services activés échouent si le service manque :
une indisponibilité ne devient pas un succès ou un skip silencieux.

### Messages planifiés

La première série a reproduit quatorze échecs sur dix-sept cas : envoi non
confirmé déclaré réussi, exception d’envoi non maîtrisée, concurrence pouvant
répéter l’action, annulation devenue inefficace après sélection, dates invalides
et observation macOS absente traitée comme écran déverrouillé.

Les corrections :

- Une revendication durable `sending` précède les actions. Un verrou de fichier
  par base sérialise les destinataires entre workers, y compris entre deux
  processus réels. L’annulation avant revendication empêche l’envoi.
- Écran inconnu/verrouillé : aucun envoi. L’état est recontrôlé après navigation.
  Le format natif d’une observation valide a été vérifié en lecture seule.
- Seul `state_confirmed=True` permet d’annoncer le succès. Une exception après
  début d’envoi ou un résultat incertain n’entraîne aucune relance automatique.
- Le succès et la prochaine récurrence sont enregistrés atomiquement. Une panne
  SQL après l’effet laisse la revendication visible et empêche une répétition.
- Les éléments à vérifier apparaissent dans la liste vocale et le CLI, avec
  instruction de vérifier la conversation avant toute nouvelle tentative.
- Les échecs connus avant commande d’envoi restent réessayables dans le délai
  existant. Un échec de notification après un envoi confirmé ne le répète pas.

Les essais ne démontrent pas une livraison réelle à un destinataire ni une
maîtrise de toutes les courses de focus avec un humain. Une revendication
persistant après arrêt brutal demande une vérification manuelle, même si aucun
message n’était finalement parti : le choix privilégie l’absence de renvoi
incertain. Le test de revendication interrompue reproduit l’état durable ; il ne
constitue pas une coupure électrique. Le verrou sérialise les workers de cette
base, pas toutes les applications extérieures.

### Documents

Une limite de cinquante pages PDF pouvait masquer des pages absentes tout en
renvoyant `truncated=False`. Le lecteur signale désormais cette lecture partielle
et cesse d’extraire d’autres pages lorsque le budget de texte est dépassé.
Une vraie génération PDF de cinquante et une pages vérifie la propagation du
statut dans l’analyse ; des lecteurs instrumentés vérifient la borne d’extraction.
La mémoire nécessaire à l’extraction d’une unique page hostile reste hors de
cette preuve : la bibliothèque PDF doit encore analyser cette page.

Les quatre cas Ollama réels passent : budget/date dans un TXT, date dans un
DOCX, responsable absent et consigne parasite contradictoire dans le document.
Ce corpus ne prouve pas la fidélité de tout résumé ou la résistance à toute
injection. Les preuves/citations et le résultat observable restent nécessaires.

### Confidentialité et effacement

Des contrôles sur les octets ont révélé que `DELETE` seul laissait le texte dans
le fichier SQLite. Le parcours d’effacement des rappels/messages en attente
annulait seulement les lignes, et la limite de liste de cinquante laissait des
éléments oubliés.

Les connexions concernées activent `secure_delete`. Après un effacement explicite,
le journal WAL est checkpointé et tronqué. Si un lecteur retient les anciennes
pages, le nettoyage signale un échec plutôt que d’annoncer une purge complète.
Si l’activation de cette politique échoue, la connexion est fermée avant une
écriture sensible.

Les tests observent les fichiers et la relecture SQL : archives en modes DELETE
et WAL, contexte, checklists, historique des missions et oubli d’un souvenir
avec contrôle de l’index de recherche et conservation des vingt-neuf autres.
La confirmation de purge supprime les soixante-cinq rappels/messages de test en
attente, au-delà de l’ancienne limite, sans exposer de contenu résiduel dans la
base testée. Les lignes historiques hors du scope demandé restent distinctes :
il ne s’agit pas d’une suppression indistincte de toutes les données de Jarvis.

Un secret identifiable dans un dossier parent était aussi archivé lorsque le
nom final du fichier paraissait normal. Les marqueurs de secret et préfixes de
clé sont désormais vérifiés dans les parents. La détection heuristique de forte
entropie reste limitée au nom final pour éviter de bloquer tout long nom de
répertoire ordinaire. Ce filtrage ne constitue pas un détecteur universel de
secrets et n’altère pas les filtres par défaut de la mémoire.

L’effacement vérifié concerne les fichiers SQLite/WAL actifs. Aucune garantie
n’est donnée sur les sauvegardes, snapshots, copies externes, mémoire vive ou
récupération physique sur SSD. Les tests se limitent à leurs bases temporaires.

## Régression et CI

Les mutations ciblées passent de neuf à quatorze : acceptation d’un envoi non
confirmé, revendication d’un message annulé, désactivation de l’effacement SQLite,
troncature PDF masquée et secret de dossier conservé sont toutes détectées par
des assertions. Le seuil combiné de couverture planification/effacement est fixé
à 90 %, en complément des seuils recherche et rappels.

La suite complète et les nouveaux cas sont vérifiés localement ; la CI contrôle
le commit propre, sans le travail caméra local. Les modifications caméra sont
préservées. Les deux corrections de purge et l’affichage des envois à vérifier
dans le registre sont indexés séparément de ce travail non commité.

```bash
.venv/bin/python -m pytest tests/test_qa_scheduled_safety.py tests/test_qa_document_privacy.py tests/test_qa_privacy_erasure.py -q
JARVIS_RUN_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live_document_quality.py -q
.venv/bin/python scripts/check_regression_sensitivity.py --json /tmp/jarvis-qa-mutations.json
```

Les validations matérielles, comptes de test, grande diversité de formulations
et latences de conversation restent ouvertes. La session d’endurance de deux
heures n’est pas lancée dans cette campagne.
