from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from . import captions, media, providers, store
from .models import Scene, split_story
from .composition import asset_definitions, asset_key, planned_assets


def sid(): return "s_"+uuid.uuid4().hex[:8]


def selected(p, scene_id=None):
    scenes=p["scenes"]
    if not scenes: raise ValueError("Prima crea o importa le scene.")
    if scene_id:
        scenes=[s for s in scenes if s["id"]==scene_id]
        if not scenes: raise ValueError("Scena non trovata.")
    return scenes


def split(p, request, ctx):
    if p["scenes"] and not request.get("force"):
        raise ValueError("Le scene esistono gia'. Conferma la nuova divisione o modificale nell'editor.")
    store.archive_json(p)
    p["scenes"]=[Scene(id=sid(),text=t).model_dump() for t in split_story(p["story"],request["target_words"])]
    p["assets"]["images"]={}; p["assets"]["audio"]={}
    store.invalidate(p,audio=True); store.save(p)
    ctx.progress(f"Create {len(p['scenes'])} scene senza riscrivere il copione",100)


def generate_prompts(p, request, ctx):
    items=selected(p,request.get("scene_id"))
    for i,s in enumerate(items):
        assets=asset_definitions(s) if request.get("asset_id") else planned_assets(s)
        if request.get("asset_id"):
            assets=[a for a in assets if a["id"]==request["asset_id"]]
            if not assets: raise ValueError(f"Scena {s['id']}: asset '{request['asset_id']}' mancante")
        for asset in assets:
            current_image=p["assets"]["images"].get(asset_key(s["id"],asset["id"]))
            if request.get("action")=="complete" and current_image and not current_image.get("stale"): continue
            if asset["prompt"].strip() and not request.get("force"): continue
            ctx.progress(f"Prompt scena {i+1}/{len(items)} / {asset['id']}",int(i*90/len(items)))
            prompt=providers.image_prompt(providers.spoken_text(s["text"]),p["story"],p["settings"]["visual_style"],p["settings"]["ollama_model"],ctx)
            if asset["id"]=="default": s["prompt"]=prompt
            else: next(a for a in s["assets"] if a["id"]==asset["id"])["prompt"]=prompt
            if current_image and current_image["source"]!="manual": current_image["stale"]=True
            store.invalidate(p); store.save(p)


def synthesize_voice(text, path, settings, ctx, delivery="natural"):
    source=path.with_name(path.stem+".delivery-source.wav")
    try:
        if settings["voice_provider"]=="huggingface":
            words=providers.huggingface_tts(text,source,settings["voice"],settings["speed"],ctx)
        elif settings["voice_provider"]=="kokoro":
            words=providers.kokoro(text,source,settings["voice"],settings["speed"],ctx)
        elif settings["voice_provider"]=="gemini":
            options=dict(voice_prompt=settings.get("voice_prompt",""),
                         max_attempts=settings.get("gemini_max_attempts",2))
            if settings.get("voice_directions"):
                options["voice_directions"]=settings["voice_directions"]
            words=providers.google_gemini_tts(text,source,settings["voice"],settings["speed"],delivery,ctx,
                                            **options)
        elif settings["voice_provider"]=="chirp":
            words=providers.google_chirp_tts(text,source,settings["voice"],settings["speed"],ctx)
        else:
            words=providers.espeak(text,source,settings["speed"],ctx)
        before=media.wav_seconds(source)
        # Gemini receives the scene direction natively; applying the FFmpeg
        # profile as well would exaggerate pace and pitch changes.
        media.apply_voice_delivery(source,path,"natural" if settings["voice_provider"]=="gemini" else delivery,ctx)
        after=media.wav_seconds(path)
        if words and before:
            scale=after/before
            words=[dict(word=word["word"],start=word["start"]*scale,end=word["end"]*scale) for word in words]
        return words
    finally:
        source.unlink(missing_ok=True)


