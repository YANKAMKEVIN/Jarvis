from jarvis.desktop.backchannel import NEUTRAL, Backchannel, LevelSmoother, nod_envelope

DT = .033
VOICE, QUIET = .08, .003


def run(bc, seconds, level, state='listening'):
    frames = []
    for _ in range(round(seconds / DT)):
        frames.append(bc.update(state, level, DT))
    return frames


def test_smoother_attacks_fast_and_releases_slowly():
    s = LevelSmoother()
    for _ in range(4):
        s.update(.5, DT)
    risen = s.value
    assert risen > .4
    for _ in range(4):
        s.update(0, DT)
    assert risen * .4 < s.value < risen
    s.update(5, DT)
    assert s.value <= 1


def test_nod_envelope_is_a_single_bounded_dip():
    assert nod_envelope(0) == nod_envelope(1) == nod_envelope(-1) == 0
    assert nod_envelope(.5) == 1
    assert all(0 <= nod_envelope(i / 50) <= 1 for i in range(51))


def test_silence_stays_neutral_and_never_nods():
    bc = Backchannel()
    frames = run(bc, 3, QUIET)
    assert all(f.nod == 0 for f in frames)
    assert frames[-1].attention < .01 and frames[-1].pulse < .01


def test_speech_raises_attention_and_pulse_follows_the_level():
    bc = Backchannel()
    soft = run(bc, 1, .03)[-1]
    loud = run(bc, 1, .2)[-1]
    assert soft.attention > .9 and loud.attention > .9
    assert 0 < soft.pulse < loud.pulse <= 1
    assert all(f.nod == 0 for f in run(Backchannel(), 2, VOICE))  # no nod mid-sentence


def test_short_pause_after_speech_triggers_exactly_one_nod():
    bc = Backchannel()
    run(bc, 1, VOICE)
    pause = run(bc, .9, QUIET)
    nods = [f.nod for f in pause]
    assert max(nods) > .9
    first = next(i for i, n in enumerate(nods) if n > 0)
    assert .25 < first * DT < .6          # shortly after the pause, before VAD's 1.1 s
    assert nods[-1] == 0                  # finished and returned to rest
    # Speaking again too soon does not chain nods; after the cooldown it does.
    run(bc, .2, VOICE)
    assert max(f.nod for f in run(bc, .5, QUIET)) == 0
    run(bc, 1, VOICE)
    assert max(f.nod for f in run(bc, .9, QUIET)) > .9


def test_brief_noise_burst_is_not_enough_for_a_nod():
    bc = Backchannel()
    run(bc, .2, VOICE)
    assert max(f.nod for f in run(bc, 1, QUIET)) == 0


def test_noise_floor_adapts_so_steady_background_is_not_speech():
    bc = Backchannel()
    run(bc, 4, .015)   # fan noise just above the absolute threshold
    frames = run(bc, 3, .015)
    assert not bc.speaking
    assert all(f.nod == 0 for f in frames)
    run(bc, 1, .12)
    assert bc.speaking


def test_other_states_and_disabled_setting_fade_or_reset():
    bc = Backchannel()
    run(bc, 1, VOICE)
    run(bc, .4, QUIET)                    # nod in progress
    thinking = run(bc, 1.5, VOICE, 'thinking')
    assert thinking[0].nod == 0 and thinking[-1].attention < .05
    assert all(f.pulse == 0 for f in thinking)   # Jarvis' own voice never drives it
    run(bc, 1, VOICE)
    assert bc.update('listening', VOICE, DT, enabled=False) == NEUTRAL
    assert bc.attention == 0 and not bc.speaking


def test_long_silence_ends_the_turn():
    bc = Backchannel()
    run(bc, 1, VOICE)
    end = run(bc, 3, QUIET)
    assert sum(1 for a, b in zip(end, end[1:]) if a.nod == 0 and b.nod > 0) == 1
    assert end[-1].attention < .05


def test_gaps_between_words_are_not_pauses():
    bc = Backchannel()
    frames = []
    for _ in range(10):                   # ~2 s of syllables with short gaps
        frames += run(bc, .15, VOICE) + run(bc, .066, QUIET)
    assert all(f.nod == 0 for f in frames)
    assert bc.speaking and frames[-1].attention > .9
    assert max(f.nod for f in run(bc, .9, QUIET)) > .9
