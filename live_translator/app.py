import ctypes
import os
import queue
import sys

import pyaudiowpatch as pyaudio

from .audio import Jobs, LoopbackCapture, Segmenter, display_name, loopback_devices
from .config import load_config, save_config
from .overlay import Overlay
from .whisper_worker import WhisperWorker
from .winapi import GlobalHotkey


def pick_output(devices: list[dict], wanted: str) -> dict:
    """Find the configured output, or ask which one Discord plays into."""
    if wanted:
        for d in devices:
            if wanted.lower() in d["name"].lower():
                return d
        print(f'Couldn\'t find the audio output "{wanted}".\n')
    print("Which audio output does Discord play into?")
    print("(Pick one you don't listen to yourself, see the README.)\n")
    for i, d in enumerate(devices, 1):
        print(f"  {i}. {display_name(d)}")
    while True:
        answer = input("\nNumber: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(devices):
            return devices[int(answer) - 1]


class Listener:
    """The audio output currently being recorded. Switching swaps it live.

    Only call listen/switch from the main (Tk) thread: Windows refuses audio
    streams opened from other threads.
    """

    def __init__(self, pa: pyaudio.PyAudio, devices: list[dict], audio_q: queue.Queue):
        self.pa, self.devices, self.q = pa, devices, audio_q
        self.cap: LoopbackCapture | None = None
        self.ready = False  # becomes True once the model has loaded

    def listen(self, device: dict) -> None:
        new = LoopbackCapture(self.pa, device, self.q)
        new.start()  # raises OSError if Windows won't open it; the old one keeps running
        if self.cap is not None:
            self.cap.close()
            self.q.put(("rate", new.rate))
        self.cap = new
        new.enabled = self.ready

    def enable(self) -> None:
        self.ready = True
        self.cap.enabled = True

    def switch(self, name: str) -> str | None:
        """Listen to the output with this name. Returns an error message, or None."""
        device = next((d for d in self.devices if display_name(d) == name), None)
        if device is None:
            return f"{name} not found"
        try:
            self.listen(device)
        except OSError as e:
            return f"Could not listen to {name}: {e}"
        return None


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays
    except (AttributeError, OSError):
        pass

    cfg = load_config()
    pa = pyaudio.PyAudio()
    devices = loopback_devices(pa)
    if not devices:
        print("No audio outputs found.")
        input("\nPress Enter to close.")
        return
    device = pick_output(devices, cfg["audio_device"])
    if not cfg["audio_device"] or cfg["audio_device"].lower() not in device["name"].lower():
        cfg["audio_device"] = display_name(device)
        save_config(cfg, ("audio_device",))

    audio_q: queue.Queue = queue.Queue()
    ui_q: queue.Queue = queue.Queue()
    listener = Listener(pa, devices, audio_q)
    try:
        listener.listen(device)
    except OSError as e:
        print(f"Could not listen to {display_name(device)}: {e}")
        input("\nPress Enter to close.")
        return

    jobs = Jobs()
    seg = Segmenter(cfg, listener.cap.rate, audio_q, jobs)

    def on_ready() -> None:
        seg.start()
        listener.enable()

    WhisperWorker(cfg, jobs, ui_q, on_ready).start()
    GlobalHotkey(
        cfg["lock_hotkey"],
        on_press=lambda: ui_q.put(("toggle_lock",)),
        on_fail=lambda: ui_q.put(("hotkey_failed",)),
    ).start()

    print(f"Listening to: {display_name(device)}")
    print("Translations also show here. Close the overlay or this window to quit.\n")
    Overlay(cfg, ui_q, seg, display_name(device), [display_name(d) for d in devices], listener.switch).run()
    listener.cap.close()
    pa.terminate()
    # The worker threads are blocked in the GPU model and a Windows message
    # loop; exit right away instead of waiting on them.
    os._exit(0)
