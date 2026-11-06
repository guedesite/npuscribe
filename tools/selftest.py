r"""Test de bout en bout sans micro : un WAV tient lieu de flux audio.

    python tools\selftest.py chemin\vers\extrait.wav [debut] [duree]
"""
import os
import sys
import time

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wispr.audio as audiomod  # noqa: E402
from wispr import inject, win32  # noqa: E402
from wispr import app as appmod  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    start = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0

    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    clip = audio[int(start * sr):int((start + dur) * sr)].copy()
    print(f"extrait : {len(clip)/sr:.1f}s a {sr} Hz")

    class FakeCapture:
        def __init__(self, device=None, samplerate=16000):
            self.i = 0
            self.device_name = "micro simulé (WAV)"
            self.device_sr = 16000

        def start(self):
            pass

        def stop(self):
            pass

        def pull(self):
            out = clip[self.i:self.i + 320]
            self.i += 320
            return out

        @property
        def done(self):
            return self.i >= len(clip)

    audiomod.Capture = FakeCapture

    win32.dpi_aware()
    app = appmod.App()
    app.cfg["paste"] = False          # ne pas coller dans la console
    app.overlay.create()
    t0 = time.time()
    app.asr.load()
    print(f"modele charge en {time.time()-t0:.1f}s")
    app.ready = True

    app.start_recording()
    while not app.capture.done:
        time.sleep(0.05)
    time.sleep(0.3)
    app.stop_recording()

    deadline = time.time() + 60
    while app._worker and app._worker.is_alive() and time.time() < deadline:
        time.sleep(0.1)

    text = " ".join(app.parts).strip()
    print("\n--- resultat ---")
    print("segments :", len(app.parts))
    print("texte    :", text)
    return 0 if text else 1


if __name__ == "__main__":
    sys.exit(main())
