"""Local audio device identities and PCM helpers; no SDK or Qt imports."""
from array import array
from math import pi, sin, sqrt

RATE = 24000


class AudioDeviceError(Exception):
    """Only safe application-owned messages, never PortAudio exception payloads."""


def pcm_level(data):
    samples = array('h')
    samples.frombytes(data)
    return sqrt(sum(value * value for value in samples) / len(samples)) / 32768 if samples else 0.0


def valid_choice(value):
    return (isinstance(value, dict) and set(value) == {'name', 'hostapi'}
            and all(isinstance(v, str) and 0 < len(v) <= 300 for v in value.values()))


def catalog(devices):
    try:
        hosts = devices.query_hostapis()
        rows = devices.query_devices()
        entries = []
        for index, row in enumerate(rows):
            host = str(hosts[row['hostapi']]['name'])
            entries.append({'index': index, 'choice': {'name': str(row['name']), 'hostapi': host},
                            'input': row['max_input_channels'] > 0, 'output': row['max_output_channels'] > 0})
        return entries
    except Exception:
        raise AudioDeviceError('Impossible de lire les périphériques audio. Vérifiez leur connexion puis actualisez.') from None


def resolve_device(devices, choice, direction):
    if direction not in {'input', 'output'}:
        raise ValueError('Invalid audio direction')
    index = None
    if choice is not None:
        if not valid_choice(choice):
            raise AudioDeviceError('Le choix audio enregistré est invalide. Sélectionnez un périphérique dans Réglages.')
        matches = [row for row in catalog(devices) if row[direction] and row['choice'] == choice]
        if not matches:
            raise AudioDeviceError('Le périphérique choisi est déconnecté ou indisponible. Actualisez les périphériques dans Réglages.')
        if len(matches) != 1:
            raise AudioDeviceError('Plusieurs périphériques portent le même nom. Renommez-les dans macOS ou choisissez le périphérique système par défaut.')
        index = matches[0]['index']
    try:
        check = devices.check_input_settings if direction == 'input' else devices.check_output_settings
        check(device=index, samplerate=RATE, channels=1, dtype='int16')
    except Exception:
        raise AudioDeviceError('Le périphérique audio ne prend pas en charge ce format vocal. Essayez un autre périphérique dans Réglages.') from None
    return index


def test_tone():
    samples = array('h')
    count = int(RATE * 0.15)
    for frequency in (660, 880):
        for index in range(count):
            samples.append(int(1800 * sin(pi * index / count) ** 2 * sin(2 * pi * frequency * index / RATE)))
    return samples.tobytes()
