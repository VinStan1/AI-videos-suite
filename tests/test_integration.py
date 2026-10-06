import io
import json
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import store,media,providers,pipeline
from app.main import app
from app.jobs import JOBS


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    root=tmp_path_factory.mktemp('cryptid-test')
    old=store.DATA_ROOT;store.DATA_ROOT=root
    with TestClient(app) as c:yield c
    store.DATA_ROOT=old


def wait(c,jid):
    for _ in range(600):
        job=c.get('/api/jobs/'+jid).json()
        if job['status'] not in ('queued','running'):return job
        time.sleep(.1)
    pytest.fail('Job timeout')


def board(c,pid):return c.get(f'/api/projects/{pid}/storyboard').json()


def edit(c,pid,body):
    r=c.put(f'/api/projects/{pid}/storyboard',json=body)
    assert r.status_code==200,r.text
    return r.json()


@pytest.fixture(scope='module')
def demo(client):
    if not shutil.which('ffmpeg') or not(shutil.which('espeak-ng') or shutil.which('espeak')):
        pytest.skip('Requires ffmpeg and espeak: execute inside project Docker image')
    result=client.post('/api/demo');assert result.status_code==201,result.text
    result=result.json();j=wait(client,result['job']['id']);assert j['status']=='completed',j
    return client.get('/api/projects/'+result['project']['id']).json()


def test_demo_end_to_end(client,demo):
    assert demo['preview']['width']==540 and demo['preview']['height']==960
    assert demo['subtitles']['source']=='estimate'
    root=store.project_dir(demo['id']);info=media.probe(root/demo['preview']['path'])
    assert {'audio','video'} <= {s['codec_type'] for s in info['streams']}
    assert abs(float(info['format']['duration'])-demo['narration']['duration'])<.15
    assert any('stimati' in w for w in demo['warnings'])


def test_static_assets(client):
    assert client.get('/').status_code==200
    assert 'Content-Security-Policy' in client.get('/').headers
    assert client.get('/static/app.js').status_code==200


def test_origin_rejected(client):
    r=client.post('/api/projects',json={'title':'x'},headers={'Origin':'http://evil.example'})
    assert r.status_code==403


def test_large_body_header_rejected(client):
    r=client.post('/api/projects',json={'title':'x'},headers={'Content-Length':'999999999'})
    assert r.status_code==413


def test_manifest_validation(client):
    pid=client.post('/api/projects',json={'title':'Manuale'}).json()['id']
    b=board(client,pid);b['scenes']=[{'id':'s_1234abcd','text':'Una voce nel buio.','prompt':'','motion':'still','duration':None}]
    edit(client,pid,b)
    b=board(client,pid);b['scenes'][0]['id']='../../bad'
    assert client.put(f'/api/projects/{pid}/storyboard',json=b).status_code==422


def test_revision_conflict(client,demo):
    b=board(client,demo['id']);edit(client,demo['id'],b)
    assert client.put(f"/api/projects/{demo['id']}/storyboard",json=b).status_code==409


def test_common_voice_prompt_import_and_audio_invalidation(client):
    pid=client.post('/api/projects',json={'title':'Bray Road'}).json()['id']
    imported=json.loads((Path(__file__).parents[1]/'examples/the-beast-of-bray-road.json').read_text('utf-8'))
    saved=edit(client,pid,imported)
    first,second=[s['id'] for s in saved['scenes'][:2]]
    saved['assets']['audio']={first:{'source':'gemini','stale':False},second:{'source':'manual','stale':False}}
    store.save(saved)
    b=board(client,pid)
    assert b['settings']['gemini_max_attempts']==1
    b['settings']['voice_prompt']='Voce più profonda e uniforme.'
    saved=edit(client,pid,b)
    assert saved['assets']['audio'][first]['stale']
    assert not saved['assets']['audio'][second]['stale']


