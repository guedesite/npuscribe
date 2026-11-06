"""Emplacements de l'application et de ses donnees.

Lance depuis les sources, tout vit dans le depot. Une fois installe
(executable PyInstaller), le programme est dans son dossier d'installation —
souvent en lecture seule — et les donnees vont dans %LOCALAPPDATA%\\NPUScribe.
"""
from __future__ import annotations

import os
import sys

APP_NAME = "NPUScribe"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Ressources embarquees (icone). PyInstaller les place dans _internal."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_dir())
    return app_dir()


def data_dir() -> str:
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_NAME)
    else:
        d = app_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def models_dir() -> str:
    return os.path.join(data_dir(), "models")


def cache_dir() -> str:
    return os.path.join(data_dir(), "cache_npu")
