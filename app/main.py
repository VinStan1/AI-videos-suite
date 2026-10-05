from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__, captions, media, pipeline, providers, store
from .jobs import JOBS
from .models import CaptionText, JobRequest, ProjectCreate, Scene, Storyboard

STATIC=Path(__file__).parent/"static"
MAX_UPLOAD=int(os.getenv("MAX_UPLOAD_MB","250"))*1024*1024
AUDIO_EXTENSIONS=(".wav",".mp3",".m4a",".aac",".ogg",".flac",".opus",".mp4",".webm")


@asynccontextmanager
async def lifespan(app):
    store.DATA_ROOT.mkdir(parents=True,exist_ok=True)
    JOBS.runner=pipeline.execute; JOBS.recover()
    yield


app=FastAPI(title="AI Video Studio",version=__version__,lifespan=lifespan,
            description="Pipeline locale. Non esporre questo servizio su Internet.")
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","testserver","cryptid-studio"])
app.mount("/static",StaticFiles(directory=STATIC),name="static")


@app.middleware("http")
async def local_guard(request: Request, call_next):
    if request.method not in ("GET","HEAD","OPTIONS"):
        origin=request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail":"Origine non autorizzata."},status_code=403)
        try:
            if int(request.headers.get("content-length","0"))>MAX_UPLOAD:
                return JSONResponse({"detail":"Upload troppo grande."},status_code=413)
        except ValueError: return JSONResponse({"detail":"Content-Length non valido."},status_code=400)
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    if request.url.path=="/":
        response.headers["Content-Security-Policy"]="default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(ValueError)
async def bad_input(request,exc): return JSONResponse({"detail":str(exc)},status_code=400)


@app.exception_handler(FileNotFoundError)
async def not_found(request,exc): return JSONResponse({"detail":"Progetto o file non trovato."},status_code=404)


@app.get("/")
def index(): return FileResponse(STATIC/"index.html")


@app.get("/api/health")
def health(): return {"status":"ok","version":__version__,"mode":"local","ffmpeg":bool(shutil.which("ffmpeg"))}


@app.get("/api/services")
def services(): return providers.status()


@app.get("/api/projects")
def projects(): return store.list_projects()


@app.post("/api/projects",status_code=201)
def create(body:ProjectCreate): return store.create(body.title,body.story)


@app.get("/api/projects/{pid}")
def read(pid:str): return store.load(pid)


@app.get("/api/projects/{pid}/storyboard")
def get_storyboard(pid:str):
    p=store.load(pid)
    return {k:p[k] for k in ("title","story","scenes","settings","revision")}


@app.put("/api/projects/{pid}/storyboard")
def edit(pid:str,body:Storyboard):
    with JOBS.lock:
        JOBS.assert_idle(pid); p=store.load(pid); new=body.model_dump()
        if body.revision is not None and body.revision!=p["revision"]:
            raise HTTPException(409,"Il progetto e' stato aggiornato. Ricarica la pagina prima di salvare.")
        store.archive_json(p)
        old={s["id"]:s for s in p["scenes"]}
        old_settings=p["settings"]
        new_voice=any(old_settings[k]!=new["settings"][k] for k in ("voice","voice_provider","speed"))
        if new["settings"]["voice_provider"]=="gemini":
            new_voice |= old_settings.get("voice_prompt","").strip()!=new["settings"]["voice_prompt"].strip()
        music_profile_changed=old_settings.get("music_preset","mist")!=new["settings"]["music_preset"]
        scene_texts_changed=(
            [(s["id"],s["text"]) for s in p["scenes"]] !=
            [(s["id"],s["text"]) for s in new["scenes"]]
        )
        audio_changed=(old_settings["pause_seconds"]!=new["settings"]["pause_seconds"] or
                       old_settings["audio_mode"]!=new["settings"]["audio_mode"] or
                       [(s["id"],s["text"],s["duration"]) for s in p["scenes"]] !=
                       [(s["id"],s["text"],s["duration"]) for s in new["scenes"]])
        for s in new["scenes"]:
            previous=old.get(s["id"])
            audio=p["assets"]["audio"].get(s["id"])
            image=p["assets"]["images"].get(s["id"])
            changed=previous and previous["text"]!=s["text"]
            delivery_changed=previous and previous.get("delivery","natural")!=s.get("delivery","natural")
            if audio and (changed or ((new_voice or delivery_changed) and audio["source"]!="manual")):
                audio["stale"]=True; audio_changed=True
            if image and image["source"]!="manual" and (changed or
                (previous and previous["prompt"]!=s["prompt"]) or old_settings["visual_style"]!=new["settings"]["visual_style"]):
                image["stale"]=True
        full_audio=p["assets"].get("full_audio")
        if full_audio and full_audio.get("source")!="manual" and (new_voice or scene_texts_changed):
            full_audio["stale"]=True; audio_changed=True
        ids={s["id"] for s in new["scenes"]}
        p["assets"]["images"]={k:v for k,v in p["assets"]["images"].items() if k in ids}
        p["assets"]["audio"]={k:v for k,v in p["assets"]["audio"].items() if k in ids}
        music=p["assets"].get("music")
        if music_profile_changed and music and music.get("source")=="generated": music["stale"]=True
        changed=any(p[k]!=new[k] for k in ("title","story","scenes","settings"))
        p.update({k:new[k] for k in ("title","story","scenes","settings")})
        if changed: store.invalidate(p,audio=audio_changed)
        return store.save(p)


