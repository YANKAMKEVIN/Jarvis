"""Small private settings-based schedules; no microphone or task replay on startup."""
import json
import uuid
from datetime import datetime


def load_triggers(settings):
    try: values=json.loads(settings.value('experience/triggers','[]'))
    except (ValueError,TypeError):return []
    if not isinstance(values,list):return []
    return [row for row in values[:50] if isinstance(row,dict) and
            isinstance(row.get('id'),str) and isinstance(row.get('routine'),str) and
            isinstance(row.get('kind'),str) and row['kind'] in {'time','application'} and isinstance(row.get('value'),str)]


def save_trigger(settings, routine, kind, value):
    routine,value=routine.strip(),value.strip()
    if not routine or len(routine)>80 or not value or len(value)>180:raise ValueError('Routine ou déclencheur invalide.')
    if kind=='time':
        try: datetime.strptime(value,'%H:%M')
        except ValueError:raise ValueError('Utilisez une heure locale HH:MM.') from None
        value=datetime.strptime(value,'%H:%M').strftime('%H:%M')
    elif kind!='application':raise ValueError('Déclencheur inconnu.')
    rows=load_triggers(settings)
    if len(rows)>=50:raise ValueError('Limite de 50 déclencheurs atteinte.')
    row={'id':uuid.uuid4().hex,'routine':routine,'kind':kind,'value':value,'enabled':True,'last':''}
    rows.append(row);settings.setValue('experience/triggers',json.dumps(rows));return row


def due_triggers(rows, now, launched):
    result=[]
    for row in rows:
        if row.get('enabled') is not True:continue
        if row['kind']=='time':
            marker=now.strftime('%Y-%m-%d')
            due=now.strftime('%H:%M')==row['value']
        else:
            marker=None
            due=row['value'].casefold().removesuffix('.app') in launched
        if due and (marker is None or row.get('last')!=marker):
            if marker:row['last']=marker
            result.append(dict(row))
    return result
