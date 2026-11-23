"""Settings > Serveurs MCP: list, test, pre-approve tools, add or remove."""
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from jarvis.mcp import editor
from jarvis.mcp.config import MCPConfigError


class _Tester(QObject):
    done = Signal(object)

    def __init__(self, raw, name, opener):
        super().__init__();self.raw, self.name, self.opener = raw, name, opener

    def run(self):
        try:result = editor.probe_server(self.raw, self.name, self.opener)
        except Exception as error:  # noqa: BLE001 - shown to the user, never raised in Qt
            result = {'ok': False, 'error': str(error) or type(error).__name__, 'tools': []}
        self.done.emit(result)


class MCPDialog(QDialog):
    def __init__(self, parent=None, path=None, opener=None, threaded=True):
        super().__init__(parent)
        self.path, self.opener, self.threaded = path, opener, threaded
        self.thread = None;self.tester = None;self.tested = {}
        self.setWindowTitle('Serveurs MCP');self.resize(620, 560)
        layout = QVBoxLayout(self)
        hint = QLabel('Outils externes branchés sur Jarvis. Un outil coché s’exécute sans confirmation orale : '
                      'réservez-le aux lectures. Jetons et variables d’environnement ne sont jamais affichés.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.servers = QListWidget();self.servers.setAccessibleName('Serveurs MCP configurés');layout.addWidget(self.servers)
        self.detail = QLabel();self.detail.setWordWrap(True);self.detail.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.detail)
        self.disabled = QCheckBox('Désactivé (garder l’entrée sans démarrer le serveur)');self.disabled.toggled.connect(self.toggle_disabled);layout.addWidget(self.disabled)
        row = QHBoxLayout()
        self.test_button = QPushButton('Tester la connexion');self.test_button.clicked.connect(self.test);row.addWidget(self.test_button)
        self.remove_button = QPushButton('Supprimer ce serveur');self.remove_button.clicked.connect(self.remove);row.addWidget(self.remove_button)
        layout.addLayout(row)
        layout.addWidget(QLabel('Outils pré-approuvés (sans confirmation) :'))
        self.tools = QListWidget();self.tools.setAccessibleName('Outils du serveur, cochés si pré-approuvés')
        self.tools.itemChanged.connect(self.tool_toggled);layout.addWidget(self.tools)
        add = QHBoxLayout()
        self.new_name = QLineEdit();self.new_name.setPlaceholderText('nom (ex. github)');self.new_name.setAccessibleName('Nom du nouveau serveur')
        self.new_target = QLineEdit();self.new_target.setPlaceholderText('commande (npx -y …) ou URL https://…');self.new_target.setAccessibleName('Commande ou URL du nouveau serveur')
        add_button = QPushButton('Ajouter');add_button.clicked.connect(self.add)
        add.addWidget(self.new_name, 1);add.addWidget(self.new_target, 2);add.addWidget(add_button);layout.addLayout(add)
        bottom = QHBoxLayout()
        save = QPushButton('Enregistrer');save.clicked.connect(self.save);bottom.addWidget(save)
        close = QPushButton('Fermer');close.clicked.connect(self.close);bottom.addWidget(close)
        layout.addLayout(bottom)
        self.status = QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.servers.currentItemChanged.connect(self.show_server)
        self.reload()

    def reload(self):
        try:self.raw = editor.read_raw_config(self.path)
        except MCPConfigError as error:
            self.raw = None;self.status.setText(f'Fichier mcp.json invalide, corrigez-le à la main : {error}');self.render_list();return
        self.render_list()

    def render_list(self, select=None):
        self.servers.blockSignals(True);self.servers.clear()
        for row in editor.server_rows(self.raw or {}):
            item = QListWidgetItem(f"{row['name']} · {'désactivé · ' if row['disabled'] else ''}{row['target'][:60]}")
            item.setData(Qt.ItemDataRole.UserRole, row['name']);self.servers.addItem(item)
            if row['name'] == select:self.servers.setCurrentItem(item)
        self.servers.blockSignals(False)
        if self.servers.currentItem() is None and self.servers.count():self.servers.setCurrentRow(0)
        self.show_server()

    def current(self):
        item = self.servers.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None

    def show_server(self, *_):
        name = self.current();has = name is not None and self.raw is not None
        for widget in (self.disabled, self.test_button, self.remove_button, self.tools):widget.setEnabled(has)
        self.tools.blockSignals(True);self.tools.clear()
        if not has:
            self.detail.setText('Aucun serveur configuré. Ajoutez-en un ci-dessous.' if self.raw is not None else '');self.tools.blockSignals(False);return
        row = next(r for r in editor.server_rows(self.raw) if r['name'] == name)
        secrets = f" · secrets : {', '.join(row['secret_keys'])}" if row['secret_keys'] else ''
        self.detail.setText(f"{row['transport']} · {row['target']}{secrets}")
        self.disabled.blockSignals(True);self.disabled.setChecked(row['disabled']);self.disabled.blockSignals(False)
        for tool in sorted(set(self.tested.get(name, [])) | set(row['auto_approve'])):
            item = QListWidgetItem(tool);item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if tool in row['auto_approve'] else Qt.CheckState.Unchecked)
            self.tools.addItem(item)
        self.tools.blockSignals(False)

    def toggle_disabled(self, checked):
        if self.current():editor.set_disabled(self.raw, self.current(), checked);self.status.setText('Modifié · pensez à enregistrer.')

    def tool_toggled(self, _item):
        name = self.current()
        if not name:return
        approved = [self.tools.item(i).text() for i in range(self.tools.count()) if self.tools.item(i).checkState() == Qt.CheckState.Checked]
        editor.set_auto_approve(self.raw, name, approved);self.status.setText('Modifié · pensez à enregistrer.')

    def add(self):
        if self.raw is None:return
        try:editor.add_server(self.raw, self.new_name.text(), self.new_target.text())
        except MCPConfigError as error:self.status.setText(str(error));return
        name = self.new_name.text().strip();self.new_name.clear();self.new_target.clear()
        self.render_list(select=name);self.status.setText(f'{name} ajouté · testez-le puis enregistrez.')

    def remove(self):
        name = self.current()
        if name:editor.remove_server(self.raw, name);self.tested.pop(name, None);self.render_list();self.status.setText(f'{name} retiré · enregistrez pour confirmer.')

    def save(self):
        if self.raw is None:return False
        try:path = editor.save_raw_config(self.raw, self.path)
        except (MCPConfigError, OSError) as error:self.status.setText(f'Rien enregistré : {error}');return False
        self.status.setText(f'Enregistré dans {path.name}. Les changements valent pour la prochaine session vocale.');return True

    def test(self):
        name = self.current()
        if not name or (self.thread is not None and self.thread.isRunning()):return
        self.status.setText(f'Connexion à {name}…');self.test_button.setEnabled(False)
        self.tester = _Tester(self.raw, name, self.opener)
        self.tester.done.connect(lambda result, name=name: self.tested_server(name, result))
        if not self.threaded:self.tester.run();return
        self.thread = QThread(self);self.tester.moveToThread(self.thread)
        self.thread.started.connect(self.tester.run);self.tester.done.connect(self.thread.quit);self.thread.start()

    def tested_server(self, name, result):
        self.test_button.setEnabled(True)
        if result['ok']:
            self.tested[name] = result['tools'];self.status.setText(f"{name} joignable · {len(result['tools'])} outil(s).")
        else:self.status.setText(f"{name} injoignable : {result['error'] or 'erreur inconnue'}.")
        if self.current() == name:self.show_server()

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():self.thread.quit();self.thread.wait(3000)
        super().closeEvent(event)
