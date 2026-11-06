"""Couche Win32 native : touche globale, icone de notification, pastille.

Aucun framework graphique n'est charge au repos. La pastille est une fenetre
en couches dessinee par GDI dans un DIB 32 bits, donc son cout est celui de
quelques appels GDI par image, pas celui d'un moteur de rendu.
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes as w

import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, WPARAM, LPARAM)

# --- constantes -----------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_NOTICE = WM_APP + 5          # « je suis deja lance », envoye par l'instance 2

SHELL_CLASS = "NPUScribeShell"
SHELL_TITLE = "NPUScribe"

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_TIMER = 0x0113

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_POPUP = 0x0000, 0x0800, 0x0008, 0x0010
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100

DT_LEFT, DT_VCENTER, DT_SINGLELINE, DT_NOPREFIX, DT_END_ELLIPSIS = (
    0x0000, 0x0004, 0x0020, 0x0800, 0x8000)
TRANSPARENT, ANTIALIASED_QUALITY = 1, 4

# --- structures -----------------------------------------------------------
class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
        ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
        ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
        ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
        ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
        ("biClrImportant", w.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
        ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
        ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
        ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON),
    ]


user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, WPARAM, LPARAM]
user32.RegisterClassExW.restype = w.ATOM
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.CreatePopupMenu.restype = w.HMENU
user32.TrackPopupMenu.restype = ctypes.c_int
gdi32.CreateDIBSection.restype = w.HBITMAP

# Les handles Windows sont des pointeurs 64 bits : sans argtypes, ctypes les
# tronque en int 32 bits et echoue avec OverflowError.
gdi32.CreateCompatibleDC.argtypes = [w.HDC]
gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateDIBSection.argtypes = [w.HDC, ctypes.POINTER(BITMAPINFO), w.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), w.HANDLE,
                                   w.DWORD]
gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.SetBkMode.argtypes = [w.HDC, ctypes.c_int]
gdi32.SetTextColor.argtypes = [w.HDC, w.DWORD]
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR]
gdi32.CreateFontW.restype = w.HFONT
user32.GetDC.argtypes = [w.HWND]
user32.GetDC.restype = w.HDC
user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
user32.DrawTextW.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int,
                             ctypes.POINTER(w.RECT), w.UINT]
user32.UpdateLayeredWindow.argtypes = [w.HWND, w.HDC, ctypes.POINTER(w.POINT),
                                       ctypes.POINTER(w.SIZE), w.HDC,
                                       ctypes.POINTER(w.POINT), w.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), w.DWORD]
user32.UpdateLayeredWindow.restype = w.BOOL
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, w.UINT]
user32.LoadIconW.argtypes = [w.HINSTANCE, w.LPCWSTR]
user32.LoadIconW.restype = w.HICON
user32.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int,
                              ctypes.c_int, w.UINT]
user32.LoadImageW.restype = w.HANDLE
user32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
user32.FindWindowW.restype = w.HWND
user32.PostMessageW.argtypes = [w.HWND, w.UINT, WPARAM, LPARAM]
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
user32.AppendMenuW.restype = w.BOOL
user32.DestroyMenu.argtypes = [w.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, w.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int


def dpi_aware() -> None:
    """Coordonnees physiques : la pastille ne floute pas sur un ecran HiDPI."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


class Surface:
    """DIB 32 bits top-down expose comme tableau numpy BGRA."""

    def __init__(self, wd: int, ht: int):
        self.wd, self.ht = wd, ht
        self.hdc = gdi32.CreateCompatibleDC(None)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = wd
        bmi.bmiHeader.biHeight = -ht        # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        self.bits = ctypes.c_void_p()
        self.hbm = gdi32.CreateDIBSection(
            self.hdc, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.hdc, self.hbm)
        self.buf = np.ctypeslib.as_array(
            (ctypes.c_ubyte * (wd * ht * 4)).from_address(self.bits.value))
        self.view = self.buf.reshape(ht, wd, 4)

    def release(self) -> None:
        gdi32.DeleteObject(self.hbm)
        gdi32.DeleteDC(self.hdc)


