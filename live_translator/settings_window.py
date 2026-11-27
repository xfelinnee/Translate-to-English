from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser
from typing import TYPE_CHECKING

from .config import DEFAULTS, UI_KEYS, save_config
from .theme import BG, DIM, FG, FIELD, KNOB, OK, PANEL, WARN

if TYPE_CHECKING:
    from .overlay import Overlay

LOOK_KEYS = ("bg_opacity", "text_opacity", "font_size", "history", "hide_after_seconds", "bg", "fg")


class SettingsWindow:
    """Every change shows on the overlay right away and is saved."""

    def __init__(self, ov: Overlay):
        self.ov, self.o, self.cfg = ov, ov.o, ov.cfg
        w = self.win = tk.Toplevel(ov.root)
        w.title("Translate to English - settings")
        w.configure(bg=PANEL)
        w.attributes("-topmost", True)
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.close)

        self.body = tk.Frame(w, bg=PANEL, padx=18, pady=12)
        self.body.pack(fill="both")
        self.row = 0
        self._vars: list[tk.Variable] = []  # Tk forgets a variable once Python drops it

        self.heading("Look")
        self.slider("Background opacity", 0, 100, 5, self.o["bg_opacity"] * 100, "{:.0f}%", self._set_bg_opacity)
        self.slider("Text opacity", 20, 100, 5, self.o["text_opacity"] * 100, "{:.0f}%", self._set_text_opacity)
        self.slider("Text size", 9, 40, 1, self.o["font_size"], "{:.0f}", self._set_font)
        self.slider("Lines kept", 3, 100, 1, self.o["history"], "{:.0f}", self._set_history)
        self.slider(
            "Hide lines after", 0, 120, 5, self.o["hide_after_seconds"],
            lambda v: "never" if v == 0 else f"{v:.0f} s", self._set_hide,
        )
        self.color_row("Text color", "fg")
        self.color_row("Background", "bg")
        self.check(
            f"Lock overlay: mouse goes through it ({ov.hotkey_label} toggles)", ov.lock_var,
            lambda: ov.set_locked(ov.lock_var.get()),
        )

        self.heading("Translation")
        self.check("Also show the Portuguese (more GPU)", ov.show_pt, ov.toggle_original)
        self.check("Grey live guesses while talking (more GPU)", ov.live_preview, ov.toggle_preview)
        self.slider(
            "Pause that ends a line", 0.3, 1.5, 0.1, self.cfg["silence_end_seconds"], "{:.1f} s", self._set_pause,
        )
        self.note("Shorter = faster lines, but long sentences may get split.")

        self.heading("Audio")
        self.device_row()
        self.device_note = self.note("The output Discord plays into. Switches right away.")

        buttons = tk.Frame(w, bg=PANEL, padx=18, pady=12)
        buttons.pack(fill="x")
        self.button(buttons, "Reset look", self.reset_look).pack(side="left")
        self.button(buttons, "Done", self.close).pack(side="right")

        self._place()

    # -- building blocks
    def heading(self, text: str) -> None:
        pad = (0, 6) if self.row == 0 else (14, 6)
        tk.Label(self.body, text=text, bg=PANEL, fg=OK, font=("Segoe UI Semibold", 10)).grid(
            row=self.row, column=0, columnspan=3, sticky="w", pady=pad
        )
        self.row += 1

    def note(self, text: str) -> tk.Label:
        label = tk.Label(self.body, text=text, bg=PANEL, fg=DIM, font=("Segoe UI", 8))
        label.grid(row=self.row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.row += 1
        return label

    def label(self, text: str) -> None:
        tk.Label(self.body, text=text, bg=PANEL, fg=FG, font=("Segoe UI", 9)).grid(
            row=self.row, column=0, sticky="w", padx=(0, 12), pady=3
        )

    def slider(self, text, lo, hi, step, value, fmt, on_change) -> None:
        self.label(text)
        show = fmt if callable(fmt) else fmt.format
        val = tk.Label(self.body, text=show(value), bg=PANEL, fg=DIM, font=("Segoe UI", 9), width=7, anchor="e")
        val.grid(row=self.row, column=2, sticky="e")

        def changed(v: str) -> None:
            x = round(float(v), 2)
            val.configure(text=show(x))
            on_change(x)

        var = tk.DoubleVar(value=value)
        self._vars.append(var)
        tk.Scale(
            self.body, from_=lo, to=hi, resolution=step, orient="horizontal", variable=var,
            showvalue=False, length=200, command=changed, bg=KNOB, fg=FG, troughcolor=FIELD,
            activebackground=OK, highlightthickness=0, bd=0, sliderrelief="flat", sliderlength=14, width=10,
        ).grid(row=self.row, column=1, sticky="we")
        self.row += 1

    def check(self, text: str, var: tk.BooleanVar, command) -> None:
        tk.Checkbutton(
            self.body, text=text, variable=var, command=command, bg=PANEL, fg=FG,
            selectcolor=FIELD, activebackground=PANEL, activeforeground=FG, font=("Segoe UI", 9),
            bd=0, highlightthickness=0,
        ).grid(row=self.row, column=0, columnspan=3, sticky="w", pady=2)
        self.row += 1

    def color_row(self, text: str, key: str) -> None:
        self.label(text)
        swatch = tk.Label(
            self.body, bg=self.o[key], width=4, relief="flat", cursor="hand2",
            highlightthickness=1, highlightbackground=DIM,
        )
        swatch.grid(row=self.row, column=1, sticky="w", pady=3)

        def pick(_event) -> None:
            _, hexcode = colorchooser.askcolor(color=self.o[key], parent=self.win, title=text)
            if hexcode:
                self.o[key] = hexcode
                swatch.configure(bg=hexcode)
                self.ov.apply_look()

        swatch.bind("<Button-1>", pick)
        self.row += 1

    def device_row(self) -> None:
        self.label("Listen to")
        names = list(dict.fromkeys(self.ov.devices)) or [self.ov.device_name]
        # Show what is actually being recorded, not just what's saved.
        var = tk.StringVar(value=self.ov.device_name)

        def chosen(name: str) -> None:
            error = self.ov.change_device(name)
            if error:
                var.set(self.ov.device_name)
                self.device_note.configure(text=error, fg=WARN)
                return
            self.device_note.configure(text=f"Now listening to {name}.", fg=OK)
            self.cfg["audio_device"] = name
            self.ov.save_soon()

        self._vars.append(var)
        menu = tk.OptionMenu(self.body, var, *names, command=chosen)
        menu.configure(
            bg=FIELD, fg=FG, activebackground=FIELD, activeforeground=FG, highlightthickness=0,
            bd=0, relief="flat", font=("Segoe UI", 9), width=24, anchor="w",
        )
        menu["menu"].configure(bg=FIELD, fg=FG, activebackground=OK, activeforeground=BG)
        menu.grid(row=self.row, column=1, columnspan=2, sticky="we", pady=3)
        self.row += 1

    @staticmethod
    def button(parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, bg=FIELD, fg=FG, activebackground=OK,
            activeforeground=BG, relief="flat", bd=0, padx=14, pady=4, font=("Segoe UI", 9), cursor="hand2",
        )

    # -- changes
    def _set_bg_opacity(self, v: float) -> None:
        self.o["bg_opacity"] = round(v / 100, 2)
        self.ov.apply_look()

    def _set_text_opacity(self, v: float) -> None:
        self.o["text_opacity"] = round(v / 100, 2)
        self.ov.apply_look()

    def _set_font(self, v: float) -> None:
        self.o["font_size"] = int(v)
        self.ov.apply_look()

    def _set_history(self, v: float) -> None:
        self.o["history"] = int(v)
        self.ov.apply_look()

    def _set_hide(self, v: float) -> None:
        self.o["hide_after_seconds"] = int(v)
        self.ov.apply_look()

    def _set_pause(self, v: float) -> None:
        self.cfg["silence_end_seconds"] = v  # the segmenter reads this live
        self.ov.save_soon()

    def reset_look(self) -> None:
        for key in LOOK_KEYS:
            self.o[key] = DEFAULTS["overlay"][key]
        self.ov.apply_look()
        self.win.destroy()
        self.ov.settings_win = SettingsWindow(self.ov)

    def close(self) -> None:
        save_config(self.cfg, UI_KEYS)
        self.win.destroy()
        self.ov.settings_win = None

    def _place(self) -> None:
        """Open beside the overlay, not on top of it."""
        w, r = self.win, self.ov.root
        w.update_idletasks()
        width, height = w.winfo_reqwidth(), w.winfo_reqheight()
        x = r.winfo_x() + r.winfo_width() + 12
        if x + width > w.winfo_screenwidth():
            x = max(0, r.winfo_x() - width - 12)
        y = max(0, min(r.winfo_y(), w.winfo_screenheight() - height - 60))
        w.geometry(f"+{x}+{y}")
