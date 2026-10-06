"""Resolve authored fractions only after the real audio timeline is available."""
import copy
import json
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from app import media, store
from app.composition import normalize_scene
from app.models import Scene, Settings, Storyboard, Transition


def scene(**fields):
    return dict(id='s_00000001', text='Testo della scena.', prompt='An image.', motion='still', **fields)


def event(plan, kind):
    return next(e for e in plan['events'] if e['type'] == kind)


@pytest.mark.parametrize('actual', [7.873333333333333, 12.25, .2])
def test_full_image_adapts_to_shorter_and_longer_audio(actual):
    raw = scene(time_unit='scene', visual_events=[dict(type='show_image', asset='default', start=0, end=1)])
    original = copy.deepcopy(raw)
    plan = normalize_scene(raw, actual, {})
    assert event(plan, 'show_image')['start'] == 0
    assert event(plan, 'show_image')['end'] == actual
    assert raw == original


def test_scene_speech_and_seconds_can_be_mixed():
    raw = scene(time_unit='scene', visual_events=[
        dict(type='show_image', asset='default', start=0, end=1),
        dict(type='headline', text='Titolo', start=.5, end=1, time_unit='speech'),
        dict(type='label', text='Etichetta', start=.1, end=.8, time_unit='seconds'),
    ])
    plan = normalize_scene(raw, 8, {}, speech_duration=6)
    assert event(plan, 'show_image')['end'] == 8
    assert event(plan, 'headline')['start'] == 3
    assert event(plan, 'headline')['end'] == 6
    assert event(plan, 'label')['start'] == .1
    assert event(plan, 'label')['end'] == .8


def test_event_can_opt_in_without_changing_legacy_scene_units():
    raw = scene(visual_events=[dict(type='headline', text='Titolo', start=.25, end=1, time_unit='scene')])
    plan = normalize_scene(raw, 10, {})
    assert event(plan, 'headline')['start'] == 2.5
    assert event(plan, 'headline')['end'] == 10
    assert Scene.model_validate(raw).time_unit == 'seconds'


@pytest.mark.parametrize('unit,expected', [('scene', .8), ('speech', .6), ('seconds', .1)])
def test_scene_transition_uses_its_own_reference(unit, expected):
    plan = normalize_scene(scene(transition=dict(type='zoom_through', duration=.1,
        time_unit=unit, target=[.65, .4])), 8, {}, speech_duration=6)
    assert plan['transition']['duration'] == pytest.approx(expected)
    assert plan['transition']['target'] == (.65, .4)
    assert 'time_unit' not in plan['transition']


def test_relative_transition_is_limited_to_its_shot():
    raw = scene(time_unit='scene', visual_events=[dict(type='show_image', asset='default', start=.9, end=1,
        transition=dict(type='crossfade', duration=.5, time_unit='scene'))])
    plan = normalize_scene(raw, 8, {})
    image = event(plan, 'show_image')
    assert image['transition']['duration'] == pytest.approx(.8)
    raw['visual_events'][0]['transition'] = dict(type='crossfade', duration=1, time_unit='seconds')
    with pytest.raises(ValueError, match='evento 1.*transizione'):
        normalize_scene(raw, 8, {})


@pytest.mark.parametrize('unit', ['scene', 'speech'])
def test_invalid_inherited_and_explicit_fractions_identify_the_event(unit):
    for raw in [
        scene(time_unit=unit, visual_events=[dict(type='headline', text='X', end=1.1)]),
        scene(visual_events=[dict(type='headline', text='X', end=1.1, time_unit=unit)]),
    ]:
        with pytest.raises(ValueError, match='Scena s_00000001.*evento 1'):
            Scene.model_validate(raw)
    with pytest.raises(ValueError):
        Transition(type='blur', time_unit=unit, duration=1.1)


def test_old_fixed_seconds_still_fail_when_outside_actual_audio():
    raw = scene(duration=9, visual_events=[dict(type='show_image', asset='default', end=9)])
    with pytest.raises(ValueError, match='evento 1.*9.000s.*7.873s'):
        normalize_scene(raw, 7.873333333333333, {})