def synthesize_voice_with_pauses(text, path, settings, ctx, delivery="natural"):
    # Chirp supports real SSML breaks, so keep the whole scene in one request.
    # This preserves prosody and avoids multiplying billable API calls.
    if settings["voice_provider"]=="chirp":
        return synthesize_voice(text,path,settings,ctx,delivery)
    plan=providers.speech_plan(text)
    if len(plan)==1:
        return synthesize_voice(plan[0][1],path,settings,ctx,delivery)
    parts=[]; word_groups=[]; speech_paths=[]
    try:
        for index,(kind,value) in enumerate(plan):
            if kind=="pause":
                parts.append((None,float(value))); continue
            segment=path.with_name(path.stem+f"_part_{index}.wav")
            words=synthesize_voice(value,segment,settings,ctx,delivery)
            parts.append((segment,0)); speech_paths.append(segment); word_groups.append(words)
        offsets=media.join_voice_parts(parts,path)
        if not all(word_groups): return []
        return [dict(word=word["word"],start=word["start"]+offset,end=word["end"]+offset)
                for words,offset in zip(word_groups,offsets) for word in words]
    finally:
        for segment in speech_paths: segment.unlink(missing_ok=True)


def full_voice_text(scenes):
    """One continuous transcript: paragraph breaks guide prosody without extra API calls."""
    return "\n\n".join(providers.spoken_text(s["text"]) for s in scenes)


def directed_voice_settings(settings, scenes, full=False):
    """Keep authored voice instructions separate from the spoken transcript."""
    if settings["voice_provider"]!="gemini": return settings
    directions=[]
    for index,scene in enumerate(scenes,1):
        prompt=scene.get("voice_prompt","").strip()
        if prompt:
            directions.append(f"Paragrafo {index} della narrazione: {prompt}" if full else prompt)
    if not directions: return settings
    return dict(settings,voice_directions="\n".join(directions))


def full_voice_signature(scenes, settings):
    signature=store.digest([
        full_voice_text(scenes),settings["voice_provider"],settings["voice"],settings["speed"],
        settings.get("voice_prompt","").strip() if settings["voice_provider"]=="gemini" else "",
        "full-voice-v1",
    ])
    if settings["voice_provider"]=="gemini" and any(s.get("voice_prompt","").strip() for s in scenes):
        signature=store.digest([signature,[s.get("voice_prompt","").strip() for s in scenes],"scene-voice-directions-v1"])
    return signature


def aligned_full_timeline(scenes, words, total):
    """Derive scene cuts from an aligned full-script word stream."""
    counts=[len(providers.spoken_text(s["text"]).split()) for s in scenes]
    if not counts or sum(counts)!=len(words) or any(count==0 for count in counts):
        raise ValueError("Impossibile ricavare i cambi scena dai timestamp della narrazione completa.")
    rows=[]; word_index=0; scene_start=0.0
    for index,(scene,count) in enumerate(zip(scenes,counts)):
        scene_words=words[word_index:word_index+count]; word_index+=count
        speech_end=scene_words[-1]["end"]
        if index==len(scenes)-1:
            scene_end=total
        else:
            next_start=words[word_index]["start"]
            scene_end=(speech_end+next_start)/2
        rows.append(dict(id=scene["id"],text=scene["text"],start=scene_start,
                         speech_end=speech_end,end=scene_end))
        scene_start=scene_end
    return rows