def upload_to_temp(file:UploadFile,root:Path) -> Path:
    suffix=Path(file.filename or "file").suffix.lower()
    target=root/"cache"/("upload_"+uuid.uuid4().hex+suffix)
    target.parent.mkdir(parents=True,exist_ok=True)
    size=0
    try:
        with target.open("wb") as out:
            while chunk:=file.file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_UPLOAD: raise ValueError("File oltre il limite di upload.")
                out.write(chunk)
        if not size: raise ValueError("Il file caricato e' vuoto.")
        return target
    except BaseException:
        target.unlink(missing_ok=True); raise


@app.get("/api/music-library")
def music_library(): return store.list_music_tracks()


@app.post("/api/music-library",status_code=201)
def upload_music_library(file:UploadFile=File(...)):
    root=store.music_library_dir(); raw=upload_to_temp(file,root); target=None
    try:
        if raw.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError("Formato audio non supportato. Usa WAV, MP3, M4A, AAC, OGG, FLAC, OPUS, MP4 o WebM.")
        track_id="m_"+uuid.uuid4().hex[:12]; target=store.music_track_path(track_id)
        media.normalize_audio(raw,target)
        name="".join(c for c in Path(file.filename or "Traccia").stem.strip() if c.isprintable())[:150] or "Traccia"
        track=dict(id=track_id,name=name,duration=media.wav_seconds(target),sha256=store.file_hash(target),created=time.time())
        return store.save_music_track(track)
    except BaseException:
        if target: target.unlink(missing_ok=True)
        raise
    finally:
        raw.unlink(missing_ok=True)


@app.delete("/api/music-library/{track_id}")
def remove_music_library(track_id:str):
    store.delete_music_track(track_id); return {"deleted":track_id}


@app.get("/api/music-library/{track_id}/file")
def play_music_library(track_id:str):
    track=store.get_music_track(track_id)
    return FileResponse(store.music_track_path(track_id),media_type="audio/wav",filename=None,
                        headers={"ETag":track["sha256"]})


@app.post("/api/projects/{pid}/music-library/{track_id}")
def use_music_library(pid:str,track_id:str):
    with JOBS.lock,store.LOCK:
        JOBS.assert_idle(pid); p=store.load(pid); root=store.project_dir(pid)
        track=store.get_music_track(track_id); source=store.music_track_path(track_id)
        target=root/"assets/music"/("library_"+track_id+".wav")
        shutil.copy2(source,target)
        p["assets"]["music"]=store.asset(root,str(target.relative_to(root)),"library",duration=media.wav_seconds(target),
                                           stale=False,library_id=track_id,name=track["name"])
        store.invalidate(p); return store.save(p)


