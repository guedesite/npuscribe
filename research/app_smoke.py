r"""Lance l'app, declenche la dictee par de vraies frappes, mesure CPU et RAM.

    .venv\Scripts\python.exe research\app_smoke.py
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
        key(VK_CTRL, True); time.sleep(0.01); key(VK_WIN, True)
    else:
        key(VK_WIN, False); time.sleep(0.01); key(VK_CTRL, False)


cfg_path = os.path.join(ROOT, "config.json")
cfg = {}
if os.path.isfile(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
cfg["paste"] = False
cfg["hotkey"] = "ctrl+win"
json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

log_path = os.path.join(ROOT, "research", "smoke.log")
log = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.pyw")],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
time.sleep(1.0)
parent = psutil.Process(proc.pid)
ps = sorted([parent] + parent.children(recursive=True),
            key=lambda p: p.memory_info().rss, reverse=True)[0]


def cpu_over(seconds, label):
    t0 = ps.cpu_times()
    time.sleep(seconds)
    t1 = ps.cpu_times()
    used = (t1.user - t0.user) + (t1.system - t0.system)
    print(f"{label:26s} {100*used/seconds:5.2f} % d'un coeur", flush=True)
    return used / seconds


try:
    for _ in range(300):
        if "pret en" in open(log_path, encoding="utf-8", errors="ignore").read():
            break
        time.sleep(0.2)
    print(f"modele pret ; RAM {ps.memory_info().rss/2**20:.0f} Mo", flush=True)

    time.sleep(2)
    cpu_over(8, "au repos (veille touches)")

    print("\n-> maintien 1 s", flush=True)
    combo(True)
    time.sleep(1.0)
    cpu_over(5, "pendant l'ecoute")
    combo(False)
    time.sleep(3)
    print(f"RAM apres {ps.memory_info().rss/2**20:.0f} Mo", flush=True)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log.close()
    print("\n--- journal ---", flush=True)
    print(open(log_path, encoding="utf-8", errors="ignore").read()[-600:], flush=True)
