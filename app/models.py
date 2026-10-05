from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SoundCue(StrictModel):
    effect: Literal["wind", "rumble", "snap", "impact", "heartbeat", "static", "whisper_texture", "riser"]
    at: float = Field(default=0, ge=0, le=3600)
    volume: float = Field(default=0.25, ge=0.02, le=1)


class Scene(StrictModel):
    id: str = Field(pattern=r"^s_[a-f0-9]{8}$")
    text: str = Field(min_length=1, max_length=5000)
    prompt: str = Field(default="", max_length=12000)
    motion: Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "still"] = "zoom_in"
    delivery: Literal["natural", "ominous", "emphatic", "urgent", "intimate"] = "natural"
    duration: float | None = Field(default=None, gt=0.1, le=3600)
    effects: list[SoundCue] = Field(default_factory=list, max_length=8)


class Settings(StrictModel):
    voice_provider: Literal["huggingface", "espeak", "kokoro", "gemini", "chirp"] = "huggingface"
    image_provider: Literal["cloudflare", "huggingface", "comfyui"] = "cloudflare"
    voice: str = Field(default="im_nicola", pattern=r"^[a-zA-Z0-9_+(). -]{1,100}$")
    voice_prompt: str = Field(default="", max_length=2000)
    gemini_max_attempts: int = Field(default=2, ge=1, le=2)
    speed: float = Field(default=0.95, ge=0.5, le=2.0)
    pause_seconds: float = Field(default=0.2, ge=0, le=3)
    audio_mode: Literal["scenes", "full_generated", "full"] = "scenes"
    resolution: Literal["1080x1920", "720x1280", "540x960"] = "1080x1920"
    fps: Literal[24, 30] = 30
    fit: Literal["cover", "contain"] = "cover"
    subtitle_size: int = Field(default=62, ge=32, le=90)
    subtitle_bottom: int = Field(default=340, ge=100, le=800)
    music_volume: float = Field(default=0.07, ge=0, le=0.4)
    music_preset: Literal["mist", "suspense", "ritual"] = "mist"
    subtitles_enabled: bool = True
    ollama_model: str = Field(default="qwen2.5:3b", pattern=r"^[a-zA-Z0-9_./:-]{1,150}$")
    visual_style: str = Field(default="Stile cinematografico, composizione curata, luce coerente con la scena, nessuna scritta. Adatta atmosfera e colori al contenuto del copione. Mantieni coerenza tra soggetti, ambientazioni e stile nelle scene.", max_length=10000)


class ProjectCreate(StrictModel):
    title: str = Field(default="Nuovo progetto", min_length=1, max_length=150)
    story: str = Field(default="", max_length=100000)


class Storyboard(StrictModel):
    title: str = Field(min_length=1, max_length=150)
    story: str = Field(default="", max_length=100000)
    scenes: list[Scene] = Field(default_factory=list, max_length=100)
    settings: Settings = Field(default_factory=Settings)
    revision: int | None = None

    @model_validator(mode="after")
    def distinct_ids(self):
        ids = [s.id for s in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Gli ID delle scene devono essere univoci.")
        for s in self.scenes:
            if not s.text.strip():
                raise ValueError("Una scena non puo' avere testo vuoto.")
        return self


class JobRequest(StrictModel):
    action: Literal["split", "prompts", "voice", "images", "music", "assemble_audio", "captions", "render", "complete"]
    target_words: int = Field(default=30, ge=5, le=150)
    scene_id: str | None = Field(default=None, pattern=r"^s_[a-f0-9]{8}$")
    caption_method: Literal["timings", "whisper", "estimate"] = "timings"
    allow_estimated: bool = False
    generate_images: bool = False
    preview: bool = False
    force: bool = False


class CaptionText(StrictModel):
    text: str = Field(max_length=500000)


def split_story(text: str, target_words: int = 30) -> list[str]:
    """Faithful splitter: preserve the complete word sequence; never rewrite."""
    text = text.strip()
    if not text:
        raise ValueError("Inserisci il copione prima di dividerlo in scene.")
    units = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    result, current = [], []
    for unit in units:
        words = unit.split()
        if not words:
            continue
        if current and len(current) + len(words) > target_words * 1.35:
            result.append(" ".join(current)); current = []
        # Split very long sentences without dropping punctuation or words.
        while len(words) > target_words * 1.6:
            if current:
                result.append(" ".join(current)); current = []
            result.append(" ".join(words[:target_words])); words = words[target_words:]
        current.extend(words)
        if len(current) >= target_words:
            result.append(" ".join(current)); current = []
    if current:
        result.append(" ".join(current))
    if len(result) > 100:
        raise ValueError("Oltre 100 scene: aumenta le parole per scena o dividi il copione in piu' progetti.")
    assert " ".join(text.split()) == " ".join(" ".join(result).split())
    return result
