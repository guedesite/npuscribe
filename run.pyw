"""Point d'entree — sans console, une seule instance a la fois."""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ERROR_ALREADY_EXISTS = 183


def main() -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_wchar_p]
    # Le handle reste ouvert pendant toute la duree du processus : c'est lui
    # qui signale l'instance unique.
    kernel32.CreateMutexW(None, False, "Local\\NPUScribe.SingleInstance")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        try:
            from wispr import win32
            hwnd = win32.user32.FindWindowW(win32.SHELL_CLASS, win32.SHELL_TITLE)
            if hwnd:
                win32.user32.PostMessageW(hwnd, win32.WM_NOTICE, 0, 0)
        except Exception:
            pass
        return 0

    from wispr.app import App
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
