"""Desktop voice palette and independent, persistent per-appearance assignments."""
from dataclasses import dataclass
from jarvis.desktop.appearances import CATALOG, valid_appearance


@dataclass(frozen=True)
class Voice:
    id: str
    description: str


VOICES = (
    Voice('Puck', 'Enjouée'),
    Voice('Kore', 'Ferme'),
    Voice('Charon', 'Informative'),
    Voice('Aoede', 'Légère'),
    Voice('Fenrir', 'Expressive'),
    Voice('Zephyr', 'Lumineuse'),
    Voice('Leda', 'Juvénile'),
    Voice('Orus', 'Ferme'),
    Voice('Callirrhoe', 'Décontractée'),
    Voice('Autonoe', 'Lumineuse'),
    Voice('Enceladus', 'Soufflée'),
    Voice('Iapetus', 'Claire'),
    Voice('Umbriel', 'Décontractée'),
    Voice('Algieba', 'Fluide'),
    Voice('Despina', 'Fluide'),
    Voice('Erinome', 'Claire'),
    Voice('Algenib', 'Rocailleuse'),
    Voice('Rasalgethi', 'Informative'),
    Voice('Laomedeia', 'Enjouée'),
    Voice('Achernar', 'Douce'),
    Voice('Alnilam', 'Ferme'),
    Voice('Schedar', 'Régulière'),
    Voice('Gacrux', 'Mature'),
    Voice('Pulcherrima', 'Affirmée'),
    Voice('Achird', 'Amicale'),
    Voice('Zubenelgenubi', 'Décontractée'),
    Voice('Vindemiatrix', 'Délicate'),
    Voice('Sadachbia', 'Vive'),
    Voice('Sadaltager', 'Érudite'),
    Voice('Sulafat', 'Chaleureuse'),
)
VOICE_IDS = frozenset(voice.id for voice in VOICES)
# Initial assignments are deliberately shared. Saving one avatar never edits another.
DEFAULT_VOICES = dict(zip((a.id for a in CATALOG), (
    'Puck', 'Kore', 'Aoede', 'Charon', 'Fenrir', 'Aoede',
    'Charon', 'Aoede', 'Kore', 'Charon', 'Puck', 'Fenrir',
    'Fenrir', 'Kore', 'Charon', 'Puck',
)))


class VoicePreferences:
    def __init__(self, settings):
        self.settings = settings

    def load(self, appearance):
        appearance = valid_appearance(appearance)
        value = self.settings.value(f'voice/avatars/{appearance}')
        return value if isinstance(value, str) and value in VOICE_IDS else DEFAULT_VOICES[appearance]

    def save(self, appearance, voice):
        if appearance not in DEFAULT_VOICES or voice not in VOICE_IDS:
            raise ValueError('Unknown avatar or voice')
        self.settings.setValue(f'voice/avatars/{appearance}', voice)
        return voice

    def reset(self, appearance):
        appearance = valid_appearance(appearance)
        self.settings.remove(f'voice/avatars/{appearance}')
        return self.load(appearance)

    def favorites(self):
        values = self.settings.value('voice/favorites', [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple)):
            return frozenset()
        return frozenset(value for value in values if isinstance(value, str) and value in VOICE_IDS)

    def set_favorite(self, voice, enabled):
        if voice not in VOICE_IDS:
            raise ValueError('Unknown voice')
        values = set(self.favorites())
        values.add(voice) if enabled else values.discard(voice)
        self.settings.setValue('voice/favorites', sorted(values))