def test_full_generated_audio_is_invalidated_by_script_edit(client):
    pid=client.post('/api/projects',json={'title':'Voce completa'}).json()['id']
    b=board(client,pid)
    b['settings']['audio_mode']='full_generated'
    b['settings']['voice_provider']='gemini';b['settings']['voice']='Charon'
    b['scenes']=[{'id':'s_1234abcd','text':'Una voce nel buio.','prompt':'','motion':'still',
                  'delivery':'natural','duration':None,'effects':[]}]
    saved=edit(client,pid,b)
    saved['assets']['full_audio']={'source':'gemini','signature':'old','stale':False}
    store.save(saved)
    b=board(client,pid);b['scenes'][0]['text']='Una voce diversa nel buio.'
    saved=edit(client,pid,b)
    assert saved['assets']['full_audio']['stale'] is True
    assert saved['narration'] is None


def test_full_generated_voice_job_uses_one_synthesis(client,monkeypatch):
    import wave
    pid=client.post('/api/projects',json={'title':'Una richiesta'}).json()['id']
    b=board(client,pid)
    b['settings']['audio_mode']='full_generated'
    b['settings']['voice_provider']='gemini';b['settings']['voice']='Charon'
    b['scenes']=[
        {'id':'s_11111111','text':'Prima scena.','prompt':'','motion':'still','delivery':'ominous','duration':None,'effects':[]},
        {'id':'s_22222222','text':'Seconda scena.','prompt':'','motion':'still','delivery':'urgent','duration':None,'effects':[]},
    ]
    edit(client,pid,b);calls=[]
    def fake_synthesize(text,path,settings,ctx,delivery):
        calls.append((text,delivery))
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(b'\x00\x00'*4800)
        return []
    monkeypatch.setattr(pipeline,'synthesize_voice',fake_synthesize)
    job=client.post(f'/api/projects/{pid}/jobs',json={'action':'voice'}).json()
    assert wait(client,job['id'])['status']=='completed'
    project=client.get(f'/api/projects/{pid}').json()
    assert calls==[('Prima scena.\n\nSeconda scena.','natural')]
    assert project['assets']['full_audio']['generated_full'] is True


def test_cached_render(client,demo):
    root=store.project_dir(demo['id']);before={p.name:p.stat().st_mtime_ns for p in (root/'cache/render').glob('*.mp4') if 'part' not in p.name}
    r=client.post(f"/api/projects/{demo['id']}/jobs",json={'action':'render','preview':True})
    j=wait(client,r.json()['id']);assert j['status']=='completed',j
    after={p.name:p.stat().st_mtime_ns for p in (root/'cache/render').glob('*.mp4') if 'part' not in p.name}
    assert before==after


def test_generate_local_soundscape(client,demo):
    pid=demo['id'];b=board(client,pid);b['settings']['music_preset']='suspense';edit(client,pid,b)
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'music'}).json();result=wait(client,j['id'])
    assert result['status']=='completed',result
    music=client.get('/api/projects/'+pid).json()['assets']['music']
    assert music['source']=='generated' and music['profile']=='suspense' and music['duration']==pytest.approx(24,abs=.05)


def test_manual_image_upload(client,demo):
    b=io.BytesIO();Image.new('RGB',(300,500),(20,30,40)).save(b,format='PNG')
    pid=demo['id'];sid=demo['scenes'][0]['id']
    r=client.post(f'/api/projects/{pid}/upload?kind=image&scene_id={sid}',files={'file':('custom.png',b.getvalue(),'image/png')})
    assert r.status_code==200,r.text
    image=r.json()['assets']['images'][sid]
    assert image['source']=='manual' and image['width']==300
    assert r.json()['preview']['stale'] is True


