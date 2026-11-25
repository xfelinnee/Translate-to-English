"""The few Windows calls Tk can't do: click-through windows and a global hotkey."""
import ctypes
import threading
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020  # mouse goes through to whatever is below
WS_EX_TOOLWINDOW = 0x00000080   # not in Alt+Tab
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000   # clicking it never takes focus from the game

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
NAMED_KEYS = {
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "insert": 0x2D, "delete": 0x2E, "`": 0xC0, "-": 0xBD, "=": 0xBB,
    "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}


def window_handle(win: tk.Misc) -> int:
    return user32.GetParent(win.winfo_id())


def set_click_through(win: tk.Misc, on: bool) -> None:
    hwnd = window_handle(win)
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    new = style | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    new = new | WS_EX_TRANSPARENT if on else new & ~WS_EX_TRANSPARENT
    if new != style:
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)


def parse_hotkey(combo: str) -> tuple[int, int]:
    """'ctrl+shift+l' -> (modifier flags, virtual key code)."""
    mods, vk = 0, 0
    for part in combo.lower().replace(" ", "").split("+"):
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x70 + int(part[1:]) - 1
        elif part in NAMED_KEYS:
            vk = NAMED_KEYS[part]
        else:
            raise ValueError(f"unknown key '{part}' in hotkey '{combo}'")
    if not vk:
        raise ValueError(f"hotkey '{combo}' has no key")
    return mods, vk


def pretty_hotkey(combo: str) -> str:
    """'ctrl+shift+l' -> 'Ctrl+Shift+L'"""
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in combo.replace(" ", "").split("+"))


class GlobalHotkey(threading.Thread):
    """Calls on_press whenever the key combo is pressed, even inside a game."""

    def __init__(self, combo: str, on_press, on_fail):
        super().__init__(daemon=True)
        self.combo, self.on_press, self.on_fail = combo, on_press, on_fail

    def run(self) -> None:
        try:
            mods, vk = parse_hotkey(self.combo)
        except ValueError as e:
            print(e)
            self.on_fail()
            return
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            print(f"The hotkey {self.combo} is already used by another program.")
            self.on_fail()
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.on_press()
