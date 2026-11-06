"""Compile le modele pour le NPU une premiere fois et remplit le cache.

Sans cette etape, le premier lancement de l'application passe cinq a huit
minutes a compiler les graphes. Avec le cache, le chargement tombe a ~3 s.
"""
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wispr import config  # noqa: E402
from wispr.asr import NpuWhisper  # noqa: E402


def main() -> int:
    cfg = config.load()
    model = cfg["model_dir"]
    if not os.path.isfile(os.path.join(model, "openvino_encoder_model.xml")):
        print(f"modele absent : {model}\nlancez d'abord tools/fetch_model.py")
        return 1
    w = NpuWhisper(model, cfg["device"], cfg["cache_dir"])
    t0 = time.time()
    w.load()
    print(f"chargement : {time.time()-t0:.1f}s")

    t0 = time.time()
    txt = w.transcribe(np.zeros(5 * 16000, np.float32), cfg.get("language", "fr"))
    print(f"inference a vide : {time.time()-t0:.2f}s -> {txt!r}")
    print("cache pret :", cfg["cache_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