def test_full_manual_audio_srt_render(client,demo):
    pid=client.post('/api/projects',json={'title':'Manuale completo'}).json()['id']
    b=board(client,pid);b['settings']['resolution']='540x960';b['settings']['fps']=24
    b['scenes']=[dict(id='s_87654321',text='Narrazione caricata manualmente.',prompt='',motion='pan_left',duration=None)]
    edit(client,pid,b)
    root=store.project_dir(demo['id']);audio=(root/demo['narration']['path']).read_bytes()
    r=client.post(f'/api/projects/{pid}/upload?kind=full_audio',files={'file':('manual.wav',audio,'audio/wav')})
    assert r.status_code==200,r.text
    b=io.BytesIO();Image.new('RGB',(200,350),'gray').save(b,format='PNG')
    assert client.post(f'/api/projects/{pid}/upload?kind=image&scene_id=s_87654321',files={'file':('image.png',b.getvalue(),'image/png')}).status_code==200
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'assemble_audio'}).json();assert wait(client,j['id'])['status']=='completed'
    sub='1\n00:00:00,000 --> 00:00:02,000\nSottotitolo manuale.\n'
    assert client.put(f'/api/projects/{pid}/captions',json={'text':sub}).status_code==200
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'render'}).json();assert wait(client,j['id'])['status']=='completed'
    p=client.get(f'/api/projects/{pid}').json();assert p['output']['height']==960 and p['subtitles']['source']=='manual'
    response=client.get(f'/api/projects/{pid}/export');assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert {'storyboard.json','narrazione.wav','output/video_finale.mp4','output/sottotitoli.srt'} <= set(z.namelist())


def test_manual_audio_not_overwritten(client,demo,monkeypatch):
    pid=demo['id'];sid=demo['scenes'][0]['id'];root=store.project_dir(pid)
    source=root/demo['assets']['audio'][sid]['path']
    r=client.post(f'/api/projects/{pid}/upload?kind=scene_audio&scene_id={sid}',files={'file':('voice.wav',source.read_bytes(),'audio/wav')})
    assert r.status_code==200,r.text
    before=r.json()['assets']['audio'][sid]
    def fail(*a,**kw):raise AssertionError('Manual audio must be retained')
    monkeypatch.setattr(providers,'espeak',fail)
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'voice','scene_id':sid,'force':True}).json()
    assert wait(client,j['id'])['status']=='completed'
    after=client.get(f'/api/projects/{pid}').json()['assets']['audio'][sid]
    assert before==after


def test_stale_audio_and_confirm(client,demo):
    pid=demo['id'];sid=demo['scenes'][0]['id'];b=board(client,pid)
    b['scenes'][0]['text']='Ho cambiato il testo.'
    p=edit(client,pid,b);assert p['assets']['audio'][sid]['stale'] is True
    r=client.post(f'/api/projects/{pid}/assets/confirm?kind=scene_audio&scene_id={sid}')
    assert r.status_code==200
    assert r.json()['assets']['audio'][sid]['source']=='manual' and not r.json()['assets']['audio'][sid]['stale']


def test_stale_subtitles_can_be_confirmed_for_current_audio(client,demo):
    pid=demo['id'];sid=demo['scenes'][0]['id'];b=board(client,pid)
    b['scenes'][0]['text']='La stessa voce, ma con parole nuove.'
    p=edit(client,pid,b);assert p['subtitles']['stale'] is True
    assert client.post(f'/api/projects/{pid}/assets/confirm?kind=scene_audio&scene_id={sid}').status_code==200
    r=client.post(f'/api/projects/{pid}/assets/confirm?kind=subtitles');assert r.status_code==200
    assert not r.json()['subtitles']['stale'] and r.json()['subtitles']['accept_next_audio'] is True
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'render','preview':True}).json();result=wait(client,j['id'])
    assert result['status']=='completed',result
    sub=client.get('/api/projects/'+pid).json()['subtitles']
    assert not sub['stale'] and sub['audio_sha'] and 'accept_next_audio' not in sub


def test_job_restart_recovery(client):
    path=JOBS.root/'j_0123456789ab.json'
    store.atomic_json(path,{'id':'j_0123456789ab','project_id':'p_0123456789ab','status':'running','created':time.time()})
    JOBS.recover()
    assert JOBS.read('j_0123456789ab')['status']=='interrupted'


def test_cancellation(client,monkeypatch):
    old=JOBS.runner
    def slow(pid,request,ctx):
        for _ in range(500):ctx.check();time.sleep(.01)
    monkeypatch.setattr(JOBS,'runner',slow)
    pid=client.post('/api/projects',json={'title':'Annulla'}).json()['id']
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'render'}).json()
    client.post('/api/jobs/'+j['id']+'/cancel')
    assert wait(client,j['id'])['status']=='cancelled'