class Overlay:
    """Pastille flottante, non focusable, traversee par les clics."""

    W, H = 420, 60

    def __init__(self, on_close=None):
        self.on_close = on_close
        self._cls = "WisprNpuOverlay"
        self._proc = WNDPROC(self._wndproc)
        self._surface = None
        self.hwnd = None
        self.text = ""
        self.state = "idle"
        self._levels = np.zeros(18, dtype=np.float32)
        self._font = None
        self._text_surf = None
        self._lock = threading.Lock()

    # -- creation ----------------------------------------------------------
    def create(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT,
            self._cls, "wispr", WS_POPUP, 0, 0, self.W, self.H,
            None, None, hinst, None)
        self._surface = Surface(self.W, self.H)
        self._text_surf = Surface(self.W, self.H)
        return self

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    # -- positionnement ----------------------------------------------------
    def show(self):
        if not self.hwnd:
            return
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def hide(self):
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def move_to(self, x: int, y: int):
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, self.W, self.H,
                                SWP_NOACTIVATE)

    # -- rendu -------------------------------------------------------------
    def push_level(self, v: float):
        with self._lock:
            self._levels = np.roll(self._levels, -1)
            self._levels[-1] = max(0.0, min(1.0, v))

    def set_text(self, s: str):
        self.text = s

    def draw(self, accent=(255, 138, 76)):
        with self._lock:
            levels = self._levels.copy()
        img = render_pill(self.W, self.H, levels, self.text,
                          self._text_surf, accent=accent,
                          active=self.state == "recording")
        self._surface.view[...] = img
        present(self.hwnd, self._surface.hdc, self.W, self.H)


def _rounded_alpha(wd, ht, radius):
    yy, xx = np.mgrid[0:ht, 0:wd]
    dx = np.maximum(np.maximum(radius - 0.5 - xx, xx - (wd - radius - 0.5)), 0)
    dy = np.maximum(np.maximum(radius - 0.5 - yy, yy - (ht - radius - 0.5)), 0)
    d = np.sqrt(dx * dx + dy * dy)
    return np.clip(radius - d + 0.5, 0.0, 1.0)


def _draw_text(surf: Surface, text: str, font, wd: int, ht: int, right: int):
    """Dessine le texte en blanc sur noir ; le canal rouge sert d'alpha.

    Le fond doit etre remis a zero a chaque image : DrawText ne peint que les
    glyphes, il n'efface pas l'image precedente.
    """
    surf.view[...] = 0
    gdi32.SetBkMode(surf.hdc, TRANSPARENT)
    gdi32.SetTextColor(surf.hdc, 0x00FFFFFF)
    old = gdi32.SelectObject(surf.hdc, font)
    rc = w.RECT(20, 0, right, ht)
    user32.DrawTextW(surf.hdc, text, -1, ctypes.byref(rc),
                     DT_LEFT | DT_VCENTER | DT_SINGLELINE
                     | DT_NOPREFIX | DT_END_ELLIPSIS)
    if old:
        gdi32.SelectObject(surf.hdc, old)


_CACHE: dict = {}


def _static(wd, ht, radius=20):
    """Calques invariants : masque arrondi et degrade de fond, en BGR."""
    key = ("static", wd, ht, radius)
    lay = _CACHE.get(key)
    if lay is None:
        mask = _rounded_alpha(wd, ht, radius).astype(np.float32)
        t = (np.arange(ht, dtype=np.float32) / max(ht - 1, 1))[:, None, None]
        top = np.array([21, 18, 18], np.float32)      # BGR de (18,18,21)
        bot = np.array([33, 28, 28], np.float32)
        bg = np.broadcast_to(top * (1 - t) + bot * t, (ht, wd, 3))
        bg = np.ascontiguousarray(bg, np.float32)
        lay = (mask, bg)
        _CACHE[key] = lay
    return lay