def generate_voice(p, request, ctx):
    mode=p["settings"]["audio_mode"]
    if mode=="full":
        if p["assets"].get("full_audio",{}).get("source")=="manual": return
        raise ValueError("Modalita' audio unico: carica la narrazione oppure scegli 'audio per scena'.")
    if mode=="full_generated":
        if request.get("scene_id"):
            raise ValueError("La narrazione completa si genera tutta insieme, non per singola scena.")
        scenes=selected(p); root=store.project_dir(p["id"]); settings=p["settings"]
        text=full_voice_text(scenes); signature=full_voice_signature(scenes,settings)
        existing=p["assets"].get("full_audio")
        if (existing and existing.get("source")!="manual" and existing.get("signature")==signature
                and not existing.get("stale") and not request.get("force")):
            return
        ctx.progress("Genero la narrazione completa in una sola richiesta TTS",10)
        path=root/"assets/audio"/("full_"+uuid.uuid4().hex[:8]+".wav")
        words=synthesize_voice(text,path,directed_voice_settings(settings,scenes,full=True),ctx,"natural")
        p["assets"]["full_audio"]=store.asset(
            root,str(path.relative_to(root)),settings["voice_provider"],signature=signature,
            text_sha=store.digest(text),duration=media.wav_seconds(path),words=words,
            stale=False,delivery="natural",generated_full=True,
        )
        store.invalidate(p,audio=True); store.save(p)
        ctx.progress("Narrazione completa generata",100)
        return
    root=store.project_dir(p["id"]); items=selected(p,request.get("scene_id")); settings=p["settings"]
    for i,s in enumerate(items):
        ctx.progress(f"Voce scena {i+1}/{len(items)}",int(i*90/len(items)))
        existing=p["assets"]["audio"].get(s["id"])
        delivery=s.get("delivery","natural")
        sig=store.digest([s["text"],settings["voice_provider"],settings["voice"],settings["speed"],delivery,"delivery-v1"])
        if settings["voice_provider"]=="gemini" and settings.get("voice_prompt","").strip():
            sig=store.digest([sig,settings["voice_prompt"].strip()])
        if settings["voice_provider"]=="gemini" and s.get("voice_prompt","").strip():
            sig=store.digest([sig,s["voice_prompt"].strip(),"scene-voice-directions-v1"])
        if existing and existing["source"]=="manual":
            if existing.get("stale"): raise ValueError("Audio manuale da riconfermare dopo la modifica del testo, scena "+s["id"])
            continue
        if existing and existing.get("signature")==sig and not existing.get("stale") and not request.get("force"): continue
        path=root/"assets/audio"/(s["id"]+"_"+uuid.uuid4().hex[:8]+".wav")
        words=synthesize_voice_with_pauses(s["text"],path,directed_voice_settings(settings,[s]),ctx,delivery)
        p["assets"]["audio"][s["id"]]=store.asset(root,str(path.relative_to(root)),settings["voice_provider"],
                 signature=sig,text_sha=store.digest(s["text"]),duration=media.wav_seconds(path),words=words,stale=False,delivery=delivery)
        store.invalidate(p,audio=True); store.save(p)


def generate_music(p, request, ctx):
    root=store.project_dir(p["id"]); profile=p["settings"]["music_preset"]
    ctx.progress("Creo sottofondo originale locale",20)
    path=root/"assets/music"/("procedural_"+uuid.uuid4().hex[:8]+".wav")
    media.generate_soundscape(profile,path,ctx)
    p["assets"]["music"]=store.asset(root,str(path.relative_to(root)),"generated",duration=media.wav_seconds(path),stale=False,profile=profile,generator="soundscape-v2")
    store.invalidate(p); store.save(p)


def generate_images(p, request, ctx):
    root=store.project_dir(p["id"]); items=selected(p,request.get("scene_id"))
    for i,s in enumerate(items):
        assets=asset_definitions(s) if request.get("asset_id") else planned_assets(s)
        if request.get("asset_id"):
            assets=[a for a in assets if a["id"]==request["asset_id"]]
            if not assets: raise ValueError(f"Scena {s['id']}: asset '{request['asset_id']}' mancante")
        for asset in assets:
            key=asset_key(s["id"],asset["id"])
            ctx.progress(f"Immagine scena {i+1}/{len(items)} / {asset['id']}",int(i*90/len(items)))
            existing=p["assets"]["images"].get(key)
            if existing and existing["source"]=="manual": continue
            if existing and not existing.get("stale") and not request.get("force"): continue
            prompt=asset["prompt"].strip()
            if not prompt: raise ValueError(f"Scrivi o genera il prompt visivo della scena {s['id']}, asset '{asset['id']}'")
            path=root/"assets/images"/(key+"_"+uuid.uuid4().hex[:8]+".png")
            seed=int(uuid.uuid4().hex[:8],16); provider=p["settings"]["image_provider"]
            generator={"cloudflare":providers.cloudflare_image,"huggingface":providers.huggingface_image,"comfyui":providers.comfy_image}[provider]
            generator(prompt,p["settings"]["visual_style"],path,seed,ctx)
            p["assets"]["images"][key]=store.asset(root,str(path.relative_to(root)),provider,seed=seed,stale=False)
            store.invalidate(p); store.save(p)


