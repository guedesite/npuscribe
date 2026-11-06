"""Moteur de transcription sur le NPU Intel, via OpenVINO.

Choix mesures sur Core Ultra 7 265K (NPU 3) :

- `whisper-large-v3-turbo` en FP16 : 3,6 Go de RAM, ~1,5 s pour 20 s d'audio.
- La variante int4 est *plus lente et plus gourmande* (4,2 Go) : aucune raison
  de quantifier.
- `return_timestamps=True` est obligatoire : sans lui, le pipeline renvoie une
  chaine vide sur une fraction notable des entrees (defaut du chemin
  « notimestamps » d'openvino_genai).
- Une entree de 30,0 s pile renvoie aussi du vide : on plafonne a 24 s.
"""
from __future__ import annotations

import os
import re
import threading

import numpy as np

MODEL_SR = 16000
MAX_INPUT = 30 * MODEL_SR      # taille attendue par le graphe
SAFE_CONTENT = 24.0            # au-dela, le pipeline renvoie parfois du vide
MODEL_REPO = "OpenVINO/whisper-large-v3-turbo-fp16-ov"

_TS = re.compile(r"<\|[\d.,]+\|>")


def model_present(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "openvino_encoder_model.xml"))


def download_model(dest: str, progress=None, log=print) -> str:
    """Telecharge le modele OpenVINO depuis Hugging Face, avec progression."""
    from huggingface_hub import snapshot_download

    os.makedirs(dest, exist_ok=True)
    log(f"telechargement {MODEL_REPO} -> {dest}")
    kwargs = {}
    if progress is not None:
        try:
            from tqdm.auto import tqdm

            class _Progress(tqdm):
                def update(self, n=1):
                    out = super().update(n)
                    try:
                        if self.total:
                            progress(min(1.0, self.n / self.total))
                    except Exception:
                        pass
                    return out

            kwargs["tqdm_class"] = _Progress
        except Exception:
            pass
    return snapshot_download(MODEL_REPO, local_dir=dest,
                             allow_patterns=["*.xml", "*.bin", "*.json", "*.txt"],
                             **kwargs)


class NpuWhisper:
    def __init__(self, model_dir: str, device: str = "NPU",
                 cache_dir: str | None = None, log=print):
        self.model_dir = model_dir
        self.device = device
        self.cache_dir = cache_dir
        self.log = log
        self.pipe = None
        self._lock = threading.Lock()
        self._cfg = None
        self._lang_cache: str | None = None

    # -- chargement --------------------------------------------------------
    def load(self) -> None:
        import openvino_genai as og
        kwargs = {}
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
            kwargs["CACHE_DIR"] = self.cache_dir
        self._og = og
        self.pipe = og.WhisperPipeline(self.model_dir, self.device, **kwargs)
        self._cfg = og.WhisperGenerationConfig()
        self._cfg.return_timestamps = True
        self._cfg.max_new_tokens = 448
        self._cfg.task = "transcribe"
        self.log(f"modele charge sur {self.device}")

    # -- inference ---------------------------------------------------------
    def transcribe(self, audio: np.ndarray, language: str = "fr",
                   hotwords: str | None = None) -> str:
        if self.pipe is None:
            raise RuntimeError("modele non charge")
        x = np.ascontiguousarray(audio, dtype=np.float32)
        if len(x) > int(SAFE_CONTENT * MODEL_SR):
            x = x[:int(SAFE_CONTENT * MODEL_SR)]
        buf = np.zeros(MAX_INPUT, np.float32)
        buf[:len(x)] = x

        with self._lock:
            text = self._gen(self.pipe, buf, language, hotwords, self._cfg)
            if len(text.strip()) < 2:
                # Repli : un court silence en tete debloque le decodeur.
                buf2 = np.zeros(MAX_INPUT, np.float32)
                lead = int(0.3 * MODEL_SR)
                buf2[lead:lead + len(x)] = x[:MAX_INPUT - lead]
                alt = self._gen(self.pipe, buf2, language, hotwords, self._cfg)
                if len(alt.strip()) > len(text.strip()):
                    text = alt
        return _clean(text)

    def _gen(self, pipe, buf, language, hotwords, cfg):
        c = self._og.WhisperGenerationConfig()
        c.return_timestamps = cfg.return_timestamps
        c.max_new_tokens = cfg.max_new_tokens
        c.task = cfg.task
        if language and language != "auto":
            c.language = f"<|{language}|>"
        # `hotwords` et `initial_prompt` sont volontairement ignores : sur NPU
        # ils font echouer infer_request (forme statique du prompt). Le
        # dictionnaire est applique en post-traitement, de facon deterministe.
        try:
            return str(pipe.generate(buf, c))
        except Exception:
            return ""


def _clean(text: str) -> str:
    t = _TS.sub("", text or "")
    t = " ".join(t.split())
    return t.strip()
