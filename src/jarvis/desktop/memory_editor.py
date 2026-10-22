"""Explicit local memory review; contents are never sent to the model on open."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QListWidget,
    QListWidgetItem,QLineEdit,QPlainTextEdit,QPushButton,QLabel,QFormLayout)
from jarvis.memory.store import MemoryStore
from jarvis.context_store import ContextStore
from jarvis.memory.guard import contains_secret

class MemoryEditor(QDialog):
    def __init__(self,parent=None,memory=None,context=None):
        super().__init__(parent);self.memory=memory or MemoryStore();self.context=context or ContextStore()
        self.setWindowTitle('Mémoire de Jarvis');self.resize(650,620)
        layout=QVBoxLayout(self)
        hint=QLabel('Consultez ce que Jarvis retient. Ouvrir cette fenêtre ne transmet rien à Gemini.');hint.setWordWrap(True);layout.addWidget(hint)
        self.kind=QComboBox();self.kind.addItem('Préférences et faits','memory');self.kind.addItem('Notes de contexte','context');layout.addWidget(self.kind)
        self.list=QListWidget();self.list.setAccessibleName('Souvenirs locaux');layout.addWidget(self.list)
        form=QFormLayout();self.subject=QLineEdit();self.subject.setMaxLength(120);self.content=QPlainTextEdit()
        form.addRow('Sujet',self.subject);form.addRow('Contenu',self.content);layout.addLayout(form)
        actions=QHBoxLayout()
        for title,callback in [('Nouveau',self.new),('Enregistrer',self.save),('Supprimer la sélection',self.delete),('Actualiser',self.reload)]:
            b=QPushButton(title);b.clicked.connect(callback);actions.addWidget(b)
        layout.addLayout(actions);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        close=QPushButton('Fermer');close.clicked.connect(self.close);layout.addWidget(close)
        self.list.currentItemChanged.connect(self.select);self.kind.currentIndexChanged.connect(self.reload);self.reload()
    def current(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def new(self):self.list.setCurrentRow(-1);self.subject.clear();self.subject.setReadOnly(False);self.content.clear()
    def reload(self,*_):
        self.list.clear();self.new();self.subject.setEnabled(self.kind.currentData()=='memory')
        try:
            rows=([{'id':r.id,'subject':r.subject,'content':r.content,'kind':r.kind} for r in self.memory.list(limit=100) if r.kind!='procedure']
                  if self.kind.currentData()=='memory' else [{'id':r['id'],'subject':'Contexte','content':r['text']} for r in self.context.recent(50)])
            for row in rows:
                item=QListWidgetItem(row['subject']+' · '+row['content'][:70].replace('\n',' '));item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
            self.status.setText(f'{len(rows)} élément(s) locaux.')
        except Exception:self.status.setText('Mémoire locale indisponible.')
    def select(self,*_):
        row=self.current()
        if row:self.subject.setText(row['subject']);self.subject.setReadOnly(True);self.content.setPlainText(row['content'])
    def save(self):
        row=self.current();content=self.content.toPlainText().strip();subject=self.subject.text().strip()
        if not content or contains_secret(subject,content):self.status.setText('Contenu vide ou secret détecté : rien enregistré.');return
        try:
            if self.kind.currentData()=='memory':self.memory.remember(row['kind'] if row else 'preference',subject,content,'user')
            elif row:
                if not self.context.update(row['id'],content):self.status.setText('Élément introuvable. Actualisez la liste.');return
            else:self.context.add(content)
            self.reload();self.status.setText('Mémoire mise à jour localement.')
        except Exception:self.status.setText('Enregistrement impossible : vérifiez le sujet et la longueur du contenu.')
    def delete(self):
        row=self.current()
        if not row:return
        try:
            self.memory.delete(row['id']) if self.kind.currentData()=='memory' else self.context.delete(row['id'])
            self.reload();self.status.setText('Élément supprimé.')
        except Exception:self.status.setText('Suppression indisponible.')