def save_caption_text(p:dict,text:str):
    cues=captions.parse_srt(text); root=store.project_dir(p["id"])
    path=root/"assets"/("captions_"+uuid.uuid4().hex[:8]+".srt")
    path.write_text(captions.to_srt(cues),"utf-8")
    narration=p.get("narration")
    p["subtitles"]=store.asset(root,str(path.relative_to(root)),"manual",stale=False,
                              audio_sha=narration["sha256"] if narration else None,cues=len(cues))
    store.invalidate(p); return store.save(p)


@app.post("/api/projects/{pid}/upload")
def upload(pid:str,kind:Literal["image","scene_audio","full_audio","music","subtitles"]=Query(...),
           scene_id:str|None=None,file:UploadFile=File(...)):
    with JOBS.lock:
        JOBS.assert_idle(pid); p=store.load(pid); root=store.project_dir(pid)
        scene=next((s for s in p["scenes"] if s["id"]==scene_id),None)
        if kind in ("image","scene_audio") and not scene: raise ValueError("Seleziona una scena valida.")
        raw=upload_to_temp(file,root)
        try:
            if kind=="subtitles":
                if raw.stat().st_size>500000: raise ValueError("SRT troppo grande.")
                return save_caption_text(p,raw.read_text("utf-8-sig"))
            token=uuid.uuid4().hex[:12]
            if kind=="image":
                path=root/"assets/images"/(token+".png")
                try:
                    info=media.normalize_image(raw,path)
                except (OSError, SyntaxError) as exc:
                    raise ValueError("Immagine non leggibile. Usa un PNG, JPEG o WebP valido.") from exc
                p["assets"]["images"][scene_id]=store.asset(root,str(path.relative_to(root)),"manual",stale=False,**info)
                store.invalidate(p)
            else:
                if raw.suffix.lower() not in AUDIO_EXTENSIONS:
                    raise ValueError("Formato audio non supportato. Usa WAV, MP3, M4A, AAC, OGG, FLAC, OPUS, MP4 o WebM.")
                folder="assets/music" if kind=="music" else "assets/audio"
                path=root/folder/(token+".wav"); media.normalize_audio(raw,path)
                info=store.asset(root,str(path.relative_to(root)),"manual",duration=media.wav_seconds(path),stale=False)
                if kind=="scene_audio":
                    info.update(text_sha=store.digest(scene["text"]),words=[])
                    p["assets"]["audio"][scene_id]=info
                else:
                    p["assets"][kind]=info
                    if kind=="full_audio": p["settings"]["audio_mode"]="full"
                store.invalidate(p,audio=kind!="music")
            return store.save(p)
        finally: raw.unlink(missing_ok=True)


@app.get("/api/projects/{pid}/captions",response_class=PlainTextResponse)
def get_captions(pid:str):
    p=store.load(pid)
    if not p.get("subtitles"): return ""
    return store.safe_path(store.project_dir(pid),p["subtitles"]["path"]).read_text("utf-8")


@app.put("/api/projects/{pid}/captions")
def set_captions(pid:str,body:CaptionText):
    with JOBS.lock:
        JOBS.assert_idle(pid); return save_caption_text(store.load(pid),body.text)


@app.post("/api/projects/{pid}/assets/confirm")
def confirm_asset(pid:str,kind:Literal["image","scene_audio","subtitles"],scene_id:str|None=None):
    with JOBS.lock:
        JOBS.assert_idle(pid); p=store.load(pid)
        if kind=="subtitles":
            sub=p.get("subtitles")
            if not sub: raise ValueError("Sottotitoli non trovati.")
            # This acceptance applies only to the narration assembled next.
            sub.update(stale=False,accept_next_audio=True)
            store.invalidate(p); return store.save(p)
        key="images" if kind=="image" else "audio"
        a=p["assets"][key].get(scene_id)
        if not a: raise ValueError("Contenuto non trovato.")
        a.update(stale=False,source="manual")
        store.invalidate(p,audio=kind=="scene_audio"); return store.save(p)