def _wave_geom(wd, ht, n, bw=3, gap=3):
    key = ("wave", wd, ht, n, bw, gap)
    g = _CACHE.get(key)
    if g is None:
        wave_w = n * (bw + gap) - gap
        x0 = wd - 20 - wave_w
        idx = np.arange(wave_w)
        bar = np.minimum(idx // (bw + gap), n - 1)
        inside = (idx % (bw + gap)) < bw
        yv = np.abs(np.arange(ht, dtype=np.float32) - ht // 2.0)[:, None]
        g = (x0, wave_w, bar, inside, yv)
        _CACHE[key] = g
    return g


def _text_layer(text_surf, text, wd, ht, right, mask):
    key = ("text", wd, ht, right, text)
    ta = _CACHE.get(key)
    if ta is None:
        _draw_text(text_surf, text, _font_for(wd), wd, ht, right)
        ta = (text_surf.view[:, :, 2].astype(np.float32) / 255.0 * mask)[:, :, None]
        if len(_CACHE) > 64:            # le texte defile : on borne le cache
            for k in [k for k in _CACHE if k[0] == "text"][:-32]:
                _CACHE.pop(k, None)
        _CACHE[key] = ta
    return ta


def render_pill(wd, ht, levels, text, text_surf, accent=(255, 138, 76),
                active=True):
    """Compose la pastille en BGRA premultiplie.

    Le fond et le texte sont mis en cache par texte : entre deux changements,
    seules les barres de l'onde sont recalculees, sur une bande de 96 pixels.
    """
    mask, bg = _static(wd, ht)
    lv = np.asarray(levels, np.float32)
    n = len(lv)
    x0, wave_w, bar, inside, yv = _wave_geom(wd, ht, n)

    key = ("frame", wd, ht, text)
    out = _CACHE.get(key)
    if out is None:
        rgb = bg.copy()
        a = mask * 0.94
        if text:
            ta = _text_layer(text_surf, text, wd, ht, x0 - 16, mask)
            rgb = rgb * (1 - ta) + 245.0 * ta
            a = np.maximum(a, ta[:, :, 0] * 0.98)
        out = np.empty((ht, wd, 4), np.uint8)
        out[:, :, :3] = np.clip(rgb * a[:, :, None], 0, 255)
        out[:, :, 3] = (a * 255).astype(np.uint8)
        if len([k for k in _CACHE if k[0] == "frame"]) > 16:
            for k in [k for k in _CACHE if k[0] == "frame"][:-8]:
                _CACHE.pop(k, None)
        _CACHE[key] = out

    # Bande de l'onde : recalculee a chaque image.
    heights = np.maximum(2.0, lv * (ht * 0.40))
    m = inside[None, :] & (yv <= heights[bar][None, :])
    if m.any():
        fade = (0.30 + 0.70 * lv)[bar]
        alpha = np.where(m, fade[None, :], 0.0)[:, :, None]
        col = np.array([accent[2], accent[1], accent[0]], np.float32)
        aslice = (mask[:, x0:x0 + wave_w] * 0.94)[:, :, None]
        reg = bg[:, x0:x0 + wave_w, :]
        reg = reg * (1 - alpha) + col * alpha
        out[:, x0:x0 + wave_w, :3] = np.clip(reg * aslice, 0, 255)
    return out


_fonts: dict = {}


def _font_for(wd):
    key = (wd, 16)
    if key not in _fonts:
        _fonts[key] = gdi32.CreateFontW(
            -16, 0, 0, 0, 500, 0, 0, 0, 1, 0, 0, ANTIALIASED_QUALITY, 0,
            "Segoe UI")
    return _fonts[key]


def present(hwnd, hdc_mem, wd, ht):
    hdc_screen = user32.GetDC(None)
    pt_dst = w.POINT(0, 0)
    size = w.SIZE(wd, ht)
    pt_src = w.POINT(0, 0)
    blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
    user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst),
                               ctypes.byref(size), hdc_mem, ctypes.byref(pt_src),
                               0, ctypes.byref(blend), ULW_ALPHA)
    user32.ReleaseDC(None, hdc_screen)


