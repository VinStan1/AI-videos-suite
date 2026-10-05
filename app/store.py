from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from .models import Settings

DATA_ROOT = Path(os.getenv("DATA_DIR", "/data"))
LOCK = threading.RLock()


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def project_dir(pid: str) -> Path:
    if not re.fullmatch(r"p_[0-9a-f]{12}", pid):
        raise ValueError("ID progetto non valido.")
    path = DATA_ROOT / "projects" / pid
    if not (path / "project.json").is_file():
        raise FileNotFoundError("Progetto non trovato.")
    return path


def music_library_dir() -> Path:
    path=DATA_ROOT/"music_library"
    path.mkdir(parents=True,exist_ok=True)
    return path


def music_track_path(track_id: str, suffix: str = ".wav") -> Path:
    if not re.fullmatch(r"m_[0-9a-f]{12}",track_id):
        raise ValueError("ID traccia non valido.")
    return music_library_dir()/(track_id+suffix)


def save_music_track(track: dict) -> dict:
    with LOCK:
        atomic_json(music_track_path(track["id"],".json"),track)
    return track


def get_music_track(track_id: str) -> dict:
    with LOCK:
        metadata=music_track_path(track_id,".json")
        audio=music_track_path(track_id)
        if not metadata.is_file() or not audio.is_file():
            raise FileNotFoundError("Traccia non trovata.")
        track=json.loads(metadata.read_text("utf-8"))
        if track.get("id")!=track_id: raise ValueError("Metadati traccia non validi.")
        return track


def list_music_tracks() -> list[dict]:
    tracks=[]
    for metadata in music_library_dir().glob("m_*.json"):
        try:
            track=json.loads(metadata.read_text("utf-8"))
            if music_track_path(track["id"]).is_file(): tracks.append(track)
        except (OSError,ValueError,KeyError,json.JSONDecodeError):
            continue
    return sorted(tracks,key=lambda track:track.get("created",0),reverse=True)


def delete_music_track(track_id: str) -> None:
    with LOCK:
        # Validate the exact local targets before deleting either file.
        audio=music_track_path(track_id); metadata=music_track_path(track_id,".json")
        if not audio.is_file() and not metadata.is_file(): raise FileNotFoundError("Traccia non trovata.")
        audio.unlink(missing_ok=True); metadata.unlink(missing_ok=True)


def safe_path(root: Path, relative: str) -> Path:
    if not relative or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("Percorso non valido.")
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or p == root.resolve():
        raise ValueError("Percorso esterno al progetto.")
    return p


def load(pid: str) -> dict:
    with LOCK:
        project=json.loads((project_dir(pid) / "project.json").read_text("utf-8"))
        # Projects saved before cloud providers did not have this required setting.
        project.setdefault("settings",{}).setdefault("image_provider","cloudflare")
        project["settings"].setdefault("music_preset","mist")
        project["settings"].setdefault("voice_prompt","")
        project["settings"].setdefault("gemini_max_attempts",2)
        # Keep older storyboards compatible with per-scene direction and effects.
        for scene in project.setdefault("scenes",[]):
            scene.setdefault("delivery","natural")
            scene.setdefault("effects",[])
        return project


def save(project: dict) -> dict:
    with LOCK:
        project["revision"] = project.get("revision", 0) + 1
        project["updated"] = time.time()
        atomic_json(project_dir(project["id"]) / "project.json", project)
    return project


def create(title: str, story: str) -> dict:
    pid = "p_" + uuid.uuid4().hex[:12]
    root = DATA_ROOT / "projects" / pid
    for folder in ("assets/images", "assets/audio", "assets/music", "cache", "output", "history"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    p = dict(id=pid, title=title, story=story, scenes=[], settings=Settings().model_dump(),
             assets={"images": {}, "audio": {}, "full_audio": None, "music": None},
             narration=None, subtitles=None, output=None, preview=None, warnings=[],
             revision=0, created=time.time(), updated=time.time())
    atomic_json(root / "project.json", p)
    return p


def list_projects() -> list[dict]:
    root = DATA_ROOT / "projects"
    out = []
    if root.exists():
        for path in root.glob("p_*/project.json"):
            try:
                p = json.loads(path.read_text("utf-8"))
                out.append({k: p[k] for k in ("id", "title", "updated", "revision")})
            except (OSError, ValueError, KeyError):
                continue
    return sorted(out, key=lambda p: p["updated"], reverse=True)


def asset(root: Path, relative: str, source: str, **extra) -> dict:
    path = safe_path(root, relative)
    return dict(path=relative, sha256=file_hash(path), source=source, **extra)


def archive_json(p: dict) -> None:
    root = project_dir(p["id"])
    atomic_json(root / "history" / f"revision_{p['revision']:05d}.json", p)


def invalidate(p: dict, audio: bool = False, captions: bool = False) -> None:
    if audio:
        p["narration"] = None
    if captions or audio:
        if p.get("subtitles"):
            p["subtitles"]["stale"] = True
    for key in ("output", "preview"):
        if p.get(key):
            p[key]["stale"] = True
