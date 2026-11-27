import collections
import queue
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio


def loopback_devices(pa: pyaudio.PyAudio) -> list[dict]:
    """Every Windows audio output we can record from."""
    return list(pa.get_loopback_device_info_generator())


def display_name(device: dict) -> str:
    """'Realtek Digital Output (3- Realtek(R) Audio) [Loopback]' -> 'Realtek Digital Output'"""
    return device["name"].replace(" [Loopback]", "").split(" (")[0]


class LoopbackCapture:
    """Records whatever Windows plays into one output device."""

    def __init__(self, pa: pyaudio.PyAudio, device: dict, out_q: queue.Queue):
        self.pa = pa
        self.device = device
        self.rate = int(device["defaultSampleRate"])
        self.channels = int(device["maxInputChannels"])
        self.q = out_q
        self.stream = None
        self.enabled = False  # audio is dropped until the model is ready

    def _callback(self, data, frames, time_info, status):
        if self.enabled:
            a = np.frombuffer(data, dtype=np.float32)
            if self.channels > 1:
                a = a.reshape(-1, self.channels).mean(axis=1)
            else:
                a = a.copy()
            self.q.put(a)
        return (None, pyaudio.paContinue)

    def start(self) -> None:
        # Has to run on the main thread: WASAPI refuses streams opened elsewhere.
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self.device["index"],
            frames_per_buffer=int(self.rate * 0.02),
            stream_callback=self._callback,
        )

    def close(self) -> None:
        self.enabled = False
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
        except OSError:
            pass
        self.stream = None


def to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    """Resample to the 16 kHz Whisper expects."""
    audio = audio.astype(np.float32)
    if rate == 16000:
        return audio
    # Low-pass below 8 kHz first so high frequencies don't fold back in.
    taps = 63
    n = np.arange(taps) - (taps - 1) / 2
    fc = 7600 / rate
    h = 2 * fc * np.sinc(2 * fc * n) * np.hamming(taps)
    h /= h.sum()
    audio = np.convolve(audio, h, mode="same").astype(np.float32)
    if rate % 16000 == 0:
        return audio[:: rate // 16000].copy()
    n_out = int(len(audio) * 16000 / rate)
    x = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(x, np.arange(len(audio)), audio).astype(np.float32)


def quietest_cut(audio: np.ndarray, rate: int) -> int:
    """Index of the quietest 30 ms in the last 3 s, for cutting long speech."""
    frame = int(rate * 0.03)
    start = max(0, len(audio) - 3 * rate)
    tail = audio[start:]
    nframes = len(tail) // frame
    if nframes < 2:
        return len(audio)
    energy = (tail[: nframes * frame].reshape(nframes, frame) ** 2).mean(axis=1)
    return start + int(np.argmin(energy)) * frame + frame // 2


class Jobs:
    """Finished lines in order, plus only the newest preview."""

    def __init__(self):
        self.cv = threading.Condition()
        self.finals: collections.deque = collections.deque()
        self.preview = None

    def add_final(self, audio) -> None:
        with self.cv:
            self.finals.append(audio)
            self.preview = None
            self.cv.notify()

    def set_preview(self, audio) -> None:
        with self.cv:
            self.preview = audio
            self.cv.notify()

    def get(self, timeout: float):
        with self.cv:
            self.cv.wait_for(lambda: self.finals or self.preview is not None, timeout)
            if self.finals:
                return "final", self.finals.popleft()
            if self.preview is not None:
                p, self.preview = self.preview, None
                return "preview", p
            return None


class Segmenter(threading.Thread):
    """Splits the audio stream into lines at pauses and hands them on at 16 kHz.

    Put ("rate", new_rate) in the queue after switching to another output: it
    drops the half-finished line and continues at the new sample rate.
    """

    def __init__(self, cfg: dict, rate: int, in_q: queue.Queue, jobs: Jobs):
        super().__init__(daemon=True)
        self.cfg, self.rate, self.in_q, self.jobs = cfg, rate, in_q, jobs
        self.level = 0.0
        self.last_audio = 0.0

    def run(self) -> None:
        rate = self.rate
        preroll: collections.deque = collections.deque()
        preroll_len, preroll_max = 0, int(0.3 * rate)
        buf: list = []
        buf_len = voiced_len = 0
        speaking = False
        last_voice = last_preview = 0.0
        # Pauses are timed on the audio's own clock, so if the PC is busy and
        # audio piles up, the backlog still splits at the right places.
        t = 0.0
        last_tick = time.monotonic()
        while True:
            try:
                chunk = self.in_q.get(timeout=0.05)
            except queue.Empty:
                chunk = None
            if isinstance(chunk, tuple):  # ("rate", new_rate): output switched
                rate = self.rate = chunk[1]
                preroll.clear()
                preroll_len, preroll_max = 0, int(0.3 * rate)
                buf, buf_len, voiced_len, speaking = [], 0, 0, False
                self.jobs.set_preview(None)
                continue
            now = time.monotonic()
            has_audio = chunk is not None and len(chunk) > 0

            if has_audio:
                t += len(chunk) / rate
            else:
                # Windows sends nothing while nothing plays, so once we're
                # caught up, silence passes at wall-clock speed.
                t += now - last_tick
            last_tick = now

            if has_audio:
                self.last_audio = now
                rms = float(np.sqrt(np.mean(chunk * chunk)))
                self.level = rms
                voiced = rms >= self.cfg["speech_threshold"]
                if speaking:
                    buf.append(chunk)
                    buf_len += len(chunk)
                    if voiced:
                        last_voice = t
                        voiced_len += len(chunk)
                elif voiced:
                    speaking = True
                    buf = list(preroll) + [chunk]
                    buf_len = preroll_len + len(chunk)
                    voiced_len = len(chunk)
                    preroll.clear()
                    preroll_len = 0
                    last_voice = last_preview = t
                else:
                    preroll.append(chunk)
                    preroll_len += len(chunk)
                    while preroll_len > preroll_max:
                        preroll_len -= len(preroll.popleft())
            elif now - self.last_audio > 0.3:
                self.level = 0.0

            if not speaking:
                continue

            if t - last_voice >= self.cfg["silence_end_seconds"]:
                audio = np.concatenate(buf)
                # Under 0.3 s of sound is a click or a key press, not speech.
                self.jobs.add_final(to_16k(audio, rate) if voiced_len / rate >= 0.3 else None)
                speaking, buf, buf_len, voiced_len = False, [], 0, 0
            elif buf_len / rate >= self.cfg["max_segment_seconds"]:
                audio = np.concatenate(buf)
                cut = quietest_cut(audio, rate)
                self.jobs.add_final(to_16k(audio[:cut], rate))
                rest = audio[cut:]
                buf, buf_len, voiced_len = [rest], len(rest), len(rest)
                last_preview = t
            elif (
                self.cfg["live_preview"]
                and buf_len / rate >= self.cfg["preview_start_seconds"]
                and t - last_preview >= self.cfg["preview_every_seconds"]
            ):
                self.jobs.set_preview(to_16k(np.concatenate(buf), rate))
                last_preview = t
