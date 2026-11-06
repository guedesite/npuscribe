"""Historique des transcriptions, conserve dans un JSONL append-only."""
from __future__ import annotations

import json
import os
import threading
import time

from . import paths


def default_path() -> str:
    return os.path.join(paths.data_dir(), "history.jsonl")


class History:
    def __init__(self, path: str | None = None, limit: int = 2000):
        self.path = path or default_path()
        self.limit = limit
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._load()

    # -- disque ------------------------------------------------------------
    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._items.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
        self._items.sort(key=lambda r: r.get("id", 0), reverse=True)
        if len(self._items) > self.limit:
            self._items = self._items[: self.limit]
            self._rewrite()

    def _rewrite(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for rec in reversed(self._items):
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        except Exception:
            pass

    # -- operations --------------------------------------------------------
    def add(self, text: str, **meta) -> dict:
        rec = {
            "id": int(time.time() * 1000),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text": text,
        }
        rec.update({k: v for k, v in meta.items() if v is not None})
        with self._lock:
            # Deux dictees dans la meme milliseconde : on decale.
            while self._items and self._items[0]["id"] >= rec["id"]:
                rec["id"] += 1
            self._items.insert(0, rec)
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass
            if len(self._items) > self.limit:
                self._items = self._items[: self.limit]
                self._rewrite()
        return rec

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def get(self, rid: int) -> dict | None:
        with self._lock:
            for rec in self._items:
                if rec["id"] == rid:
                    return rec
        return None

    def search(self, query: str) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return self.all()
        with self._lock:
            return [r for r in self._items if q in r.get("text", "").lower()]

    def delete(self, rid: int) -> None:
        with self._lock:
            self._items = [r for r in self._items if r["id"] != rid]
            self._rewrite()

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._rewrite()
