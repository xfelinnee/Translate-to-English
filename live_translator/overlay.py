from __future__ import annotations

import queue
import time
import tkinter as tk

from .audio import Segmenter
from .config import UI_KEYS, save_config
from .settings_window import SettingsWindow
from .theme import DIM, FIELD, OK, WARN
from .winapi import pretty_hotkey, set_click_through


class Overlay:
    """The always-on-top subtitle window.

    It's two windows stacked on each other so the background and the text can
    fade separately: `back` is the coloured panel, `root` holds the text on a
    see-through background.
    """

    def __init__(self, cfg: dict, ui_q: queue.Queue, seg: Segmenter | None, device_name: str, devices: list[str]):
        self.cfg, self.o, self.ui_q, self.seg = cfg, cfg["overlay"], ui_q, seg
        self.device_name = device_name
        self.devices = devices
        self.lines: list[tuple[str, str, float]] = []  # (english, portuguese, time shown)
        self.preview = ""
        self.ready = False
        self.locked = cfg["click_through"]
        self.hotkey_failed = False
        self.hotkey_label = pretty_hotkey(cfg["lock_hotkey"])
        self.status_base = "Starting…"
        self.settings_win: SettingsWindow | None = None
        self._save_job = None
        self._shown = -1

        r = self.root = tk.Tk()
        r.title("Translate to English")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.geometry(f'{self.o["width"]}x{self.o["height"]}+{self.o["x"]}+{self.o["y"]}')

        b = self.back = tk.Toplevel(r)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        r.bind("<Configure>", lambda e: self._sync_back() if e.widget is r else None)

        bar = tk.Frame(r)
        bar.pack(fill="x", padx=10, pady=(6, 0))
        self.dot = tk.Label(bar, text="●", fg=WARN, font=("Segoe UI", 9))
        self.dot.pack(side="left")
        self.status = tk.Label(bar, fg=DIM, font=("Segoe UI", 9), anchor="w")
        self.status.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self.close_btn = tk.Label(bar, text="✕", fg=DIM, font=("Segoe UI", 10), cursor="hand2")
        self.close_btn.bind("<Button-1>", lambda e: self.quit())
        self.gear = tk.Label(bar, text="⚙", fg=DIM, font=("Segoe UI", 11), cursor="hand2")
        self.gear.bind("<Button-1>", lambda e: self.open_settings())
        self.meter = tk.Canvas(bar, width=60, height=6, bg=FIELD, highlightthickness=0)
        self.meter.pack(side="right", padx=8)
        self.meter_bar = self.meter.create_rectangle(0, 0, 0, 6, fill=OK, width=0)

        self.text = tk.Text(r, wrap="word", bd=0, highlightthickness=0, padx=10, pady=6, cursor="fleur", takefocus=0)
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")

        self.grip = tk.Label(r, text="◢", fg=DIM, cursor="size_nw_se", font=("Segoe UI", 9))
        self.grip.bind("<ButtonPress-1>", self._grip_start)
        self.grip.bind("<B1-Motion>", self._grip_move)
        self.grip.bind("<ButtonRelease-1>", lambda e: self._save_geometry())

        self._bg_widgets = [r, b, bar, self.dot, self.status, self.close_btn, self.gear, self.text, self.grip]

        # Where the background is see-through, clicks land on the back panel.
        for w in (b, bar, self.status, self.dot, self.text):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", lambda e: self._save_geometry())
            w.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.show_pt = tk.BooleanVar(value=cfg["show_original"])
        self.live_preview = tk.BooleanVar(value=cfg["live_preview"])
        self.lock_var = tk.BooleanVar(value=self.locked)
        self.menu = tk.Menu(r, tearoff=0)
        self.menu.add_command(label="Settings…", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_checkbutton(label="Also show Portuguese (more GPU)", variable=self.show_pt, command=self.toggle_original)
        self.menu.add_checkbutton(label="Grey live guesses (more GPU)", variable=self.live_preview, command=self.toggle_preview)
        self.menu.add_checkbutton(
            label=f"Lock: mouse goes through ({self.hotkey_label})", variable=self.lock_var,
            command=lambda: self.set_locked(self.lock_var.get()),
        )
        self.menu.add_separator()
        self.menu.add_command(label="Clear", command=self.clear)
        self.menu.add_command(label="Quit", command=self.quit)

        self._apply_colors()
        self._apply_fonts()
        r.update_idletasks()
        self._apply_opacity()
        self.set_locked(self.locked, save=False)
        self._render()
        r.after(50, self._poll)
        r.after(50, self._restack)
        r.after(100, self._tick_meter)
        r.after(1000, self._tick_hide)
        r.after(3000, self._keep_on_top)

    # -- look
    def _apply_colors(self) -> None:
        for w in self._bg_widgets:
            w.configure(bg=self.o["bg"])
        # Pixels of exactly this colour in the text window become see-through,
        # so the back panel (same colour) shows through at its own opacity.
        self.root.attributes("-transparentcolor", self.o["bg"])

    def _apply_fonts(self) -> None:
        fs = self.o["font_size"]
        self.text.tag_configure("en", font=("Segoe UI Semibold", fs), foreground=self.o["fg"], spacing1=4)
        self.text.tag_configure("pt", font=("Segoe UI", max(8, fs - 4), "italic"), foreground=DIM)
        self.text.tag_configure("preview", font=("Segoe UI", fs, "italic"), foreground=DIM, spacing1=4)
        self.text.tag_configure("hint", font=("Segoe UI", max(8, fs - 3)), foreground=DIM)

    def _apply_opacity(self) -> None:
        self.root.attributes("-alpha", self.o["text_opacity"])
        # Never fully 0, or the panel couldn't be grabbed to drag it.
        self.back.attributes("-alpha", max(0.01, self.o["bg_opacity"]))
        self._apply_lock_style()  # changing alpha can reset the window style

    def apply_look(self) -> None:
        self._apply_opacity()
        self._apply_colors()
        self._apply_fonts()
        del self.lines[: -self.o["history"]]
        self._render()
        self.save_soon()

    # -- lock (click-through)
    def set_locked(self, locked: bool, save: bool = True) -> None:
        self.locked = bool(locked)
        self.lock_var.set(self.locked)
        self.cfg["click_through"] = self.locked
        self._apply_lock_style()
        # The buttons and resize corner can't be clicked while locked.
        if self.locked:
            self.gear.pack_forget()
            self.close_btn.pack_forget()
            self.grip.place_forget()
        else:
            self.close_btn.pack(side="right", before=self.meter)
            self.gear.pack(side="right", padx=6, before=self.meter)
            self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self._show_status()
        if save:
            save_config(self.cfg, UI_KEYS)

    def _apply_lock_style(self) -> None:
        for w in (self.root, self.back):
            set_click_through(w, self.locked)

    def _show_status(self) -> None:
        if self.hotkey_failed:
            hint = f"{self.hotkey_label} unavailable, lock from the right-click menu"
        elif self.locked:
            hint = f"Locked · {self.hotkey_label} to unlock"
        else:
            hint = f"Unlocked · {self.hotkey_label} to lock"
        self.status.configure(text=f"{self.status_base}   {hint}")

    # -- window stacking
    def _sync_back(self) -> None:
        r = self.root
        self.back.geometry(f"{r.winfo_width()}x{r.winfo_height()}+{r.winfo_x()}+{r.winfo_y()}")

    def _restack(self) -> None:
        """Panel directly under the text, settings above both."""
        self._sync_back()
        self.back.lift()
        self.root.lift()
        if self.settings_win is not None and self.settings_win.win.winfo_exists():
            self.settings_win.win.lift()

    def _keep_on_top(self) -> None:
        # Games sometimes push topmost windows down; put it back every few seconds.
        self.back.attributes("-topmost", True)
        self.root.attributes("-topmost", True)
        self._restack()
        self._apply_lock_style()
        self.root.after(3000, self._keep_on_top)

    # -- text
    def _visible_lines(self) -> list[tuple[str, str, float]]:
        hide = self.o["hide_after_seconds"]
        if not hide:
            return self.lines
        now = time.monotonic()
        return [ln for ln in self.lines if now - ln[2] < hide]

    def _render(self) -> None:
        t = self.text
        lines = self._visible_lines()
        self._shown = len(lines)
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not self.lines and not self.preview and self.ready:
            t.insert("end", "Waiting for someone to talk…", "hint")
        for i, (en, pt, _) in enumerate(lines):
            t.insert("end", ("\n" if i else "") + en, "en")
            if pt:
                t.insert("end", "\n" + pt, "pt")
        if self.preview:
            t.insert("end", ("\n" if lines else "") + self.preview + " …", "preview")
        t.configure(state="disabled")
        t.see("end")

    def _poll(self) -> None:
        """Handle messages from the worker threads."""
        try:
            while True:
                kind, *args = self.ui_q.get_nowait()
                if kind == "status":
                    self.status_base = args[0]
                    self._show_status()
                elif kind == "ready":
                    self.ready = True
                    self.dot.configure(fg=OK)
                    self.status_base = f"PT → EN · {args[0]} · {self.device_name}"
                    self._show_status()
                    self._render()
                elif kind == "toggle_lock":
                    self.set_locked(not self.locked)
                elif kind == "hotkey_failed":
                    # Without the hotkey a locked overlay could never be unlocked.
                    self.hotkey_failed = True
                    self.set_locked(False)
                elif kind == "preview":
                    self.preview = args[0]
                    self._render()
                elif kind == "final":
                    self.preview = ""
                    en, pt = args
                    if en:
                        self.lines.append((en, pt, time.monotonic()))
                        del self.lines[: -self.o["history"]]
                    self._render()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _tick_meter(self) -> None:
        level = self.seg.level if self.seg else 0.0
        self.meter.coords(self.meter_bar, 0, 0, int(min(1.0, level / 0.15) * 60), 6)
        self.root.after(100, self._tick_meter)

    def _tick_hide(self) -> None:
        if self.o["hide_after_seconds"] and len(self._visible_lines()) != self._shown:
            self._render()
        self.root.after(1000, self._tick_hide)

    # -- moving and resizing
    def _drag_start(self, e) -> None:
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag_move(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _grip_start(self, e) -> None:
        self._gx, self._gy = e.x_root, e.y_root
        self._gw, self._gh = self.root.winfo_width(), self.root.winfo_height()

    def _grip_move(self, e) -> None:
        w = max(260, self._gw + e.x_root - self._gx)
        h = max(90, self._gh + e.y_root - self._gy)
        self.root.geometry(f"{w}x{h}")

    def _save_geometry(self) -> None:
        r = self.root
        self.o.update(x=r.winfo_x(), y=r.winfo_y(), width=r.winfo_width(), height=r.winfo_height())
        save_config(self.cfg, UI_KEYS)

    # -- actions
    def toggle_original(self) -> None:
        self.cfg["show_original"] = self.show_pt.get()
        save_config(self.cfg, UI_KEYS)

    def toggle_preview(self) -> None:
        self.cfg["live_preview"] = self.live_preview.get()
        if not self.cfg["live_preview"]:
            self.preview = ""
            self._render()
        save_config(self.cfg, UI_KEYS)

    def save_soon(self) -> None:
        """Save shortly after the last change instead of on every slider tick."""
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, lambda: save_config(self.cfg, UI_KEYS))

    def open_settings(self) -> None:
        if self.settings_win is not None and self.settings_win.win.winfo_exists():
            self.settings_win.win.lift()
            self.settings_win.win.focus_force()
        else:
            self.settings_win = SettingsWindow(self)

    def clear(self) -> None:
        self.lines.clear()
        self.preview = ""
        self._render()

    def quit(self) -> None:
        self._save_geometry()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
