"""Ouvre l'historique et le diagnostic, verifie qu'aucune exception ne sort."""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wispr import win32  # noqa: E402
from wispr.app import App  # noqa: E402
from wispr.windows import DiagnosticsWindow, HistoryWindow  # noqa: E402

errors: list[str] = []


def guard(fn):
    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            errors.append(traceback.format_exc())
    threading.Thread(target=run, daemon=True).start()


win32.dpi_aware()
app = App()
app.overlay.create()

guard(lambda: HistoryWindow(app.history, app._copy, app._paste).open())
time.sleep(1.2)
guard(lambda: DiagnosticsWindow(app.snapshot).open())
time.sleep(3.0)

print("erreurs :", len(errors), flush=True)
for e in errors:
    print(e[-600:], flush=True)
os._exit(0 if not errors else 1)
