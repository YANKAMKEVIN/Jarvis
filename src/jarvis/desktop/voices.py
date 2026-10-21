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
