# Phase 3 — Boucle de planification

> Statut : **3a fait** (moteur + adaptateur Ollama local, testés). 3b et 3c à
> venir. Contrainte retenue : **aucune dépense** — le cerveau est un modèle
> local Ollama, gratuit et privé ; le moteur reste indépendant du modèle.

## Le problème

Aujourd'hui, Gemini Live enchaîne les tools un par un, en temps réel. Ça marche
pour « ouvre Safari » ou « monte le son », mais pas pour une vraie tâche :

> « Prépare ma réunion de demain : retrouve le dernier mail de Paul, ouvre le
> document lié et résume-le-moi. »

Une telle demande exige de **découper**, **exécuter**, **vérifier** chaque
étape, **corriger** en cas d'échec, puis **rendre compte**. Un modèle vocal
temps réel n'est pas fait pour raisonner longtemps : il doit répondre vite.

## L'idée : une voix et un cerveau

```
 Toi ──voix──▶ Gemini Live (la voix, rapide)
                  │  demande simple → tools directs (comme aujourd'hui)
                  │  tâche complexe → run_task(objectif)
                  ▼
            Planificateur (le cerveau, raisonne)
                  │  planifier → exécuter → vérifier → corriger
                  ▼
            Les mêmes 67 tools (mêmes verrous, journal, confirmations)
                  │
                  ▼
               Ton Mac
```

- **Gemini Live garde la conversation** et les actions simples. Rien ne change
  pour « monte le son ».
- **Un nouveau tool `run_task(objectif)`** confie une tâche en plusieurs étapes
  au planificateur.
- **Le planificateur** est un modèle de raisonnement qui pilote **exactement
  les mêmes tools** (pas de copie : mêmes vérifications `state_confirmed`,
  même journal, même mémoire appliquée localement).

## La boucle

1. **Comprendre** l'objectif et consulter la mémoire si besoin (`recall`).
2. **Planifier** quelques étapes.
3. **Exécuter** une étape via un tool.
4. **Vérifier** : `ok`, `state_confirmed`, et si besoin relire l'état
   (`get_active_window`, `browse_get_active_tab`…). Un `state_confirmed=false`
   n'est jamais pris pour un succès.
5. **Corriger** : autre approche sûre si une étape échoue (focaliser le champ
   avant de taper, activer la fenêtre…), sinon s'arrêter et expliquer.
6. **Rendre compte** : un résumé court que Gemini te dit à voix haute.

## Sécurité : ce qui ne change pas

- **Le planificateur ne peut jamais envoyer un message seul.** Il n'a pas accès
  à `confirm_action` / `cancel_action`. S'il prépare un envoi
  (`prepare_send_message`), la tâche se **met en pause** et rend la main à
  Gemini, qui t'annonce destinataire et contenu et attend ton oui. Même chose
  pour un souvenir déduit (`propose_memory`).
- **Tools exclus du planificateur** : `confirm_action`, `cancel_action`,
  `lock_screen`, et les clics souris à coordonnées (`move_mouse`, `click`…),
  trop risqués à l'aveugle.
- **Garde-fous de budget** : 25 étapes max, 3 minutes max, arrêt après 3 échecs
  consécutifs. Au-delà, il s'arrête et dit où il en est.
- **Une tâche à la fois**, et tu peux dire « stop » à tout moment
  (`cancel_task`).
- **Journal** : chaque tâche apparaît dans `recent_activity` (objectif
  résumé, étapes, résultat), toujours sans contenu sensible.

## Tâche en arrière-plan

Un planificateur met plusieurs secondes par étape ; une tâche peut prendre une
minute. Bloquer la voix pendant ce temps serait pénible (et les appels de tools
du modèle temps réel ont des délais limites). Donc :

