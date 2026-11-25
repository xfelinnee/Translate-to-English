import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
MODELS_DIR = APP_DIR / "models"

DEFAULTS: dict = {
    # Part of the name of the audio output Discord plays into.
    # Empty means: ask on the next start.
    "audio_device": "",
    "model": "large-v3",
    "device": "cuda",
    # float16 is the model's full precision and the fastest option on RTX
    # cards. int8_float16 uses ~1.5 GB less GPU memory, slightly less accurate.
    "compute_type": "float16",
    "cpu_fallback_model": "small",
    "source_language": "pt",
    "show_original": False,
    # Grey "still talking" guesses. Each one is a full Whisper pass, so they
    # cost GPU time; the final lines are the same either way.
    "live_preview": False,
    "preview_every_seconds": 2.5,
    "preview_start_seconds": 2.0,
    # Audio louder than this counts as speech (0 to 1).
    "speech_threshold": 0.006,
    # A pause this long ends a line.
    "silence_end_seconds": 0.7,
    # Longer speech gets cut at the quietest point.
    "max_segment_seconds": 12,
    # Locked: the mouse goes straight through the overlay.
    "click_through": True,
    "lock_hotkey": "ctrl+shift+l",
    "overlay": {
        "x": 60,
        "y": 60,
        "width": 720,
        "height": 220,
        "font_size": 15,
        "bg_opacity": 0.85,
        "text_opacity": 1.0,
        "history": 30,
        "hide_after_seconds": 0,
        "bg": "#111316",
        "fg": "#f3f4f6",
    },
}

# Settings the app changes itself. Only these are written back while it runs,
# so edits made to config.json by hand in the meantime survive.
UI_KEYS = ("overlay", "show_original", "live_preview", "silence_end_seconds", "audio_device", "click_through")


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if not CONFIG_PATH.exists():
        save_config(cfg)
        return cfg
    try:
        user = json.loads(CONFIG_PATH.read_text("utf-8"))
    except (OSError, ValueError) as e:
        print(f"config.json could not be read ({e}), using defaults.")
        return cfg
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    return cfg


def save_config(cfg: dict, only: tuple[str, ...] | None = None) -> None:
    data = cfg
    if only is not None and CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text("utf-8"))
        except (OSError, ValueError):
            data = dict(cfg)
        for key in only:
            data[key] = cfg[key]
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2), "utf-8")
    except OSError as e:
        print(f"Could not save config.json: {e}")
