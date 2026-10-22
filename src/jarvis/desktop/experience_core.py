"""Validated product preferences, progress hints and reversible-file receipts."""
from dataclasses import dataclass, fields
from pathlib import Path
import time
import uuid

TONES = {'balanced': 'Adopte un ton naturel et direct.', 'warm': 'Adopte un ton chaleureux, sans flatterie.', 'playful': 'Adopte un ton leger et joueur, sans nuire a la precision.'}
DETAILS = {'short': 'Reponds en une ou deux phrases quand cela suffit.', 'normal': 'Adapte le niveau de detail a la demande.', 'detailed': 'Explique le raisonnement utile et les resultats, sans raconter chaque clic.'}

@dataclass
class ExperienceOptions:
    tone: str = 'balanced'
    detail: str = 'normal'
    initiative: str = 'reactive'
    quiet: bool = False
    headphones: bool = False
    history: bool = False
    tracking: bool = True
    articulated: bool = False
    theme: str = 'night'
    font_size: int = 13
    briefing: str = 'Agenda, rappels et priorités du jour'

    @classmethod
    def load(cls, settings):
        result = cls()
        for field in fields(result):
            value = settings.value('experience/'+field.name, getattr(result, field.name))
            if isinstance(getattr(result, field.name), bool):
                value = value in (True, 'true', 1)
            if field.name == 'font_size':
                try: value = int(value)
                except (ValueError, TypeError): value = 13
            setattr(result, field.name, value)
        return result.validated()

    def validated(self):
        if not isinstance(self.tone,str) or self.tone not in TONES: self.tone = 'balanced'
        if not isinstance(self.detail,str) or self.detail not in DETAILS: self.detail = 'normal'
        if not isinstance(self.initiative,str) or self.initiative not in {'reactive','suggest'}: self.initiative = 'reactive'
        if not isinstance(self.theme,str) or self.theme not in {'night','dawn','contrast'}: self.theme = 'night'
        if not isinstance(self.font_size,int) or self.font_size not in {13,15,17}: self.font_size = 13
        if not isinstance(self.briefing,str): self.briefing = 'Agenda, rappels et priorités du jour'
        self.briefing = self.briefing.strip()[:180]
        return self

    def save(self, settings):
        self.validated()
        for field in fields(self): settings.setValue('experience/'+field.name, getattr(self,field.name))

    def profile(self):
        return {'tone':self.tone,'detail':self.detail,'initiative':self.initiative,
                'quiet':self.quiet,'headphones':self.headphones,'history':self.history}


def profile_instructions(profile):
    tone = TONES.get(profile.get('tone'), TONES['balanced'])
    detail = DETAILS.get(profile.get('detail'), DETAILS['normal'])
    initiative = ('Tu peux suggerer une prochaine etape pertinente, sans l executer sans demande.'
                  if profile.get('initiative') == 'suggest' else 'Reste concentre sur la demande, sans proposer systematiquement de suite.')
    quiet = 'Une reponse ecrite sera affichee; ne suppose pas que le haut-parleur est audible.' if profile.get('quiet') else ''
    return '\n'.join((tone,detail,initiative,quiet))


class TurnProgress:
    def __init__(self, clock=time.monotonic):
        self.clock=clock; self.pending=None; self.warned=False
    def received(self):
        self.pending=self.clock();self.warned=False
        return {'type':'request_progress','stage':'received','message':'Demande reçue'}
    def response(self): self.pending=None;self.warned=False
    def poll(self, agent, user, suppressed=False):
        if self.pending is None or self.warned or user=='speaking' or suppressed: return None
        if agent in {'thinking','speaking'}: self.response();return None
        if self.clock()-self.pending>=10:
            self.warned=True
            return {'type':'request_progress','stage':'waiting','message':'Réponse attendue · consultez l’activité ou reconnectez le vocal si le délai persiste.'}
        return None


class UndoLedger:
    """Session-only inverses, only for unchanged regular files with verified moves."""
    def __init__(self): self.tickets={};self.undoing=False
    @staticmethod
    def fingerprint(path):
        p=Path(path)
        if p.is_symlink() or not p.is_file(): raise ValueError('Fichier non réversible')
        s=p.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    def record(self, tool, result):
        if not self.undoing and tool=='set_reminder' and isinstance(result,dict) and result.get('ok') is True:
            identifier,due=result.get('reminder_id'),result.get('due_at')
            if type(identifier) is int and isinstance(due,(int,float)) and due>time.time()+5:
                token=uuid.uuid4().hex
                self.tickets[token]={'id':token,'kind':'reminder','reminder_id':identifier,'due_at':due,'recurrence':result.get('recurrence','none')}
                while len(self.tickets)>10:self.tickets.pop(next(iter(self.tickets)))
            return
        if self.undoing or tool not in {'move_file','rename_file'} or not isinstance(result,dict):return
        if result.get('ok') is not True or result.get('state_confirmed') is not True:return
        old,new=result.get('previous_path'),result.get('path')
        if not all(isinstance(p,str) and Path(p).is_absolute() for p in (old,new)) or old==new:return
        try: fingerprint=self.fingerprint(new)
        except (ValueError,OSError):return
        ticket={'id':uuid.uuid4().hex,'kind':'file','old':old,'new':new,'fingerprint':fingerprint}
        self.tickets[ticket['id']]=ticket
        while len(self.tickets)>10:self.tickets.pop(next(iter(self.tickets)))
    def summaries(self):
        rows=[]
        for t in reversed(list(self.tickets.values())):
            if t.get('kind')=='reminder':rows.append({'id':t['id'],'kind':'reminder','label':'Annuler le rappel créé n°'+str(t['reminder_id']),'source':'Rappel créé dans cette session','destination':'Annuler ce rappel uniquement'})
            else:rows.append({'id':t['id'],'kind':'file','label':'Rétablir '+Path(t['new']).name,'source':t['new'],'destination':t['old']})
        return rows
    def validate(self, ticket_id):
        t=self.tickets.get(ticket_id)
        if not t:raise ValueError('Cette annulation n’est plus disponible.')
        if t.get('kind')=='reminder':return t
        if Path(t['old']).exists() or Path(t['old']).is_symlink():raise ValueError('Le chemin d’origine est occupé. Aucun fichier remplacé.')
        try: current=self.fingerprint(t['new'])
        except (OSError,ValueError):raise ValueError('Le fichier a disparu ou changé. Annulation refusée.') from None
        if current!=t['fingerprint']:raise ValueError('Le fichier a été modifié. Annulation refusée.')
        return t


ACTION_LABELS={
    'open_app':'Ouvrir une application','close_app':'Fermer une application',
    'run_task':'Organiser la demande en mission','run_macro':'Lancer la routine demandée',
    'morning_briefing':'Préparer le briefing','ask_about_screen':'Analyser la fenêtre demandée',
    'describe_screen':'Décrire la fenêtre demandée','ask_about_document':'Analyser le document',
    'compare_documents':'Comparer les documents','extract_document_actions':'Extraire les tâches du document',
    'move_file':'Déplacer un fichier','rename_file':'Renommer un fichier',
    'set_reminder':'Créer le rappel demandé','search_the_web':'Chercher sur le web',
    'save_task_procedure':'Mémoriser la procédure demandée','run_procedure':'Adapter la procédure demandée',
}

class DesktopActionError(ValueError):
    """Only application-owned public messages may use this exception."""
