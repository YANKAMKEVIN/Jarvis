# Dix nouvelles capacités vocales

Disponibles sur `feat/desktop-ui`, dans la session vocale existante. Les phrases
ci-dessous sont des exemples d’intention : Gemini choisit les outils, et peut
redemander un titre, une date ou un identifiant si plusieurs cibles correspondent.
Aucun champ de saisie n’est nécessaire.

| Capacité | Exemple vocal | Comportement |
| --- | --- | --- |
| 1. Minuteurs multiples | « Lance un minuteur de trois minutes pour mon thé, puis un autre de dix minutes pour le four. » | Minuteurs indépendants, annonce de fin et carte de résultat. « Quels minuteurs tournent ? » donne leur temps restant à cet instant. Annulation ciblée possible. |
| 2. Recherche et lecture des notes | « Retrouve ma note sur le voyage et relis-la. » | Recherche parmi les notes Jarvis et lecture d’un extrait de la note choisie. Une ambiguïté doit être résolue avant de modifier une note. |
| 3. Ajout à une note | « Ajoute “prendre le chargeur” à ma note de voyage. » | Ajout à la fin de la note existante, sans remplacer le texte déjà présent. Une erreur de cible ne crée pas une autre note. |
| 4. Checklists persistantes | « Crée une checklist Départ, ajoute Préparer les documents, puis coche cet élément. » | Créer, retrouver, afficher, ajouter, cocher et décocher. Chaque liste et élément possède son identifiant ; les listes restent après redémarrage. |
| 5. Disponibilités d’agenda | « Cherche une plage libre d’une heure demain entre 9 h et 18 h. » | Lecture de la fenêtre demandée et proposition des plages assez longues. Aucun rendez-vous n’est créé. |
| 6. Conflits d’agenda | « Ai-je des rendez-vous qui se chevauchent demain ? » | Liste des paires d’événements qui se superposent. Ne déplace et ne supprime rien. |
| 7. Comparaison de documents | « Retrouve ces deux comptes rendus et compare-les. » | Points communs et différences proposés avec des citations présentes dans les extraits lus. Lecture seule. |
| 8. Extraction d’un document | « Extrais les actions, les décisions et les dates de ce compte rendu. » | Liste proposée avec citations vérifiées dans l’extrait. Aucun rappel, rendez-vous ou tâche n’est créé à partir de cette liste. |
| 9. Missions dépendantes | « Lance cette comparaison après la recherche en cours. » | La nouvelle mission attend la réussite de la mission désignée par son identifiant. Elle n’occupe pas le bureau ni une place d’exécution pendant cette attente. |
| 10. Pause et reprise de la file | « Mets en pause la mission de rangement qui attend. » puis « Reprends-la. » | Pause uniquement avant le début de l’exécution. Une mission déjà lancée reste active ; son annulation demeure une commande distincte. |

## Minuteurs et conservation

Les minuteurs appartiennent à la session active : quitter Jarvis ou fermer la
session les annule. Ils ne réveillent pas le Mac et ne remplacent pas les rappels
persistants. Maximum dix minuteurs actifs, durée entre une seconde et 24 heures.
La carte indique un état reçu, pas un compte à rebours animé. L’annonce vocale
nécessite une session encore connectée ; le résultat de fin est également envoyé
à l’interface.

Les notes restent dans le dossier Jarvis Notes habituel. La recherche examine les
200 notes les plus récentes et leurs extraits lisibles : aucun résultat ne prouve
pas l’absence du texte dans toutes les notes. Lecture limitée à 12 000 caractères,
fichiers de 100 Ko maximum ; ajout de 20 000 caractères maximum. Les liens
symboliques et chemins sortant du dossier des notes sont refusés. La création
utilise un nom unique et un fichier privé.

