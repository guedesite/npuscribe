"""Capture micro et decoupage en segments de parole.

Le fil audio ne fait que recopier des blocs. Toute la logique (VAD, mise en
forme, decoupage) tourne dans le thread appelant, a 50 Hz, sur des tableaux
numpy de 20 ms : le cout est de l'ordre de quelques dixiemes de pourcent.
"""
from __future__ import annotations

import threading
from collections import deque

import numpy as np

SR = 16000
FRAME = int(0.02 * SR)      # 20 ms


def list_inputs() -> list[tuple[int, str, int]]:
    """Entrees audio disponibles, dedoublonnees par nom (WASAPI/MSSound...).

    Renvoie [(index, nom, frequence_native)].
    """
    import sounddevice as sd
    seen: dict[str, tuple[int, str, int]] = {}
    try:
        for idx, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) <= 0:
                continue
            name = d["name"].strip()
            if name not in seen:
                seen[name] = (idx, name, int(d["default_samplerate"]))
    except Exception:
        pass
    return sorted(seen.values(), key=lambda t: t[1].lower())


def resolve_device(spec) -> int | None:
    """Nom ou index configure -> index sounddevice ; None = peripherique par defaut."""
    if spec in (None, "", "default", 0):
        return None
    if isinstance(spec, int):
        return spec
    for idx, name, _ in list_inputs():
        if name == spec:
            return idx
    low = str(spec).lower()
    for idx, name, _ in list_inputs():
        if low in name.lower():
            return idx
    return None


class Capture:
    """Micro en continu, 16 kHz mono, blocs de 20 ms environ."""

    def __init__(self, samplerate: int = SR, device=None):
        self.samplerate = samplerate
        self.device = resolve_device(device)
        self.device_name = ""
        self._chunks: deque = deque()
        self._lock = threading.Lock()
        self._stream = None
        self.device_sr = samplerate
        self._resid = np.zeros(0, np.float32)

    def _cb(self, indata, frames, t, status):  # thread PortAudio
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        import sounddevice as sd
        last = None
        for rate in (self.samplerate, None):
            try:
                info = sd.query_devices(self.device, kind="input")
                if rate is None:
                    rate = int(info["default_samplerate"])
                self.device_name = str(info["name"]).strip()
                self.device_sr = rate
                self._stream = sd.InputStream(
                    device=self.device, samplerate=rate, channels=1,
                    dtype="float32", blocksize=max(256, rate // 50),
                    callback=self._cb)
                self._stream.start()
                return
            except Exception as e:  # noqa: BLE001
                last = e
                self._stream = None
        raise RuntimeError(f"micro indisponible : {last}")

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def pull(self) -> np.ndarray:
        with self._lock:
            if not self._chunks:
                return np.zeros(0, np.float32)
            data = np.concatenate(self._chunks)
            self._chunks.clear()
        if self.device_sr != SR:
            data = _to_16k(data, self.device_sr)
        return data


def _to_16k(x: np.ndarray, sr: int) -> np.ndarray:
    """Decimation entiere exacte si possible, sinon interpolation lineaire."""
    if sr % SR == 0:
        f = sr // SR
        n = (len(x) // f) * f
        return x[:n].reshape(-1, f).mean(axis=1).astype(np.float32)
    n = int(len(x) * SR / sr)
    if n <= 0:
        return np.zeros(0, np.float32)
    return np.interp(np.linspace(0, len(x) - 1, n),
                     np.arange(len(x)), x).astype(np.float32)


class Segmenter:
    """Transforme le flux continu en morceaux de parole prets pour l'ASR.

    Un segment se ferme apres un silence suffisant, ou de force a la duree
    maximale. Le silence de fin est retire pour ne pas faire halluciner le
    modele.
    """

    def __init__(self, silence_s: float = 0.65, min_speech_s: float = 0.8,
                 max_chunk_s: float = 24.0, preroll_s: float = 0.25,
                 tail_s: float = 0.30):
        self.silence_s = silence_s
        self.min_speech_s = min_speech_s
        self.max_chunk_s = max_chunk_s
        self.tail_s = tail_s
        self.preroll = int(preroll_s * SR)
        self._pre = np.zeros(0, np.float32)
        self._parts: list[np.ndarray] = []
        self._pending = np.zeros(0, np.float32)
        self._speech = 0.0
        self._silence = 0.0
        self._cal: list[float] = []
        self._noise = 0.005
        self._level = 0.0

    @property
    def threshold(self) -> float:
        return min(max(self._noise * 4.0, 0.005), 0.06)

    # -- etat pour la pastille --------------------------------------------
    @property
    def level(self) -> float:
        return self._level

    @property
    def speaking(self) -> bool:
        return self._speech > 0

    def feed(self, x: np.ndarray) -> list[np.ndarray]:
        out = []
        if len(x) == 0:
            return out
        nframes = len(x) // FRAME
        for i in range(nframes):
            fr = x[i * FRAME:(i + 1) * FRAME]
            out.extend(self._frame(fr))
        rest = x[nframes * FRAME:]
        if len(rest):
            out.extend(self._frame(rest))
        return out

    def _frame(self, fr: np.ndarray) -> list[np.ndarray]:
        out = []
        rms = float(np.sqrt(np.mean(fr * fr)) + 1e-12)
        self._level = min(1.0, rms / 0.12)

        # Calibration courte en debut de dictee, puis seuil fige. Une
        # estimation glissante derive pendant les longues prises de parole et
        # finit par considerer la voix elle-meme comme du bruit.
        if len(self._cal) < 15:
            self._cal.append(rms)
            if len(self._cal) == 15:
                self._noise = float(np.clip(
                    np.percentile(self._cal, 20), 1e-4, 0.03))
        voiced = rms > self.threshold

        if not self._speech and not voiced:
            self._pre = np.concatenate([self._pre, fr])[-self.preroll:]
            return out

        if voiced:
            if self._speech == 0.0:
                self._parts = [self._pre]
                self._pre = np.zeros(0, np.float32)
            self._speech += len(fr) / SR
            self._silence = 0.0
        else:
            self._silence += len(fr) / SR

        self._pending = fr
        self._parts.append(fr)

        total = sum(len(p) for p in self._parts) / SR
        closed = None
        if self._silence >= self.silence_s and self._speech >= self.min_speech_s:
            # On garde une queue apres la derniere trame voisee : les consonnes
            # finales (« factures ») sont sous le seuil et seraient coupees.
            closed = total - self._silence + self.tail_s
        elif total >= self.max_chunk_s:
            closed = total
        elif self._silence >= 1.2 and self._speech < self.min_speech_s:
            self._reset()          # bruit isole, on jette
            return out

        if closed is not None:
            audio = np.concatenate(self._parts) if self._parts else np.zeros(0, np.float32)
            keep = min(int(max(0.0, closed) * SR), len(audio))
            seg = audio[:keep]
            if len(seg) / SR >= self.min_speech_s:
                out.append(seg)
            self._reset()
        return out

    def _reset(self) -> None:
        self._parts = []
        self._pending = np.zeros(0, np.float32)
        self._speech = 0.0
        self._silence = 0.0

    def flush(self) -> np.ndarray | None:
        if not self._parts:
            return None
        audio = np.concatenate(self._parts)
        self._reset()
        return audio if len(audio) / SR >= 0.25 else None
