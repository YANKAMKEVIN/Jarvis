"""Search session results and durable mission metadata; replay is always explicit."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QComboBox,
    QListWidget,QListWidgetItem,QPlainTextEdit,QPushButton,QLabel,QInputDialog,QFileDialog,QGridLayout)
from jarvis.memory.store import MemoryStore

class HistoryDialog(QDialog):
    def __init__(self,experience,parent=None,store=None):
        super().__init__(parent);self.experience=experience;self.store=store or MemoryStore()
        self.setWindowTitle('Missions, résultats et procédures');self.resize(760,650)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Rechercher un objectif ou une procédure…');layout.addWidget(self.search)
        self.filter=QComboBox()
        for title,value in [('Toutes les missions','all'),('Terminées','completed'),('À vérifier','failed'),('Procédures enregistrées','procedures'),('Résultats d’outils archivés','receipts')]:self.filter.addItem(title,value)
        layout.addWidget(self.filter);self.list=QListWidget();self.list.setAccessibleName('Missions et procédures enregistrées');layout.addWidget(self.list)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setAccessibleName('Résultats et étapes disponibles');layout.addWidget(self.details)
        actions=QGridLayout()
        for index,(title,callback) in enumerate([('Actualiser',self.reload),('Nouvelle mission similaire…',self.resume),('Mémoriser la dernière réussite…',self.learn),('Exporter les détails…',self.export),('Afficher les fichiers produits',self.reveal),('Effacer les résultats archivés',self.clear_archive)]):
            b=QPushButton(title);b.clicked.connect(callback);actions.addWidget(b,index//2,index%2)
        layout.addLayout(actions);self.status=QLabel('Les objectifs sont conservés localement. L’archivage des résultats d’outils pendant 30 jours est optionnel ; aucune conversation n’est enregistrée.');self.status.setWordWrap(True);layout.addWidget(self.status)
        close=QPushButton('Fermer');close.clicked.connect(self.close);layout.addWidget(close)
        self.search.textChanged.connect(self.reload);self.filter.currentIndexChanged.connect(self.reload);self.list.currentItemChanged.connect(self.select);self.reload()
    def reload(self,*_):
        self.list.clear();needle=self.search.text().casefold();kind=self.filter.currentData()
        try:
            if kind=='receipts':
                from jarvis.desktop.result_history import ResultHistoryStore
                rows=[dict(row,goal=row['title'],status='receipt',archived=True,content=row['body']) for row in ResultHistoryStore().list()]
            elif kind=='procedures':rows=[{'goal':r.subject,'status':'procedure','content':r.content} for r in self.store.list(kind='procedure',limit=100)]
            else:
                current=[dict(r,goal=r.get('objective','')) for r in self.experience.c.mission_list()]
                archived=[{'goal':r.goal,'status':r.status,'step_count':r.step_count,'archived':True} for r in self.store.recent_missions(100)]
                rows=current+archived
            for row in rows:
                if needle and needle not in row['goal'].casefold():continue
                if kind=='completed' and row['status']!='completed':continue
                if kind=='failed' and row['status'] not in {'failed','unknown','budget_exceeded','blocked'}:continue
                item=QListWidgetItem(row['goal']+' · '+row['status']);item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
        except Exception:self.status.setText('Historique local indisponible.')
    def current(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def select(self,*_):
        row=self.current()
        if not row:self.details.clear();return
        parts=[row['goal'],row['status']]
        for step in row.get('steps',[]):parts.append(step.get('label','')+' · '+step.get('status',''))
        if row.get('content'):parts.append(row['content'])
        if row.get('paths'):parts+=['Fichiers produits :',*row['paths']]
        if not row.get('archived'):
            parts.append('Cartes de la session — toutes missions confondues :')
            for card in self.experience.c.cards.values():
                parts += [card.get('title',''),card.get('body',''),*card.get('items',[])]
        self.details.setPlainText('\n'.join(str(p) for p in parts))
    def resume(self):
        row=self.current()
        if not row:return
        if row['status']=='receipt':self.status.setText('Choisissez un objectif dans les missions pour en créer une nouvelle.');return
        if row['status']=='procedure':self.experience.submit('run_procedure',{'name':row['goal']})
        else:self.experience.submit('run_task',{'goal':'Reprends cet objectif en vérifiant d’abord ce qui est déjà fait ; évite les doublons et demande confirmation pour tout envoi : '+row['goal']})
    def learn(self):
        name,ok=QInputDialog.getText(self,'Mémoriser une procédure','Nom de la dernière mission réussie à mémoriser :')
        if ok and name.strip():self.experience.submit('save_task_procedure',{'name':name.strip()[:80]})
    def export(self):
        if not self.details.toPlainText():return
        path,_=QFileDialog.getSaveFileName(self,'Exporter les détails','mission-jarvis.txt','Texte (*.txt)')
        if path:
            try:
                from pathlib import Path
                Path(path).write_text(self.details.toPlainText(),encoding='utf-8');self.status.setText('Détails exportés.')
            except OSError:self.status.setText('Impossible d’écrire ce fichier.')

    def reveal(self):
        row=self.current()
        paths=(row or {}).get('paths',[])
        if not paths:self.status.setText('Aucun chemin de fichier associé à ce résultat.');return
        from pathlib import Path
        import subprocess,sys
        try:
            for value in paths[:5]:
                path=Path(value)
                if sys.platform=='darwin':subprocess.run(['open','-R',str(path)],check=True,timeout=5)
                else:
                    from PySide6.QtGui import QDesktopServices
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        except Exception:self.status.setText('Emplacement indisponible. Le fichier a peut-être été déplacé.')
    def clear_archive(self):
        if self.experience.c.voice_worker is not None:
            self.status.setText("Arrêtez le vocal avant de vider l’archive, afin de terminer les écritures en cours.");return
        from jarvis.desktop.result_history import ResultHistoryStore
        try:ResultHistoryStore().clear();self.reload();self.status.setText('Résultats archivés effacés. Les autres souvenirs ne sont pas modifiés.')
        except Exception:self.status.setText('Archive occupée. Réessayez après la tâche en cours.')
