from pathlib import Path
import json
import shutil
import subprocess
import wave
import pytest
from PIL import Image
from app import captions, media, pipeline, providers, store
from app.models import Scene, Settings, SoundCue, Storyboard, split_story


def test_split_faithful():
    text="Era buio. Nessuno vide la creatura!\n\nPoi una voce disse: non voltarti. "*10
    parts=split_story(text,12)
    assert ' '.join(text.split())==' '.join(' '.join(parts).split())
    assert len(parts)>2


def test_split_long_sentence():
    text=' '.join('parola'+str(i) for i in range(95))
    assert ' '.join(split_story(text,10))==text


def test_empty_story():
    with pytest.raises(ValueError): split_story('   ')


def test_duplicate_scenes():
    scene=Scene(id='s_1234abcd',text='Prova')
    with pytest.raises(ValueError): Storyboard(title='Test',scenes=[scene,scene])


def test_scene_sound_cues_are_validated():
    scene=Scene(id='s_1234abcd',text='Un colpo nel buio.',effects=[SoundCue(effect='impact',at=.4,volume=.3)])
    assert scene.effects[0].effect=='impact' and scene.delivery=='natural'
    with pytest.raises(ValueError):
        Scene(id='s_1234abcd',text='Prova',effects=[{'effect':'unknown'}])
    with pytest.raises(ValueError):
        Scene(id='s_1234abcd',text='Prova',delivery='tragic')


def test_documented_storyboard_schema_matches_the_model():
    path=Path(__file__).parents[1]/'docs/storyboard.schema.json'
    assert json.loads(path.read_text('utf-8'))==Storyboard.model_json_schema()


def test_missing_image_provider_uses_cloudflare_default():
    settings=Settings.model_validate({'voice_provider':'kokoro'})
    assert settings.image_provider=='cloudflare'


def test_gemini_uses_native_scene_direction(tmp_path,monkeypatch):
    calls={}
    class Context: pass
    def fake_gemini(text,path,voice,speed,delivery,ctx,**kwargs):
        calls['provider']=(text,voice,speed,delivery)
        calls['options']=kwargs
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(b'\x00\x00'*4800)
        return []
    def fake_delivery(source,target,preset,ctx):
        calls['postprocess']=preset;shutil.copy2(source,target)
    monkeypatch.setattr(providers,'google_gemini_tts',fake_gemini)
    monkeypatch.setattr(media,'apply_voice_delivery',fake_delivery)
    settings=Settings(voice_provider='gemini',voice='Charon',speed=.95,
                      voice_prompt='Voce leggermente più profonda e uniforme.',gemini_max_attempts=1).model_dump()
    pipeline.synthesize_voice('Nel buio.',tmp_path/'voice.wav',settings,Context(),'ominous')
    assert calls['provider']==('Nel buio.','Charon',.95,'ominous')
    assert calls['postprocess']=='natural'
    assert calls['options']=={'voice_prompt':settings['voice_prompt'],'max_attempts':1}


def test_chirp_keeps_pause_in_one_request_and_applies_local_direction(tmp_path,monkeypatch):
    calls={}
    class Context: pass
    def fake_chirp(text,path,voice,speed,ctx):
        calls['provider']=(text,voice,speed)
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(b'\x00\x00'*4800)
        return []
    def fake_delivery(source,target,preset,ctx):
        calls['postprocess']=preset;shutil.copy2(source,target)
    monkeypatch.setattr(providers,'google_chirp_tts',fake_chirp)
    monkeypatch.setattr(media,'apply_voice_delivery',fake_delivery)
    settings=Settings(voice_provider='chirp',voice='Charon',speed=.95).model_dump()
    text='Nel buio. [[pausa=0.6]] Qualcosa si mosse.'
    pipeline.synthesize_voice_with_pauses(text,tmp_path/'voice.wav',settings,Context(),'ominous')
    assert calls['provider']==(text,'Charon',.95)
    assert calls['postprocess']=='ominous'