Les checklists sont stockées localement dans
`~/Library/Application Support/Jarvis/checklists.db` : 50 listes maximum et
100 éléments par liste. Le périmètre `checklists` de l’effacement des données
personnelles, ou le périmètre `all`, les supprime après la confirmation vocale
habituelle. Cocher un élément ne lance aucune action extérieure.

## Agenda : lecture native requise

Les deux analyses utilisent EventKit et nécessitent l’autorisation Calendrier du
Mac. Elles incluent les événements qui commencent avant la fenêtre mais la
traversent, ainsi que les événements de journée entière. Une lecture refusée,
une date illisible ou une réponse excessive est signalée comme une erreur ;
Jarvis n’en déduit pas que la période est libre.

La fenêtre est limitée à sept jours et 1 000 événements. Les bornes transmises
aux outils doivent porter un fuseau explicite. Un créneau proposé peut couvrir
plusieurs heures : les horaires de travail, pauses et préférences ne sont pas
inférés. Les propositions sont limitées à 20 plages et les conflits à 50 paires ;
le résultat signale la troncature. Deux événements contigus ne sont pas un conflit.
Il n’y a pas de repli AppleScript pour ces analyses, car une lecture incomplète
pourrait produire une fausse disponibilité.

## Documents : propositions appuyées par des extraits

Les formats déjà pris en charge par la lecture de fichiers restent applicables
(notamment les PDF si `pypdf` est installé). Au maximum 12 000 caractères par
document sont transmis au modèle de planification configuré ; la lecture PDF
reste bornée aux 50 premières pages. Par défaut, ce modèle doit être **local**
(Ollama sur une adresse de bouclage) : si le planificateur configuré est distant,
`ask_about_document`, `compare_documents` et `extract_document_actions` refusent
avec `remote_model_blocked` et **n’envoient rien**, afin qu’un document privé ne
quitte pas la machine. L’envoi à un modèle distant doit être autorisé
explicitement par la variable d’environnement `JARVIS_DOCUMENT_ALLOW_REMOTE`. Les
documents sont des données, sans outils d’exécution donnés au modèle d’analyse.

Chaque ligne retournée doit respecter un schéma et citer du texte réellement
présent dans l’extrait correspondant. Une réponse mal formée ou une citation
inventée est refusée. Cette vérification ne garantit pas la justesse de
l’interprétation : il faut vérifier les propositions, surtout lorsque la lecture
est tronquée. Maximum 20 éléments. L’interface présente six résumés au maximum ;
les citations sont incluses dans le résultat de l’outil disponible à l’assistant.
Les actions extraites ne deviennent pas automatiquement des missions.

## Dépendances et pause

`run_task` accepte maintenant `after_id`, l’identifiant d’une mission déjà connue.
Seul un résultat `completed` autorise la mission suivante à démarrer. Un échec,
une annulation ou un arrêt pour confirmation/clarification la laisse `blocked` :
aucune action en aval n’est exécutée. Les références futures sont refusées, ce
qui évite les cycles. Une nouvelle demande explicite permet de relancer un travail
bloqué ; il n’y a pas de reprise automatique après reconnexion.

`pause_task` et `resume_task` prennent un identifiant précis. Une pause en attente
retire la demande des ressources et libère un verrou du bureau éventuellement
obtenu pendant l’attente d’une place. La reprise conserve la dépendance et attend
à nouveau les ressources disponibles. Elle ne rejoue pas les actions terminées.
Les plafonds existants restent deux exécutions et six demandes actives. Les
missions qui pilotent le bureau restent sérialisées. Les actions extérieures
conservent le mécanisme existant de confirmation vocale.

## Mails : résumé local des non-lus

