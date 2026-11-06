"""Raccourcis globaux : maintien pour parler, double appui pour l'ecoute continue.

Detection par crochet clavier bas niveau (`WH_KEYBOARD_LL`). Ce crochet ne se
reveille qu'a la frappe : au repos le thread est bloque dans sa boucle de
messages, donc le cout est nul. Il accepte n'importe quelle combinaison, y
compris Ctrl+Win, que `RegisterHotKey` refuse car Windows se l'est reservee.

Si le crochet ne peut pas etre installe, on retombe sur une scrutation a 30 Hz
(`GetAsyncKeyState`), moins econome mais sans dependance.

Gestes :
  maintien                -> dictee tant que les touches restent enfoncees
  double appui            -> mode continu, les touches peuvent etre lachees
  nouvel appui en continu -> arret
  Echap pendant l'ecoute  -> annulation, rien n'est insere
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
ESC_VK = 0x1B

VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10,
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "enter": 0x0D, "ins": 0x2D, "del": 0x2E, "home": 0x24, "end": 0x23,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
    **{str(d): 0x30 + d for d in range(10)},
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
WIN_ALIASES = ("win", "windows", "super", "meta", "cmd")
WIN_VKS = (0x5B, 0x5C)

# Le crochet rapporte les touches gauche et droite separement.
GROUPS = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "control": {0x11, 0xA2, 0xA3},
    "alt": {0x12, 0xA4, 0xA5},
    "shift": {0x10, 0xA0, 0xA1},
    "win": set(WIN_VKS),
    "windows": set(WIN_VKS),
    "super": set(WIN_VKS),
    "meta": set(WIN_VKS),
    "cmd": set(WIN_VKS),
}

TAP_MAX = 0.30        # duree sous laquelle un appui est un « tap »
DOUBLE_GAP = 0.35     # delai maximal entre deux appuis pour un double
POLL_IDLE = 1.0 / 30.0


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HHOOK = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
user32.SetWindowsHookExW.restype = HHOOK
user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]


def _parts(spec: str) -> list[str]:
    return [p.strip().lower() for p in spec.split("+") if p.strip()]


def parse_combo(spec: str) -> list[int]:
    """« ctrl+win » -> [17, 91, 92] ; leve ValueError si une touche est inconnue."""
    codes: list[int] = []
    for part in _parts(spec):
        if part in WIN_ALIASES:
            codes.extend(WIN_VKS)
        elif part in VK:
            codes.append(VK[part])
        elif len(part) == 1:
            codes.append(ord(part.upper()))
        else:
            raise ValueError(f"touche inconnue : {part}")
    if not codes:
        raise ValueError("combinaison vide")
    return codes


def parse_groups(spec: str) -> list[set[int]]:
    """Chaque element doit etre satisfait ; les synonymes sont acceptes."""
    groups: list[set[int]] = []
    for part in _parts(spec):
        if part in GROUPS:
            groups.append(set(GROUPS[part]))
        elif part in VK:
            groups.append({VK[part]})
        elif len(part) == 1:
            groups.append({ord(part.upper())})
        else:
            raise ValueError(f"touche inconnue : {part}")
    if not groups:
        raise ValueError("combinaison vide")
    return groups


def combo_label(spec: str) -> str:
    pretty = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Maj",
              "win": "Win", "windows": "Win", "space": "Espace", "esc": "Échap",
              "super": "Win", "meta": "Win", "cmd": "Win"}
    return " + ".join(pretty.get(p, p.capitalize()) for p in _parts(spec))


class ComboState:
    """Machine a etats du geste, independante de la source d'evenements."""

    def __init__(self, on_start, on_stop, on_mode):
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_mode = on_mode
        self.continuous = False
        self.pending = False
        self._press_t = 0.0
        self._last_up = 0.0

    @staticmethod
    def _fire(fn, *a):
        try:
            fn(*a)
        except Exception:
            pass

    def press(self, now: float) -> None:
        if self.continuous:
            self.continuous = False
            self.pending = False
            self._fire(self.on_mode, False)
            self._fire(self.on_stop)
            return
        if self.pending and now - self._last_up <= DOUBLE_GAP:
            self.pending = False
            self.continuous = True
            self._fire(self.on_mode, True)
            return
        self._press_t = now
        self._fire(self.on_start)

    def release(self, now: float) -> None:
        if self.continuous:
            return
        if now - self._press_t >= TAP_MAX:
            self._fire(self.on_stop)
        else:
            self.pending = True
            self._last_up = now

    def tick(self, now: float) -> None:
        if self.pending and now - self._last_up >= DOUBLE_GAP:
            self.pending = False
            self.continuous = False
            self._fire(self.on_stop)

    def reset(self) -> None:
        self.pending = False
        self.continuous = False