def test_missing_services_have_no_silent_fallback(client):
    pid=client.post('/api/projects',json={'title':'No timing','story':'Una voce.'}).json()['id']
    b=board(client,pid);b['settings'].update(voice_provider='espeak',voice='it');edit(client,pid,b)
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'split'}).json();assert wait(client,j['id'])['status']=='completed'
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'voice'}).json();assert wait(client,j['id'])['status']=='completed'
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'captions','caption_method':'timings'}).json();r=wait(client,j['id'])
    assert r['status']=='failed' and 'Timestamp' in r['message']


def test_invalid_image_error(client,demo):
    r=client.post(f"/api/projects/{demo['id']}/upload?kind=image&scene_id={demo['scenes'][0]['id']}",files={'file':('bad.png',b'not an image','image/png')})
    assert r.status_code==400 and 'Immagine' in r.json()['detail']


def test_reusable_local_music_library(client):
    import wave,math,struct
    music=io.BytesIO()
    with wave.open(music,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
        output.writeframes(b''.join(struct.pack('<h',int(1800*math.sin(i*2*math.pi*140/48000))) for i in range(24000)))
    uploaded=client.post('/api/music-library',files={'file':('bosco.wav',music.getvalue(),'audio/wav')})
    assert uploaded.status_code==201,uploaded.text
    track=uploaded.json();assert track['name']=='bosco' and track['duration']==pytest.approx(.5,abs=.01)
    assert any(item['id']==track['id'] for item in client.get('/api/music-library').json())
    playable=client.get(f"/api/music-library/{track['id']}/file")
    assert playable.status_code==200 and playable.headers['content-type'].startswith('audio/wav')
    pid=client.post('/api/projects',json={'title':'Libreria audio'}).json()['id']
    selected=client.post(f"/api/projects/{pid}/music-library/{track['id']}")
    assert selected.status_code==200,selected.text
    asset=selected.json()['assets']['music']
    assert asset['source']=='library' and asset['library_id']==track['id'] and asset['name']=='bosco'
    project_copy=store.project_dir(pid)/asset['path'];assert project_copy.is_file()
    assert client.delete('/api/music-library/'+track['id']).status_code==200
    assert not client.get('/api/music-library').json() and project_copy.is_file()


def test_full_hd_with_background_music(client):
    import wave,math,struct
    pid=client.post('/api/projects',json={'title':'Full HD test'}).json()['id']
    b=board(client,pid);b['settings']['resolution']='1080x1920';b['settings']['fps']=30
    b['settings'].update(voice_provider='espeak',voice='it')
    b['scenes']=[dict(id='s_aabbccdd',text='Una voce nel buio.',prompt='',motion='zoom_out',duration=None,
                      effects=[dict(effect='impact',at=0,volume=.22)])]
    edit(client,pid,b)
    image=io.BytesIO();Image.new('RGB',(600,800),'gray').save(image,format='PNG')
    client.post(f'/api/projects/{pid}/upload?kind=image&scene_id=s_aabbccdd',files={'file':('image.png',image.getvalue(),'image/png')})
    music=io.BytesIO()
    with wave.open(music,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
        f.writeframes(b''.join(struct.pack('<h',int(2000*math.sin(i*2*math.pi*120/48000))) for i in range(48000)))
    r=client.post(f'/api/projects/{pid}/upload?kind=music',files={'file':('test.wav',music.getvalue(),'audio/wav')});assert r.status_code==200,r.text
    j=client.post(f'/api/projects/{pid}/jobs',json={'action':'complete','allow_estimated':True}).json()
    result=wait(client,j['id']);assert result['status']=='completed',result
    p=client.get('/api/projects/'+pid).json()
    assert p['output']['width']==1080 and p['output']['height']==1920 and p['output']['fps']==30
    info=media.probe(store.project_dir(pid)/p['output']['path'])
    codecs={s['codec_type']:s['codec_name'] for s in info['streams']}
    assert codecs=={'video':'h264','audio':'aac'}
    effects=list((store.project_dir(pid)/'cache').glob('effects_*.wav'))
    assert effects and media.wav_seconds(effects[-1])==pytest.approx(p['narration']['duration'],abs=.02)
