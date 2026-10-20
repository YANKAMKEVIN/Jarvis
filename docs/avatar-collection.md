# Avatar collection

The `feat/avatar-collection` branch uses the approved artwork from commit
`5d9c7e8fc6f0c23d7c56d52c195d1380f9b1e33d`. No generated replacement artwork
is used. The 16 references and 16 transparent WebPs were verified after fetching
GitHub. The six character assets are 1254 × 1254 atlases with listening,
thinking, speaking and success in reading order. Abstract assets are single
images; Event Horizon is 1774 × 887 and retains its aspect ratio.

NovaBot is the default. The Appearance button opens a native icon grid with all
16 names and previews. Click, Space or Return applies the focused choice
immediately; arrows navigate and Escape closes. The floating companion offers
Appearance in its context menu. QSettings stores `appearance/avatar`; missing or
invalid preferences fall back to NovaBot.

`appearances.py` defines identity and presentation metadata independently of
agents. `avatar_assets.py` caches decoded images and extracts atlas cells.
`visuals.py` renders the existing `Orb` widget API with artwork, eased state
colors, pose/appearance fades, floating, breathing and gentle movement.
`avatar_selector.py` owns the picker; `AppearancePreference` owns persistence.
The controller supplies one appearance to full, compact and floating views.
Changing appearance does not replace the controller, voice worker or missions.

Audio animation uses the existing RMS signal only. Motion reduction renders a
still, current-state image; hidden widgets stop their animation timers. Confirmed
activity and completed missions produce a temporary success reaction; errors
produce an error accent. Idle and error reuse the listening artwork because the
atlases provide four poses. These are 2D transformations and crossfades, with no
3D rig or lip synchronization.

## Validation

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_desktop*.py -q
```

156 desktop tests passed, including 51 avatar checks and the existing two-mission
cancellation/cycling tests. Coverage includes default and invalid preferences,
on-disk persistence, all assets/poses, immediate changes preserving two missions
and the voice worker, all three modes, keyboard activation, reduced motion,
hidden timers, and success/error states. An intermittent PySide6 shutdown crash
was isolated to onboarding dialogs left alive by tests; the fixture now deletes
them while Qt is still running. The desktop suite subsequently exited normally.

A wheel was built with `pip wheel --no-deps .`, installed in an isolated target,
and loaded from that target. All 16 packaged WebPs decoded across six states
(96 loads). Package data is declared explicitly in `pyproject.toml`.

Real Qt widget captures are in [screenshots/avatars](screenshots/avatars/):
NovaBot, selector, Kitsune, Aura Light, two missions, compact and floating modes.
These are offscreen renders of the application in demo mode, not concepts or
composited mockups. The GIF contains 60 captured application frames, with
simulated state/audio events and no microphone capture. Static screenshots use
reduced motion. Reproduce them with:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_avatar_preview.py
# Optional raw animation frames (PNG):
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_avatar_preview.py --animation-frames /tmp/jarvis-frames
```

## Run on macOS Apple Silicon

```sh
cd ~/dev/Jarvis
git fetch origin
git switch feat/avatar-collection
git pull --ff-only origin feat/avatar-collection
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[desktop,live]'
jarvis-desktop --demo
# Other demo modes:
jarvis-desktop --demo --compact
jarvis-desktop --demo --orb
```

On the Mac, verify native window placement/scaling, sustained animation
performance, and microphone/speaker reactions during a real LiveKit/Gemini
session with the configured credentials and permissions. Those live checks were
not performed by the automated demo. Compact mode preserves the existing
one-card mission carousel; full mode shows two independently controlled cards.

## Individual choreography

Each appearance now has its own deterministic motion profile in
`avatar_motion.py`. Motion stays bounded (at most 2% translation, 3.1 degrees
rotation and 5% scale), is audio-reactive through the existing RMS signal, and
uses the same renderer in all three window modes. Reduced motion yields an
exactly neutral transform and omits decorative animation layers.

| Appearance | Motion and decoration |
| --- | --- |
| NovaBot | Levitation, gentle sway, thruster rings |
| Neo Guide | Attentive tilt and side beacons |
| Kitsune | Feline drift and ascending fireflies |
| Digital Avatar | Holographic breathing and vertical scan markers |
| Synth Companion | Mechanical breathing and synchronized segments |
| Holo Face | Slow drift and transmission marks |
| Orbital Atlas | Precession and elliptical satellite paths |
| Aura Light | Soft deformation and aurora arcs |
| Liquid Chrome | Opposing scale waves and moving reflections |
| Vector Grid | Grid breathing and square data packets |
| Prism Core | Crystal oscillation and refracted rays |
| Event Horizon | Slow precession and flattened accretion arcs |
| Solar Forge | Solar pulse and outward embers |
| Command Deck | Stable core and moving navigation reticle |
| Neural Entity | Organic contraction and intermittent connections |
| Arc Reactor | Audio pulse and segmented charge crown |

The comparison [PNG](screenshots/avatars/distinct-motion.png) and
[GIF](screenshots/avatars/distinct-motion.gif) capture the actual Qt avatar
widgets in a gallery. Listening, thinking, speaking and audio levels are
simulated; no microphone or model is started. Capture the PNG frames with:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_avatar_motion.py --frames /tmp/avatar-motion
```

Additional regression checks cover every profile's bounds and audio response,
distinct trajectories, actual moving renders, still reduced-motion renders and
hidden timers for all 16 appearances. Native macOS performance and live audio
remain manual checks.
