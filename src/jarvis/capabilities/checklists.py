"""Small persistent checklists. IDs are explicit; SQL values are parameterized."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from jarvis.capabilities.results import ToolResult


class ChecklistsCapability:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else Path.home() / 'Library/Application Support/Jarvis/checklists.db'

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        os.chmod(self.path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('CREATE TABLE IF NOT EXISTS lists(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL);'
                                 'CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT,list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,text TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0);')
        return connection

    def manage(self, operation, list_id=None, text=None, item_id=None, done=True):
        if operation not in {'create', 'list', 'show', 'add', 'check'}:
            return ToolResult.failure('manage_checklist', 'Operation inconnue.', 'invalid_operation')
        if operation in {'create', 'add'} and (not isinstance(text, str) or not text.strip() or len(text) > 300):
            return ToolResult.failure('manage_checklist', 'Texte obligatoire, 300 caracteres maximum.', 'invalid_text')
        if operation in {'show', 'add', 'check'} and (type(list_id) is not int or list_id <= 0):
            return ToolResult.failure('manage_checklist', 'Identifiant de liste obligatoire.', 'invalid_id')
        if operation == 'check' and (type(item_id) is not int or item_id <= 0 or type(done) is not bool):
            return ToolResult.failure('manage_checklist', 'Element ou etat invalide.', 'invalid_id')
        try:
            with closing(self._connect()) as conn, conn:
                if operation != 'list':
                    conn.execute('BEGIN IMMEDIATE')
                if operation == 'list':
                    rows = [dict(row) for row in conn.execute('SELECT id,title FROM lists ORDER BY id DESC LIMIT 50')]
                    return ToolResult.success('manage_checklist', f'{len(rows)} liste(s).', lists=rows)
                if operation == 'create':
                    if conn.execute('SELECT COUNT(*) FROM lists').fetchone()[0] >= 50:
                        return ToolResult.failure('manage_checklist', 'Limite de 50 listes atteinte.', 'limit_reached')
                    list_id = conn.execute('INSERT INTO lists(title) VALUES (?)', (text.strip(),)).lastrowid
                record = conn.execute('SELECT id,title FROM lists WHERE id=?', (list_id,)).fetchone()
                if record is None:
                    return ToolResult.failure('manage_checklist', 'Liste introuvable.', 'list_not_found')
                if operation == 'add':
                    if conn.execute('SELECT COUNT(*) FROM items WHERE list_id=?', (list_id,)).fetchone()[0] >= 100:
                        return ToolResult.failure('manage_checklist', 'Limite de 100 elements atteinte.', 'limit_reached')
                    conn.execute('INSERT INTO items(list_id,text) VALUES (?,?)', (list_id, text.strip()))
                if operation == 'check':
                    cursor = conn.execute('UPDATE items SET done=? WHERE id=? AND list_id=?', (int(done), item_id, list_id))
                    if not cursor.rowcount:
                        return ToolResult.failure('manage_checklist', 'Element introuvable dans cette liste.', 'item_not_found')
                items = [dict(row) for row in conn.execute('SELECT id,text,done FROM items WHERE list_id=? ORDER BY id', (list_id,))]
                return ToolResult.success('manage_checklist', 'Liste mise a jour.' if operation != 'show' else 'Voici la liste.',
                    list_id=list_id, title=record['title'], items=items, state_confirmed=True)
        except (OSError, sqlite3.Error):
            return ToolResult.failure('manage_checklist', 'Les checklists sont indisponibles.', 'storage_error')

    def clear(self):
        if not self.path.exists():
            return 0
        with closing(self._connect()) as conn, conn:
            count = conn.execute('SELECT COUNT(*) FROM lists').fetchone()[0]
            conn.execute('DELETE FROM items')
            conn.execute('DELETE FROM lists')
            return count