def test_full_generated_voice_uses_one_tts_request(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA_ROOT',tmp_path)
    project=store.create('Voce unica','Prima scena. Seconda scena.')
    project['scenes']=[
        Scene(id='s_11111111',text='Prima scena. [[pausa=0.4]] Continua.').model_dump(),
        Scene(id='s_22222222',text='Seconda scena.').model_dump(),
    ]
    project['settings']=Settings(audio_mode='full_generated',voice_provider='gemini',voice='Charon',
                                 voice_prompt='Voce uniforme.',gemini_max_attempts=1).model_dump()
    store.save(project);calls=[]
    class Context:
        def progress(self,*args): pass
    def fake_synthesize(text,path,settings,ctx,delivery):
        calls.append((text,delivery))
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(b'\x00\x00'*48000)
        return []
    monkeypatch.setattr(pipeline,'synthesize_voice',fake_synthesize)
    pipeline.generate_voice(project,{},Context())
    pipeline.generate_voice(project,{},Context())
    assert calls==[('Prima scena. Continua.\n\nSeconda scena.','natural')]
    assert project['assets']['full_audio']['source']=='gemini'
    narration=pipeline.assemble_audio(project,Context())
    assert narration['duration']==pytest.approx(1) and narration['timing_kind']=='proportional'
    narration['timing_kind']='whisper_aligned'
    assert pipeline.assemble_audio(project,Context())['timing_kind']=='whisper_aligned'


def test_aligned_full_timeline_uses_word_boundaries():
    scenes=[dict(id='a',text='due parole'),dict(id='b',text='ultima')]
    words=[
        {'word':'due','start':.2,'end':.5},
        {'word':'parole','start':.55,'end':1.0},
        {'word':'ultima','start':1.4,'end':2.1},
    ]
    timeline=pipeline.aligned_full_timeline(scenes,words,2.4)
    assert timeline[0]['start']==0 and timeline[0]['speech_end']==1
    assert timeline[0]['end']==timeline[1]['start']==pytest.approx(1.2)
    assert timeline[1]['speech_end']==2.1 and timeline[1]['end']==2.4


def test_aevalsrc_quotes_expression_with_commas():
    expression='0.20*sin(2*PI*54*t)*pow(abs(sin(2*PI*0.7*t)),18)'
    assert media.aevalsrc(expression,2)=="aevalsrc=exprs='0.20*sin(2*PI*54*t)*pow(abs(sin(2*PI*0.7*t)),18)':sample_rate=48000:duration=2"


def test_safe_paths(tmp_path):
    assert store.safe_path(tmp_path,'assets/ok.png')==tmp_path/'assets/ok.png'
    for bad in ('../escape','/etc/passwd','assets\\evil',''):
        with pytest.raises(ValueError): store.safe_path(tmp_path,bad)


def test_local_music_library_metadata(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA_ROOT',tmp_path)
    track_id='m_123456789abc';audio=store.music_track_path(track_id);audio.write_bytes(b'normalized audio placeholder')
    track={'id':track_id,'name':'Bosco','duration':12.5,'sha256':'abc','created':10}
    store.save_music_track(track)
    assert store.get_music_track(track_id)==track
    assert store.list_music_tracks()==[track]
    with pytest.raises(ValueError): store.music_track_path('../outside')
    store.delete_music_track(track_id)
    assert store.list_music_tracks()==[] and not audio.exists()


def test_srt_roundtrip():
    cues=[{'start':0.0,'end':1.123,'text':'Non voltarti.'},{'start':1.4,'end':4.0,'text':'La creatura \u00e8 qui.'}]
    assert captions.parse_srt(captions.to_srt(cues))==cues


def test_srt_invalid():
    for text in ('','hello','1\n00:99:00,000 --> 01:00:00,000\nx','1\n00:00:02,000 --> 00:00:01,000\nx'):
        with pytest.raises(ValueError): captions.parse_srt(text)
    with pytest.raises(ValueError):
        captions.parse_srt('1\n00:00:00,000 --> 00:00:03,000\nx\n\n2\n00:00:02,000 --> 00:00:04,000\ny')


def test_ass_escaping():
    result=captions.ass_text(r'{\pos(0,0)}hello\Nworld')
    assert '{' not in result and r'\pos' not in result


def test_bad_timestamps_filtered():
    words=[{'word':'a','start':0,'end':1},{'word':'x','start':float('nan'),'end':2},{'word':'b','start':.8,'end':2}]
    assert captions.normalize_words(words,2)==[{'word':'a','start':0,'end':1},{'word':'b','start':1,'end':2}]


def test_estimated_captions_bounded():
    cues=captions.estimated_cues([dict(text='Una voce si alzo tra gli alberi senza foglie.',start=0,end=6,speech_end=5.8)])
    assert cues[0]['start']==0
    assert cues[-1]['end']==pytest.approx(5.8)
    assert len(cues)>=2


def test_whisper_timings_are_corrected_with_script_words():
    recognized=[
        {'word':'Pier','start':0.0,'end':.3},
        {'word':'Fortunato','start':.32,'end':.75},
        {'word':'Zanfletta','start':.77,'end':1.25},
        {'word':'vide','start':1.3,'end':1.55},
        {'word':'una','start':1.58,'end':1.75},
        {'word':'luce','start':1.78,'end':2.15},
    ]
    aligned,stats=captions.align_script_words(
        'Pier Fortunato Zanfretta vide una luce.',recognized,2.3
    )
    assert [word['word'] for word in aligned]==['Pier','Fortunato','Zanfretta','vide','una','luce.']
    assert aligned[2]['start']==.77 and aligned[2]['end']==1.25
    assert aligned[-1]['end']==2.15
    assert stats['score']>.8 and stats['recognized_words']==6


def test_whisper_script_alignment_fills_a_missing_word_without_overlap():
    recognized=[
        {'word':'Non','start':0,'end':.25},{'word':'era','start':.27,'end':.45},
        {'word':'animale','start':.47,'end':1.0},{'word':'Era','start':1.25,'end':1.48},
        {'word':'troppo','start':1.5,'end':1.82},{'word':'alto','start':1.84,'end':2.2},
    ]
    aligned,_=captions.align_script_words('Non era un animale. Era troppo alto.',recognized,2.3)
    assert [word['word'] for word in aligned]==['Non','era','un','animale.','Era','troppo','alto.']
    assert all(word['end']>word['start'] for word in aligned)
    assert all(left['end']<=right['start'] for left,right in zip(aligned,aligned[1:]))


def test_whisper_script_alignment_rejects_unrelated_audio():
    recognized=[{'word':word,'start':index*.3,'end':index*.3+.25}
                for index,word in enumerate('questa registrazione contiene parole completamente diverse'.split())]
    with pytest.raises(ValueError,match='divergono troppo'):
        captions.align_script_words('Zanfretta vide una creatura nella notte.',recognized,2)


def test_full_audio_timeline():
    scenes=[dict(id='a',text='due parole',duration=None),dict(id='b',text='una',duration=None)]
    timeline,kind=media.full_timeline(scenes,9)
    assert kind=='proportional' and timeline[0]['end']==6 and timeline[-1]['end']==9
    scenes[0]['duration']=6
    with pytest.raises(ValueError):media.full_timeline(scenes,9)
    scenes[1]['duration']=3
    assert media.full_timeline(scenes,9)[1]=='manual'
    with pytest.raises(ValueError):media.full_timeline(scenes,10)


def test_workflow_substitution():
    from app.providers import substitute
    obj={'a':'{{SEED}}','b':['text {{PROMPT}}']}
    actual=substitute(obj,{'{{SEED}}':12,'{{PROMPT}}':'two "eyes"'})
    assert actual=={'a':12,'b':['text two "eyes"']}


def test_explicit_speech_pauses_are_removed_from_spoken_text():
    plan=providers.speech_plan('Non voltarti. [[pausa=0,35]] E ascolta.')
    assert plan==[('speech','Non voltarti.'),('pause',.35),('speech','E ascolta.')]
    assert providers.spoken_text('Non voltarti. [[pausa=0.35]] E ascolta.')=='Non voltarti. E ascolta.'
    with pytest.raises(ValueError,match='al massimo'):
        providers.speech_plan('Aspetta [[pausa=6]] ancora.')


def test_join_voice_parts_encodes_an_explicit_silence(tmp_path):
    first=tmp_path/'first.wav'; second=tmp_path/'second.wav'
    for path in (first,second):
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
            output.writeframes(b'\x01\x00' * 4800)
    target=tmp_path/'voice.wav'
    assert media.join_voice_parts([(first,0),(None,.25),(second,0)],target)==[0,.35]
    assert media.wav_seconds(target)==pytest.approx(.45)


def test_local_effect_track_is_aligned_and_audible(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('Requires ffmpeg')
    class Context:
        run=staticmethod(media.run)
    project={'scenes':[{'id':'s_1234abcd','effects':[{'effect':'impact','at':.4,'volume':.5}]}]}
    timeline=[{'id':'s_1234abcd','start':0,'end':2.0}]
    path=media.build_effects_track(tmp_path,project,timeline,Context())
    assert path and media.wav_seconds(path)==pytest.approx(2,abs=.001)
    with wave.open(str(path),'rb') as source:
        assert (source.getnchannels(),source.getsampwidth(),source.getframerate())==(1,2,48000)
        quiet=source.readframes(48000*3//10)
        source.setpos(48000*45//100); active=source.readframes(48000//5)
    assert quiet==b'\x00'*len(quiet)
    assert max(abs(int.from_bytes(active[i:i+2],'little',signed=True)) for i in range(0,len(active),2))>500


def test_generated_soundscape_has_a_seamless_loop(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('Requires ffmpeg')
    class Context:
        run=staticmethod(media.run)
    path=tmp_path/'soundscape.wav';media.generate_soundscape('suspense',path,Context())
    with wave.open(str(path),'rb') as source:
        frames=source.getnframes();first=source.readframes(1)
        source.setpos(frames-1);last=source.readframes(1)
        assert frames/source.getframerate()==pytest.approx(24,abs=.001)
    decode=lambda value:int.from_bytes(value,'little',signed=True)
    assert abs(decode(first)-decode(last))<200


def test_scene_voice_direction_profiles_and_timestamps(tmp_path,monkeypatch):
    if not shutil.which('ffmpeg'):
        pytest.skip('Requires ffmpeg')
    class Context:
        run=staticmethod(media.run)
    def fake_espeak(text,path,speed,ctx):
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
            output.writeframes(b'\x01\x00'*48000)
        return [{'word':'Prova','start':0,'end':1}]
    monkeypatch.setattr(providers,'espeak',fake_espeak)
    settings=Settings(voice_provider='espeak').model_dump()
    lengths={}
    for delivery in media.VOICE_DELIVERY:
        path=tmp_path/(delivery+'.wav')
        words=pipeline.synthesize_voice('Prova',path,settings,Context(),delivery)
        lengths[delivery]=media.wav_seconds(path)
        assert words[-1]['end']==pytest.approx(lengths[delivery],abs=.002)
    assert lengths['ominous']>lengths['natural']>lengths['urgent']


def test_effect_offset_must_fall_inside_its_scene(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('Requires ffmpeg')
    class Context:
        run=staticmethod(media.run)
    project={'scenes':[{'id':'s_1234abcd','effects':[{'effect':'snap','at':1.0,'volume':.2}]}]}
    timeline=[{'id':'s_1234abcd','start':0,'end':1.0}]
    with pytest.raises(ValueError,match='oltre la durata'):
        media.build_effects_track(tmp_path,project,timeline,Context())


def test_renderer_mixes_local_effects_into_the_final_audio(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Requires ffmpeg and ffprobe')
    class Context:
        def run(self,args,cwd=None,timeout=7200):
            result=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
            assert result.returncode==0,result.stderr.decode(errors='replace')
            return result.stdout
        def progress(self,*args): pass
    for folder in ('assets/images','cache/render','output'):
        (tmp_path/folder).mkdir(parents=True,exist_ok=True)
    image=tmp_path/'assets/images/scene.png';Image.new('RGB',(180,320),'gray').save(image)
    audio=tmp_path/'cache/narration.wav'
    with wave.open(str(audio),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000)
        output.writeframes(b'\x00\x00'*72000)
    timeline=[{'id':'s_1234abcd','text':'Test','start':0,'speech_end':1.5,'end':1.5}]
    project={'settings':Settings(resolution='540x960',fps=24,subtitles_enabled=False).model_dump(),
             'scenes':[{'id':'s_1234abcd','text':'Test','prompt':'','motion':'still','duration':None,
                        'effects':[{'effect':'impact','at':.25,'volume':.8}]}],
             'assets':{'images':{'s_1234abcd':{'path':'assets/images/scene.png','sha256':store.file_hash(image),'source':'manual','stale':False}},
                       'audio':{},'full_audio':None,'music':None}}
    narration={'path':'cache/narration.wav','duration':1.5,'timeline':timeline}
    movie,info=media.render_movie(tmp_path,project,narration,None,True,Context())
    assert info['duration']==pytest.approx(1.5,abs=.15)
    extracted=tmp_path/'output/extracted.wav'
    media.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(movie),'-map','0:a:0','-ar','48000','-ac','1','-c:a','pcm_s16le',str(extracted)])
    with wave.open(str(extracted),'rb') as source: samples=source.readframes(source.getnframes())
    assert max(abs(int.from_bytes(samples[i:i+2],'little',signed=True)) for i in range(0,len(samples),2))>500