class HotkeyService(threading.Thread):
    def __init__(self, spec: str, on_start, on_stop, on_mode, on_escape=None):
        super().__init__(daemon=True)
        self._spec = spec
        self.groups = parse_groups(spec)
        self.codes = parse_combo(spec)
        self.state = ComboState(on_start, on_stop, on_mode)
        self.on_escape = on_escape
        self.mode = ""                       # "crochet" ou "scrutation"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._pressed: set[int] = set()
        self._down = False
        self._recording = False
        self._esc_down = False
        self._hook = None
        self._proc = HOOKPROC(self._hook_handler)
        self._timer: threading.Timer | None = None

    # -- pilotage ----------------------------------------------------------
    def set_recording(self, on: bool) -> None:
        self._recording = on

    def stop(self) -> None:
        self._stop.set()
        if self._hook:
            try:
                user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
        if self._timer:
            self._timer.cancel()

    @property
    def combo_down(self) -> bool:
        return all(self._pressed & g for g in self.groups)

    # -- crochet clavier ---------------------------------------------------
    def _install_hook(self) -> bool:
        # hMod doit valoir NULL pour WH_KEYBOARD_LL : la procedure vit dans
        # le processus courant, et un handle de module fait echouer l'appel
        # avec ERROR_MOD_NOT_FOUND (126).
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        return bool(self._hook)

    def _hook_handler(self, ncode, wparam, lparam):
        if ncode == 0:
            try:
                kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                self._on_key(int(kb.vkCode), wparam in (WM_KEYDOWN, WM_SYSKEYDOWN))
            except Exception:
                pass
        return user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _on_key(self, vk: int, down: bool) -> None:
        with self._lock:
            if down:
                self._pressed.add(vk)
            else:
                self._pressed.discard(vk)
            now = time.monotonic()
            combo = self.combo_down
            if combo and not self._down:
                self._down = True
                self.state.press(now)
            elif not combo and self._down:
                self._down = False
                self.state.release(now)
                if self.state.pending:
                    self._arm_timer()
            if vk == ESC_VK and down and self._recording and self.on_escape:
                try:
                    self.on_escape()
                except Exception:
                    pass

    def _arm_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(DOUBLE_GAP + 0.02, self._timeout)
        self._timer.daemon = True
        self._timer.start()

    def _timeout(self) -> None:
        with self._lock:
            self.state.tick(time.monotonic())

    # -- boucle ------------------------------------------------------------
    def run(self) -> None:
        try:
            self.mode = "crochet" if self._install_hook() else "scrutation"
        except Exception:
            self.mode = "scrutation"
        try:
            print(f"[hotkey] {self._spec} — {self.mode}", flush=True)
        except Exception:
            pass
        if self.mode == "crochet":
            self._pump()
        else:
            self._poll_loop()

    def _pump(self) -> None:
        msg = w.MSG()
        while not self._stop.is_set():
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(POLL_IDLE)
            with self._lock:
                now = time.monotonic()
                combo = any(user32.GetAsyncKeyState(c) & 0x8000
                            for c in self.codes)
                if combo and not self._down:
                    self._down = True
                    self.state.press(now)
                elif not combo and self._down:
                    self._down = False
                    self.state.release(now)
                else:
                    self.state.tick(now)
                esc = bool(user32.GetAsyncKeyState(ESC_VK) & 0x8000)
                if esc and not self._esc_down and self._recording and self.on_escape:
                    try:
                        self.on_escape()
                    except Exception:
                        pass
                self._esc_down = esc