def load_icon(path: str):
    """Charge une icone .ico depuis le disque, sinon None."""
    if not path or not os.path.isfile(path):
        return None
    try:
        return user32.LoadImageW(None, path, IMAGE_ICON, 0, 0,
                                 LR_LOADFROMFILE | LR_DEFAULTSIZE)
    except Exception:
        return None


# --- touche globale + icone de notification --------------------------------
class Shell:
    """Fenetre de messages : touche globale, menu de l'icone, arret propre."""

    def __init__(self, on_hotkey=None, on_command=None, tip="NPUScribe",
                 on_notice=None):
        self.on_hotkey = on_hotkey
        self.on_command = on_command
        self.on_notice = on_notice
        self.tip = tip
        self.icon_path = ""
        self._cls = SHELL_CLASS
        self._proc = WNDPROC(self._wndproc)
        self.hwnd = None
        self.hotkey_id = 0xB00B
        self._nid = None
        self._icon = None
        self._menu_cmds: list[tuple[int, str]] = []
        self._thread = None

    def create(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, self._cls, SHELL_TITLE, WS_POPUP,
                                           0, 0, 0, 0, None, None, hinst, None)
        self._icon = load_icon(self.icon_path) or user32.LoadIconW(
            None, ctypes.c_wchar_p(32512))
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._icon
        nid.szTip = self.tip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._nid = nid
        return self

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_HOTKEY and wp == self.hotkey_id and self.on_hotkey:
            try:
                self.on_hotkey()
            except Exception:
                pass
            return 0
        if msg == WM_TRAYICON:
            if lp == WM_RBUTTONUP:
                self._show_menu()
            elif lp == WM_LBUTTONUP:
                try:
                    self.on_command(1)
                except Exception:
                    pass
            return 0
        if msg == WM_NOTICE:
            if self.on_notice:
                try:
                    self.on_notice()
                except Exception:
                    pass
            return 0
        if msg == WM_COMMAND:
            try:
                self.on_command(int(wp) & 0xFFFF)
            except Exception:
                pass
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def set_menu(self, items):
        """items : (« sep »,) | (« cmd », id, libelle) | (« sub », libelle, [items])."""
        self._menu_cmds = items

    def _fill(self, menu, items):
        for item in items:
            kind = item[0]
            if kind == "sep":
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            elif kind == "cmd":
                user32.AppendMenuW(menu, MF_STRING, item[1], item[2])
            elif kind == "sub":
                sub = user32.CreatePopupMenu()
                self._fill(sub, item[2])
                user32.AppendMenuW(menu, MF_POPUP, sub, item[1])

    def set_tip(self, text: str) -> None:
        """Met a jour l'infobulle de l'icone (etat de l'application)."""
        if not self._nid:
            return
        self._nid.szTip = text[:127]
        self._nid.uFlags = NIF_TIP
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        self._fill(menu, self._menu_cmds)
        pt = w.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if cmd:
            self.on_command(cmd)

    def register_hotkey(self, mods: int, vk: int) -> bool:
        if not self.hwnd:
            return False
        user32.UnregisterHotKey(self.hwnd, self.hotkey_id)
        ok = user32.RegisterHotKey(self.hwnd, self.hotkey_id,
                                   mods | MOD_NOREPEAT, vk)
        return bool(ok)

    def run_forever(self):
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def run_in_thread(self):
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            user32.PostQuitMessage(0)


VK_CODES = {
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    **{f"f{i}": 0x70 + i - 1 for i in range(1, 25)},
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
    **{str(d): 0x30 + d for d in range(10)},
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}


def parse_hotkey(spec: str):
    """'ctrl+alt+space' -> (modificateurs, code de touche virtuelle)."""
    mods, vk = 0, 0
    for part in [p.strip().lower() for p in spec.split("+") if p.strip()]:
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "super", "meta"):
            mods |= MOD_WIN
        elif part in VK_CODES:
            vk = VK_CODES[part]
        elif len(part) == 1:
            vk = ord(part.upper())
        else:
            raise ValueError(f"touche inconnue : {part}")
    if not vk:
        raise ValueError("aucune touche principale dans le raccourci")
    return mods, vk
