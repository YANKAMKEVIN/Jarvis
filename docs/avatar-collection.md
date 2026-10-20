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

182 desktop tests passed, including 72 avatar checks and the existing two-mission
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
not performed by the automated demo. Compact mode now shows the avatar alone with two hover controls; its menu opens
missions in the full view, where two cards remain independently controlled.

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

## Continuous life for abstract appearances

The ten abstract appearances keep breathing and moving while idle, with no voice
worker and no microphone signal. Their existing individual paths and decorations
remain active. A small autonomous heartbeat complements the real audio envelope.

Listening narrows the decorative field and introduces a receptive sway; thinking
adds a circulating gesture and progressively faster motion; speaking expands the
shape rhythmically, with actual RMS levels increasing its expression. Success
opens and slightly lifts the form; error contracts it and brings the decorative
field inward. Every gesture is defined independently of audio, so silent states
remain visibly distinct. The renderer interpolates normalized state weights and
keeps the phase clock running, rather than resetting motion at state boundaries.

Reduced motion still renders a neutral, current-state image. Hidden views still
stop their timer. State and audio continue to come from the same controller in
all three modes. Character choreography and voice/session logic are unchanged.

The new [idle PNG](screenshots/avatars/abstract-idle.png) and
[interaction GIF](screenshots/avatars/abstract-life.gif) capture real Qt widgets;
the GIF covers idle, listening, thinking, speaking, success and error, with
simulated events/audio and no microphone. Reproduce raw frames with:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_avatar_motion.py --abstract --interactions --frames /tmp/abstract-life
```

Tests additionally verify motion at zero-audio idle for all ten abstract forms,
distinct silent interaction trajectories and rendered frames, and progressive
state interpolation. Native macOS fluidity/live audio remain manual checks.

## Avatar-first compact companion

`CompanionWindow` replaces the compact dashboard with a 320 × 340 transparent,
frameless, always-on-top window. The avatar is 320 × 320 and keeps its size even
when missions arrive. There is no permanent title, card, footer or voice dock.
The resting pose has no pedestal. Two 32 px overlay controls appear on hover:
open the full assistant, and open the companion menu. Their appearance never
changes the avatar layout. Leaving hides them; keyboard focus and an open menu
keep them available. Tab/Space/Enter reveal controls; Tab navigates; Escape hides.

Dragging the avatar moves the window and persists its position. Clicking the
avatar alone neither opens the main window nor starts microphone capture. The
menu provides explicit voice start/stop, microphone and interrupt commands,
current capture/error/confirmation status, missions, cards, appearance, settings,
hide and quit. It updates while open and respects demo, reconnection and stopping
states. Status is also available as an avatar tooltip; no transcript is shown.

Session ownership, missions, position restoration, mode transitions, audio
signals and reduced motion continue to use the existing shared controller.
The smaller `--orb` view is preserved. Two simultaneous missions remain visible
and independently cancellable in the full assistant, reached through the menu.

Five new companion tests cover transparent corners and the two-control limit,
hover without resizing, keyboard access, dragging/persistence, no microphone on
click, live commands and two-mission/session continuity, menu state, and hidden
animation timers. Existing compact tests now verify these menu routes instead
of the retired compact card carousel.

Capture the real demo widgets with:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_companion_preview.py
```

[Idle](screenshots/avatars/companion-avatar.png),
[hover](screenshots/avatars/companion-hover.png) and
[abstract avatar](screenshots/avatars/companion-abstract.png) are transparent
captures of the real window. The [comparison](screenshots/avatars/companion-comparison.png)
places those same captures on a labelled backing canvas solely to make their
transparency readable. Native macOS desktop interaction and scaling still need
manual verification.

The companion was also opened and captured from a freshly built wheel installed
in an isolated target; the installed implementation retained its 320 px avatar
and hidden-by-default controls.