- `run_task` **répond tout de suite** (« je m'en occupe ») et la tâche tourne
  en arrière-plan.
- Gemini peut te donner l'avancement (`task_status`) et t'annonce la fin.
- Pendant ce temps tu peux continuer à parler à Jarvis pour autre chose.

## Choix techniques

- **Boucle écrite à la main** plutôt que le « Tool Runner » du SDK : on doit
  pouvoir mettre en pause sur une confirmation, appliquer les budgets, annuler
  à la demande et journaliser chaque étape. Une boucle explicite reste simple et
  entièrement testable.
- **Réutilisation des tools existants** : les schémas des 67 tools sont déjà
  décrits pour Gemini ; on les convertit automatiquement pour le planificateur.
  Aucune duplication.
- **Coût maîtrisé** : la liste des tools et les consignes sont identiques à
  chaque appel, donc mises en cache côté API (environ 10 fois moins cher sur
  cette partie). Seules les étapes nouvelles sont facturées plein tarif.
- **Tests** :
  - unitaires avec un « faux modèle » scénarisé (plan, échec, correction,
    pause sur confirmation, budget dépassé, annulation) : déterministes et
    gratuits ;
  - smoke test d'une poignée de **vraies tâches** sur le Mac (ex. « ouvre
    example.com dans Safari et copie le titre de la page dans TextEdit »),
    avec mesure du taux de réussite.

## Découpage proposé

1. **3a — Le moteur** : boucle, budgets, pause sur confirmation, annulation,
   tests avec faux modèle. Pas encore branché à la voix.
2. **3b — Branchement** : `run_task`, `task_status`, `cancel_task` dans Gemini
   Live, tâche en arrière-plan, annonce de fin.
3. **3c — Vraies tâches** : groupe `tasks` dans le smoke test, réglage des
   consignes selon les échecs observés.
4. **Plus tard — Apprentissage** : une tâche réussie devient une procédure
   réutilisable en mémoire (« refais comme la dernière fois »).

## État de la phase 3a

- `src/jarvis/planner/engine.py` : la boucle, les budgets (25 étapes,
  3 minutes, 3 échecs consécutifs), la pause sur action sortante,
  l'annulation, et une liste fermée de 37 tools.
- `src/jarvis/planner/models.py` : l'interface modèle, un faux modèle
  scénarisé pour les tests, et l'adaptateur Ollama local.
- Essai manuel : `PYTHONPATH=src .venv/bin/python -m jarvis.planner "objectif"`.

### Mesures sur le Mac actuel (M3, 8 Go, `granite4:3b`)

- Premier tour ≈ 35 s (chargement du modèle + ~4 200 tokens de consignes et
  de tools), une tâche simple ≈ 1 min. Contexte réglé à 8 192 tokens : à
  16 384, le Mac swappait au point de dépasser 2 minutes.
- Le modèle choisit correctement le tool sur des tâches courtes et rapporte
  honnêtement un échec au lieu d'inventer.
- **Limite principale : la mémoire.** Modèle chargé, le Mac swappe fortement
  et les autres commandes ralentissent (un `osascript` est passé de 0,1 s à
  11 s et a dépassé le délai de Jarvis). Un modèle local de 3 milliards de
  paramètres convient aux tâches de 2 ou 3 étapes, pas au-delà.

## Décisions qui te reviennent

**1. Quel modèle pour le cerveau ?** *(tranché pour l'instant : local et
gratuit, Ollama ; à revoir si besoin de plus de puissance)*

| Option | Pour | Contre |
|---|---|---|
| **Claude Opus 5.5** (`claude-opus-5-5`) — recommandé | Le plus fiable pour les longues chaînes d'outils et l'auto-correction | Nouvelle clé API Anthropic ; ~4 $ / 20 $ par million de tokens (entrée / sortie), cache inclus beaucoup moins |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Plus rapide, deux fois moins cher | Un peu moins solide sur les tâches longues |
| Gemini Pro | Clé Google déjà en place, un seul fournisseur | À évaluer sur la fiabilité de la boucle |

Je peux rendre le modèle configurable (variable d'environnement) et mesurer
les deux sur les mêmes vraies tâches avant de trancher.

**2. Confidentialité.** Comme Gemini aujourd'hui, le planificateur est un
service cloud : il voit l'objectif et les **résultats des tools** de la tâche
(noms d'apps, titres de pages, texte copié si la tâche en copie). La mémoire
n'est toujours pas envoyée d'avance ; seuls les `recall` faits pendant la tâche
remontent. Ça te va ?

**3. Niveau d'autonomie par défaut.** Le planificateur agit seul sur les
actions réversibles et met en pause uniquement sur les actions sortantes
(messages) — c'est ma proposition. Tu préfères qu'il annonce son plan et
attende ton feu vert avant de commencer ?
