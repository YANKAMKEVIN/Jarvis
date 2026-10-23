"""Routine configuration reuses the same MacroStore and planner as voice tools."""
import sqlite3
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,
    QLineEdit,QPlainTextEdit,QPushButton,QFormLayout)
from jarvis.macros import MacroStore,MacroError

TEMPLATES={
    'Ma journée':'Lis mon agenda et mes rappels pour aujourd’hui. Résume les horaires, conflits et priorités. Ne crée, ne modifie et n’envoie rien.',
    'Concentration':'Lance un minuteur de 25 minutes intitulé Concentration, puis annonce le début de cette session. Ne change aucun réglage système et n’envoie aucun message.',
}

class RoutineDialog(QDialog):
    def __init__(self,controller,parent=None,store=None):
        super().__init__(parent)
        self.controller=controller;self.store=store or MacroStore();self.pending_name=None
        self.setWindowTitle('Routines vocales');self.resize(620,600)
        self.setStyleSheet('QDialog {background:#0d1c2b;} QLineEdit,QPlainTextEdit,QListWidget {background:#13283b;color:#e3f5ff;border:1px solid #42617a;}')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Configurez une routine, puis dites « lance la routine [nom] ».'))
        self.list=QListWidget();self.list.setAccessibleName('Routines enregistrées');layout.addWidget(self.list)
        self.list.currentTextChanged.connect(self.select)
        form=QFormLayout();self.name=QLineEdit();self.name.setMaxLength(80);self.name.setAccessibleName('Nom de la routine')
        self.goal=QPlainTextEdit();self.goal.setAccessibleName('Objectif de la routine');self.goal.setPlaceholderText('Les actions que vous souhaitez réutiliser, en 500 caractères maximum.')
        form.addRow('Nom',self.name);form.addRow('Objectif',self.goal);layout.addLayout(form)
        templates=QHBoxLayout()
        for name in TEMPLATES:
            b=QPushButton('Exemple · '+name);b.clicked.connect(lambda checked=False,n=name:self.template(n));templates.addWidget(b)
        layout.addLayout(templates)
        actions=QHBoxLayout()
        for title,callback in [('Nouveau',self.new),('Enregistrer',self.save),('Supprimer',self.delete)]:
            b=QPushButton(title);b.clicked.connect(callback);actions.addWidget(b)
        self.run=QPushButton('Lancer la routine sélectionnée');self.run.clicked.connect(self.launch);actions.addWidget(self.run)
        layout.addLayout(actions)
        self.notice=QLabel('Les exemples ne sont enregistrés ni exécutés avant votre choix.');self.notice.setWordWrap(True);self.notice.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.notice)
        close=QPushButton('Fermer');close.clicked.connect(self.close);layout.addWidget(close)
        controller.changed.connect(self.refresh_enabled)
        controller.routine_result.connect(self.receipt)
        self.reload();self.refresh_enabled()
    def reload(self,selected=None):
        self.list.blockSignals(True);self.list.clear()
        try:
            for row in self.store.list():self.list.addItem(row['name'])
        except (OSError,sqlite3.Error):self.notice.setText('Les routines locales sont indisponibles.')
        self.list.blockSignals(False)
        if selected:
            matches=self.list.findItems(selected,Qt.MatchFlag.MatchExactly)
            if matches:self.list.setCurrentItem(matches[0])
    def new(self):self.list.clearSelection();self.name.clear();self.goal.clear()
    def template(self,name):self.name.setText(name);self.goal.setPlainText(TEMPLATES[name]);self.notice.setText('Exemple prêt à adapter · Enregistrer ne lance aucune action.')
    def select(self,name):
        try:row=self.store.get(name) if name else None
        except (OSError,sqlite3.Error):row=None
        if row:self.name.setText(row['name']);self.goal.setPlainText(row['goal'])
    def save(self):
        try:
            row=self.store.save(self.name.text(),self.goal.toPlainText());self.reload(row['name'])
            self.notice.setText('Enregistrée. Dites « lance la routine '+row['name']+' ».')
        except MacroError as e:self.notice.setText(e.message)
        except (OSError,sqlite3.Error):self.notice.setText('Impossible d’enregistrer la routine locale.')
    def delete(self):
        name=self.list.currentItem().text() if self.list.currentItem() else None
        if not name:return
        try:self.store.delete(name);self.reload();self.new();self.notice.setText('Routine supprimée.')
        except (OSError,sqlite3.Error):self.notice.setText('Impossible de supprimer cette routine.')
    def refresh_enabled(self):
        c=self.controller
        self.run.setEnabled(not c.demo and c.voice_worker is not None and c.voice_state not in {'starting','stopping','error'})
    def receipt(self,event):
        if event.get('name')!=self.pending_name:return
        self.pending_name=None
        messages={'read_only_mode':'Routine refusée : le mode lecture seule est activé.',
                  'macro_not_found':'Routine introuvable. Enregistrez-la à nouveau.'}
        self.notice.setText('Mission lancée · consultez les missions de Jarvis.' if event.get('ok') else messages.get(event.get('reason'),'La routine n’a pas pu démarrer. Consultez l’activité.'))
        self.refresh_enabled()

    def launch(self):
        item=self.list.currentItem()
        if not item:self.notice.setText('Enregistrez et sélectionnez une routine avant de la lancer.');return
        try:row=self.store.get(item.text())
        except (OSError,sqlite3.Error):
            self.notice.setText('Routine locale indisponible.');return
        if not row or self.name.text().strip()!=row['name'] or self.goal.toPlainText().strip()!=row['goal']:
            self.notice.setText('Enregistrez vos modifications avant de lancer la routine.');return
        self.pending_name=item.text()
        if self.controller.run_routine(item.text()) is False:
            self.pending_name=None
            self.notice.setText('Demande refusée : session indisponible ou file pleine. Réessayez après les demandes en cours.')
            self.refresh_enabled()
            return
        self.run.setEnabled(False)
        QTimer.singleShot(1000,self.refresh_enabled)
        self.notice.setText('Demande transmise · suivez sa mission dans Jarvis.')
