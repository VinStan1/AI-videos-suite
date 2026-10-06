"""Shared composition styles. Sizes are fractions of the output height."""
from copy import deepcopy

LAYER_Z = {"background": 0, "images": 10, "diagrams": 20, "annotations": 30,
           "text": 40, "subtitles": 90, "effects": 80}

BASE_THEME = {
    "version": "composition-theme-v1",
    "font": "DejaVuSans.ttf", "font_bold": "DejaVuSans-Bold.ttf",
    "subtitle_font": "DejaVu Sans", "background": "#101827",
    "foreground": "#F4F6FC", "accent": "#7DE0DE", "card": "#182638ED",
    "margin": 0.07, "stroke": 0.004, "radius": 0.018,
    "text_padding": 0.02, "card_padding": 0.014, "arrow_head": 0.018,
    "diagram_node_size": (0.27, 0.085), "diagram_label_size": (0.36, 0.07),
    "typewriter_char_seconds": 0.025,
    "animation_duration": 0.25,
    "styles": {
        "headline": {"size": 0.046, "position": (0.5, 0.18), "bold": True},
        "body": {"size": 0.03, "position": (0.5, 0.35), "bold": False},
        "label": {"size": 0.023, "position": (0.5, 0.68), "bold": True},
        "statistic": {"size": 0.085, "position": (0.5, 0.40), "bold": True},
    },
    "transition": {"type": "cut", "duration": 0.35, "target": (0.5, 0.5)},
    "hold_seconds": 5.0, "reframe_seconds": 3.0, "reframe_zoom": 0.92,
    "auto_headline": False, "headline_seconds": 2.5,
}
EDUCATIONAL_THEME = deepcopy(BASE_THEME)
EDUCATIONAL_THEME.update({
    "version": "educational-theme-v1", "background": "#101727",
    "transition": {"type": "crossfade", "duration": 0.25, "target": (0.5, 0.5)},
    "hold_seconds": 2.5, "reframe_seconds": 1.8, "reframe_zoom": 0.86,
    "auto_headline": True,
})


def get_theme(settings: dict) -> dict:
    return deepcopy(EDUCATIONAL_THEME if settings.get("video_mode") == "educational" else BASE_THEME)