def assemble_audio(p, ctx):
    selected(p); root=store.project_dir(p["id"])
    settings=p["settings"]
    if settings["audio_mode"] in ("full","full_generated"):
        info=p["assets"].get("full_audio")
        if not info:
            message=("Genera la narrazione completa." if settings["audio_mode"]=="full_generated"
                     else "Carica l'audio della narrazione completa.")
            raise ValueError(message)
        if settings["audio_mode"]=="full" and info.get("source")!="manual":
            raise ValueError("Modalita' audio caricato: carica la narrazione completa.")
        if settings["audio_mode"]=="full_generated":
            expected=full_voice_signature(p["scenes"],settings)
            if info.get("source")=="manual" or info.get("signature")!=expected or info.get("stale"):
                raise ValueError("La narrazione completa generata non e' aggiornata. Rigenerala.")
        src=store.safe_path(root,info["path"]); length=media.wav_seconds(src)
        timeline,kind=media.full_timeline(p["scenes"],length)
        signature=store.digest([info["sha256"],timeline,settings["audio_mode"],"full-v2"])
        current=p.get("narration") or {}
        if current.get("signature")==signature and store.safe_path(root,current["path"]).exists():
            return current
        words=info.get("words",[])
        path=root/"cache"/("narration_"+signature[:16]+".wav")
        if not path.exists(): shutil.copy2(src,path)
    else:
        parts=[]; sources=[]
        for s in p["scenes"]:
            info=p["assets"]["audio"].get(s["id"])
            if not info: raise ValueError("Manca l'audio della scena "+s["id"]+". Caricalo o genera la voce.")
            if info.get("stale"): raise ValueError("Audio non aggiornato per "+s["id"]+". Rigeneralo o riconferma quello manuale.")
            parts.append((store.safe_path(root,info["path"]),s["id"],providers.spoken_text(s["text"])))
            sources.append([s["id"],s["text"],info["sha256"]])
        signature=store.digest([sources,settings["pause_seconds"],"scenes-v1"])
        if p.get("narration",{}) and p["narration"].get("signature")==signature and store.safe_path(root,p["narration"]["path"]).exists():
            return p["narration"]
        path=root/"cache"/("narration_"+signature[:16]+".wav")
        temp=path.with_suffix(".part.wav")
        timeline=media.join_wavs(parts,temp,settings["pause_seconds"]); os.replace(temp,path)
        length=media.wav_seconds(path); kind="per_scene_audio"; words=[]
        complete=True
        for row in timeline:
            local=p["assets"]["audio"][row["id"]].get("words",[])
            if not local: complete=False; break
            words.extend(dict(word=w["word"],start=w["start"]+row["start"],end=w["end"]+row["start"]) for w in local)
        if not complete: words=[]
    p["narration"]=store.asset(root,str(path.relative_to(root)),"assembled",signature=signature,
               duration=length,timeline=timeline,timing_kind=kind,words=words)
    if p.get("subtitles"):
        sub=p["subtitles"]
        if sub.pop("accept_next_audio",False):
            sub.update(audio_sha=p["narration"]["sha256"],stale=False)
        elif sub.get("audio_sha") and sub["audio_sha"]!=p["narration"]["sha256"]: sub["stale"]=True
        elif sub.get("audio_sha")==p["narration"]["sha256"]: sub["stale"]=False
    store.atomic_json(root/"output"/"timeline.json",p["narration"])
    store.save(p); return p["narration"]


def generate_captions(p, request, ctx):
    narration=assemble_audio(p,ctx)
    current=p.get("subtitles")
    if current and current["source"]=="manual":
        if current.get("stale"): raise ValueError("L'audio e' cambiato: verifica e salva di nuovo l'SRT manuale.")
        return
    if current and not current.get("stale") and not request.get("force"): return
    root=store.project_dir(p["id"]); method=request.get("caption_method","timings")
    words=narration.get("words",[]); timestamp_details={}
    if method=="whisper":
        ctx.progress("Trascrizione italiana dell'audio (Whisper CPU)",20)
        recognized=providers.whisper(store.safe_path(root,narration["path"]),ctx)
        script=" ".join(providers.spoken_text(row["text"]) for row in narration["timeline"])
        words,alignment=captions.align_script_words(script,recognized,narration["duration"])
        source="whisper_script"; cues=captions.words_to_cues(words)
        timestamp_details={"alignment":alignment,"whisper_words":recognized}
        if p["settings"]["audio_mode"] in ("full","full_generated"):
            narration["timeline"]=aligned_full_timeline(p["scenes"],words,narration["duration"])
            narration["timing_kind"]="whisper_aligned"
            narration["words"]=words
            store.atomic_json(root/"output"/"timeline.json",narration)
    elif method=="timings" and words:
        source="tts_timings"; cues=captions.words_to_cues(words)
    elif method=="estimate" or request.get("allow_estimated"):
        source="estimate"; cues=captions.estimated_cues(narration["timeline"])
    else:
        raise ValueError("Timestamp parola-per-parola non disponibili. Carica un SRT, attiva Whisper oppure scegli esplicitamente 'Bozza stimata'.")
    if not cues: raise ValueError("Nessun sottotitolo generato.")
    name="assets/captions_"+uuid.uuid4().hex[:8]+".srt"
    store.safe_path(root,name).write_text(captions.to_srt(cues),"utf-8")
    if words:
        store.atomic_json(root/"output"/"word_timestamps.json",{
            "source":source,"audio_sha":narration["sha256"],"words":words,**timestamp_details
        })
    else:
        (root/"output"/"word_timestamps.json").unlink(missing_ok=True)
    p["subtitles"]=store.asset(root,name,source,audio_sha=narration["sha256"],stale=False,cues=len(cues),
                                  **({"alignment":timestamp_details["alignment"]} if timestamp_details else {}))
    store.invalidate(p); store.save(p)