@app.delete("/api/projects/{pid}/assets")
def delete_asset(pid:str,kind:Literal["image","scene_audio","full_audio","music","subtitles"],scene_id:str|None=None):
    with JOBS.lock:
        JOBS.assert_idle(pid); p=store.load(pid)
        if kind in ("image","scene_audio"):
            p["assets"]["images" if kind=="image" else "audio"].pop(scene_id,None)
        elif kind=="subtitles": p["subtitles"]=None
        else: p["assets"][kind]=None
        store.invalidate(p,audio=kind in ("scene_audio","full_audio")); return store.save(p)


@app.post("/api/projects/{pid}/jobs",status_code=202)
def submit(pid:str,body:JobRequest):
    store.project_dir(pid)
    return JOBS.submit(pid,body.model_dump())


@app.get("/api/jobs/{jid}")
def job(jid:str): return JOBS.read(jid)


@app.get("/api/projects/{pid}/jobs")
def project_jobs(pid:str):
    store.project_dir(pid); return JOBS.list(pid)[:40]


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid:str): return JOBS.update(jid,cancel_requested=True)


@app.get("/api/projects/{pid}/file/{relative:path}")
def get_file(pid:str,relative:str,download:bool=False):
    path=store.safe_path(store.project_dir(pid),relative)
    if not path.is_file() or ".part." in path.name or path.suffix==".tmp":
        raise FileNotFoundError()
    return FileResponse(path,filename=path.name if download else None)


@app.get("/api/projects/{pid}/prompts",response_class=PlainTextResponse)
def prompts(pid:str):
    p=store.load(pid)
    lines=[p["title"],"", "Riferimento stilistico e continuita':",p["settings"]["visual_style"],"",
           "Genera le immagini separatamente, senza testo, in verticale 9:16.",
           "Mantieni coerenti soggetti, personaggi, prodotti e ambientazioni tra le scene, quando ricorrenti.",
           "I nomi suggeriti servono per il caricamento multiplo nell'ordine dello storyboard.",""]
    for i,s in enumerate(p["scenes"],1):
        lines += [f"SCENA {i:02d} | file {i:02d}.png",f"Narrazione: {s['text']}",
                  "Prompt: "+(s["prompt"] or "Crea un'illustrazione rappresentativa della scena narrata, coerente con lo stile sopra."),""]
    return "\n".join(lines)


@app.get("/api/projects/{pid}/export")
def export(pid:str):
    with JOBS.lock:
        JOBS.assert_idle(pid); p=store.load(pid); root=store.project_dir(pid)
        target=root/"cache"/"progetto_export.zip"
        board={k:p[k] for k in ("title","story","scenes","settings")}
        with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            z.writestr("storyboard.json",json.dumps(board,ensure_ascii=False,indent=2))
            z.writestr("racconto.txt",p["story"])
            z.write(root/"project.json","project.json")
            for folder in ("assets","output","history"):
                for f in (root/folder).rglob("*"):
                    if f.is_file() and ".part." not in f.name and f.suffix!=".tmp": z.write(f,str(f.relative_to(root)))
            if p.get("narration"):
                z.write(store.safe_path(root,p["narration"]["path"]),"narrazione.wav")
        return FileResponse(target,filename=pid+".zip",media_type="application/zip")


@app.post("/api/demo",status_code=201)
def demo():
    texts=["Nessuno tornava al lago dopo il tramonto.","Quella sera, qualcosa si mosse tra le canne.",
           "Non era un animale. Era troppo alto.","Poi, dal buio, una voce pronuncio' il mio nome."]
    p=store.create("Il lago dopo il tramonto - DEMO", " ".join(texts)); root=store.project_dir(p["id"])
    p["scenes"]=[Scene(id=pipeline.sid(),text=t,prompt="Immagine segnaposto tecnica: sostituiscila con una tua illustrazione.").model_dump() for t in texts]
    p["settings"]["resolution"]="540x960"; p["settings"]["fps"]=24
    for i,s in enumerate(p["scenes"],1):
        path=root/"assets/images"/(s["id"]+".png"); media.demo_card(path,i)
        p["assets"]["images"][s["id"]]=store.asset(root,str(path.relative_to(root)),"demo",stale=False)
    store.save(p)
    job=JOBS.submit(p["id"],JobRequest(action="complete",allow_estimated=True,preview=True).model_dump())
    return {"project":p,"job":job}