`summarize_unread_emails` lit le **corps** des mails non lus et en donne une
phrase de résumé chacun. La lecture passe par IMAP en `BODY.PEEK[]`, donc
résumer un mail **ne le marque pas comme lu** ; les pièces jointes sont ignorées
et chaque corps est borné. Comme pour les documents, le contenu reste
**on-device par défaut** : si le planificateur configuré n'est pas local, le
résumé est refusé avec `remote_model_blocked` et **rien n'est lu ni envoyé**,
sauf opt-in explicite `JARVIS_MAIL_ALLOW_REMOTE`. L'expéditeur et le sujet de
chaque ligne proviennent des en-têtes réels, jamais du modèle, donc un résumé
est toujours rattaché à un vrai message ; le texte est généré et à vérifier.
IMAP est requis (les en-têtes seuls ne suffisent pas) : sans lui, Jarvis propose
de lister les non-lus. Aucun mail n'est envoyé ni modifié.

## Historique des missions (persistant)

`task_status` ne voit que la session en cours. `recent_missions` relit un
**historique conservé localement** qui **survit à un redémarrage** : pour chaque
mission terminée, son objectif, son statut final (terminée, échec, annulée…),
l'heure et le nombre d'étapes. On ne reprend pas une coroutine interrompue — ce
qui est persisté, c'est le compte rendu, pas la mission vivante. L'historique est
stocké dans la base mémoire locale (`~/Library/Application Support/Jarvis/memory.db`,
0600), sans arguments d'étape, résultat d'outil ni contenu de message, avec une
rétention de 30 jours comme le journal d'activité. `privacy_overview` en donne le
compte ; `clear_personal_data` accepte le périmètre `missions` (et `all`) pour
l'effacer après la confirmation vocale habituelle.

## Mode sécurité (lecture seule global)

« Passe en mode sécurité », « mode lecture seule », « ne touche à rien » active
`enable_safe_mode` ; « quitte le mode sécurité » appelle `disable_safe_mode`.
Tant qu'il est actif, Jarvis peut encore lire, chercher, analyser, prendre des
notes et gérer ses propres rappels, mais **toute action qui modifie le Mac ou
envoie quelque chose vers l'extérieur** (ouvrir/fermer une app, fenêtres,
fichiers, presse-papiers, clavier/souris, mail, agenda, messages, navigation
web, confirmation d'action, effacement de données, rejeu de macro) est refusée
avec `read_only_mode` **sans aucun effet** — rien n'est fait ni envoyé.

La garde est un **point d'application unique** en politique *default-deny* : seuls
les outils d'une liste explicite de lecture/stores privés passent ; tout outil
ajouté plus tard est bloqué en mode sécurité tant qu'il n'y est pas inscrit
délibérément. Les missions partagent la même garde : une mission ne peut pas
agir vers l'extérieur en mode sécurité, et activer le mode stoppe aussi les
actions sortantes d'une mission déjà en cours. Le mode est propre à la session
et ne persiste pas après un redémarrage. L'interrupteur lui-même n'est jamais
bloqué : il y a toujours un moyen d'en sortir.

## Vérification

Les tests utilisent des horloges, agendas, documents, modèles et exécuteurs
simulés pour vérifier les effets, erreurs et conditions de concurrence sans
microphone, connexion Gemini ni modification du Mac. Les captures sont de vrais
rendus Qt alimentés par des exemples explicitement simulés.

Sur macOS, vérifier ensuite deux minuteurs et leur annulation ciblée, la relecture
d’une note modifiée, une checklist après redémarrage, un événement traversant
minuit, un refus de permission Calendrier, les extraits de deux vrais documents,
puis une mission dépendante et une mission en pause. L’audio et les autorisations
natives ne sont pas validés par l’exécution Linux.

Validation de ce lot : **134 tests ciblés passants** (capacités, notes, agenda,
concurrence et desktop). Suite complète : **902 tests et 149 sous-tests passants**,
avec les mêmes **210 échecs préexistants** que le snapshot de référence Linux
(207 liés aux frameworks macOS absents et 3 à `pypdf` absent). Aucun nouvel
identifiant de test en échec. Les derniers ajustements de stockage ont été
revérifiés par la suite ciblée ; la validation native reste à faire sur Mac.
