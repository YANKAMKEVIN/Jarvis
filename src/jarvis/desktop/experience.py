"""Desktop experience coordinator. All external work stays behind guarded tools."""
from datetime import datetime
import json
import re
import time
from collections import deque
from pathlib import Path
from PySide6.QtCore import QObject,QEvent,QTimer,Qt
from PySide6.QtGui import QColor,QKeySequence,QShortcut,QAccessible,QAccessibleAnnouncementEvent
from PySide6.QtWidgets import QDialog,QPushButton,QInputDialog,QMessageBox
from jarvis.desktop.experience_core import ExperienceOptions,TONES,DETAILS
from jarvis.desktop.experience_storage import load_triggers,due_triggers


class Experience(QObject):
    def __init__(self,shell):
        super().__init__(shell.controller);self.shell=shell;self.c=shell.controller;self.app=shell.app
        previous=getattr(shell.app,"_jarvis_experience",None)
        if previous:previous.close()
        shell.app._jarvis_experience=self
        self.closed=False
        self.options=ExperienceOptions.load(shell.settings);self.dialogs={};self.pending=deque(maxlen=10)
        self.last_application="";self.application_fired={}
        from jarvis.desktop.application_context import ApplicationContext
        self.context=ApplicationContext(self)
        self.context.activated.connect(lambda name:setattr(self,"last_application",name))
        self.context.launched.connect(self.application_launched)
        self.previous_apps=None;self.pumping=False;self.last_announcement=''
        from jarvis.desktop.app import STYLE
        self.base_style=STYLE;self.shortcuts=[]
        self.timer=QTimer(self);self.timer.setInterval(10000);self.timer.timeout.connect(self.check_triggers)
        self.drop_targets=[]
        for window in (shell.full,shell.compact,shell.orb_window):
            for key in ('Ctrl+K',):
                shortcut=QShortcut(QKeySequence(key),window);shortcut.activated.connect(self.palette);self.shortcuts.append(shortcut)
            targets=[window,window.assistant.orb if hasattr(window.assistant,'orb') else window.orb]
            for target in targets:
                target.setAcceptDrops(True);self.drop_targets.append(target)
        self.c.changed.connect(self.render);shell.app.installEventFilter(self)
        shell.app.aboutToQuit.connect(self.close);self.reload_triggers();self.apply_theme();self.render()
        if not self.c.demo and shell.app.platformName() != "offscreen":self.context.start()
    def close(self):
        if self.closed:return
        self.closed=True
        self.context.close()
        self.timer.stop();self.app.removeEventFilter(self)
        for dialog in self.dialogs.values():
            try:dialog.close()
            except RuntimeError:pass
    def ready(self):
        return not self.c.demo and self.c.voice_worker is not None and self.c.voice_state in {'listening','thinking','speaking','muted'}
    def submit(self,tool,arguments):
        if not self.ready():self.status('Démarrez le vocal pour lancer cette action.');return False
        if not hasattr(self.c.voice_worker,'request_action'):self.status('Cette session doit être redémarrée pour utiliser les nouvelles commandes.');return False
        accepted=self.c.voice_worker.request_action(tool,arguments)
        self.status('Demande transmise · suivez l’activité.' if accepted is not False else 'La file de commandes est pleine. Réessayez après la tâche en cours.')
        return accepted is not False
    def status(self,text):
        self.c.request_status=text;self.c.changed.emit()
    def set_option(self,key,value):
        if not hasattr(self.options,key):return
        setattr(self.options,key,value);self.options.validated().save(self.shell.settings)
        if self.c.voice_worker and hasattr(self.c.voice_worker,'set_profile'):self.c.voice_worker.set_profile(self.options.profile())
        if key in {'theme','font_size'}:self.apply_theme()
        self.c.changed.emit()
    def clear_replies(self):self.c.quiet_replies.clear();self.c.changed.emit()
    def commands(self):
        return [
            ('Mon briefing personnalisé',self.briefing),('Comprendre la fenêtre active',self.screen),
            ('Résumer un document…',self.pick_document),('Mes routines',self.shell.show_routines),
            ('Mémoire et préférences retenues',self.memory),('Missions et procédures',self.history),
            ('Déclencheurs de routines',self.triggers),('Voix des avatars',self.shell.show_voices),
            ('Apparence du compagnon',self.shell.show_appearances),('Bien démarrer avec Jarvis',self.setup),
            ('Préférences et réponses écrites',self.open),('Demander une mission…',self.task),
            ('Annuler une action réversible…',self.undo),('Démarrer le vocal',self.c.start_voice),
            ('Arrêter le vocal',self.c.stop_voice),('Réglages audio',self.shell.show_settings),
            ('Faire danser le compagnon',self.c.dance.start),('Ouvrir Jarvis',self.shell.show_full),
        ]
    def show_dialog(self,key,dialog):
        old=self.dialogs.get(key)
        if old:old.close();old.deleteLater()
        self.dialogs[key]=dialog;dialog.show();dialog.raise_();return dialog
    def open(self):
        from jarvis.desktop.experience_ui import ExperienceDialog
        return self.show_dialog('experience',ExperienceDialog(self,self.shell.visible_window()))
    def palette(self):
        from jarvis.desktop.experience_ui import CommandPalette
        return self.show_dialog('palette',CommandPalette(self,self.shell.visible_window()))
    def setup(self):
        from jarvis.desktop.experience_ui import SetupGuide
        dialog=SetupGuide(self,self.shell.visible_window())
        dialog.finished.connect(lambda: self.shell.settings.setValue("experience/setup_seen",True))
        return self.show_dialog("setup",dialog)
    def memory(self):
        from jarvis.desktop.memory_editor import MemoryEditor
        return self.show_dialog('memory',MemoryEditor(self.shell.visible_window()))
    def history(self):
        from jarvis.desktop.history_dialog import HistoryDialog
        return self.show_dialog('history',HistoryDialog(self,self.shell.visible_window()))
    def triggers(self):
        from jarvis.desktop.experience_ui import TriggerDialog
        return self.show_dialog('triggers',TriggerDialog(self,self.shell.visible_window()))
    def briefing(self):
        detail={'short':'en cinq points maximum','normal':'avec les points importants','detailed':'avec les horaires et priorités détaillés'}[self.options.detail]
        return self.submit('run_task',{'goal':f'Prépare mon briefing du jour {detail}. Sujets souhaités : {self.options.briefing}. Lis les sources nécessaires, distingue les indisponibilités. Ne crée, ne modifie et n’envoie rien.','read_only':True})
    def screen(self):
        from jarvis.desktop.experience_ui import ScreenQuestion
        self.show_dialog('screen',ScreenQuestion(self,self.shell.visible_window()))
    def task(self):
        goal,ok=QInputDialog.getText(self.shell.visible_window(),'Nouvelle mission','Quel objectif souhaitez-vous confier à Jarvis ?')
        if ok and goal.strip():self.submit('run_task',{'goal':goal.strip()[:1000]})
    def pick_document(self):
        from PySide6.QtWidgets import QFileDialog
        paths,_=QFileDialog.getOpenFileNames(self.shell.visible_window(),'Choisir un ou deux documents','','Documents (*.txt *.md *.pdf *.docx *.csv *.json *.log)')
        if paths:
            from PySide6.QtCore import QUrl
            self.drop([QUrl.fromLocalFile(p) for p in paths])
    def drop(self,urls):
        from jarvis.desktop.document_drop import dropped_files,DocumentDropDialog
        try:self.show_dialog('document',DocumentDropDialog(self,dropped_files(urls),self.shell.visible_window()))
        except (ValueError,OSError) as error:self.status(str(error))
    def undo(self):
        rows=self.c.undo_tickets
        if not rows:self.status('Aucune action réversible vérifiée dans cette session.');return
        labels=[str(i+1)+'. '+r['label'] for i,r in enumerate(rows)]
        label,ok=QInputDialog.getItem(self.shell.visible_window(),'Annuler une action','Action à rétablir :',labels,0,False)
        if not ok:return
        row=rows[labels.index(label)]
        box=QMessageBox(self.shell.visible_window());box.setWindowTitle('Annuler cette action ?');box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(row['source']+'\n→ '+row['destination']+'\n\n'+('Seul ce rappel sera annulé.' if row.get('kind')=='reminder' else 'Aucun fichier existant ne sera remplacé.'))
        box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        if box.exec()==QMessageBox.StandardButton.Yes:self.submit('undo',{'id':row['id']})
    def configure(self,event):
        receipt=event.get('receipt')
        if receipt is None or receipt.cancelled():return
        try:
            from jarvis.desktop.appearances import BY_ID
            from jarvis.desktop.voices import VOICE_IDS
            normalize=lambda value:re.sub(r'[\W_]+','',value.casefold())
            aliases={normalize(value):a.id for a in BY_ID.values() for value in (a.name,a.id)}
            appearance=event.get('appearance','');voice=event.get('voice','');tone=event.get('tone','');detail=event.get('detail','');quiet=event.get('quiet')
            choose_appearance=appearance=='choose';choose_voice=voice=='choose'
            if choose_appearance:appearance=''
            if choose_voice:voice=''
            if appearance:appearance=aliases.get(normalize(appearance),appearance)
            if voice:voice={v.casefold():v for v in VOICE_IDS}.get(voice.casefold(),voice)
            if appearance and appearance not in BY_ID:raise ValueError('Apparence inconnue.')
            if voice and voice not in VOICE_IDS:raise ValueError('Voix inconnue.')
            if tone and tone not in TONES:raise ValueError('Ton inconnu.')
            if detail and detail not in DETAILS:raise ValueError('Longueur de réponse inconnue.')
            if quiet is not None and not isinstance(quiet,bool):raise ValueError('Mode discret invalide.')
            if receipt.cancelled():return
            if appearance:self.shell.set_appearance(appearance)
            if voice:self.shell.set_avatar_voice(self.c.appearance,voice)
            if tone:self.set_option('tone',tone)
            if detail:self.set_option('detail',detail)
            if quiet is not None:self.set_option('quiet',quiet)
            if choose_appearance:self.shell.show_appearances()
            if choose_voice:self.shell.show_voices()
            if not receipt.done():receipt.set_result({'ok':True,'message':('Sélecteur ouvert ; choisissez une option.' if choose_appearance or choose_voice else 'Réglages appliqués. La voix change à la prochaine connexion.'),'voice':self.c.selected_voice,'quiet':self.options.quiet})
        except (ValueError,TypeError,AttributeError) as error:
            if not receipt.done():receipt.set_result({'ok':False,'message':str(error)})
    def reload_triggers(self):
        self.rows=load_triggers(self.shell.settings)
        enabled={row['id'] for row in self.rows if row.get('enabled')}
        self.pending=deque((item for item in self.pending if item[1]['id'] in enabled),maxlen=10)
        if any(row.get('enabled') for row in self.rows) and not self.c.demo:self.timer.start()
        else:self.timer.stop()
    def applications(self):
        try:
            from AppKit import NSWorkspace
            result=set()
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                for value in (app.localizedName(),app.bundleIdentifier()):
                    if value:result.add(str(value).casefold().removesuffix('.app'))
            return result
        except ImportError:return set()
    def application_launched(self,names):
        if self.closed:return
        self.queue_triggers(datetime.now().astimezone(),set(names))
        if self.previous_apps is not None:self.previous_apps.update(names)
        self.pump()
    def queue_triggers(self,now,launched):
        for row in due_triggers(self.rows,now,launched):
            if row['kind']=='application':
                if time.monotonic()-self.application_fired.get(row['id'],-1000)<30:continue
                self.application_fired[row['id']]=time.monotonic()
            if len(self.pending)>=10:
                self.c.notice.emit({'key':'trigger-full:'+row['id'],'text':'Routine non lancée : la file d’attente est pleine.','destination':'experience'});continue
            self.pending.append((time.monotonic(),row))
            self.c.notice.emit({'key':'trigger:'+row['id']+':'+now.strftime('%Y%m%d%H%M'),'text':'Routine prête : '+row['routine'],'destination':'experience'})
        self.shell.settings.setValue('experience/triggers',json.dumps(self.rows))
    def check_triggers(self,now=None,applications=None):
        now=now or datetime.now().astimezone();apps=self.applications() if applications is None else applications
        launched=set() if self.previous_apps is None else apps-self.previous_apps;self.previous_apps=set(apps)
        self.queue_triggers(now,launched)
        self.pump()
    def pump(self):
        if self.pumping:return
        self.pumping=True
        try:
            while self.pending and time.monotonic()-self.pending[0][0]>600:
                _,expired=self.pending.popleft()
                self.c.notice.emit({'key':'trigger-expired:'+expired['id'],'text':'Routine non lancée : le délai d’attente de dix minutes a expiré.','destination':'experience'})
            if self.pending and self.ready() and self.c.voice_state=='listening' and not self.c.input_suppressed and not self.c.ptt_held:
                _,row=self.pending.popleft();self.submit('run_macro',{'name':row['routine']})
        finally:self.pumping=False
    def transform_style(self,style):
        if self.options.theme=='night':result=style
        else:
            def color(match):
                c=QColor(match.group());light=c.lightnessF()
                if self.options.theme=='contrast':return '#ffffff' if light>.45 else '#777777' if light>.25 else '#000000'
                return '#f2e3d4' if light>.65 else '#e0b68d' if light>.45 else '#785c53' if light>.25 else '#211b20' if light>.09 else '#130f12'
            result=re.sub(r'#[0-9a-fA-F]{6}\b',color,style)
        delta=self.options.font_size-13
        if delta:result=re.sub(r'font-size:\s*(\d+)px',lambda m:'font-size: '+str(int(m.group(1))+delta)+'px',result)
        return result
    def apply_theme(self):
        style=self.transform_style(self.base_style)
        if self.app.styleSheet()!=style:self.app.setStyleSheet(style)
        roots=(self.shell.full,self.shell.compact,self.shell.orb_window,*self.dialogs.values())
        from PySide6.QtWidgets import QWidget
        widgets=[]
        for root in roots:
            try:widgets.extend([root,*root.findChildren(QWidget)])
            except RuntimeError:continue
        for widget in widgets:
            if widget is self.shell.compact or widget is self.shell.orb_window:continue
            if not hasattr(widget,'_jarvis_base_style'):widget._jarvis_base_style=widget.styleSheet()
            if widget._jarvis_base_style:
                style=self.transform_style(widget._jarvis_base_style)
                if widget.styleSheet()!=style:widget.setStyleSheet(style)
    def style_dialog(self,dialog):
        if not hasattr(dialog,'_jarvis_base_style'):dialog._jarvis_base_style=dialog.styleSheet() or 'QDialog {background:#0d1c2b;}'
        style=self.transform_style(dialog._jarvis_base_style)
        if dialog.styleSheet()!=style:dialog.setStyleSheet(style)
        for button in dialog.findChildren(QPushButton):
            if not button.accessibleName():button.setAccessibleName(button.text().replace('&',''))
    def render(self):
        if self.closed:return
        for window in (self.shell.full,self.shell.compact,self.shell.orb_window):
            orb=window.assistant.orb if hasattr(window.assistant,'orb') else window.orb
            orb.tracking=self.options.tracking;orb.articulated=self.options.articulated
        message=self.c.request_status
        if message and message!=self.last_announcement:
            self.last_announcement=message
            QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.shell.visible_window(),message))
        self.pump()
    def eventFilter(self,watched,event):
        if self.closed:return False
        kind=event.type()
        if kind==QEvent.Type.Show and isinstance(watched,QDialog):self.style_dialog(watched)
        if watched in self.drop_targets:
            if kind in {QEvent.Type.DragEnter,QEvent.Type.DragMove} and event.mimeData().hasUrls():event.acceptProposedAction();return True
            if kind==QEvent.Type.Drop and event.mimeData().hasUrls():self.drop(event.mimeData().urls());event.acceptProposedAction();return True
        return False
