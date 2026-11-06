"""Le whisper-large-v3 complet en FP16 tient-il sur le NPU, et a quelle qualite ?"""
import os
import time

import numpy as np
import soundfile as sf
import openvino_genai as og

MODEL = r"C:\Users\guedesite\Downloads\wispr-npu\models\whisper-large-v3-fp16"
CACHE = r"C:\Users\guedesite\Desktop\git\npuscribe\cache_lv3_fp16"
WAV = r"C:\Users\guedesite\Downloads\keobiz\out\Enregistrement_2026-11-04_140413_16k_mono.wav"
SR = 16000
audio, sr = sf.read(WAV, dtype="float32")

t0 = time.perf_counter()
try:
    pipe = og.WhisperPipeline(MODEL, "NPU", CACHE_DIR=CACHE)
except Exception as e:
    print(f"CHARGEMENT ECHOUE apres {time.perf_counter()-t0:.0f}s : {type(e).__name__}")
    print(str(e)[:300])
    raise SystemExit(1)
print(f"charge en {time.perf_counter()-t0:.0f}s")

for label, t, d in (("3s", 36, 3.0), ("6s", 41, 6.0), ("20s", 35, 20.0)):
    x = audio[int(t * SR):int((t + d) * SR)]
    buf = np.zeros(30 * SR, np.float32)
    buf[:len(x)] = x[:len(buf)]
    cfg = og.WhisperGenerationConfig()
    cfg.language = "<|fr|>"
    cfg.task = "transcribe"
    cfg.return_timestamps = True
    cfg.max_new_tokens = 448
    t0 = time.perf_counter()
    try:
        txt = str(pipe.generate(buf, cfg)).strip()
        print(f"  {label:4s} {time.perf_counter()-t0:5.2f}s  {txt[:110]}")
    except Exception as e:
        print(f"  {label:4s} ECHEC {type(e).__name__}: {str(e)[:150]}")
