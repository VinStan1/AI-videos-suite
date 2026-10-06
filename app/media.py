from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

Image.MAX_IMAGE_PIXELS = 36_000_000
THREADS = str(max(1, min(8, int(os.getenv("FFMPEG_THREADS", "2")))))

# Short deterministic sounds synthesized by FFmpeg.  Frequencies are deliberately
# incommensurate inside each effect so the result has texture without relying on
# random generators, downloaded samples, models or network services.
SOUND_EFFECTS = {
    "wind": (2.8, "0.16*(sin(2*PI*173*t)+0.55*sin(2*PI*281*t)+0.35*sin(2*PI*419*t))*(0.35+0.65*pow(sin(PI*t/2.8),2))", "highpass=f=120,lowpass=f=1400,afade=t=in:d=0.18,afade=t=out:st=2.25:d=0.55"),
    "rumble": (2.2, "0.28*sin(2*PI*(42+4*sin(2*PI*0.7*t))*t)+0.12*sin(2*PI*67*t)", "lowpass=f=180,afade=t=in:d=0.05,afade=t=out:st=1.35:d=0.85"),
    "snap": (0.35, "exp(-18*t)*(0.55*sin(2*PI*320*t)+0.35*sin(2*PI*710*t)+0.18*sin(2*PI*1300*t))", "highpass=f=180,afade=t=out:st=0.18:d=0.17"),
    "impact": (1.4, "exp(-5*t)*(0.55*sin(2*PI*52*t)+0.28*sin(2*PI*83*t)+0.12*sin(2*PI*127*t))", "lowpass=f=420,afade=t=out:st=0.75:d=0.65"),
    "heartbeat": (1.3, "0.50*exp(-32*abs(t-0.12))*sin(2*PI*58*t)+0.38*exp(-35*abs(t-0.42))*sin(2*PI*64*t)", "lowpass=f=240,afade=t=out:st=0.75:d=0.55"),
    "static": (0.9, "0.16*(sin(2*PI*997*t)+0.7*sin(2*PI*1481*t)+0.5*sin(2*PI*2017*t))*exp(-2.2*t)", "highpass=f=650,lowpass=f=4200,afade=t=in:d=0.02,afade=t=out:st=0.55:d=0.35"),
    "whisper_texture": (2.4, "0.12*(sin(2*PI*(510+35*sin(2*PI*0.7*t))*t)+0.7*sin(2*PI*(830+52*sin(2*PI*0.43*t))*t)+0.45*sin(2*PI*1170*t))*pow(sin(PI*t/2.4),2)", "highpass=f=350,lowpass=f=2600,afade=t=in:d=0.2,afade=t=out:st=1.8:d=0.6"),
    "riser": (3.0, "0.20*(t/3)*sin(2*PI*(120*t+55*t*t))+0.10*(t/3)*sin(2*PI*(240*t+85*t*t))", "highpass=f=90,lowpass=f=3200,afade=t=in:d=0.1,afade=t=out:st=2.82:d=0.18"),
}

# Scene-level direction is intentionally lightweight: it changes timing, tone and
# dynamics after TTS without pretending to add emotions the selected model cannot
# perform.  Pitch chains compensate their own duration; only the leading atempo
# changes the delivery length.
VOICE_DELIVERY = {
    "natural": None,
    "ominous": "atempo=0.90,asetrate=46560,aresample=48000,atempo=1.030927,bass=g=2:f=120,treble=g=-1.5:f=3500,acompressor=threshold=0.12:ratio=2:attack=20:release=250:makeup=1.15,alimiter=limit=0.95",
    "emphatic": "atempo=0.94,equalizer=f=2200:t=q:w=1:g=1.8,acompressor=threshold=0.09:ratio=3:attack=8:release=160:makeup=1.30,alimiter=limit=0.95",
    "urgent": "atempo=1.08,asetrate=48720,aresample=48000,atempo=0.985222,equalizer=f=2600:t=q:w=1:g=1.4,acompressor=threshold=0.10:ratio=2.5:attack=6:release=100:makeup=1.20,alimiter=limit=0.95",
    "intimate": "atempo=0.90,highpass=f=70,lowpass=f=6500,bass=g=1.2:f=150,treble=g=-1:f=4200,volume=0.90,acompressor=threshold=0.08:ratio=2.5:attack=12:release=220:makeup=1.20,alimiter=limit=0.90",
}


