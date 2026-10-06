"""Authored voice directions must reach synthesis, survive import and affect cache."""
import base64
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import media, pipeline, providers, store
from app.composition import normalize_scene, planned_assets
from app.main import app
from app.models import Scene, Settings, Storyboard


class Context:
    def check(self): pass
    def progress(self, *args): pass
    def run(self, args, **kwargs): return media.run(args)


def audio_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b'\x00\x00' * 4800)
    return buffer.getvalue()


def project_with_directions(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(store, 'DATA_ROOT', tmp_path)
    project = store.create('Regia completa', '')
    project['settings'] = Settings(
        audio_mode=mode, voice_provider='gemini', voice='Charon',
        voice_prompt='Mantieni lo stesso timbro.', gemini_max_attempts=1,
    ).model_dump()
    project['scenes'] = [
        Scene(id='s_11111111', text='Prima scena.', voice_prompt='Apri con curiosita.').model_dump(),
        Scene(id='s_22222222', text='Seconda scena.').model_dump(),
        Scene(id='s_33333333', text='Terza scena.', voice_prompt='Chiudi con soddisfazione.').model_dump(),
    ]
    store.save(project)
    return project


def test_old_voice_cache_and_optional_scene_prompt():
    scene = Scene(text='Una storia.', prompt='A landscape.')
    assert scene.voice_prompt == ''
    with pytest.raises(ValueError):
        Scene(text='Una storia.', voice_prompt='x' * 2001)
    scenes = [scene.model_dump()]
    settings = Settings(voice_provider='gemini', voice='Charon').model_dump()
    expected = store.digest([
        pipeline.full_voice_text(scenes), 'gemini', 'Charon', settings['speed'], '', 'full-voice-v1',
    ])
    assert pipeline.full_voice_signature(scenes, settings) == expected


@pytest.mark.parametrize('mode', ['scenes', 'full_generated'])
def test_scene_directions_reach_tts_and_only_changed_audio_is_regenerated(tmp_path, monkeypatch, mode):
    project = project_with_directions(tmp_path, monkeypatch, mode)
    calls = []

    def fake_gemini(text, path, voice, speed, delivery, ctx, **options):
        calls.append((text, options))
        path.write_bytes(audio_bytes())
        return []

    monkeypatch.setattr(providers, 'google_gemini_tts', fake_gemini)
    pipeline.generate_voice(project, {}, Context())
    initial_calls = len(calls)
    assert initial_calls == (3 if mode == 'scenes' else 1)
    assert all(options['voice_prompt'] == 'Mantieni lo stesso timbro.' for _, options in calls)
    if mode == 'scenes':
        assert calls[0] == ('Prima scena.', dict(voice_prompt='Mantieni lo stesso timbro.',
            max_attempts=1, voice_directions='Apri con curiosita.'))
        assert 'voice_directions' not in calls[1][1]
        assert calls[2][1]['voice_directions'] == 'Chiudi con soddisfazione.'
    else:
        assert calls[0][0] == 'Prima scena.\n\nSeconda scena.\n\nTerza scena.'
        directions = calls[0][1]['voice_directions']
        assert 'Paragrafo 1 della narrazione: Apri con curiosita.' in directions
        assert 'Paragrafo 3 della narrazione: Chiudi con soddisfazione.' in directions
    pipeline.generate_voice(project, {}, Context())
    assert len(calls) == initial_calls
    project['scenes'][0]['voice_prompt'] = 'Apri con enfasi.'
    pipeline.generate_voice(project, {}, Context())
    assert len(calls) == initial_calls + 1
    assert 'Apri con enfasi.' in calls[-1][1]['voice_directions']
    # Manual media stay protected even when a generation prompt changes.
    if mode == 'scenes':
        project['assets']['audio']['s_11111111']['source'] = 'manual'
        project['scenes'][0]['voice_prompt'] = 'Un altro tono.'
        pipeline.generate_voice(project, {}, Context())
        assert len(calls) == initial_calls + 1


def test_local_direction_reaches_every_explicit_pause_segment(tmp_path, monkeypatch):
    calls = []
    settings = Settings(voice_provider='gemini', voice='Charon').model_dump()
    scene = Scene(text='Prima. [[pausa=0.1]] Poi.', voice_prompt='Tono curioso.').model_dump()

    def fake_gemini(text, path, voice, speed, delivery, ctx, **options):
        calls.append((text, options['voice_directions']))
        path.write_bytes(audio_bytes())
        return []

    monkeypatch.setattr(providers, 'google_gemini_tts', fake_gemini)
    path = tmp_path / 'voice.wav'
    pipeline.synthesize_voice_with_pauses(scene['text'], path,
        pipeline.directed_voice_settings(settings, [scene]), Context())
    assert calls == [('Prima.', 'Tono curioso.'), ('Poi.', 'Tono curioso.')]
    assert media.wav_seconds(path) == pytest.approx(.3)


@pytest.mark.parametrize('mode', ['scenes', 'full_generated'])
@pytest.mark.parametrize('source', ['gemini', 'manual'])
def test_api_import_export_and_prompt_invalidation(tmp_path, monkeypatch, mode, source):
    project = project_with_directions(tmp_path, monkeypatch, mode)
    first, second, third = [scene['id'] for scene in project['scenes']]
    if mode == 'scenes':
        project['assets']['audio'] = {sid: dict(source=source, stale=False) for sid in (first, second, third)}
    else:
        project['assets']['full_audio'] = dict(source=source, stale=False)
    store.save(project)
    with TestClient(app) as client:
        url = f"/api/projects/{project['id']}/storyboard"
        board = client.get(url).json()
        board['scenes'][0]['voice_prompt'] = 'Metti in risalto la domanda.'
        response = client.put(url, json=board)
        assert response.status_code == 200, response.text
        exported = client.get(url).json()
        assert exported['scenes'][0]['voice_prompt'] == board['scenes'][0]['voice_prompt']
        assert Storyboard.model_validate(exported).settings.voice_prompt == 'Mantieni lo stesso timbro.'
        saved = response.json()
        if mode == 'scenes':
            assert saved['assets']['audio'][first]['stale'] == (source == 'gemini')
            assert not saved['assets']['audio'][second]['stale']
            assert not saved['assets']['audio'][third]['stale']
        else:
            assert saved['assets']['full_audio']['stale'] == (source == 'gemini')


def test_gemini_retry_preserves_common_and_local_instructions(tmp_path, monkeypatch):
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY', 'test-key')
    monkeypatch.setattr(providers.time, 'sleep', lambda *_: None)
    prompts = []

    def request(method, url, **kwargs):
        prompts.append(kwargs['json']['contents'][0]['parts'][0]['text'])
        if len(prompts) == 1:
            return SimpleNamespace(json=lambda: {'candidates': [{'finishReason': 'OTHER'}]})
        data = base64.b64encode(audio_bytes()).decode()
        return SimpleNamespace(json=lambda: {'candidates': [{'content': {'parts': [
            {'inlineData': {'mimeType': 'audio/wav', 'data': data}},
        ]}}]})

    monkeypatch.setattr(providers, 'request', request)
    providers.google_gemini_tts('Solo queste parole.', tmp_path / 'voice.wav', 'Charon', 1,
        'natural', Context(), voice_prompt='Timbro uniforme.', voice_directions='Enfatizza il finale.')
    assert len(prompts) == 2
    for prompt in prompts:
        assert 'Timbro uniforme.' in prompt and 'Enfatizza il finale.' in prompt
        assert prompt.split('TESTO:\n')[1] == 'Solo queste parole.'


def test_non_gemini_directions_do_not_invalidate_unaffected_audio():
    settings = Settings(voice_provider='espeak').model_dump()
    scenes = [Scene(text='Testo.', voice_prompt='Voce calda.').model_dump()]
    assert pipeline.directed_voice_settings(settings, scenes) is settings
    signature = pipeline.full_voice_signature(scenes, settings)
    scenes[0]['voice_prompt'] = 'Voce diversa.'
    assert pipeline.full_voice_signature(scenes, settings) == signature


def test_gps_storyboard_contains_generation_and_composition_instructions():
    path = Path(__file__).parents[1] / 'examples/gps-educational.json'
    board = Storyboard.model_validate_json(path.read_text('utf-8'))
    assert board.settings.voice_prompt and board.settings.voice_provider == 'gemini'
    assert board.settings.audio_mode == 'full_generated'
    assert board.settings.gemini_max_attempts == 1
    assert len(board.scenes) == 8
    for scene in board.scenes:
        assert not scene.voice_prompt
        assert len(planned_assets(scene.model_dump())) == 1
        assert all(asset.prompt.strip() for asset in scene.assets)
        normalize_scene(scene.model_dump(), 7.873333333333333, board.settings.model_dump(), speech_duration=7.673333333333333)


def test_gps_uses_one_google_request_with_one_common_voice_prompt(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / 'examples/gps-educational.json'
    board = Storyboard.model_validate_json(path.read_text('utf-8'))
    monkeypatch.setattr(store, 'DATA_ROOT', tmp_path)
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY', 'test-key')
    project = store.create(board.title, board.story)
    project['scenes'] = [scene.model_dump() for scene in board.scenes]
    project['settings'] = board.settings.model_dump()
    store.save(project)
    prompts = []

    def request(method, url, **kwargs):
        assert url.endswith(':generateContent')
        prompts.append(kwargs['json']['contents'][0]['parts'][0]['text'])
        data = base64.b64encode(audio_bytes()).decode()
        return SimpleNamespace(json=lambda: {'candidates': [{'content': {'parts': [
            {'inlineData': {'mimeType': 'audio/wav', 'data': data}},
        ]}}]})

    monkeypatch.setattr(providers, 'request', request)
    pipeline.generate_voice(project, {}, Context())
    pipeline.generate_voice(project, {}, Context())
    assert len(prompts) == 1
    assert prompts[0].count(board.settings.voice_prompt) == 1
    assert prompts[0].split('TESTO:\n')[1] == '\n\n'.join(scene.text for scene in board.scenes)
    assert 'Regia specifica dei passaggi' not in prompts[0]
    assert not project['assets']['audio']
    assert project['assets']['full_audio']['generated_full'] is True
