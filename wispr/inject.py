"""Insertion du texte au curseur : presse-papier puis Ctrl+V natif."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL, VK_V, VK_SHIFT, VK_MENU = 0x11, 0x56, 0x10, 0x12
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [w.HWND]
user32.OpenClipboard.restype = w.BOOL
user32.CloseClipboard.restype = w.BOOL
user32.EmptyClipboard.restype = w.BOOL
user32.GetClipboardData.argtypes = [w.UINT]
user32.GetClipboardData.restype = w.HANDLE
user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
user32.SetClipboardData.restype = w.HANDLE
kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = w.HGLOBAL
kernel32.GlobalLock.argtypes = [w.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
user32.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def get_text() -> str | None:
    if not user32.OpenClipboard(None):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def set_text(text: str) -> bool:
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return False
        ctypes.memmove(ptr, ctypes.addressof(data), size)
        kernel32.GlobalUnlock(h)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        user32.CloseClipboard()


def _tap(vk: int, down: bool):
    ev = INPUT(type=INPUT_KEYBOARD)
    ev.u.ki = KEYBDINPUT(wVk=vk, wScan=0,
                         dwFlags=0 if down else KEYEVENTF_KEYUP,
                         time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(INPUT))


def paste(text: str, restore: bool = True, delay: float = 0.05,
          mode: str = "ctrl+v") -> bool:
    """Colle `text` dans la fenetre qui a le focus, puis restaure le presse-papier.

    `mode` : « ctrl+v » partout, « ctrl+shift+v » pour les terminaux qui
    interceptent Ctrl+V.
    """
    if not text:
        return False
    previous = get_text() if restore else None
    if not set_text(text):
        return False
    time.sleep(delay)
    shifted = mode.replace(" ", "") == "ctrl+shift+v"
    _tap(VK_CONTROL, True)
    time.sleep(0.01)
    if shifted:
        _tap(VK_SHIFT, True)
        time.sleep(0.01)
    _tap(VK_V, True)
    time.sleep(0.01)
    _tap(VK_V, False)
    time.sleep(0.01)
    if shifted:
        _tap(VK_SHIFT, False)
        time.sleep(0.01)
    _tap(VK_CONTROL, False)
    if restore and previous is not None:
        # Laisse au programme cible le temps de lire le presse-papier.
        def _later():
            time.sleep(0.6)
            set_text(previous)
        import threading
        threading.Thread(target=_later, daemon=True).start()
    return True
