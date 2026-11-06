r"""Teste le raccourci en injectant de vraies frappes clavier.

    .venv\Scripts\python.exe research\test_hotkey.py
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes as w

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wispr.inject import INPUT, KEYBDINPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

VK_CTRL, VK_WIN = 0x11, 0x5B


def key(vk, down):
    ev = INPUT(type=INPUT_KEYBOARD)
    ev.u.ki = KEYBDINPUT(wVk=vk, wScan=0,
                         dwFlags=0 if down else KEYEVENTF_KEYUP,
                         time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(INPUT))


def combo(down):
    if down:
        key(VK_CTRL, True)
        time.sleep(0.01)
        key(VK_WIN, True)
    else:
        key(VK_WIN, False)
        time.sleep(0.01)
        key(VK_CTRL, False)


def fg_class():
    h = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(w.HWND(h), buf, 256)
    return h, buf.value


cfg_path = os.path.join(ROOT, "config.json")
cfg = {}
if os.path.isfile(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
cfg["paste"] = False
cfg["hotkey"] = "ctrl+win"
json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

log_path = os.path.join(ROOT, "research", "hotkey.log")
log = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.pyw")],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
time.sleep(1.0)
ps = psutil.Process(proc.pid)
kids = ps.children(recursive=True)
ps = sorted([ps] + kids, key=lambda p: p.memory_info().rss, reverse=True)[0]

try:
    for _ in range(300):
        if "pret en" in open(log_path, encoding="utf-8", errors="ignore").read():
            break
        time.sleep(0.2)
    print("application prete")

    before = fg_class()
    print("\n1) maintien 1,2 s")
    combo(True)
    time.sleep(1.2)
    combo(False)
    time.sleep(1.5)
    after = fg_class()
    print("   fenetre au premier plan avant/apres :", before[1], "/", after[1])
    print("   menu Demarrer ouvert :", "CoreWindow" in after[1] or "Start" in after[1])

    print("\n2) double appui -> mode continu")
    combo(True); time.sleep(0.08); combo(False)
    time.sleep(0.12)
    combo(True); time.sleep(0.08); combo(False)
    time.sleep(1.5)
    print("   (on est cense ecouter sans tenir les touches)")

    print("\n3) appui unique -> arret")
    combo(True); time.sleep(0.08); combo(False)
    time.sleep(2.0)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log.close()
    print("\n--- journal ---")
    print(open(log_path, encoding="utf-8", errors="ignore").read()[-800:])
