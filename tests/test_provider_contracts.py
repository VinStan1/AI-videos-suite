"""Mocked API contract tests; they do NOT run or validate AI model inference."""
import base64
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from app import providers, media, pipeline
from app.models import Storyboard

class Context:
    def check(self): pass
    def run(self,args,**kwargs): return media.run(args)


def wav_bytes():
    b=io.BytesIO()
    with wave.open(b,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\x00\x00'*48000)
    return b.getvalue()


def test_ollama_contract(monkeypatch):
    def request(method,url,**kw):
        assert method=='POST' and url.endswith('/api/generate')
        assert kw['json']['format']['required']==['prompt']
        assert kw['json']['keep_alive']==0 and kw['json']['stream'] is False
        return SimpleNamespace(json=lambda:{'response':json.dumps({'prompt':'A misty lake at dusk.'})})
    monkeypatch.setattr(providers,'request',request)
    assert providers.image_prompt('Un lago.','Storia','No text','qwen2.5:3b',Context())=='A misty lake at dusk.'


def test_comfyui_contract(monkeypatch,tmp_path):
    b=io.BytesIO();Image.new('RGB',(100,160),'gray').save(b,'PNG')
    calls=[]
    def request(method,url,**kw):
        calls.append(url)
        if url.endswith('/prompt'):
            assert isinstance(kw['json']['prompt']['5']['inputs']['seed'],int)
            return SimpleNamespace(json=lambda:{'prompt_id':'example'})
        if '/history/' in url:return SimpleNamespace(json=lambda:{'example':{'outputs':{'7':{'images':[{'filename':'sample.png','subfolder':'','type':'output'}]}}}})
        if url.endswith('/view'):return SimpleNamespace(content=b.getvalue())
        if url.endswith('/free'):return SimpleNamespace(json=lambda:{})
        raise AssertionError(url)
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'image.png'
    providers.comfy_image('Lake','Style',output,42,Context())
    assert output.is_file() and len(calls)==4


def test_kokoro_captioned_contract(monkeypatch,tmp_path):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,json):
            assert url.endswith('/dev/captioned_speech')
            assert json['voice']=='im_nicola'
            return httpx.Response(200,json={'audio':base64.b64encode(wav_bytes()).decode(),
                'timestamps':[{'word':'Ciao','start_time':0,'end_time':.4},{'word':'mondo','start_time':.45,'end_time':.9}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(providers.httpx,'Client',Client)
    out=tmp_path/'voice.wav';words=providers.kokoro('Ciao mondo',out,'im_nicola',1,Context())
    assert out.exists() and len(words)==2 and words[1]['start']==.45


def test_kokoro_no_timestamp_fallback(monkeypatch,tmp_path):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,json):return httpx.Response(422,request=httpx.Request('POST',url))
    monkeypatch.setattr(providers.httpx,'Client',Client)
    def request(method,url,**kwargs):
        assert url.endswith('/v1/audio/speech');return SimpleNamespace(content=wav_bytes())
    monkeypatch.setattr(providers,'request',request)
    assert providers.kokoro('Ciao mondo',tmp_path/'voice.wav','im_nicola',1,Context())==[]


def test_huggingface_image_contract(monkeypatch,tmp_path):
    b=io.BytesIO();Image.new('RGB',(100,160),'gray').save(b,'PNG')
    monkeypatch.setenv('HF_TOKEN','hf_test')
    def request(method,url,**kwargs):
        assert method=='POST' and url.endswith('/'+providers.HF_IMAGE_MODEL)
        assert kwargs['headers']=={'Authorization':'Bearer hf_test'}
        assert kwargs['json']=={'inputs':'Lake\nStyle','parameters':{'seed':42}}
        return SimpleNamespace(content=b.getvalue())
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'image.png'
    providers.huggingface_image('Lake','Style',output,42,Context())
    assert output.is_file()


def test_huggingface_tts_requires_token(monkeypatch,tmp_path):
    monkeypatch.delenv('HF_TOKEN',raising=False)
    with pytest.raises(RuntimeError,match='HF_TOKEN'):
        providers.huggingface_tts('Ciao',tmp_path/'voice.wav','',1,Context())


def test_google_gemini_tts_contract(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY','gemini_test_key')
    pcm=b'\x00\x00'*24000
    def request(method,url,**kwargs):
        assert method=='POST' and url.endswith('/'+providers.GOOGLE_GEMINI_TTS_MODEL+':generateContent')
        assert kwargs['headers']['x-goog-api-key']=='gemini_test_key'
        config=kwargs['json']['generationConfig']
        assert config['responseModalities']==['AUDIO']
        assert config['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName']=='Charon'
        prompt=kwargs['json']['contents'][0]['parts'][0]['text']
        assert 'TESTO:\nPoi arrivo il silenzio.' in prompt and 'Tono cupo e inquietante' in prompt
        return SimpleNamespace(json=lambda:{'candidates':[{'content':{'parts':[{'inlineData':{
            'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(pcm).decode()
        }}]}}]})
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'gemini.wav'
    assert providers.google_gemini_tts('Poi arrivo il silenzio.',output,'Charon',.95,'ominous',Context())==[]
    assert output.is_file()
    with wave.open(str(output),'rb') as audio:
        assert (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())==(1,2,48000)


def test_google_gemini_tts_requires_key(monkeypatch,tmp_path):
    monkeypatch.delenv('GOOGLE_GEMINI_TTS_KEY',raising=False)
    with pytest.raises(RuntimeError,match='GOOGLE_GEMINI_TTS_KEY'):
        providers.google_gemini_tts('Ciao',tmp_path/'voice.wav','Charon',1,'natural',Context())


def test_google_gemini_tts_retries_other_without_audio(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY','gemini_test_key')
    monkeypatch.setattr(providers.time,'sleep',lambda _seconds: None)
    pcm=b'\x00\x00'*24000
    responses=[
        {'candidates':[{'finishReason':'OTHER'}]},
        {'candidates':[{'content':{'parts':[{'inlineData':{
            'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(pcm).decode()
        }}]}}]},
    ]
    prompts=[]
    def request(_method,_url,**kwargs):
        prompts.append(kwargs['json']['contents'][0]['parts'][0]['text'])
        return SimpleNamespace(json=lambda:responses.pop(0))
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'retried.wav'
    voice_prompt='Voce profonda e uniforme.'
    assert providers.google_gemini_tts('Non sono uomini!',output,'Charon',.96,'emphatic',Context(),voice_prompt=voice_prompt)==[]
    assert output.is_file()
    assert len(prompts)==2 and prompts[0]!=prompts[1]
    assert all(voice_prompt in prompt for prompt in prompts)


def test_google_gemini_tts_reports_other_after_retry(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY','gemini_test_key')
    monkeypatch.setattr(providers.time,'sleep',lambda _seconds: None)
    monkeypatch.setattr(providers,'request',lambda *args,**kwargs:SimpleNamespace(
        json=lambda:{'candidates':[{'finishReason':'OTHER','finishMessage':'unknown termination'}]}
    ))
    with pytest.raises(ValueError,match='due tentativi'):
        providers.google_gemini_tts('Ciao',tmp_path/'voice.wav','Charon',1,'natural',Context())


def test_google_gemini_tts_quota_mode_does_not_retry(monkeypatch,tmp_path):
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY','gemini_test_key')
    calls=[]
    def request(*args,**kwargs):
        calls.append(kwargs['json'])
        return SimpleNamespace(json=lambda:{'candidates':[{'finishReason':'OTHER'}]})
    monkeypatch.setattr(providers,'request',request)
    with pytest.raises(ValueError,match='Nessun tentativo automatico aggiuntivo'):
        providers.google_gemini_tts('Ciao',tmp_path/'voice.wav','Charon',1,'natural',Context(),max_attempts=1)
    assert len(calls)==1


def test_bray_road_storyboard_uses_ten_calls_with_same_voice_prompt(monkeypatch,tmp_path):
    path=Path(__file__).parents[1]/'examples/the-beast-of-bray-road.json'
    board=Storyboard.model_validate_json(path.read_text('utf-8'))
    monkeypatch.setenv('GOOGLE_GEMINI_TTS_KEY','gemini_test_key')
    monkeypatch.setattr(media,'normalize_audio',lambda source,target,ctx:target.write_bytes(source.read_bytes()))
    prompts=[]
    def request(*args,**kwargs):
        body=kwargs['json'];prompts.append(body['contents'][0]['parts'][0]['text'])
        assert body['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName']==board.settings.voice
        return SimpleNamespace(json=lambda:{'candidates':[{'content':{'parts':[{'inlineData':{
            'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(b'\x00\x00'*2400).decode()
        }}]}}]})
    monkeypatch.setattr(providers,'request',request)
    for index,scene in enumerate(board.scenes):
        assert scene.delivery=='natural'
        pipeline.synthesize_voice_with_pauses(scene.text,tmp_path/f'{index}.wav',board.settings.model_dump(),Context(),scene.delivery)
    assert len(prompts)==len(board.scenes)==10
    assert all(board.settings.voice_prompt in prompt for prompt in prompts)
    assert board.story==' '.join(scene.text for scene in board.scenes)


def test_google_chirp_tts_contract(monkeypatch,tmp_path):
    monkeypatch.setattr(providers,'google_cloud_tts_headers',lambda:{'Authorization':'Bearer test'})
    audio=wav_bytes()
    def request(method,url,**kwargs):
        assert method=='POST' and url==providers.GOOGLE_CLOUD_TTS_API_URL
        assert kwargs['headers']['Authorization']=='Bearer test'
        body=kwargs['json']
        assert body['input']=={'text':'Poi arrivo il silenzio.'}
        assert body['voice']=={'languageCode':'it-IT','name':'it-IT-Chirp3-HD-Charon'}
        assert body['audioConfig']=={'audioEncoding':'LINEAR16','speakingRate':.95}
        return SimpleNamespace(json=lambda:{'audioContent':base64.b64encode(audio).decode()})
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'chirp.wav'
    assert providers.google_chirp_tts('Poi arrivo il silenzio.',output,'Charon',.95,Context())==[]
    assert output.is_file()


def test_google_chirp_translates_pauses_to_safe_ssml():
    value=providers.chirp_synthesis_input('A & B. [[pausa=0.6]] Poi <silenzio>.')
    assert value=={'ssml':'<speak>A &amp; B. <break time="0.6s"/> Poi &lt;silenzio&gt;.</speak>'}


def test_google_chirp_requires_credentials_file(monkeypatch):
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS',raising=False)
    with pytest.raises(RuntimeError,match='GOOGLE_APPLICATION_CREDENTIALS'):
        providers.google_cloud_tts_headers()


def test_cloudflare_image_contract(monkeypatch,tmp_path):
    b=io.BytesIO();Image.new('RGB',(100,160),'gray').save(b,'JPEG')
    monkeypatch.setenv('CF_ACCOUNT_ID','account')
    monkeypatch.setenv('CF_API_TOKEN','token')
    def request(method,url,**kwargs):
        assert method=='POST' and url.endswith('/account/ai/run/'+providers.CF_IMAGE_MODEL)
        assert kwargs['headers']=={'Authorization':'Bearer token'}
        assert kwargs['json']['steps']==8
        assert kwargs['json']['prompt'].startswith('Vertical 9:16 TikTok video composition.')
        return SimpleNamespace(json=lambda:{'success':True,'result':{'image':base64.b64encode(b.getvalue()).decode()}})
    monkeypatch.setattr(providers,'request',request)
    output=tmp_path/'image.png'
    providers.cloudflare_image('Lake, no gore','non gore style',output,42,Context())
    assert output.is_file()


def test_cloudflare_safety_error_is_actionable(monkeypatch,tmp_path):
    monkeypatch.setenv('CF_ACCOUNT_ID','account')
    monkeypatch.setenv('CF_API_TOKEN','token')
    def request(*args,**kwargs):
        raise RuntimeError('HTTP 400. {"errors":[{"code":8007}]}')
    monkeypatch.setattr(providers,'request',request)
    with pytest.raises(RuntimeError,match='bloccato il prompt'):
        providers.cloudflare_image('Lake','Style',tmp_path/'image.png',42,Context())


def test_cloudflare_image_requires_configuration(monkeypatch,tmp_path):
    monkeypatch.delenv('CF_ACCOUNT_ID',raising=False)
    monkeypatch.delenv('CF_API_TOKEN',raising=False)
    with pytest.raises(RuntimeError,match='CF_ACCOUNT_ID'):
        providers.cloudflare_image('Lake','Style',tmp_path/'image.png',42,Context())


def test_whisper_contract(monkeypatch,tmp_path):
    path=tmp_path/'voice.wav';path.write_bytes(wav_bytes())
    def request(method,url,**kwargs):
        assert kwargs['data']['language']=='it' and 'file' in kwargs['files']
        return SimpleNamespace(json=lambda:{'words':[{'word':'Ciao','start':0,'end':.7}]})
    monkeypatch.setattr(providers,'request',request)
    assert providers.whisper(path,Context())==[{'word':'Ciao','start':0,'end':.7}]
