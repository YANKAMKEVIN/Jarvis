"""Validated, persistent presentation choices for the compact companion."""
from dataclasses import dataclass

ANCHORS = ('free','bottom_right','bottom_left','top_right','top_left')

@dataclass
class CompanionPreferences:
    size: int = 320
    opacity: float = 1.0
    anchor: str = 'free'
    quiet: bool = False
    bubbles: bool = True

    @classmethod
    def load(cls, settings):
        def number(key, default, choices):
            try:
                value = float(settings.value('companion/'+key,default))
                return value if value in choices else default
            except (TypeError,ValueError): return default
        def flag(key, default):
            return settings.value('companion/'+key,default) in (True,'true',1)
        anchor = settings.value('companion/anchor','free')
        return cls(int(number('size',320,(240,320,400))),number('opacity',1.,(.65,.85,1.)),
                   anchor if anchor in ANCHORS else 'free',flag('quiet',False),flag('bubbles',True))

    def save(self, settings):
        for key in ('size','opacity','anchor','quiet','bubbles'):
            settings.setValue('companion/'+key,getattr(self,key))