def run(args: list[str], timeout=600):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise ValueError(f"File non leggibile o elaborazione non riuscita: {result.stderr.decode(errors='replace')[-2500:]}")
    return result.stdout


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams", "-of", "json", str(path)]))


def duration(path: Path) -> float:
    info = probe(path)
    try: value = float(info["format"]["duration"])
    except (ValueError, KeyError): raise ValueError("Durata audio non rilevabile.")
    if not 0.1 <= value <= 3600:
        raise ValueError("L'audio deve durare tra 0.1 secondi e 60 minuti.")
    return value


def normalize_audio(source: Path, target: Path, ctx=None):
    duration(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    args=["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
          "-protocol_whitelist","file,pipe","-i",str(source),"-map","0:a:0","-vn",
          "-ar","48000","-ac","1","-c:a","pcm_s16le","-t","3600",str(target)]
    (ctx.run(args) if ctx else run(args))


def apply_voice_delivery(source: Path, target: Path, preset: str, ctx) -> None:
    if preset not in VOICE_DELIVERY: raise ValueError("Preset di regia vocale non valido.")
    filters=VOICE_DELIVERY[preset]
    target.parent.mkdir(parents=True,exist_ok=True)
    if not filters:
        shutil.copy2(source,target); return
    ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
             "-i",str(source),"-map","0:a:0","-vn","-af",filters,
             "-ar","48000","-ac","1","-c:a","pcm_s16le",str(target)])


def aevalsrc(expression: str, duration: float) -> str:
    escaped=expression.replace("\\", "\\\\").replace("'", r"\'")
    return f"aevalsrc=exprs='{escaped}':sample_rate=48000:duration={duration}"


def generate_soundscape(profile: str, target: Path, ctx) -> None:
    expressions={
        "mist":"0.280*sin(2*PI*110*t)+0.160*sin(2*PI*165*t)+0.064*sin(2*PI*220*t)",
        "suspense":"0.320*sin(2*PI*55*t)*(0.65+0.35*sin(2*PI*0.125*t))+0.120*sin(2*PI*82.5*t)",
        "ritual":"0.240*sin(2*PI*(220/3)*t)+0.168*sin(2*PI*110*t)+0.096*sin(2*PI*(440/3)*t)",
    }
    expression=expressions.get(profile)
    if not expression: raise ValueError("Profilo di sottofondo non valido.")
    target.parent.mkdir(parents=True,exist_ok=True)
    ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
             # Render two cycles and discard the first one so the high/low-pass
             # filters have reached their periodic steady state at the loop seam.
             "-f","lavfi","-i",aevalsrc(expression,48),
             # The 24-second source is deliberately seamless.  Entry/exit fades
             # are applied once to the complete video, not once per loop.
             "-af","highpass=f=35,lowpass=f=1800,alimiter=limit=0.95,atrim=start=24:end=48,asetpts=PTS-STARTPTS",
             "-ar","48000","-ac","1","-c:a","pcm_s16le",str(target)])


def generate_effect_sample(effect: str, target: Path, ctx) -> None:
    spec=SOUND_EFFECTS.get(effect)
    if not spec: raise ValueError("Effetto sonoro non valido.")
    length,expression,filters=spec
    target.parent.mkdir(parents=True,exist_ok=True)
    ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
             "-f","lavfi","-i",aevalsrc(expression,length),"-af",filters+",alimiter=limit=0.95",
             "-ar","48000","-ac","1","-c:a","pcm_s16le",str(target)])


def join_voice_parts(parts: list[tuple[Path | None, float]], target: Path) -> list[float]:
    """Join normalized speech files and explicit silences; return speech offsets."""
    offsets=[]; cursor=0
    target.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(target),"wb") as dest:
        dest.setnchannels(1); dest.setsampwidth(2); dest.setframerate(48000)
        for path,pause in parts:
            if path is None:
                frames=round(48000*pause)
                dest.writeframesraw(b"\x00\x00"*frames); cursor+=frames
                continue
            offsets.append(cursor/48000)
            with wave.open(str(path),"rb") as src:
                if (src.getnchannels(),src.getsampwidth(),src.getframerate()) != (1,2,48000):
                    raise ValueError("Audio non normalizzato: ricaricalo dall'interfaccia.")
                while chunk:=src.readframes(48000):
                    dest.writeframesraw(chunk); cursor+=len(chunk)//2
    return offsets


