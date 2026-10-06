from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SoundCue(StrictModel):
    effect: Literal["wind", "rumble", "snap", "impact", "heartbeat", "static", "whisper_texture", "riser"]
    at: float = Field(default=0, ge=0, le=3600)
    volume: float = Field(default=0.25, ge=0.02, le=1)


Unit = Annotated[float, Field(ge=0, le=1)]
Point = tuple[Unit, Unit]
Rect = tuple[Unit, Unit, Unit, Unit]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
Layer = Literal["background", "images", "diagrams", "annotations", "text", "subtitles", "effects"]
TransitionType = Literal["cut", "crossfade", "slide_left", "slide_right", "zoom_in", "zoom_out", "zoom_through", "whip_left", "whip_right", "blur"]
TimeUnit = Literal["seconds", "scene", "speech"]


class Transition(StrictModel):
    type: TransitionType = "cut"
    duration: float = Field(default=0.35, ge=0, le=2)
    target: Point = (0.5, 0.5)
    time_unit: TimeUnit = "seconds"

    @model_validator(mode="after")
    def nonzero_animation(self):
        if self.time_unit != "seconds" and self.duration > 1:
            raise ValueError("Una durata relativa deve essere compresa fra 0 e 1")
        if self.type != "cut" and self.duration <= 0:
            raise ValueError("Una transizione animata richiede duration > 0")
        return self


class VisualAsset(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    prompt: str = Field(default="", max_length=12000)


class DiagramNode(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    label: str = Field(max_length=120)
    position: Point


class DiagramEdge(StrictModel):
    source: str
    target: str
    label: str = Field(default="", max_length=80)


class VisualEvent(StrictModel):
    type: Literal["show_image", "reframe", "zoom", "pan", "crop", "focus", "show_text", "headline", "label", "arrow", "circle", "highlight", "line", "statistic", "diagram", "background"]
    start: float = Field(default=0, ge=0, le=3600)
    end: float = Field(gt=0, le=3600)
    time_unit: TimeUnit | None = None
    asset: str | None = None
    layer: Layer | None = None
    z: int | None = Field(default=None, ge=0, le=100)
    text: str = Field(default="", max_length=500)
    value: str = Field(default="", max_length=40)
    position: Point | None = None
    size: Point | None = None
    to: Rect | None = None
    from_rect: Rect | None = None
    points: list[Point] = Field(default_factory=list, max_length=32)
    color: Color | None = None
    style: Literal["headline", "body", "label", "statistic"] = "body"
    animation: Literal["none", "fade", "pop", "slide_up", "typewriter"] = "none"
    transition: Transition | None = None
    nodes: list[DiagramNode] = Field(default_factory=list, max_length=32)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def event_content(self):
        if self.end <= self.start:
            raise ValueError("end deve essere maggiore di start")
        if self.time_unit in ("scene", "speech") and self.end > 1:
            raise ValueError("Tempi relativi: start/end devono essere compresi fra 0 e 1")
        for name in ("to", "from_rect"):
            rect = getattr(self, name)
            if rect and (rect[2] <= 0 or rect[3] <= 0 or rect[0]+rect[2] > 1.000001 or rect[1]+rect[3] > 1.000001):
                raise ValueError(f"{name}: crop [x,y,larghezza,altezza] deve rimanere dentro 0–1")
        if self.type == "show_image" and not self.asset:
            raise ValueError("show_image richiede asset")
        if self.type in ("reframe", "zoom", "pan", "crop", "focus") and not self.to:
            raise ValueError(f"{self.type} richiede to: [x,y,larghezza,altezza]")
        if self.type in ("show_text", "headline", "label") and not self.text.strip():
            raise ValueError(f"{self.type} richiede text non vuoto")
        if self.type == "statistic" and not self.value.strip():
            raise ValueError("statistic richiede value")
        if self.type in ("arrow", "line") and len(self.points) < 2:
            raise ValueError(f"{self.type} richiede almeno due points")
        if self.type in ("circle", "highlight") and (not self.position or not self.size or min(self.size) <= 0):
            raise ValueError(f"{self.type} richiede position e size positive")
        if self.type == "diagram":
            ids = [n.id for n in self.nodes]
            if not ids or len(set(ids)) != len(ids):
                raise ValueError("diagram richiede nodi con ID univoci")
            if any(e.source not in ids or e.target not in ids for e in self.edges):
                raise ValueError("diagram: un collegamento fa riferimento a un nodo mancante")
        if self.transition and self.type != "show_image":
            raise ValueError("transition si applica a show_image o alla scena")
        if self.layer == "subtitles":
            raise ValueError("Il livello subtitles e' riservato ai sottotitoli SRT")
        return self


class Scene(StrictModel):
    id: str = Field(default_factory=lambda:"s_"+uuid.uuid4().hex[:8],pattern=r"^s_[a-f0-9]{8}$")
    text: str = Field(min_length=1, max_length=5000)
    prompt: str = Field(default="", max_length=12000)
    motion: Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "still"] = "zoom_in"
    delivery: Literal["natural", "ominous", "emphatic", "urgent", "intimate"] = "natural"
    voice_prompt: str = Field(default="", max_length=2000)
    duration: float | None = Field(default=None, gt=0.1, le=3600)
    time_unit: TimeUnit = "seconds"
    effects: list[SoundCue] = Field(default_factory=list, max_length=8)
    assets: list[VisualAsset] = Field(default_factory=list, max_length=32)
    visual_events: list[VisualEvent] = Field(default_factory=list, max_length=200)
    transition: Transition | None = None

    @model_validator(mode="before")
    @classmethod
    def contextual_visual_errors(cls, data):
        if not isinstance(data, dict):
            return data
        sid = data.get("id", "senza ID")
        for index, item in enumerate(data.get("visual_events") or []):
            try:
                VisualEvent.model_validate(item)
            except ValueError as exc:
                raise ValueError(f"Scena {sid}, evento {index+1}: {exc}") from exc
        if data.get("transition") is not None:
            try:
                Transition.model_validate(data["transition"])
            except ValueError as exc:
                raise ValueError(f"Scena {sid}, transizione: {exc}") from exc
        return data

    @model_validator(mode="after")
    def visual_references(self):
        ids = [a.id for a in self.assets]
        if "default" in ids or len(set(ids)) != len(ids):
            raise ValueError(f"Scena {self.id}: ID asset duplicato o riservato ('default')")
        for index, event in enumerate(self.visual_events, 1):
            if event.asset and event.asset not in ["default", *ids]:
                raise ValueError(f"Scena {self.id}, evento {index}: asset '{event.asset}' mancante")
            unit = event.time_unit or self.time_unit
            if unit != "seconds" and event.end > 1:
                raise ValueError(f"Scena {self.id}, evento {index}: tempi relativi fuori da 0-1")
            if unit == "seconds" and self.duration is not None and event.end > self.duration+0.000001:
                raise ValueError(f"Scena {self.id}, evento {index}: end {event.end}s oltre durata {self.duration}s")
        return self


class Settings(StrictModel):
    video_mode: Literal["narrative", "educational"] = "narrative"
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
    asset_id: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    caption_method: Literal["timings", "whisper", "estimate"] = "timings"
    allow_estimated: bool = False
    generate_images: bool = False
    preview: bool = False
    force: bool = False

    @model_validator(mode="after")
    def asset_target(self):
        if self.asset_id and (not self.scene_id or self.action not in ("images", "prompts")):
            raise ValueError("asset_id richiede scene_id e un'azione images o prompts")
        return self


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
