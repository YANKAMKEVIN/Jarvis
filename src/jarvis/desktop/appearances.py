"""Appearance metadata is independent of voice sessions and future agent identities."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Appearance:
    id: str
    name: str
    atlas: bool
    accent: str
    motion: str

_NAMES = (
    ('nova_bot', 'NovaBot'), ('neo_guide', 'Neo Guide'), ('kitsune', 'Kitsune'),
    ('digital_avatar', 'Digital Avatar'), ('synth_companion', 'Synth Companion'),
    ('holo_face', 'Holo Face'), ('orbital_atlas', 'Orbital Atlas'),
    ('aurora_light', 'Aura Light'), ('liquid_chrome', 'Liquid Chrome'),
    ('vector_grid', 'Vector Grid'), ('prism_core', 'Prism Core'),
    ('event_horizon', 'Event Horizon'), ('solar_forge', 'Solar Forge'),
    ('command_deck', 'Command Deck'), ('neural_entity', 'Neural Entity'),
    ('arc_reactor', 'Arc Reactor'),
)
CATALOG = tuple(Appearance(key, name, i < 6,
    ('#85e7ff', '#bda6ff', '#ffce88', '#85e7ff')[i % 4],
    'float' if i < 6 else ('orbit', 'breathe', 'flow')[i % 3])
    for i, (key, name) in enumerate(_NAMES))
BY_ID = {item.id: item for item in CATALOG}
DEFAULT = 'nova_bot'

def valid_appearance(value):
    return value if isinstance(value, str) and value in BY_ID else DEFAULT

class AppearancePreference:
    def __init__(self, settings):
        self.settings = settings
    def load(self):
        return valid_appearance(self.settings.value('appearance/avatar', DEFAULT))
    def save(self, value):
        value = valid_appearance(value)
        self.settings.setValue('appearance/avatar', value)
        return value