def build_effects_track(root: Path, project: dict, timeline: list[dict], ctx) -> Path | None:
    """Create one sparse effects track aligned to the assembled narration."""
    from . import store
    rows={row["id"]:row for row in timeline}
    used=sorted({cue["effect"] for scene in project["scenes"] for cue in scene.get("effects",[])})
    if not used: return None
    samples={}
    for effect in used:
        path=root/"cache/sfx"/(effect+"_v1.wav")
        if not path.exists(): generate_effect_sample(effect,path,ctx)
        samples[effect]=path
    signature=store.digest([[s["id"],s.get("effects",[]),rows.get(s["id"])] for s in project["scenes"]]+["effects-v1"])
    target=root/"cache"/("effects_"+signature[:16]+".wav")
    if target.exists(): return target
    scene_tracks=[]
    try:
        for index,scene in enumerate(project["scenes"],1):
            row=rows.get(scene["id"])
            if not row: raise ValueError(f"Timeline mancante per la scena {index}.")
            length=float(row["end"])-float(row["start"])
            cues=scene.get("effects",[])
            for cue in cues:
                if float(cue["at"]) >= length:
                    raise ValueError(f"Effetto della scena {index} a {cue['at']:.2f}s oltre la durata della scena ({length:.2f}s).")
            temp=root/"cache"/("effect_scene_"+signature[:10]+f"_{index:03d}.wav")
            args=["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
                  "-f","lavfi","-i",f"anullsrc=r=48000:cl=mono:d={length:.9f}"]
            for cue in cues: args += ["-i",str(samples[cue["effect"]])]
            filters=[]; labels=["[0:a]"]
            for cue_index,cue in enumerate(cues,1):
                delay=round(float(cue["at"])*1000)
                label=f"e{cue_index}"
                filters.append(f"[{cue_index}:a]volume={float(cue['volume']):.6f},adelay={delay}:all=1,apad,atrim=duration={length:.9f}[{label}]")
                labels.append(f"[{label}]")
            filters.append("".join(labels)+f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[out]")
            args += ["-filter_complex",";".join(filters),"-map","[out]","-ar","48000","-ac","1","-c:a","pcm_s16le",str(temp)]
            ctx.run(args); scene_tracks.append(temp)
        joined=target.with_suffix(".part.wav")
        join_wavs([(path,"","") for path in scene_tracks],joined,0)
        os.replace(joined,target)
        return target
    finally:
        for path in scene_tracks: path.unlink(missing_ok=True)


def normalize_image(source: Path, target: Path):
    with Image.open(source) as im:
        im.load()
        im = ImageOps.exif_transpose(im)
        if im.width < 64 or im.height < 64:
            raise ValueError("Immagine troppo piccola: servono almeno 64 x 64 pixel.")
        if im.mode in ("RGBA","LA") or "transparency" in im.info:
            rgba = im.convert("RGBA"); bg=Image.new("RGBA",rgba.size,(12,15,20,255)); bg.alpha_composite(rgba); im=bg.convert("RGB")
        else: im=im.convert("RGB")
        im.thumbnail((4096,4096),Image.Resampling.LANCZOS)
        im.save(target,"PNG")
        return {"width":im.width,"height":im.height}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path),"rb") as f:
        return f.getnframes()/f.getframerate()


def join_wavs(parts: list[tuple[Path, str, str]], target: Path, pause: float) -> list[dict]:
    timeline=[]; cursor=0
    silence = b"\x00\x00" * round(48000*pause)
    with wave.open(str(target),"wb") as dest:
        dest.setnchannels(1); dest.setsampwidth(2); dest.setframerate(48000)
        for i,(path,sid,text) in enumerate(parts):
            with wave.open(str(path),"rb") as src:
                if (src.getnchannels(),src.getsampwidth(),src.getframerate()) != (1,2,48000):
                    raise ValueError("Audio non normalizzato: ricaricalo dall'interfaccia.")
                samples=src.getnframes()
                while chunk := src.readframes(48000): dest.writeframesraw(chunk)
            start=cursor/48000; cursor+=samples; speech_end=cursor/48000
            if i < len(parts)-1:
                dest.writeframesraw(silence); cursor+=len(silence)//2
            timeline.append(dict(id=sid,text=text,start=start,speech_end=speech_end,end=cursor/48000))
    return timeline


