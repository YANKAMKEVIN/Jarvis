"""Documentation media stay light and every referenced image exists (idea 24)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_ANIMATION_BYTES = 5 * 1024 * 1024


def test_no_gif_and_animations_stay_small():
    assert not list((ROOT / "docs").rglob("*.gif")), "use an animated WebP instead of a GIF"
    for path in (ROOT / "docs").rglob("*.webp"):
        assert path.stat().st_size <= MAX_ANIMATION_BYTES, path


def test_markdown_image_and_media_links_resolve():
    for page in list((ROOT / "docs").rglob("*.md")) + [ROOT / "README.md"]:
        for target in re.findall(r"\]\(([^)\s]+\.(?:png|webp|gif|mp4))\)", page.read_text()):
            assert (page.parent / target).is_file(), f"{page.name}: {target}"
