"""Decode approved WebPs once; preserve aspect ratio and explicit atlas cells."""
from functools import lru_cache
from importlib.resources import files
from PySide6.QtGui import QImage
from jarvis.desktop.appearances import BY_ID, valid_appearance

@lru_cache(maxsize=64)
def pose_image(appearance, state='listening'):
    appearance = valid_appearance(appearance)
    path = files('jarvis.desktop').joinpath('assets', 'avatars', appearance + '.webp')
    image = QImage.fromData(path.read_bytes(), 'WEBP')
    if image.isNull():
        raise ValueError(f'Cannot decode avatar: {appearance}')
    if BY_ID[appearance].atlas:
        column, row = {'thinking': (1, 0), 'speaking': (0, 1), 'success': (1, 1)}.get(state, (0, 0))
        w, h = image.width() // 2, image.height() // 2
        image = image.copy(column * w, row * h, w, h)
    return image