def full_timeline(scenes: list[dict], total: float) -> tuple[list[dict], str]:
    specified=[s.get("duration") is not None for s in scenes]
    if any(specified) and not all(specified):
        raise ValueError("Audio unico: imposta la durata per TUTTE le scene oppure lascia tutte vuote.")
    if all(specified):
        values=[float(s["duration"]) for s in scenes]
        if abs(sum(values)-total)>0.2:
            raise ValueError(f"Le durate delle scene sommano {sum(values):.2f}s, ma l'audio dura {total:.2f}s. La differenza deve essere <= 0.20s.")
        values[-1]+=total-sum(values); kind="manual"
    else:
        weights=[max(1,len(s["text"].split())) for s in scenes]
        values=[total*w/sum(weights) for w in weights]; kind="proportional"
    rows=[]; t=0.0
    for s,d in zip(scenes,values):
        rows.append(dict(id=s["id"],text=s["text"],start=t,end=t+d,speech_end=t+d)); t+=d
    rows[-1]["end"]=rows[-1]["speech_end"]=total
    return rows,kind


def prepare_frame(source: Path, output: Path, w: int, h: int, fit: str):
    # Oversampling reduces integer-coordinate jitter in FFmpeg's zoompan filter.
    size=(w*2,h*2)
    with Image.open(source) as im:
        im=im.convert("RGB")
        if fit=="cover": frame=ImageOps.fit(im,size,method=Image.Resampling.LANCZOS)
        else:
            frame=Image.new("RGB",size,(10,12,18))
            small=ImageOps.contain(im,size,method=Image.Resampling.LANCZOS)
            frame.paste(small,((size[0]-small.width)//2,(size[1]-small.height)//2))
        frame.save(output,"JPEG",quality=94)


def render_segment(image: Path, target: Path, scene: dict, frames: int, size: tuple[int,int], fps: int, settings: dict, ctx):
    w,h=size
    prepared=target.with_suffix(".jpg")
    prepare_frame(image,prepared,w,h,settings["fit"])
    n=max(1,frames-1)
    zoom="1"; x="iw/2-iw/zoom/2"; y="ih/2-ih/zoom/2"
    if scene["motion"]=="zoom_in": zoom=f"1+0.08*on/{n}"
    elif scene["motion"]=="zoom_out": zoom=f"1.08-0.08*on/{n}"
    elif scene["motion"]=="pan_left": zoom="1.08"; x=f"(iw-iw/zoom)*(1-on/{n})"
    elif scene["motion"]=="pan_right": zoom="1.08"; x=f"(iw-iw/zoom)*on/{n}"
    vf=f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p"
    temp=target.with_suffix(".part.mp4")
    ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
             "-i",str(prepared),"-vf",vf,"-filter_threads",THREADS,"-frames:v",str(frames),
             "-an","-c:v","libx264","-preset","veryfast","-crf","20","-threads",THREADS,
             "-pix_fmt","yuv420p","-r",str(fps),str(temp)])
    os.replace(temp,target); prepared.unlink(missing_ok=True)


def encode_frames(frames, target: Path, count: int, size, fps: int, ctx):
    """Stream frames to FFmpeg; retain only a few frames and permit cancellation."""
    temp=target.with_suffix(".part.mp4")
    args=["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
          "-f","rawvideo","-pixel_format","rgb24","-video_size",f"{size[0]}x{size[1]}",
          "-framerate",str(fps),"-i","pipe:0","-frames:v",str(count),"-an",
          "-c:v","libx264","-preset","veryfast","-crf","20","-threads",THREADS,
          "-pix_fmt","yuv420p",str(temp)]
    started=time.monotonic()
    with tempfile.TemporaryFile() as errors:
        proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        try:
            for frame in frames:
                if hasattr(ctx,"check"): ctx.check()
                if time.monotonic()-started > 7200: raise TimeoutError("Composizione oltre il tempo massimo.")
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            while proc.poll() is None:
                if hasattr(ctx,"check"): ctx.check()
                if time.monotonic()-started > 7200: raise TimeoutError("Codifica oltre il tempo massimo.")
                try: proc.wait(timeout=.2)
                except subprocess.TimeoutExpired: pass
            if proc.returncode:
                errors.seek(0);raise ValueError("Codifica composizione fallita: "+errors.read().decode(errors="replace")[-4500:])
            os.replace(temp,target)
        except BaseException as exc:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()
            if isinstance(exc,BrokenPipeError):
                errors.seek(0);raise ValueError("Codifica composizione fallita: "+errors.read().decode(errors="replace")[-4500:]) from exc
            raise
        finally:
            if proc.stdin and not proc.stdin.closed:
                try: proc.stdin.close()
                except BrokenPipeError: pass
            temp.unlink(missing_ok=True)


