"""Keyboard-first command palette, daily cockpit, trigger editor and setup guide."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,
    QListWidget,QListWidgetItem,QPushButton,QFormLayout,QComboBox,QCheckBox,QPlainTextEdit,
    QTabWidget,QWidget,QInputDialog,QScrollArea)
from jarvis.desktop.experience_storage import load_triggers,save_trigger
import json


def note(value):
    label=QLabel(value);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);return label


def push(title, callback):
    button=QPushButton(title);button.setAccessibleName(title);button.clicked.connect(callback);return button


class CommandPalette(QDialog):
    def __init__(self, experience, parent=None):
        super().__init__(parent);self.experience=experience;self.actions=experience.commands()
        self.setWindowTitle('Commandes Jarvis · ⌘K');self.resize(580,480)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Rechercher une commande…');self.search.setAccessibleName('Rechercher une commande')
        self.list=QListWidget();self.list.setAccessibleName('Commandes disponibles');layout.addWidget(self.search);layout.addWidget(self.list)
        self.hint=note('Entrée pour lancer · Échap pour fermer · aucune action avant votre choix.');layout.addWidget(self.hint)
        layout.addWidget(push('Exécuter la sélection',self.execute))
        self.search.textChanged.connect(self.filter);self.search.returnPressed.connect(self.execute);self.list.itemActivated.connect(self.execute)
        self.filter('');self.search.setFocus()
    def filter(self,text):
        self.list.clear()
        for index,(name,_) in enumerate(self.actions):
            if text.casefold() in name.casefold():
                item=QListWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,index);self.list.addItem(item)
        if self.list.count():self.list.setCurrentRow(0)
    def execute(self,*_):
        item=self.list.currentItem()
        if not item:return
        callback=self.actions[item.data(Qt.ItemDataRole.UserRole)][1];self.close();callback()


class ExperienceDialog(QDialog):
    def __init__(self, experience, parent=None):
        super().__init__(parent);self.experience=experience;self.setWindowTitle('Jarvis au quotidien');self.resize(760,700)
        layout=QVBoxLayout(self);layout.addWidget(note('Votre compagnon, vos habitudes'))
        tabs=QTabWidget();layout.addWidget(tabs)
        home=QWidget();home_layout=QVBoxLayout(home)
        for name,callback in experience.commands()[:10]:home_layout.addWidget(push(name,callback))
        home_layout.addStretch();tabs.addTab(home,'Actions')
        preferences=QWidget();form=QFormLayout(preferences);options=experience.options
        self.combos={}
        choices={
            'tone':('Ton',[('Naturel','balanced'),('Chaleureux','warm'),('Joueur','playful')]),
            'detail':('Réponses',[('Courtes','short'),('Adaptées','normal'),('Détaillées','detailed')]),
            'initiative':('Initiative',[('Sur demande','reactive'),('Suggestions utiles','suggest')]),
            'theme':('Thème',[('Nuit bleue','night'),('Aube cuivrée','dawn'),('Contraste élevé','contrast')]),
            'font_size':('Taille des textes',[('Standard',13),('Grande',15),('Très grande',17)]),
        }
        for key,(title,values) in choices.items():
            combo=QComboBox();combo.setAccessibleName(title)
            for label,value in values:combo.addItem(label,value)
            combo.setCurrentIndex(combo.findData(getattr(options,key)));self.combos[key]=combo;form.addRow(title,combo)
            combo.currentIndexChanged.connect(lambda _,k=key,w=combo:experience.set_option(k,w.currentData()))
        self.checks={}
        for key,title in [('quiet','Réponses écrites · haut-parleur silencieux'),('headphones','Je porte un casque · autoriser l’interruption vocale'),
                          ('history','Conserver les résultats d’outils sur ce Mac · 30 jours'),('tracking','Réagir au curseur'),('articulated','Humanoïdes articulés · style dessiné 2D')]:
            check=QCheckBox(title);check.setChecked(getattr(options,key));check.setAccessibleName(title)
            self.checks[key]=check;form.addRow(check);check.toggled.connect(lambda value,k=key:experience.set_option(k,value))
        reduced=QCheckBox('Réduire les mouvements');self.reduced=reduced;reduced.setChecked(experience.c.reduced_motion)
        reduced.toggled.connect(experience.shell.full.set_reduced_motion);form.addRow(reduced)
        briefing=QLineEdit(options.briefing);briefing.setMaxLength(180);form.addRow('Sujets du briefing',briefing)
        briefing.editingFinished.connect(lambda:experience.set_option('briefing',briefing.text()))
        form.addRow(note('Le mode dessiné articulé concerne NovaBot, Neo Guide, Digital Avatar, Synth Companion et Holo Face. Les autres apparences gardent leurs visuels actuels.'))
        form.addRow(note('Le mode écrit affiche uniquement les prochaines réponses dans cette fenêtre, en mémoire vive. Aucune conversation n’est enregistrée sur disque. Avec des haut-parleurs, l’anti-écho reste actif ; l’interruption vocale simultanée est réservée au casque.'))
        preferences_scroll=QScrollArea();preferences_scroll.setWidgetResizable(True);preferences_scroll.setWidget(preferences)
        tabs.addTab(preferences_scroll,'Préférences')
        replies=QWidget();reply_layout=QVBoxLayout(replies);reply_layout.addWidget(note('Réponses du mode discret · cinq dernières réponses, effacées en quittant Jarvis'))
        self.replies=QPlainTextEdit();self.replies.setReadOnly(True);self.replies.setAccessibleName('Réponses écrites en mémoire vive');reply_layout.addWidget(self.replies)
        reply_layout.addWidget(push('Effacer ces réponses',experience.clear_replies));tabs.addTab(replies,'Réponses écrites')
        self.progress=note(experience.c.request_status);layout.addWidget(self.progress)
        layout.addWidget(push('Fermer',self.close));experience.c.changed.connect(self.render);self.render()
    def render(self):
        for key,combo in self.combos.items():
            combo.blockSignals(True);combo.setCurrentIndex(combo.findData(getattr(self.experience.options,key)));combo.blockSignals(False)
        for key,check in self.checks.items():
            check.blockSignals(True);check.setChecked(getattr(self.experience.options,key));check.blockSignals(False)
        self.reduced.blockSignals(True);self.reduced.setChecked(self.experience.c.reduced_motion);self.reduced.blockSignals(False)
        self.progress.setText(self.experience.c.request_status)
        self.replies.setPlainText('\n\n'.join(self.experience.c.quiet_replies))


class TriggerDialog(QDialog):
    def __init__(self,experience,parent=None):
        super().__init__(parent);self.e=experience;self.setWindowTitle('Déclencheurs des routines');self.resize(650,530)
        layout=QVBoxLayout(self);layout.addWidget(note('Uniquement lorsque Jarvis est ouvert. Une routine ne démarre jamais le microphone. Si le vocal est arrêté, elle attend dix minutes maximum.'))
        self.list=QListWidget();self.list.setAccessibleName('Déclencheurs enregistrés');layout.addWidget(self.list);form=QFormLayout()
        self.routine=QComboBox();self.routine.setAccessibleName('Routine à déclencher')
        try:
            from jarvis.macros import MacroStore
            for row in MacroStore().list():self.routine.addItem(row['name'])
        except Exception:pass
        self.kind=QComboBox();self.kind.addItem('Chaque jour à une heure locale','time');self.kind.addItem('À l’ouverture d’une application','application')
        self.value=QLineEdit();self.value.setPlaceholderText('09:00 ou nom / identifiant de l’application')
        form.addRow('Routine',self.routine);form.addRow('Déclenchement',self.kind);form.addRow('Heure ou application',self.value);layout.addLayout(form)
        for title,callback in [('Ajouter et activer',self.add),('Activer / désactiver la sélection',self.toggle),('Supprimer la sélection',self.delete),('Fermer',self.close)]:layout.addWidget(push(title,callback))
        self.status=note('Les actions gardent les confirmations et le mode sécurité habituels.');layout.addWidget(self.status);self.reload()
    def reload(self):
        self.list.clear()
        for row in load_triggers(self.e.shell.settings):
            item=QListWidgetItem(('Actif · ' if row.get('enabled') else 'Désactivé · ')+row['routine']+' · '+row['value'])
            item.setData(Qt.ItemDataRole.UserRole,row['id']);self.list.addItem(item)
    def add(self):
        try:
            save_trigger(self.e.shell.settings,self.routine.currentText(),self.kind.currentData(),self.value.text());self.e.reload_triggers();self.reload();self.status.setText('Déclencheur enregistré et activé.')
        except ValueError as error:self.status.setText(str(error))
    def change(self,delete=False):
        item=self.list.currentItem()
        if not item:return
        rows=load_triggers(self.e.shell.settings);identifier=item.data(Qt.ItemDataRole.UserRole)
        if delete:rows=[row for row in rows if row['id']!=identifier]
        else:
            for row in rows:
                if row['id']==identifier:row['enabled']=not row.get('enabled',False)
        self.e.shell.settings.setValue('experience/triggers',json.dumps(rows));self.e.reload_triggers();self.reload()
    def toggle(self):self.change()
    def delete(self):self.change(True)


class SetupGuide(QDialog):
    def __init__(self,experience,parent=None):
        super().__init__(parent);self.e=experience;self.setWindowTitle('Bien démarrer avec Jarvis');self.resize(580,550)
        layout=QVBoxLayout(self);layout.addWidget(note('Préparez Jarvis en cinq étapes, dans l’ordre qui vous convient. Aucun test n’ouvre le micro sans votre clic.'))
        for title,callback in [('1 · Configurer la clé Gemini',self.key),('2 · Autorisations macOS',self.permissions),
                               ('3 · Choisir et tester les périphériques',experience.shell.show_settings),
                               ('4 · Choisir une voix et écouter un aperçu',experience.shell.show_voices),
                               ('5 · Ouvrir Jarvis et essayer une question',experience.shell.show_full)]:layout.addWidget(push(title,callback))
        self.status=note('La clé est stockée dans le fichier de configuration privé de Jarvis, jamais affichée dans les journaux.');layout.addWidget(self.status)
        layout.addWidget(push('Fermer',self.close))
    def key(self):
        from PySide6.QtWidgets import QLineEdit
        value,ok=QInputDialog.getText(self,'Clé Gemini','Clé API Gemini :',QLineEdit.EchoMode.Password)
        if not ok:return
        from jarvis.desktop.setup_config import save_api_key
        try:
            save_api_key(value)
            self.status.setText('Clé enregistrée. Écoutez un aperçu pour vérifier la connexion à Gemini.')
        except ValueError:self.status.setText('Format de clé invalide.')
        except OSError:self.status.setText('Impossible d’enregistrer la configuration privée.')
    def permissions(self):
        from jarvis.desktop.onboarding import make_onboarding_dialog
        self.e.show_dialog('permissions',make_onboarding_dialog(self.e.shell.settings,parent=self))


class ScreenQuestion(QDialog):
    def __init__(self,experience,parent=None):
        super().__init__(parent);self.e=experience;self.setWindowTitle('Comprendre votre fenêtre');self.resize(560,350)
        layout=QVBoxLayout(self)
        layout.addWidget(note('Une capture ponctuelle de l’application choisie sera envoyée à Gemini. Aucun suivi continu de l’écran.'))
        form=QFormLayout();self.app=QLineEdit(experience.last_application);self.app.setPlaceholderText('Safari, Terminal, Notes…')
        self.question=QLineEdit();self.question.setPlaceholderText('Résume cette page / explique cette erreur…')
        form.addRow('Application à analyser',self.app);form.addRow('Votre question',self.question);layout.addLayout(form)
        layout.addWidget(push('Analyser cette fenêtre',self.launch));self.status=note('Choisissez l’application qui contient le contexte, puis votre question.');layout.addWidget(self.status)
        layout.addWidget(push('Fermer',self.close))
    def launch(self):
        if not self.app.text().strip() or not self.question.text().strip():self.status.setText('Renseignez une application et une question.');return
        if not self.e.ready():self.status.setText('Démarrez le vocal avant cette analyse.');return
        import os
        os.environ['JARVIS_VISION_ENABLED']='1'
        if self.e.submit('ask_about_screen',{'question':self.question.text().strip()[:500], 'target':'window','app_name':self.app.text().strip()[:180]}):self.status.setText('Analyse demandée · consultez les cartes de Jarvis.')
