"""Verifie le collage reel dans un champ de saisie, sans toucher a vos fenetres.

On cree notre propre fenetre + zone de texte, on lui donne le focus, on pompe
ses messages pendant qu'un autre thread colle, puis on relit le contenu.
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes as w

sys.path.insert(0, r"C:\Users\guedesite\Desktop\git\npuscribe")
from wispr import inject, win32  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, w.HWND, w.HMENU,
                                   w.HINSTANCE, w.LPVOID]
user32.SendMessageW.restype = ctypes.c_ssize_t

PHRASE = "Bonjour, ceci est un test de dictée : Kéobiz et Pennylane."
win32.dpi_aware()
hinst = ctypes.windll.kernel32.GetModuleHandleW(None)

host = user32.CreateWindowExW(0, "STATIC", "test collage", 0x00CF0000,
                              100, 100, 420, 160, None, None, hinst, None)
edit = user32.CreateWindowExW(0, "EDIT", "", 0x50000000 | 0x0004,
                              10, 10, 380, 80, host, None, hinst, None)
user32.ShowWindow(host, 5)

kernel32 = ctypes.windll.kernel32
fg = user32.GetForegroundWindow()
tid_fg = user32.GetWindowThreadProcessId(w.HWND(fg), None) if fg else 0
tid_me = kernel32.GetCurrentThreadId()
if tid_fg:
    user32.AttachThreadInput(tid_fg, tid_me, True)
user32.SetForegroundWindow(host)
user32.BringWindowToTop(host)
user32.SetFocus(edit)
if tid_fg:
    user32.AttachThreadInput(tid_fg, tid_me, False)

ok_focus = user32.GetForegroundWindow() == host and user32.GetFocus() == edit
print("notre fenetre au premier plan et focus dans le champ :", ok_focus)
if not ok_focus:
    print("test annule plutot que de coller ailleurs")
    user32.DestroyWindow(host)
    sys.exit(2)

result = {}


def coller():
    time.sleep(0.5)
    result["ok"] = inject.paste(PHRASE, restore=True)


threading.Thread(target=coller, daemon=True).start()

# Pompe de messages : sans elle, le champ ne recoit jamais le Ctrl+V.
msg = w.MSG()
end = time.time() + 3.0
while time.time() < end:
    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    else:
        time.sleep(0.005)

buf = ctypes.create_unicode_buffer(512)
user32.SendMessageW(edit, 0x000D, 512, ctypes.byref(buf))
got = buf.value
print("texte colle :", repr(got))
print("identique   :", got == PHRASE)
user32.DestroyWindow(host)
sys.exit(0 if got == PHRASE else 1)
