"""Fenetres Tk : historique des transcriptions et diagnostic.

Chacune vit dans son propre thread et ne partage rien avec la boucle Win32 :
Tk n'est charge qu'a l'ouverture, donc il ne coute rien au repos.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

BG = "#f6f7fb"
CARD = "#ffffff"
INK = "#0f172a"
MUTED = "#64748b"


def _style(root):
    st = ttk.Style(root)
    try:
        st.theme_use("vista")
    except tk.TclError:
        pass
    st.configure(".", font=("Segoe UI", 10), background=BG)
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG)
    st.configure("Title.TLabel", font=("Segoe UI Semibold", 14), background=CARD)
    st.configure("Muted.TLabel", foreground=MUTED, background=CARD)


# --------------------------------------------------------------- historique
class HistoryWindow:
    def __init__(self, history, on_copy, on_paste):
        self.history = history
        self.on_copy = on_copy
        self.on_paste = on_paste
        self.items: list[dict] = []
        self.current: dict | None = None

    def open(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        root = tk.Tk()
        root.title("NPUScribe — historique")
        root.geometry("920x580")
        root.configure(bg=BG)
        _style(root)

        head = tk.Frame(root, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="Historique des transcriptions", bg=CARD, fg=INK,
                 font=("Segoe UI Semibold", 14)).pack(side="left", padx=18,
                                                     pady=(14, 4))
        self.count = tk.Label(head, text="", bg=CARD, fg=MUTED,
                              font=("Segoe UI", 9))
        self.count.pack(side="right", padx=18)

        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(10, 6))
        self.q = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.q)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<KeyRelease>", lambda e: self._refresh())
        ttk.Button(bar, text="Effacer l'historique",
                   command=self._clear).pack(side="left", padx=(8, 0))

        body = tk.PanedWindow(root, orient="horizontal", sashwidth=6,
                              bg=BG, bd=0)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        left = tk.Frame(body, bg=CARD, highlightbackground="#e2e8f0",
                        highlightthickness=1)
        body.add(left, minsize=300, width=340)
        self.list = tk.Listbox(left, bd=0, highlightthickness=0, bg=CARD,
                               fg=INK, font=("Segoe UI", 10),
                               selectbackground="#e0e7ff",
                               selectforeground=INK, activestyle="none")
        lsb = ttk.Scrollbar(left, command=self.list.yview)
        self.list.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.list.pack(fill="both", expand=True, padx=2, pady=2)
        self.list.bind("<<ListboxSelect>>", self._select)

        right = tk.Frame(body, bg=CARD, highlightbackground="#e2e8f0",
                         highlightthickness=1)
        body.add(right, minsize=380)
        self.meta = tk.Label(right, text="", bg=CARD, fg=MUTED,
                             font=("Segoe UI", 9), anchor="w", justify="left")
        self.meta.pack(fill="x", padx=14, pady=(10, 2))
        self.text = tk.Text(right, bd=0, bg=CARD, fg=INK, wrap="word",
                            font=("Segoe UI", 11), padx=14, pady=6,
                            spacing1=2, spacing3=6)
        tsb = ttk.Scrollbar(right, command=self.text.yview)
        self.text.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True, pady=(0, 4))
        self.text.configure(state="disabled")

        actions = tk.Frame(root, bg=BG)
        actions.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(actions, text="Copier",
                   command=lambda: self._act("copy")).pack(side="left")
        ttk.Button(actions, text="Coller au curseur",
                   command=lambda: self._act("paste")).pack(side="left", padx=8)
        ttk.Button(actions, text="Supprimer",
                   command=self._delete).pack(side="left")
        ttk.Button(actions, text="Fermer",
                   command=root.destroy).pack(side="right")

        self.root = root
        self._refresh()
        root.mainloop()

    def _refresh(self) -> None:
        self.items = self.history.search(self.q.get())
        self.list.delete(0, "end")
        for rec in self.items:
            snippet = " ".join(rec.get("text", "").split())[:70]
            stamp = rec.get("ts", "")[5:16]
            self.list.insert("end", f"{stamp}   {snippet}")
        self.count.configure(text=f"{len(self.items)} transcription(s)")
        if self.items:
            self.list.selection_set(0)
            self._select(None)
        else:
            self._show(None)

    def _index(self):
        sel = self.list.curselection()
        return sel[0] if sel else None

    def _select(self, _evt) -> None:
        i = self._index()
        self._show(self.items[i] if i is not None else None)

    def _show(self, rec) -> None:
        self.current = rec
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if rec:
            self.text.insert("1.0", rec.get("text", ""))
            bits = [rec.get("ts", "")]
            if rec.get("seconds"):
                bits.append(f"{rec['seconds']:.1f} s d'audio")
            if rec.get("language"):
                bits.append(str(rec["language"]))
            if rec.get("device"):
                bits.append(str(rec["device"]))
            self.meta.configure(text="  ·  ".join(bits))
        else:
            self.meta.configure(text="Aucune transcription sélectionnée.")
        self.text.configure(state="disabled")

    def _act(self, what) -> None:
        if not self.current:
            return
        text = self.current.get("text", "")
        if what == "copy":
            self.on_copy(text)
        else:
            self.root.withdraw()
            self.root.after(160, lambda: self._paste_and_show(text))

    def _paste_and_show(self, text) -> None:
        self.on_paste(text)
        self.root.deiconify()

    def _delete(self) -> None:
        if not self.current:
            return
        self.history.delete(self.current["id"])
        self.q.set("")
        self._refresh()

    def _clear(self) -> None:
        self.history.clear()
        self.q.set("")
        self._refresh()


# --------------------------------------------------------------- diagnostic
class DiagnosticsWindow:
    """Etat en direct : modele, micro, niveau, derniere transcription."""

    def __init__(self, snapshot):
        self.snapshot = snapshot          # callable -> dict

    def open(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        root = tk.Tk()
        root.title("NPUScribe — diagnostic")
        root.geometry("560x460")
        root.configure(bg=BG)
        _style(root)

        head = tk.Frame(root, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="Diagnostic", bg=CARD, fg=INK,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18,
                                                     pady=(14, 12))

        card = tk.Frame(root, bg=CARD, highlightbackground="#e2e8f0",
                        highlightthickness=1)
        card.pack(fill="x", padx=16, pady=(12, 8))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)

        self.vals = {}
        rows = [("micro", "Micro"), ("etat", "État"), ("modele", "Modèle"),
                ("raccourci", "Raccourci"), ("latence", "Dernière latence")]
        for r, (key, label) in enumerate(rows):
            tk.Label(inner, text=label, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w",
                                                pady=3)
            v = tk.Label(inner, text="—", bg=CARD, fg=INK,
                         font=("Segoe UI Semibold", 10))
            v.grid(row=r, column=1, sticky="w", padx=(16, 0))
            self.vals[key] = v
        inner.columnconfigure(1, weight=1)

        lvlcard = tk.Frame(root, bg=CARD, highlightbackground="#e2e8f0",
                           highlightthickness=1)
        lvlcard.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(lvlcard, text="Niveau du micro", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(10, 2))
        self.meter = tk.Canvas(lvlcard, height=16, bg="#eef2f7",
                               highlightthickness=0)
        self.meter.pack(fill="x", padx=16, pady=(0, 6))
        self.hint = tk.Label(lvlcard, text="", bg=CARD, fg=MUTED,
                             font=("Segoe UI", 9))
        self.hint.pack(anchor="w", padx=16, pady=(0, 10))

        last = tk.Frame(root, bg=CARD, highlightbackground="#e2e8f0",
                        highlightthickness=1)
        last.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        tk.Label(last, text="Dernière transcription", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(10, 2))
        self.last = tk.Text(last, height=6, bd=0, bg=CARD, fg=INK,
                            wrap="word", font=("Segoe UI", 10), padx=16,
                            pady=4)
        self.last.pack(fill="both", expand=True, pady=(0, 10))
        self.last.configure(state="disabled")

        self.root = root
        self._poll()
        root.mainloop()

    def _poll(self) -> None:
        try:
            s = self.snapshot()
        except Exception:
            s = {}
        for key, widget in self.vals.items():
            widget.configure(text=str(s.get(key, "—")))
        w = self.meter.winfo_width() or 480
        h = 16
        self.meter.delete("all")
        self.meter.create_rectangle(0, 0, w, h, fill="#eef2f7", outline="")
        lvl = float(s.get("niveau", 0.0))
        if lvl > 0.005:
            self.meter.create_rectangle(0, 0, max(2, int(w * min(lvl, 1.0))),
                                         h, fill="#ff8a4c", outline="")
        self.hint.configure(text=s.get("indice", ""))
        text = s.get("dernier_texte", "") or "—"
        if self.last.get("1.0", "end").strip() != text.strip():
            self.last.configure(state="normal")
            self.last.delete("1.0", "end")
            self.last.insert("1.0", text)
            self.last.configure(state="disabled")
        self.root.after(150, self._poll)