def render(p, request, ctx):
    root=store.project_dir(p["id"]); narration=assemble_audio(p,ctx)
    warnings=[]
    if narration["timing_kind"]=="proportional": warnings.append("Audio unico: i cambi scena sono proporzionali alla lunghezza del testo, non allineati alle parole. Imposta le durate manuali per precisione.")
    if any(a.get("source")=="demo" for a in p["assets"]["images"].values()): warnings.append("Sono presenti immagini segnaposto tecniche.")
    ass=None
    if p["settings"]["subtitles_enabled"]:
        sub=p.get("subtitles")
        if not sub: raise ValueError("Mancano i sottotitoli: caricali, generali o disattivali nelle impostazioni.")
        if sub.get("stale"): raise ValueError("I sottotitoli non corrispondono all'ultima versione dell'audio. Verificali o rigenerali.")
        cues=captions.parse_srt(store.safe_path(root,sub["path"]).read_text("utf-8"))
        if cues[-1]["end"]>narration["duration"]+0.15:
            raise ValueError(f"Ultimo sottotitolo a {cues[-1]['end']:.2f}s oltre la durata audio {narration['duration']:.2f}s.")
        if sub["source"]=="estimate": warnings.append("Sottotitoli stimati: tempi approssimativi, non allineamento vocale.")
        if sub["source"]=="whisper": warnings.append("Sottotitoli trascritti: controlla nomi propri, punteggiatura e parole riconosciute.")
        if sub["source"]=="whisper_script": warnings.append("Sottotitoli allineati con Whisper e corretti dal copione: controlla i tagli temporali nei passaggi molto rapidi.")
        if any(len(c["text"])>80 for c in cues): warnings.append("Alcuni sottotitoli sono lunghi: controlla che non coprano troppo l'immagine.")
        ass=captions.make_ass(cues,p["settings"])
        (root/"output"/"sottotitoli.ass").write_text(ass,"utf-8")
        (root/"output"/"sottotitoli.srt").write_text(captions.to_srt(cues),"utf-8")
    ctx.progress("Controlli prima del montaggio",5)
    preview=request.get("preview",False)
    path,info=media.render_movie(root,p,narration,ass,preview,ctx)
    p["preview" if preview else "output"]=store.asset(root,str(path.relative_to(root)),"render",stale=False,**info)
    p["warnings"]=warnings
    store.atomic_json(root/"output"/"report.json",{"checks":"passed","warnings":warnings,"video":info,"timing":narration["timing_kind"],"subtitles":p.get("subtitles",{}),"version":"1.0.0"})
    store.save(p)


def execute(pid, request, ctx):
    p=store.load(pid); action=request["action"]
    if action=="complete":
        if not p["scenes"]: split(p,request,ctx)
        if request.get("generate_images"):
            generate_prompts(p,request,ctx); generate_images(p,request,ctx)
        generate_voice(p,request,ctx)
        assemble_audio(p,ctx)
        if p["settings"]["subtitles_enabled"]: generate_captions(p,request,ctx)
        render(p,request,ctx)
    elif action=="assemble_audio": assemble_audio(p,ctx)
    else:
        {"split":split,"prompts":generate_prompts,"voice":generate_voice,"images":generate_images,
         "captions":generate_captions,"render":render,"music":generate_music}[action](p,request,ctx)
