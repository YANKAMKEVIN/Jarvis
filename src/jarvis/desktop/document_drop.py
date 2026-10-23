"""Dropping selects files only; a deliberate action starts analysis through tools."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QCheckBox

SUPPORTED={'.txt','.md','.csv','.json','.log','.py','.pdf','.docx','.html','.xml','.yaml','.yml','.rst'}
def dropped_files(urls):
    if not 1<=len(urls)<=2:raise ValueError('Déposez un document, ou deux pour les comparer.')
    paths=[]
    for url in urls:
        if not url.isLocalFile() or url.host() not in {'','localhost'}:raise ValueError('Seuls les fichiers locaux sont acceptés.')
        p=Path(url.toLocalFile()).expanduser().resolve(strict=True)
        if not p.is_file() or p.suffix.lower() not in SUPPORTED:raise ValueError('Choisissez un document texte, PDF ou DOCX.')
        if p.stat().st_size>30*1024*1024:raise ValueError('Document trop volumineux (30 Mo maximum).')
        paths.append(str(p))
    return paths

class DocumentDropDialog(QDialog):
    def __init__(self,experience,paths,parent=None):
        super().__init__(parent);self.experience=experience;self.paths=paths
        self.setWindowTitle('Que faire de ce document ?');self.resize(500,330)
        layout=QVBoxLayout(self)
        label=QLabel('\n'.join(Path(p).name for p in paths));label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);layout.addWidget(label)
        hint=QLabel('Le contenu ne sera lu qu’après votre choix. L’analyse utilise les outils et autorisations habituels de Jarvis.');hint.setWordWrap(True);layout.addWidget(hint)
        import os
        self.remote=QCheckBox('Autoriser l’analyse par un modèle distant, si configuré')
        self.remote.setChecked(os.environ.get('JARVIS_DOCUMENT_ALLOW_REMOTE','').lower() in {'1','true','yes','oui','on'})
        layout.addWidget(self.remote)
        self.buttons=[]
        if len(paths)==1:
            actions=[('Résumer','ask_about_document',{'path':paths[0],'question':'Résume ce document en français, en distinguant faits et incertitudes.'}),
                     ('Extraire les tâches','extract_document_actions',{'path':paths[0]})]
        else:actions=[('Comparer ces documents','compare_documents',{'left':paths[0],'right':paths[1]})]
        for title,tool,args in actions:
            b=QPushButton(title);b.clicked.connect(lambda checked=False,t=tool,a=args:self.launch(t,a));layout.addWidget(b);self.buttons.append(b)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        close=QPushButton('Fermer');close.clicked.connect(self.close);layout.addWidget(close)
        experience.c.changed.connect(self.render);self.render()
    def render(self):
        ready=self.experience.ready()
        for b in self.buttons:b.setEnabled(ready)
        self.status.setText('Choisissez une action.' if ready else 'Démarrez le vocal pour activer l’analyse. Aucun document n’a été envoyé.')
    def launch(self,tool,args):
        if self.experience.submit(tool,dict(args,_remote_allowed=self.remote.isChecked())):self.status.setText('Analyse demandée · suivez son résultat dans les cartes.')
