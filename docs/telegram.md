# Telegram dans Jarvis

Telegram est la deuxième messagerie de Jarvis, à côté de WhatsApp. Les outils vocaux sont les mêmes : `prepare_send_message` puis `confirm_action`, `schedule_message`, `send_last_web_result`, avec `app_name="Telegram"`.

## Pourquoi l'API et pas l'écran

L'app installée est le client natif macOS (`ru.keepcoder.Telegram`, 12.6). Elle n'expose pas le contenu de sa fenêtre à l'accessibilité : `AXChildren` échoue sur la fenêtre, on ne voit que les boutons fermer, réduire et plein écran, et le titre de fenêtre (« Telegram @ Kevin ») désigne le compte, pas la conversation. Jarvis ne pourrait donc jamais lire l'en-tête de conversation, ni vérifier le destinataire comme il le fait sur WhatsApp.

Les URL schemes (`tg://resolve?domain=…`) ouvrent une conversation, mais ne confirment rien : avec un nom d'utilisateur inconnu, l'app reste sur la conversation précédente.

Jarvis passe donc par l'API du compte (MTProto, bibliothèque Telethon), intégrée directement dans Jarvis. Il n'y a pas de serveur MCP tiers, donc la session ne quitte pas le code de Jarvis.

## Garde-fous

- Le destinataire est cherché parmi **tes conversations récentes** (300 dernières), jamais dans la recherche globale de Telegram.
- Il doit correspondre à **une seule** conversation, de l'une de ces façons :
  - le nom complet ;
  - ses premiers mots (« Joel » pour « Joel Chinda ») ;
  - un `@nom_utilisateur`.

  Zéro ou plusieurs correspondances : refus (`recipient_not_verified`, raison `recipient_not_found` ou `recipient_ambiguous`). Aucune correspondance approximative.
- Les **canaux de diffusion** sont exclus : y poster serait public. Les groupes sont acceptés, comme sur WhatsApp.
- « Messages enregistrés », « Saved Messages » ou « moi » désignent ta conversation avec toi-même.
- `recipient` est **obligatoire** pour Telegram, car il n'y a pas de « conversation ouverte » à viser.
- Même jeton de confirmation que WhatsApp. Au moment du `confirm_action`, le destinataire est **résolu à nouveau** ; s'il est devenu ambigu, rien ne part.
- L'envoi n'est confirmé (`state_confirmed`) que si Telegram renvoie l'identifiant du nouveau message. En cas d'erreur après l'envoi de la requête : « envoi incertain », sans nouvel essai automatique.
- Telegram n'est jamais envoyé vers la saisie au clavier « à l'aveugle », même avec un `query` explicite.
- Le mode sécurité bloque Telegram comme tout envoi.
- Les messages planifiés Telegram partent **même écran verrouillé**, car ils ne touchent pas à l'interface. WhatsApp attend toujours un écran déverrouillé.
- Alias mémoire par app : `remember(person, "ma mère sur Telegram", "Maman Yankam")` l'emporte sur l'alias générique « ma mère » quand l'envoi se fait sur Telegram.

## Mise en place (à faire par toi, une fois)

1. Crée une application sur https://my.telegram.org pour obtenir un `api_id` et un `api_hash`.
2. Range-les dans le Trousseau (ou dans `JARVIS_TELEGRAM_API_ID` / `JARVIS_TELEGRAM_API_HASH`) :

   ```bash
   security add-generic-password -s jarvis-telegram -a api_id -w
   ```

   ```bash
   security add-generic-password -s jarvis-telegram -a api_hash -w
   ```

3. Installe la dépendance : `~/dev/Jarvis/.venv/bin/pip install -e '.[telegram]'`
4. Connecte-toi (numéro, code reçu dans Telegram, mot de passe 2FA éventuel) :

   ```bash
   PYTHONPATH=src ~/dev/Jarvis/.venv/bin/python -m jarvis.tools.telegram_api login
   ```

   La session est écrite dans `~/Library/Application Support/Jarvis/telegram/jarvis.session` (dossier 0700, fichier 0600). **Elle donne un accès complet à ton compte Telegram.** Pour révoquer : Telegram > Réglages > Appareils.

5. Vérifie : `PYTHONPATH=src ~/dev/Jarvis/.venv/bin/python -m jarvis.tools.telegram_api status`

## Smoke test réel

Le groupe `telegram` n'envoie **qu'à « Messages enregistrés »**. Cette cible est codée en dur et ne se configure pas. Le groupe vérifie aussi qu'un destinataire inconnu est refusé sans envoi. Il faut l'activer explicitement :

```bash
JARVIS_SMOKE_TELEGRAM=1 PYTHONPATH=src ~/dev/Jarvis/.venv/bin/python scripts/smoke_test.py --group telegram
```
