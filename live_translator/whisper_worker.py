import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .audio import Jobs
from .config import MODELS_DIR

# Lines Whisper is known to invent from silence or noise.
ALWAYS_DROP = re.compile(
    r"(thanks? for watching|please subscribe|like and subscribe|subtitles? (by|made)"
    r"|legendas|amara\.org|transcri(bed|ption) by|see you in the next video)",
    re.I,
)
WEAK_DROP = re.compile(r"^(thank you|thanks|bye|you|okay|ok|\.+|\W*)[.!?]*$", re.I)


def add_cuda_dlls() -> None:
    """Let CTranslate2 find the CUDA libraries pip installed into the venv."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        d = nvidia / sub / "bin"
        if d.is_dir():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def collapse_repeats(text: str) -> str:
    """Shorten a 1-4 word phrase repeated 4+ times in a row to 3 times.

    'Hello, hello, hello, hello, hello,' -> 'Hello, hello, hello…'
    """
    words = text.split()
    norm = [re.sub(r"[^\w']", "", w).lower() for w in words]
    out: list[str] = []
    i = 0
    while i < len(words):
        for n in range(1, 5):
            unit = norm[i:i + n]
            if len(unit) < n or not all(unit):
                continue
            reps = 1
            while norm[i + reps * n:i + (reps + 1) * n] == unit:
                reps += 1
            if reps >= 4:
                kept = words[i:i + 3 * n]
                kept[-1] = kept[-1].rstrip(",.!?;:-…") + "…"
                out.extend(kept)
                i += reps * n
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def is_hallucination(text: str, seg) -> bool:
    if ALWAYS_DROP.search(text):
        return True
    return bool(WEAK_DROP.match(text)) and (seg.no_speech_prob > 0.3 or seg.avg_logprob < -0.7)


class WhisperWorker(threading.Thread):
    """Loads Whisper, then turns each finished line of audio into English."""

    def __init__(self, cfg: dict, jobs: Jobs, ui_q: queue.Queue, on_ready):
        super().__init__(daemon=True)
        self.cfg, self.jobs, self.ui_q, self.on_ready = cfg, jobs, ui_q, on_ready
        self.model = None

    def ui(self, *msg) -> None:
        self.ui_q.put(msg)

    def load_model(self) -> str:
        add_cuda_dlls()
        import ctranslate2
        from faster_whisper import WhisperModel

        MODELS_DIR.mkdir(exist_ok=True)
        use_gpu = self.cfg["device"] == "cuda" and ctranslate2.get_cuda_device_count() > 0
        name = self.cfg["model"] if use_gpu else self.cfg["cpu_fallback_model"]
        if any(MODELS_DIR.glob(f"models--*{name}")):
            self.ui("status", "Loading model…")
        else:
            self.ui("status", f"Downloading the {name} model (first start only)…")

        if use_gpu:
            try:
                self.model = WhisperModel(
                    name, device="cuda", compute_type=self.cfg["compute_type"], download_root=str(MODELS_DIR)
                )
                self.translate(np.zeros(16000, np.float32), "translate", final=False)  # warm-up
                return "GPU"
            except Exception as e:  # any CUDA/driver problem: fall back to CPU
                print(f"GPU failed ({e}), using the CPU instead.")
                name = self.cfg["cpu_fallback_model"]
                self.ui("status", "GPU failed, loading the CPU model (slower)…")

        self.model = WhisperModel(name, device="cpu", compute_type="int8", download_root=str(MODELS_DIR))
        return "CPU"

    def translate(self, audio: np.ndarray, task: str, final: bool) -> str:
        # Nobody says more than ~5 English tokens a second. Capping the output
        # stops Whisper's "hello, hello, hello…" loops from running to 448
        # tokens and holding the GPU for seconds.
        max_tokens = int(min(440, 12 + 7 * len(audio) / 16000))
        segments, _ = self.model.transcribe(
            audio,
            language=self.cfg["source_language"],
            task=task,
            beam_size=5 if final else 1,
            # Single pass. Retrying at higher temperatures is what loops
            # trigger, and every retry is another full decode.
            temperature=0.0,
            max_new_tokens=max_tokens,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
        )
        parts = []
        for s in segments:
            text = s.text.strip()
            if not text or (s.no_speech_prob > 0.6 and s.avg_logprob < -0.8) or is_hallucination(text, s):
                continue
            parts.append(text)
        return collapse_repeats(" ".join(parts))

    def run(self) -> None:
        try:
            mode = self.load_model()
        except Exception as e:  # shown in the overlay instead of a silent dead thread
            self.ui("status", f"Model failed to load: {e}")
            return
        self.on_ready()
        self.ui("ready", mode)
        while True:
            job = self.jobs.get(0.2)
            if job is None:
                continue
            kind, a16 = job  # already 16 kHz
            if a16 is None:
                self.ui("preview", "")
                continue
            try:
                en = self.translate(a16, "translate", final=(kind == "final"))
                pt = ""
                if kind == "final" and en and self.cfg["show_original"]:
                    pt = self.translate(a16, "transcribe", final=True)
            except Exception as e:
                self.ui("status", f"Error: {e}")
                continue
            if kind == "preview":
                self.ui("preview", en)
                continue
            self.ui("final", en, pt)
            if en:
                print(f"[{time.strftime('%H:%M:%S')}] {en}")
                if pt:
                    print(f"           {pt}")
