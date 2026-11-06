"""NPUScribe — dictee locale, entierement sur le NPU Intel.

Cycle : combinaison de touches -> capture -> segments de parole -> Whisper sur
NPU -> collage au curseur. Rien ne tourne sur le GPU, et le CPU ne fait que
copier des blocs audio de 20 ms.
"""
from __future__ import annotations

import ctypes
import os
import queue
import re
import subprocess
import threading
import time

from . import asr, config, hotkey, inject, paths, win32
from .asr import NpuWhisper
from .history import History
from .windows import DiagnosticsWindow, HistoryWindow

CMD_TOGGLE = 1
CMD_SETTINGS = 2
CMD_HISTORY = 3
CMD_STATUS = 4
CMD_AUTOSTART = 5
CMD_QUIT = 6
DEV_ID_BASE = 1000

ACCENT = (255, 138, 76)
WARN = (239, 68, 68)


class App:
    def __init__(self):
        self.cfg = config.load()
        self.history = History()
        self.cfg["autostart"] = config.autostart_enabled()
        icon = os.path.join(paths.resource_dir(), "assets", "app.ico")
        self.shell = win32.Shell(on_command=self.on_command,
                                 on_notice=self._already_running,
                                 tip="NPUScribe — démarrage")
        self.shell.icon_path = icon
        self.overlay = win32.Overlay()
        self.asr = NpuWhisper(self.cfg["model_dir"], self.cfg["device"],
                              self.cfg["cache_dir"], log=self._log)

        self.ready = False
        self.recording = False
        self.continuous = False
        self.capture = None
        self.segmenter = None
        self.q: queue.Queue = queue.Queue()
        self.parts: list[str] = []
        self._tick_stop = threading.Event()
        self._worker = None
        self._mic = ""
        self._last_text = ""
        self._last_ms = 0
        self._audio_s = 0.0
        self._last_loud = 0.0
        self._dev_ids: dict[int, str] = {}

        self.hk: hotkey.HotkeyService | None = None

    # ------------------------------------------------------------------ log
    def _log(self, msg: str) -> None:
        try:
            print(msg, flush=True)
        except Exception:
            pass

    # --------------------------------------------------------------- demarrage
    def run(self) -> None:
        win32.dpi_aware()
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "NPUScribe.App")
        except Exception:
            pass
        self.overlay.create()
        self.shell.create()
        self._refresh_menu()
        self._apply_hotkey()
        threading.Thread(target=self._load_model, daemon=True).start()
        self.shell.run_forever()

    def _already_running(self) -> None:
        """Une deuxieme instance a ete lancee : on le signale et on disparait."""
        self.overlay.state = "idle"
        self.overlay.set_text("NPUScribe est déjà lancé")
        self._place_overlay()
        self.overlay.show()
        self.overlay.draw()
        threading.Timer(2.0, self.overlay.hide).start()

    def _show_stage(self, text: str) -> None:
        self.overlay.state = "idle"
        self.overlay.set_text(text)
        self._place_overlay()
        self.overlay.show()
        self.overlay.draw()

    def _load_model(self) -> None:
        t0 = time.time()
        model = self.cfg.get("model_dir", "")
        self._show_stage("Chargement du modèle sur le NPU…")

        if not asr.model_present(model):
            self._log(f"modele absent : {model}")
            self._show_stage("Téléchargement du modèle (1,6 Go)…")
            self.shell.set_tip("NPUScribe — téléchargement du modèle")
            last = [0.0]

            def progress(frac: float) -> None:
                now = time.time()
                if now - last[0] < 0.3:
                    return
                last[0] = now
                self.overlay.set_text(f"Modèle — {int(frac * 100)} %")
                self.overlay.draw()

            try:
                asr.download_model(model, progress=progress, log=self._log)
            except Exception as e:  # noqa: BLE001
                self._log(f"telechargement: {e}")
                self._show_stage("Téléchargement impossible — vérifiez la connexion")
                self.shell.set_tip("NPUScribe — modèle manquant")
                time.sleep(3)
                self.overlay.hide()
                return

        # La premiere compilation pour le NPU prend plusieurs minutes.
        if not os.path.isdir(self.cfg.get("cache_dir", "")):
            self._show_stage("Compilation pour le NPU — 5 à 8 min la première fois…")
        self.overlay.set_text("Compilation pour le NPU…")
        self.overlay.draw()
        try:
            self.asr.load()
            self.ready = True
            self.overlay.set_text("Prêt · " + hotkey.combo_label(self.cfg["hotkey"]))
            self.shell.set_tip("NPUScribe — prêt")
        except Exception as e:  # noqa: BLE001
            self.overlay.set_text(f"Échec du chargement : {e}")
            self._log(f"ECHEC: {e}")
            self.shell.set_tip("NPUScribe — échec du chargement")
        self._log(f"pret en {time.time()-t0:.1f}s")
        self.overlay.draw()
        time.sleep(1.6)
        if not self.recording:
            self.overlay.hide()

    def _place_overlay(self) -> None:
        sw = win32.user32.GetSystemMetrics(0)
        sh = win32.user32.GetSystemMetrics(1)
        self.overlay.move_to((sw - self.overlay.W) // 2,
                             sh - self.overlay.H - 96)

    # ------------------------------------------------------------------ menu
    def _device_items(self) -> list:
        from .audio import list_inputs
        items = [("cmd", DEV_ID_BASE, "Par défaut (Windows)")]
        self._dev_ids = {DEV_ID_BASE: ""}
        current = self.cfg.get("input_device") or ""
        for i, (_idx, name, _sr) in enumerate(list_inputs()):
            cid = DEV_ID_BASE + 1 + i
            self._dev_ids[cid] = name
            mark = "✓ " if name == current else "   "
            items.append(("cmd", cid, f"{mark}{name[:52]}"))
        return items

    def _refresh_menu(self) -> None:
        auto = "oui" if self.cfg.get("autostart") else "non"
        self.shell.set_menu([
            ("cmd", CMD_TOGGLE, "Démarrer / arrêter la dictée"),
            ("sep",),
            ("cmd", CMD_HISTORY, "Historique…"),
            ("cmd", CMD_STATUS, "Diagnostic…"),
            ("sub", "Micro", self._device_items()),
            ("cmd", CMD_SETTINGS, "Paramètres…"),
            ("sep",),
            ("cmd", CMD_AUTOSTART, f"Arrêt automatique : {auto}"),
            ("cmd", CMD_QUIT, "Quitter"),
        ])

    def on_command(self, cmd: int) -> None:
        if cmd in self._dev_ids:
            self.cfg["input_device"] = self._dev_ids[cmd]
            config.save(self.cfg)
            self._refresh_menu()
            self.shell.set_tip(f"NPUScribe — micro : {self._dev_ids[cmd] or 'défaut'}")
            return
        if cmd == CMD_TOGGLE:
            self.toggle()
        elif cmd == CMD_SETTINGS:
            self.open_settings()
        elif cmd == CMD_HISTORY:
            HistoryWindow(self.history, on_copy=self._copy,
                          on_paste=self._paste).open()
        elif cmd == CMD_STATUS:
            DiagnosticsWindow(self.snapshot).open()
        elif cmd == CMD_AUTOSTART:
            self.cfg["autostart"] = not self.cfg.get("autostart")
            config.set_autostart(self.cfg["autostart"])
            config.save(self.cfg)
            self._refresh_menu()
        elif cmd == CMD_QUIT:
            self._shutdown()

    def _shutdown(self) -> None:
        self._tick_stop.set()
        if self.hk:
            self.hk.stop()
        if self.capture:
            try:
                self.capture.stop()
            except Exception:
                pass
        self.overlay.hide()
        os._exit(0)

    # --------------------------------------------------------------- raccourci
    def _apply_hotkey(self) -> None:
        try:
            if self.hk is not None:
                self.hk.stop()
            self.hk = hotkey.HotkeyService(
                self.cfg["hotkey"],
                on_start=self._hk_start,
                on_stop=self._hk_stop,
                on_mode=self._hk_mode,
                on_escape=self.cancel)
            self.hk.start()
        except Exception as e:  # noqa: BLE001
            self.hk = None
            self._log(f"raccourci invalide : {e}")
            self.shell.set_tip("NPUScribe — raccourci invalide")

    def _hk_start(self) -> None:
        if not self.ready:
            return
        if not self.recording:
            self.start_recording()
        self.continuous = False

    def _hk_stop(self) -> None:
        if self.recording:
            self.stop_recording()

    def _hk_mode(self, continuous: bool) -> None:
        self.continuous = continuous
        self.overlay.set_text("" if continuous else self.overlay.text)
        if continuous and not self.parts:
            self.overlay.set_text("Écoute continue — appuyez pour arrêter")
        self.overlay.draw(ACCENT)

    def toggle(self) -> None:
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()
            self.continuous = True

    # ------------------------------------------------------------ enregistrement
    def start_recording(self) -> None:
        from .audio import Capture, Segmenter

        self.parts = []
        self.q = queue.Queue()
        self._audio_s = 0.0
        self._last_loud = time.monotonic()
        self.capture = Capture(device=self.cfg.get("input_device") or None)
        try:
            self.capture.start()
        except Exception as e:  # noqa: BLE001
            self._log(f"micro: {e}")
            self._flash(f"Micro indisponible : {e}", WARN)
            return

        self._mic = self.capture.device_name or "défaut"
        self.segmenter = Segmenter(
            silence_s=self.cfg["silence_ms"] / 1000.0,
            min_speech_s=self.cfg["min_speech_s"],
            max_chunk_s=self.cfg["max_chunk_s"])
        self.recording = True
        if self.hk:
            self.hk.set_recording(True)
        self.overlay.state = "recording"
        self.overlay.set_text("Écoute…")
        self._place_overlay()
        self.overlay.show()
        self.overlay.draw(ACCENT)
        self.shell.set_tip("NPUScribe — écoute…")

        self._worker = threading.Thread(target=self._asr_worker, daemon=True)
        self._worker.start()
        self._tick_stop = threading.Event()
        threading.Thread(target=self._tick, daemon=True).start()

    def _flash(self, message: str, colour) -> None:
        self.overlay.state = "warn"
        self.overlay.set_text(message)
        self._place_overlay()
        self.overlay.show()
        self.overlay.draw(colour)
        threading.Timer(3.0, self.overlay.hide).start()

    def _tick(self) -> None:
        last = 0.0
        while not self._tick_stop.is_set():
            try:
                data = self.capture.pull()
                if len(data):
                    for seg in self.segmenter.feed(data):
                        self._audio_s += len(seg) / 16000.0
                        self.q.put(seg)
            except Exception as e:  # noqa: BLE001
                self._log(f"capture: {e}")
            lvl = self.segmenter.level
            if lvl > 0.05:
                self._last_loud = time.monotonic()
            now = time.time()
            if now - last >= 0.045:
                self._paint(lvl)
                last = now
            time.sleep(0.02)

    def _paint(self, lvl: float) -> None:
        silent = time.monotonic() - self._last_loud
        self.overlay.push_level(lvl)
        if silent > 1.5 and not self.parts:
            self.overlay.state = "warn"
            self.overlay.set_text(f"Aucun son — {self._mic[:26]}")
            self.overlay.draw(WARN)
        else:
            if self.overlay.state == "warn" and not self.parts:
                self.overlay.set_text(
                    "Écoute continue — appuyez pour arrêter" if self.continuous
                    else "Écoute…")
            self.overlay.state = "recording"
            self.overlay.draw(ACCENT)

    def _asr_worker(self) -> None:
        while True:
            seg = self.q.get()
            if seg is None:
                return
            try:
                t0 = time.time()
                txt = self.asr.transcribe(seg, self.cfg.get("language", "fr"), None)
                self._last_ms = int((time.time() - t0) * 1000)
                txt = self._apply_replacements(txt)
                if txt:
                    self.parts.append(txt)
                    self.overlay.set_text(" ".join(self.parts)[-34:])
                    self.overlay.draw(ACCENT)
            except Exception as e:  # noqa: BLE001
                self._log(f"asr: {e}")

    def _apply_replacements(self, text: str) -> str:
        out = text
        for src, dst in (self.cfg.get("replacements") or {}).items():
            try:
                out = re.sub(rf"(?<!\w){re.escape(src)}(?!\w)", dst, out,
                             flags=re.IGNORECASE)
            except Exception:
                continue
        return out

    def stop_recording(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.continuous = False
        if self.hk:
            self.hk.set_recording(False)
        self._tick_stop.set()
        try:
            self.capture.stop()
        except Exception:
            pass
        tail = self.segmenter.flush() if self.segmenter else None
        if tail is not None and len(tail):
            self._audio_s += len(tail) / 16000.0
            self.q.put(tail)
        self.q.put(None)
        self.overlay.state = "working"
        self.overlay.set_text("Transcription…")
        self.overlay.draw(ACCENT)
        self.shell.set_tip("NPUScribe — transcription…")
        threading.Thread(target=self._finish, daemon=True).start()

    def cancel(self) -> None:
        """Échap pendant l'écoute : on jette sans rien insérer."""
        if not self.recording:
            return
        self.recording = False
        self.continuous = False
        if self.hk:
            self.hk.set_recording(False)
        self._tick_stop.set()
        try:
            self.capture.stop()
        except Exception:
            pass
        self.parts = []
        self.overlay.state = "idle"
        self.overlay.set_text("Annulé")
        self.overlay.draw(WARN)
        self.shell.set_tip("NPUScribe — prêt")
        threading.Timer(1.0, self.overlay.hide).start()

    def _finish(self) -> None:
        if self._worker:
            self._worker.join(timeout=90)
        text = " ".join(self.parts).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        if text:
            self._last_text = text
            self.history.add(text, seconds=round(self._audio_s, 1),
                             language=self.cfg.get("language"),
                             device=self._mic, segments=len(self.parts))
            if self.cfg.get("paste", True):
                self._paste(text)
            else:
                inject.set_text(text)
        self.overlay.state = "idle"
        self.overlay.set_text("")
        self.overlay.hide()
        self.shell.set_tip("NPUScribe — prêt")
        self._log(f"insere {len(text)} caracteres")

    # ---------------------------------------------------------------- actions
    def _paste(self, text: str) -> None:
        inject.paste(text, restore=self.cfg.get("restore_clipboard", True),
                     mode=self.cfg.get("paste_mode", "ctrl+v"))

    @staticmethod
    def _copy(text: str) -> None:
        inject.set_text(text)

    # -------------------------------------------------------------- diagnostic
    def snapshot(self) -> dict:
        lvl = self.segmenter.level if self.segmenter else 0.0
        if not self.ready:
            etat = "modèle non chargé"
        elif self.recording:
            etat = "écoute continue" if self.continuous else "écoute (maintien)"
        else:
            etat = "prêt"
        if self.recording:
            indice = ("Signal détecté." if time.monotonic() - self._last_loud < 0.6
                      else "Aucun son capté — vérifiez le micro choisi.")
        else:
            indice = "Maintenez la combinaison pour parler, double appui pour l'écoute continue."
        return {
            "micro": self.capture.device_name if self.capture else
                     (self.cfg.get("input_device") or "par défaut (Windows)"),
            "etat": etat,
            "modele": os.path.basename(self.cfg.get("model_dir", "")),
            "raccourci": hotkey.combo_label(self.cfg["hotkey"]),
            "latence": f"{self._last_ms} ms" if self._last_ms else "—",
            "niveau": lvl,
            "indice": indice,
            "dernier_texte": self._last_text,
        }

    # ---------------------------------------------------------------- reglages
    def open_settings(self) -> None:
        threading.Thread(target=self._settings_window, daemon=True).start()

    def _settings_window(self) -> None:
        import tkinter as tk
        from tkinter import ttk
        from .audio import list_inputs

        root = tk.Tk()
        root.title("NPUScribe — réglages")
        root.geometry("540x520")
        root.configure(bg="#f6f7fb")
        st = ttk.Style(root)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure(".", font=("Segoe UI", 10))

        pad = {"padx": 16, "pady": (10, 2), "anchor": "w"}

        def label(text):
            tk.Label(root, text=text, bg="#f6f7fb",
                     font=("Segoe UI Semibold", 9)).pack(**pad)

        label("Combinaison de touches (maintien = parler, double appui = continu)")
        hk = tk.StringVar(value=self.cfg["hotkey"])
        hk_entry = ttk.Entry(root, textvariable=hk)
        hk_entry.pack(fill="x", padx=16)
        hint = tk.Label(root, text="", bg="#f6f7fb", fg="#64748b",
                        font=("Segoe UI", 9))
        hint.pack(anchor="w", padx=16)

        def check(_evt=None):
            try:
                hotkey.parse_combo(hk.get())
                hint.configure(text=hotkey.combo_label(hk.get()), fg="#16a34a")
            except Exception as e:  # noqa: BLE001
                hint.configure(text=str(e), fg="#dc2626")

        hk_entry.bind("<KeyRelease>", check)
        check()

        label("Micro")
        devs = ["Par défaut (Windows)"] + [n for _i, n, _s in list_inputs()]
        cur = self.cfg.get("input_device") or "Par défaut (Windows)"
        dev = tk.StringVar(value=cur if cur in devs else "Par défaut (Windows)")
        ttk.Combobox(root, textvariable=dev, state="readonly",
                     values=devs).pack(fill="x", padx=16)

        label("Langue")
        lang = tk.StringVar(value=self.cfg.get("language", "fr"))
        ttk.Combobox(root, textvariable=lang, state="readonly",
                     values=["fr", "en", "auto"]).pack(fill="x", padx=16)

        label("Dictionnaire (termes séparés par des virgules)")
        dic = tk.StringVar(value=", ".join(self.cfg.get("dictionary") or []))
        ttk.Entry(root, textvariable=dic).pack(fill="x", padx=16)

        label("Silence de fin de phrase (ms)")
        sil = tk.IntVar(value=int(self.cfg.get("silence_ms", 650)))
        ttk.Scale(root, from_=300, to=1500, variable=sil,
                  orient="horizontal").pack(fill="x", padx=16)

        paste = tk.BooleanVar(value=self.cfg.get("paste", True))
        ttk.Checkbutton(root, text="Coller automatiquement au curseur",
                        variable=paste).pack(anchor="w", padx=16, pady=(14, 0))
        auto = tk.BooleanVar(value=self.cfg.get("autostart", False))
        ttk.Checkbutton(root, text="Lancer au démarrage de Windows",
                        variable=auto).pack(anchor="w", padx=16, pady=(6, 0))

        def save():
            spec = hk.get().strip() or "ctrl+win"
            try:
                hotkey.parse_combo(spec)
            except Exception:
                hk.set(self.cfg["hotkey"])
                return
            self.cfg["hotkey"] = spec
            self.cfg["language"] = lang.get()
            self.cfg["dictionary"] = [x.strip() for x in dic.get().split(",") if x.strip()]
            self.cfg["silence_ms"] = int(sil.get())
            self.cfg["paste"] = bool(paste.get())
            chosen = dev.get()
            self.cfg["input_device"] = "" if chosen.startswith("Par défaut") else chosen
            if bool(auto.get()) != bool(self.cfg.get("autostart")):
                self.cfg["autostart"] = bool(auto.get())
                config.set_autostart(self.cfg["autostart"])
            config.save(self.cfg)
            self._apply_hotkey()
            self._refresh_menu()
            root.destroy()

        bar = tk.Frame(root, bg="#f6f7fb")
        bar.pack(fill="x", padx=16, pady=18)
        ttk.Button(bar, text="Annuler", command=root.destroy).pack(side="right")
        ttk.Button(bar, text="Enregistrer", command=save).pack(side="right", padx=8)
        root.mainloop()
