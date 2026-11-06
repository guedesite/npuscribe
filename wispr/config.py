"""Configuration : un fichier JSON lisible, editable a la main."""
from __future__ import annotations

import json
import os
import sys

from . import paths

CONFIG_NAME = "config.json"


def config_path() -> str:
    return os.path.join(paths.data_dir(), CONFIG_NAME)


def defaults() -> dict:
    return {
        "hotkey": "ctrl+win",
        "language": "fr",              # "fr", "en" ou "auto"
        "device": "NPU",
        "input_device": "",            # nom du micro ; vide = peripherique par defaut
        "model_dir": os.path.join(paths.models_dir(), "whisper-turbo-fp16"),
        "cache_dir": paths.cache_dir(),
        "dictionary": ["Kéobiz", "Pennylane", "Manon"],
        "replacements": {
            "penny lane": "Pennylane",
            "pennylane": "Pennylane",
            "keobis": "Kéobiz",
            "que au bis": "Kéobiz",
        },
        "max_chunk_s": 24.0,
        "silence_ms": 650,
        "min_speech_s": 0.8,
        "paste": True,
        "paste_mode": "ctrl+v",        # ou "ctrl+shift+v" pour les terminaux
        "restore_clipboard": True,
        "overlay": True,
        "autostart": True,
    }


# Compatibilite : certains modules lisent encore config.DEFAULTS.
DEFAULTS = defaults()


def load() -> dict:
    cfg = defaults()
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def autostart_command() -> str:
    """Commande placee dans la cle Run de Windows.

    Installe, c'est l'executable lui-meme. Depuis les sources on vise
    `pythonw.exe` du venv, jamais l'installation de base qui n'a pas OpenVINO.
    """
    if paths.is_frozen():
        return f'"{sys.executable}"'
    entry = os.path.join(paths.app_dir(), "run.pyw")
    here = os.path.dirname(os.path.abspath(sys.executable))
    pyw = os.path.join(here, "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = os.path.join(here, "python.exe")
    return f'"{pyw}" "{entry}"'


def autostart_enabled() -> bool:
    """Etat reel de la cle Run, pas la valeur souhaitee dans config.json."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "NPUScribe")
        return True
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "NPUScribe", 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, "NPUScribe")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
