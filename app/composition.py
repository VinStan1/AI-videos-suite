"""Normalize both storyboard generations into one scene/layer/event plan."""
from __future__ import annotations

import math
from .models import Scene
from .themes import LAYER_Z, get_theme

CAMERA_EVENTS = {"reframe", "zoom", "pan", "crop", "focus"}
TEXT_EVENTS = {"show_text", "headline", "label", "statistic"}


def asset_key(scene_id: str, asset_id: str = "default") -> str:
    return scene_id if asset_id == "default" else f"{scene_id}__{asset_id}"


def asset_definitions(scene: dict) -> list[dict]:
    return [{"id": "default", "prompt": scene.get("prompt", "")}, *scene.get("assets", [])]


def planned_assets(scene: dict) -> list[dict]:
    """Prompt/generation targets; omit an unused empty legacy default asset."""
    definitions = asset_definitions(scene)
    default_used = (not scene.get("assets") and not scene.get("visual_events")) or bool(scene.get("prompt"))
    default_used |= any(e.get("asset") == "default" for e in scene.get("visual_events", []))
    return [a for a in definitions if a["id"] != "default" or default_used]


def event_layer(event: dict) -> str:
    if event.get("layer"):
        return event["layer"]
    kind = event["type"]
    if kind == "background": return "background"
    if kind == "show_image" or kind in CAMERA_EVENTS: return "images"
    if kind == "diagram": return "diagrams"
    if kind in TEXT_EVENTS: return "text"
    return "annotations"