def test_speech_metadata_is_bounded_and_can_fall_back_to_scene():
    raw = scene(time_unit='speech', visual_events=[dict(type='headline', text='X', end=1)])
    assert event(normalize_scene(raw, 4, {}), 'headline')['end'] == 4
    assert event(normalize_scene(raw, 4, {}, speech_duration=4.1), 'headline')['end'] == 4
    with pytest.raises(ValueError, match='evento 1.*parlata senza durata'):
        normalize_scene(raw, 4, {}, speech_duration=0)
    for length in [float('nan'), float('inf'), -1]:
        with pytest.raises(ValueError, match='parlata non valida'):
            normalize_scene(raw, 4, {}, speech_duration=length)


def test_relative_camera_keeps_valid_sequence_and_rejects_overlaps():
    raw = scene(time_unit='scene', visual_events=[
        dict(type='show_image', asset='default', end=1),
        dict(type='reframe', start=0, end=.5, to=[.1, .1, .8, .8]),
        dict(type='pan', start=.5, end=1, to=[.2, .1, .8, .8]),
    ])
    plan = normalize_scene(raw, 7.873, {})
    assert event(plan, 'reframe')['end'] == pytest.approx(7.873 / 2)
    assert event(plan, 'pan')['start'] == pytest.approx(7.873 / 2)
    raw['visual_events'][2]['start'] = .4
    with pytest.raises(ValueError, match='camera sovrapposti'):
        normalize_scene(raw, 7.873, {})


def test_relative_events_are_independent_of_full_audio_length():
    board = Storyboard.model_validate_json((Path(__file__).parents[1] / 'examples/gps-educational.json').read_text('utf-8'))
    assert all(s.duration is None for s in board.scenes)
    for total in [62.5, 83.84266666666667, 95]:
        rows, kind = media.full_timeline([s.model_dump() for s in board.scenes], total)
        assert kind == 'proportional'
        for source, row in zip(board.scenes, rows):
            actual = row['end'] - row['start']
            plan = normalize_scene(source.model_dump(), actual, board.settings.model_dump())
            assert event(plan, 'show_image')['end'] == pytest.approx(actual)
            assert all(e['end'] <= actual + 1e-6 for e in plan['events'])


def test_real_renderer_resolves_speech_and_reuses_original_assets(tmp_path):
    class Context:
        def check(self): pass
        def progress(self, *args): pass
        def run(self, args, **kwargs):
            return subprocess.run(args, check=True, capture_output=True, **kwargs)

    (tmp_path / 'cache').mkdir()
    (tmp_path / 'output').mkdir()
    image = tmp_path / 'image.png'
    Image.new('RGB', (270, 480), '#183660').save(image)
    audio = tmp_path / 'cache/voice.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
        output.writeframes(b'\x00\x00' * 48000)
    hashes = {path: store.file_hash(path) for path in (image, audio)}
    source = scene(time_unit='scene', visual_events=[
        dict(type='show_image', asset='default', end=1),
        dict(type='headline', text='VOCE', start=.5, end=1, time_unit='speech'),
    ])
    project = dict(settings=Settings(subtitles_enabled=False).model_dump(), scenes=[source],
        assets=dict(images={'s_00000001':dict(path='image.png', sha256=hashes[image], stale=False)}))
    narration = dict(path='cache/voice.wav', duration=1,
        timeline=[dict(id='s_00000001', start=0, speech_end=.75, end=1)])
    movie, info = media.render_movie(tmp_path, project, narration, None, True, Context())
    assert movie.exists() and info['duration'] == pytest.approx(1, abs=.1)
    normalized = json.loads((tmp_path / 'output/composition.json').read_text('utf-8'))['scenes'][0]
    assert event(normalized, 'show_image')['end'] == 1
    assert event(normalized, 'headline')['start'] == .375
    assert event(normalized, 'headline')['end'] == .75
    assert {path: store.file_hash(path) for path in hashes} == hashes