def last_video_frame(path: Path, size):
    data=run(["ffmpeg","-hide_banner","-loglevel","error","-sseof","-0.1","-i",str(path),
              "-vf",f"reverse,scale={size[0]}:{size[1]}","-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
    with Image.open(BytesIO(data)) as image: return image.convert("RGB")


def render_movie(root: Path, project: dict, narration: dict, ass: str | None, preview: bool, ctx) -> tuple[Path,dict]:
    from . import store
    from .composition import asset_definitions, asset_key, normalize_scene, required_asset_ids
    from .compositor import Compositor
    settings=project["settings"]
    size=(540,960) if preview else tuple(map(int,settings["resolution"].split("x")))
    fps=24 if preview else settings["fps"]
    total=narration["duration"]
    timeline=narration["timeline"]
    work=root/"cache"/"render"; work.mkdir(parents=True,exist_ok=True)
    files=[]; last_frame=0
    plans=[]
    for index,(scene,row) in enumerate(zip(project["scenes"],timeline)):
        ctx.progress(f"Montaggio scena {index+1}/{len(timeline)}",10+int(65*index/len(timeline)))
        available={a["id"] for a in asset_definitions(scene) if asset_key(scene["id"],a["id"]) in project["assets"]["images"]}
        plan=normalize_scene(scene,float(row["end"])-float(row["start"]),settings,available,
                             speech_duration=float(row.get("speech_end",row["end"]))-float(row["start"]))
        plans.append(plan)
        sources={}; signatures={}
        for asset_id in sorted(required_asset_ids(plan)):
            info=project["assets"]["images"].get(asset_key(scene["id"],asset_id))
            if not info: raise ValueError(f"Manca l'immagine della scena {index+1} ({scene['id']}), asset '{asset_id}'. Caricala o generala.")
            if info.get("stale"): raise ValueError(f"Immagine della scena {index+1} ({scene['id']}), asset '{asset_id}' non aggiornata. Rigenerala o confermala.")
            sources[asset_id]=store.safe_path(root,info["path"]); signatures[asset_id]=info["sha256"]
        frame_end=round(row["end"]*fps)
        if index==len(timeline)-1: frame_end=__import__("math").ceil(total*fps)
        frames=frame_end-last_frame; last_frame=frame_end
        if frames<1: raise ValueError("Una scena dura meno di un fotogramma.")
        if plan["legacy"]:
            # Preserve the original filters, frames, cache key and encode path.
            sig=store.digest([signatures["default"],scene["motion"],settings["fit"],frames,size,fps,"renderer-v1"])
        else:
            sig=store.digest([plan,signatures,settings["fit"],frames,size,fps,
                              files[-1].name if files and plan["transition"]["type"]!="cut" else None,"composition-v2"])
        segment=work/(sig+".mp4")
        if not segment.exists():
            if plan["legacy"]:
                render_segment(sources["default"],segment,scene,frames,size,fps,settings,ctx)
            else:
                previous=last_video_frame(files[-1],size) if files and plan["transition"]["type"]!="cut" else None
                compositor=Compositor(plan,sources,size,fps,settings["fit"],previous)
                encode_frames(compositor.frames(frames),segment,frames,size,fps,ctx)
        files.append(segment)
    store.atomic_json(root/"output"/"composition.json",{"version":"composition-v1","scenes":plans})
    concat=work/"concat.txt"
    concat.write_text("\n".join("file '"+p.name+"'" for p in files),"utf-8")
    silent=work/"silent.part.mp4"
    ctx.progress("Unione delle scene",78)
    ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","1","-i","concat.txt","-c","copy",silent.name],cwd=work)
    audio=store.safe_path(root,narration["path"])
    args=["ffmpeg","-hide_banner","-loglevel","error","-y","-threads",THREADS,
          "-i",str(silent),"-i",str(audio)]
    music=project["assets"].get("music")
    if music and music.get("stale"):
        raise ValueError("Il sottofondo generato non corrisponde al profilo selezionato. Rigeneralo o scollegalo.")
    if music:
        args += ["-stream_loop","-1","-i",str(store.safe_path(root,music["path"]))]
    effects=build_effects_track(root,project,timeline,ctx)
    if effects:
        args += ["-i",str(effects)]
    filters=["[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=sample_rates=48000:channel_layouts=mono,apad[voice]"]
    if music:
        filters += [f"[2:a]aformat=sample_rates=48000:channel_layouts=mono,volume={settings['music_volume']},atrim=duration={total},afade=t=in:d=0.8,afade=t=out:st={max(0,total-1.5)}:d=1.5[bg]",
                    ]
    if effects:
        effect_input=3 if music else 2
        filters += [f"[{effect_input}:a]aformat=sample_rates=48000:channel_layouts=mono,atrim=duration={total},apad[fx]"]
    mix_inputs="[voice]"+("[bg]" if music else "")+("[fx]" if effects else "")
    mix_count=1+int(bool(music))+int(bool(effects))
    filters += [mix_inputs+(f"amix=inputs={mix_count}:duration=first:normalize=0," if mix_count>1 else "")+"alimiter=limit=0.95[outa]"]
    if ass:
        (work/"captions.ass").write_text(ass,"utf-8")
        filters += ["[0:v]ass=filename=captions.ass[outv]"]
    output=root/"output"/("preview.mp4" if preview else "video_finale.mp4")
    temp=output.with_suffix(".part.mp4")
    args += ["-filter_complex",";".join(filters),"-filter_complex_threads",THREADS,
             "-map","[outv]" if ass else "0:v:0","-map","[outa]",
             "-c:v","libx264","-preset","veryfast","-crf","21","-threads",THREADS,
             "-c:a","aac","-b:a","192k","-ar","48000","-pix_fmt","yuv420p",
             "-t",f"{total:.6f}","-movflags","+faststart",str(temp)]
    ctx.progress("Audio, sottotitoli ed esportazione MP4",85)
    ctx.run(args,cwd=work)
    info=probe(temp)
    v=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    a=next((s for s in info["streams"] if s["codec_type"]=="audio"),None)
    if not v or not a or (v["width"],v["height"]) != size:
        raise ValueError("Controllo del video esportato non superato.")
    if abs(float(info["format"]["duration"])-total)>0.15:
        raise ValueError("La durata del video esportato non corrisponde alla narrazione.")
    os.replace(temp,output)
    return output,dict(width=size[0],height=size[1],fps=fps,duration=float(info["format"]["duration"]),size_bytes=output.stat().st_size)


def demo_card(path: Path, index: int):
    """Deliberately labelled technical placeholder, not an AI illustration."""
    im=Image.new("RGB",(540,960),(16,22,35)); draw=ImageDraw.Draw(im)
    for y in range(960):
        draw.line((0,y,540,y),fill=(16+y//70,22+y//50,35+y//40))
    draw.rectangle((38,68,502,892),outline=(98,136,139),width=3)
    draw.rectangle((68,122,472,128),fill=(140,185,179))
    # Font is supplied by the OS; no font binaries are distributed in this project.
    from PIL import ImageFont
    try:
        font=ImageFont.truetype("DejaVuSans.ttf",36); small=ImageFont.truetype("DejaVuSans.ttf",19)
    except OSError: font=small=ImageFont.load_default()
    draw.text((68,168),f"SCENA {index:02d}",font=font,fill=(232,236,232))
    draw.text((68,227),"SEGNAPOSTO TECNICO",font=small,fill=(155,180,181))
    draw.text((68,775),"Sostituisci con la tua immagine",font=small,fill=(208,213,210))
    draw.text((68,810),"Demo del montaggio / non AI",font=small,fill=(155,180,181))
    im.save(path)