def normalize_scene(scene: dict, duration: float, settings: dict, available_assets=None, speech_duration=None) -> dict:
    parsed = Scene.model_validate(scene)
    data = parsed.model_dump(exclude_none=True)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Scena {parsed.id}: durata audio/scena non valida")
    speech_duration = duration if speech_duration is None else float(speech_duration)
    if not math.isfinite(speech_duration) or speech_duration < 0:
        raise ValueError(f"Scena {parsed.id}: durata della parlata non valida")
    speech_duration = min(speech_duration, duration)
    bases = {"scene": duration, "speech": speech_duration}

    def relative_base(unit, context):
        base = bases[unit]
        if base <= 0:
            raise ValueError(f"Scena {parsed.id}, {context}: parlata senza durata; usa time_unit 'scene'")
        return base

    def resolve_transition(spec, capacity, context):
        result = dict(spec)
        unit = result.pop("time_unit", "seconds")
        if unit != "seconds" and spec["duration"]:
            # Relative transitions always fit inside their incoming scene/shot.
            result["duration"] = min(spec["duration"]*relative_base(unit, context), capacity)
        return result
    theme = get_theme(settings)
    educational = settings.get("video_mode", "narrative") == "educational"
    legacy = not educational and not data["assets"] and not data["visual_events"] and not data.get("transition")
    events = list(data["visual_events"])
    for index, event in enumerate(events, 1):
        unit = event.pop("time_unit", data["time_unit"])
        if unit != "seconds":
            base = relative_base(unit, f"evento {index}")
            event["start"] *= base
            event["end"] *= base
        if event["end"] > duration+0.000001:
            raise ValueError(f"Scena {parsed.id}, evento {index}: end {event['end']:.3f}s oltre audio/scena {duration:.3f}s")
        if event.get("transition"):
            event["transition"] = resolve_transition(event["transition"], event["end"]-event["start"], f"evento {index}, transizione")
        if event.get("transition") and event["transition"]["type"] != "cut":
            if event["transition"]["duration"] > event["end"]-event["start"]:
                raise ValueError(f"Scena {parsed.id}, evento {index}: transizione piu' lunga dello shot")
    if data.get("transition"):
        data["transition"] = resolve_transition(data["transition"], duration, "transizione")
    if data.get("transition") and data["transition"]["type"] != "cut" and data["transition"]["duration"] > duration:
        raise ValueError(f"Scena {parsed.id}: transizione piu' lunga della scena")

    if not any(e["type"] == "show_image" for e in events):
        assets = planned_assets(data)
        if not assets and "default" in (available_assets or set()) and not any(e["type"]=="background" for e in events):
            assets=[{"id":"default","prompt":data["prompt"]}]
        if assets:
            # Educational holds reuse the same source; no extra AI calls.
            if educational:
                hold = theme["hold_seconds"]
                count = max(len(assets), __import__("math").ceil(duration/hold))
            else:
                count = len(assets)
            for index in range(count):
                start, end = duration*index/count, duration*(index+1)/count
                events.append({"type": "show_image", "asset": assets[index % len(assets)]["id"],
                               "start": start, "end": end, "motion": data["motion"], "auto": True})
        elif legacy:
            events.append({"type": "show_image", "asset": "default", "start": 0.0, "end": duration,
                           "motion": data["motion"], "auto": True})
    # Equal-z image overlaps have ambiguous shot boundaries. Different z/layers
    # permit intentional picture-in-picture and other simultaneous image layers.
    images = [e for e in events if e["type"] == "show_image"]
    cameras=[e for e in events if e["type"] in CAMERA_EVENTS]
    for i,left in enumerate(cameras):
        for right in cameras[i+1:]:
            if (not left.get("asset") or not right.get("asset") or left["asset"]==right["asset"]) and max(left["start"],right["start"]) < min(left["end"],right["end"])-0.000001:
                raise ValueError(f"Scena {parsed.id}: eventi camera sovrapposti; specifica intervalli distinti")
    for i, left in enumerate(images):
        for right in images[i+1:]:
            if (event_layer(left), left.get("z", LAYER_Z[event_layer(left)])) == (event_layer(right), right.get("z", LAYER_Z[event_layer(right)])) and max(left["start"],right["start"]) < min(left["end"],right["end"])-0.000001:
                raise ValueError(f"Scena {parsed.id}: show_image sovrapposti nello stesso livello/z")
    if educational:
        for image in images:
            if not any(e["type"] in CAMERA_EVENTS and e["start"] < image["end"] and e["end"] > image["start"] and (not e.get("asset") or e["asset"] == image["asset"]) for e in events):
                zoom = theme["reframe_zoom"]
                events.append({"type": "reframe", "asset": image["asset"], "start": image["start"], "end": min(image["end"],image["start"]+theme["reframe_seconds"]),
                               "to": [(1-zoom)/2, (1-zoom)/2, zoom, zoom], "auto": True})
        if theme["auto_headline"] and not any(e["type"] in TEXT_EVENTS for e in events):
            words = data["text"].split()[:7]
            events.append({"type": "headline", "text": " ".join(words), "start": 0.0,
                           "end": min(duration, theme["headline_seconds"]), "animation": "pop", "auto": True})
    layers = []
    for index, event in enumerate(events):
        event = dict(event, index=index+1)
        layer = event_layer(event)
        event["layer"] = layer
        if event.get("z") is None: event["z"] = LAYER_Z[layer]
        if event["type"] == "show_image" and not event.get("transition"):
            event["transition"] = theme["transition"] if educational else {"type": "cut", "duration": 0.35, "target": (0.5, 0.5)}
            event["transition"] = dict(event["transition"], duration=min(event["transition"]["duration"], event["end"]-event["start"]))
        layers.append(event)
    layers.sort(key=lambda e: (e["z"], e["index"]))
    return {"id": parsed.id, "duration": duration, "narration": data["text"],
            "assets": asset_definitions(data), "events": layers,
            "layers": LAYER_Z, "legacy": legacy, "motion": data["motion"],
            "transition": data.get("transition") or {"type": "cut", "duration": 0.35, "target": (0.5, 0.5)},
            "theme": theme}


def required_asset_ids(plan: dict) -> set[str]:
    return {e["asset"] for e in plan["events"] if e["type"] == "show_image"}
