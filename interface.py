"""
TriosSeconverter — Interface graphique principale.

Lance avec :  python interface.py
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

from converter import Converter
from template import TableTemplate, TemplateManager


def _resource(name: str) -> Path:
    """Résout le chemin d'une ressource (fonctionne aussi dans un .exe PyInstaller)."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name


# ── Palette de couleurs ───────────────────────────────────────────────
BG_MAIN   = "#1a1a2e"
BG_PANEL  = "#16213e"
BG_CARD   = "#0f3460"
BG_LOG    = "#0a0a14"
FG_TEXT   = "#e0e0f0"
FG_MUTED  = "#7878a0"
FG_OK     = "#56c596"
FG_ERR    = "#e05c5c"
FG_WARN   = "#e0a050"
COL_ACC   = "#e94560"   # rouge-rose accent
COL_ACC2  = "#533483"   # violet secondaire
BTN_HVR   = "#c73652"
FONT_MAIN = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_H1   = ("Segoe UI", 18, "bold")
FONT_H2   = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)


class RoundedButton(tk.Canvas):
    """Bouton à coins arrondis dessiné sur un Canvas."""

    def __init__(self, parent, text, command, bg=COL_ACC, fg="white",
                 hover_bg=BTN_HVR, font=FONT_BOLD, width=220, height=36,
                 radius=8, state='normal', **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent['bg'], highlightthickness=0, **kwargs)
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._font = font
        self._text = text
        self._command = command
        self._radius = radius
        self._state = state
        self._btn_w = width
        self._btn_h = height
        self._draw(bg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        self.create_arc(x1, y1, x1+2*r, y1+2*r, start=90,  extent=90, **kw)
        self.create_arc(x2-2*r, y1, x2, y1+2*r, start=0,   extent=90, **kw)
        self.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, **kw)
        self.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, **kw)
        self.create_rectangle(x1+r, y1, x2-r, y2, **kw)
        self.create_rectangle(x1, y1+r, x2, y2-r, **kw)

    def _draw(self, bg):
        self.delete("all")
        fill = bg if self._state == 'normal' else FG_MUTED
        self._rounded_rect(1, 1, self._btn_w-1, self._btn_h-1,
                           self._radius, fill=fill, outline=fill)
        self.create_text(self._btn_w//2, self._btn_h//2,
                         text=self._text, fill=self._fg,
                         font=self._font)

    def _on_enter(self, _):
        if self._state == 'normal':
            self._draw(self._hover_bg)

    def _on_leave(self, _):
        if self._state == 'normal':
            self._draw(self._bg)

    def _on_click(self, _):
        if self._state == 'normal' and self._command:
            self._command()

    def configure_state(self, state):
        self._state = state
        self._draw(self._bg)

    def set_text(self, text):
        self._text = text
        self._draw(self._bg if self._state == 'normal' else FG_MUTED)


class TriosSeconverterApp(tk.Tk):
    """Fenêtre principale de TriosSeconverter."""

    def __init__(self):
        super().__init__()
        self.title("TriosSeconverter")
        self.geometry("860x660")
        self.minsize(720, 560)
        self.configure(bg=BG_MAIN)

        # Icône de la fenêtre
        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._word_file    = tk.StringVar()
        self._output_dir   = tk.StringVar()
        self._queue: queue.Queue = queue.Queue()
        self._result       = None
        self._tpl_manager  = TemplateManager()
        self._tpl_var      = tk.StringVar(value=self._tpl_manager.names()[0])

        self._build_ui()
        self._poll_queue()

    # ── Construction de l'interface ───────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_body()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG_CARD, height=70)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text="Trios", font=("Segoe UI", 22, "bold"),
                 fg=COL_ACC, bg=BG_CARD).pack(side='left', padx=(22, 0), pady=14)
        tk.Label(hdr, text="Seconverter", font=("Segoe UI", 22, "bold"),
                 fg=FG_TEXT, bg=BG_CARD).pack(side='left', pady=14)

        tk.Label(
            hdr,
            text="  •  Conversion de borniers électriques vers Excel & Word",
            font=("Segoe UI", 10),
            fg=FG_MUTED, bg=BG_CARD
        ).pack(side='left', pady=14)

        # Badge version
        tk.Label(hdr, text=" v1.0 ", font=("Segoe UI", 8),
                 fg=FG_TEXT, bg=COL_ACC2,
                 padx=4, pady=2).pack(side='right', padx=20, pady=22)

    def _build_body(self):
        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=24, pady=16)

        self._build_file_section(body)
        self._build_template_section(body)
        self._build_progress_section(body)
        self._build_buttons_row(body)
        self._build_log_section(body)

    def _build_file_section(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL, padx=16, pady=14)
        card.pack(fill='x', pady=(0, 12))

        self._make_file_row(card, "Fichier Word source (.docx) :",
                            self._word_file, self._browse_word, row=0)
        self._make_file_row(card, "Dossier de destination :",
                            self._output_dir, self._browse_output,
                            row=1, is_dir=True)

    def _build_template_section(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL, padx=16, pady=10)
        card.pack(fill='x', pady=(0, 10))

        tk.Label(card, text="Modèle de tableau :", font=FONT_BOLD,
                 fg=FG_TEXT, bg=BG_PANEL, anchor='w').pack(side='left')

        self._tpl_combo = ttk.Combobox(
            card, textvariable=self._tpl_var,
            values=self._tpl_manager.names(),
            state='readonly', font=FONT_MAIN, width=26,
        )
        self._tpl_combo.pack(side='left', padx=(10, 0))

        style = ttk.Style()
        style.configure("TCombobox", fieldbackground=BG_LOG,
                        background=BG_LOG, foreground=FG_TEXT)

        tk.Label(card, text="", bg=BG_PANEL).pack(side='left', expand=True)

        tk.Button(
            card, text="+ Nouveau modèle", font=FONT_MAIN,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=10, pady=4, cursor='hand2',
            command=self._new_template,
        ).pack(side='left', padx=(6, 0))

        tk.Button(
            card, text="✎ Modifier", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=10, pady=4, cursor='hand2',
            command=self._edit_template,
        ).pack(side='left', padx=(6, 0))

        tk.Button(
            card, text="Supprimer", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_MUTED,
            activebackground="#5a1010", activeforeground="white",
            relief='flat', padx=10, pady=4, cursor='hand2',
            command=self._delete_template,
        ).pack(side='left', padx=(6, 0))

    def _refresh_template_combo(self):
        names = self._tpl_manager.names()
        self._tpl_combo['values'] = names
        if self._tpl_var.get() not in names:
            self._tpl_var.set(names[0])

    def _new_template(self):
        from template import TableTemplate
        tpl = TableTemplate(name="Nouveau modèle", columns=["COL1", "COL2"])
        dlg = TemplateEditorDialog(self, tpl, self._tpl_manager)
        self.wait_window(dlg)
        self._refresh_template_combo()

    def _edit_template(self):
        name = self._tpl_var.get()
        tpl = self._tpl_manager.get(name)
        import copy
        dlg = TemplateEditorDialog(self, copy.deepcopy(tpl),
                                   self._tpl_manager)
        self.wait_window(dlg)
        self._refresh_template_combo()
        if name in self._tpl_manager.names():
            self._tpl_var.set(name)

    def _delete_template(self):
        name = self._tpl_var.get()
        if name == "Bornier standard":
            messagebox.showinfo("Modèle protégé",
                                "Le modèle 'Bornier standard' ne peut pas "
                                "être supprimé.")
            return
        if messagebox.askyesno("Supprimer le modèle",
                               f"Supprimer « {name} » ?"):
            self._tpl_manager.delete(name)
            self._refresh_template_combo()

    def _make_file_row(self, parent, label_text, var, cmd, row, is_dir=False):
        tk.Label(parent, text=label_text, font=FONT_BOLD,
                 fg=FG_TEXT, bg=BG_PANEL, anchor='w'
                 ).grid(row=row*2, column=0, columnspan=2,
                        sticky='w', pady=(8 if row else 0, 3))

        entry = tk.Entry(parent, textvariable=var, font=FONT_MAIN,
                         bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                         relief='flat', bd=5)
        entry.grid(row=row*2+1, column=0, sticky='ew',
                   padx=(0, 10), pady=(0, 10 if row else 8))

        btn = tk.Button(parent, text="Parcourir…", font=FONT_MAIN,
                        bg=COL_ACC2, fg=FG_TEXT,
                        activebackground=COL_ACC, activeforeground="white",
                        relief='flat', padx=12, pady=5,
                        cursor='hand2', command=cmd)
        btn.grid(row=row*2+1, column=1, pady=(0, 10 if row else 8))
        parent.columnconfigure(0, weight=1)

    def _build_progress_section(self, parent):
        pf = tk.Frame(parent, bg=BG_PANEL, padx=16, pady=12)
        pf.pack(fill='x', pady=(0, 10))

        self._status_lbl = tk.Label(
            pf, text="Prêt — sélectionnez les fichiers et lancez la conversion.",
            font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL, anchor='w'
        )
        self._status_lbl.pack(fill='x', pady=(0, 8))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Trios.Horizontal.TProgressbar",
            troughcolor=BG_LOG,
            background=COL_ACC,
            lightcolor=COL_ACC,
            darkcolor=COL_ACC,
            bordercolor=BG_PANEL,
            thickness=18,
        )
        self._pbar = ttk.Progressbar(
            pf, style="Trios.Horizontal.TProgressbar",
            orient='horizontal', mode='determinate', maximum=100
        )
        self._pbar.pack(fill='x')

    def _build_buttons_row(self, parent):
        row = tk.Frame(parent, bg=BG_MAIN)
        row.pack(fill='x', pady=(0, 12))

        self._btn_start = RoundedButton(
            row, text="▶  Lancer la conversion",
            command=self._start,
            bg=COL_ACC, hover_bg=BTN_HVR,
            width=220, height=38, font=FONT_H2
        )
        self._btn_start.pack(side='left')

        self._btn_excel = self._mini_btn(row, "  Excel  ", self._open_excel)
        self._btn_excel.pack(side='left', padx=(14, 0))
        self._btn_word  = self._mini_btn(row, "  Word  ",  self._open_word)
        self._btn_word.pack(side='left', padx=(8, 0))
        self._btn_folder = self._mini_btn(row, "  Dossier  ", self._open_folder)
        self._btn_folder.pack(side='left', padx=(8, 0))

        self._result_btns = [self._btn_excel, self._btn_word, self._btn_folder]
        for b in self._result_btns:
            b.configure_state('disabled')

    def _mini_btn(self, parent, text, cmd):
        return RoundedButton(parent, text=text, command=cmd,
                             bg=BG_CARD, hover_bg=COL_ACC2,
                             width=110, height=38,
                             font=FONT_BOLD, state='disabled')

    def _build_log_section(self, parent):
        lf = tk.Frame(parent, bg=BG_MAIN)
        lf.pack(fill='both', expand=True)

        tk.Label(lf, text="Journal d'exécution", font=FONT_BOLD,
                 fg=FG_MUTED, bg=BG_MAIN, anchor='w'
                 ).pack(fill='x', pady=(0, 5))

        self._log_box = scrolledtext.ScrolledText(
            lf, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', state='disabled', height=13,
            padx=10, pady=8
        )
        self._log_box.pack(fill='both', expand=True)
        self._log_box.tag_config('ok',   foreground=FG_OK)
        self._log_box.tag_config('err',  foreground=FG_ERR)
        self._log_box.tag_config('warn', foreground=FG_WARN)
        self._log_box.tag_config('muted', foreground=FG_MUTED)
        self._log_box.tag_config('info', foreground=FG_TEXT)

    # ── Actions ───────────────────────────────────────────────────────

    def _browse_word(self):
        path = filedialog.askopenfilename(
            title="Sélectionner le fichier Word",
            filetypes=[("Documents Word", "*.docx"), ("Tous les fichiers", "*.*")]
        )
        if path:
            self._word_file.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(
            title="Sélectionner le dossier de destination"
        )
        if path:
            self._output_dir.set(path)

    def _start(self):
        word   = self._word_file.get().strip()
        outdir = self._output_dir.get().strip()

        if not word:
            messagebox.showwarning("Champ manquant",
                                   "Veuillez sélectionner le fichier Word source.")
            return
        if not Path(word).exists():
            messagebox.showerror("Fichier introuvable",
                                 f"Le fichier suivant est introuvable :\n{word}")
            return
        if not outdir:
            messagebox.showwarning("Champ manquant",
                                   "Veuillez sélectionner le dossier de destination.")
            return

        # Réinitialiser
        self._result = None
        self._btn_start.configure_state('disabled')
        self._btn_start.set_text("⏳  Conversion en cours…")
        for b in self._result_btns:
            b.configure_state('disabled')

        self._log_clear()
        self._set_progress(0.0, "Démarrage de la conversion…")
        self._log("═" * 54, 'muted')
        self._log("  TriosSeconverter  —  Conversion démarrée", 'ok')
        self._log(f"  Source  : {word}", 'muted')
        self._log(f"  Sortie  : {outdir}", 'muted')
        self._log(f"  Modèle  : {self._tpl_var.get()}", 'muted')
        self._log("═" * 54, 'muted')

        tpl = self._tpl_manager.get(self._tpl_var.get())

        def _worker():
            try:
                conv = Converter(
                    word_file=Path(word),
                    output_dir=Path(outdir),
                    template=tpl,
                    on_progress=lambda p, m: self._queue.put(('progress', p, m)),
                    on_log=lambda m:         self._queue.put(('log', m, 'info')),
                )
                result = conv.run()
                self._queue.put(('done', result))
            except Exception as exc:
                self._queue.put(('error', str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _open_excel(self):
        if self._result:
            os.startfile(str(self._result['excel']))

    def _open_word(self):
        if self._result:
            os.startfile(str(self._result['word']))

    def _open_folder(self):
        if self._result:
            os.startfile(str(self._result['excel'].parent))

    # ── Mise à jour UI depuis la queue ────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == 'progress':
                    self._set_progress(item[1], item[2])
                elif kind == 'log':
                    self._log(item[1], item[2])
                elif kind == 'done':
                    self._on_done(item[1])
                elif kind == 'error':
                    self._on_error(item[1])
        except Exception:
            pass
        self.after(80, self._poll_queue)

    def _set_progress(self, pct: float, msg: str):
        self._pbar['value'] = pct * 100
        self._status_lbl.configure(text=msg)

    def _log(self, msg: str, tag: str = 'info'):
        self._log_box.configure(state='normal')
        self._log_box.insert('end', msg + '\n', tag)
        self._log_box.see('end')
        self._log_box.configure(state='disabled')

    def _log_clear(self):
        self._log_box.configure(state='normal')
        self._log_box.delete('1.0', 'end')
        self._log_box.configure(state='disabled')

    def _on_done(self, result: dict):
        self._result = result
        self._log("═" * 54, 'ok')
        self._log(f"  ✓ {result['images']} image(s) extraite(s)", 'ok')
        self._log(f"  ✓ {result['tableaux']}/{result['total']} tableaux convertis", 'ok')
        self._log("  ✓ tous_les_borniers.xlsx  créé", 'ok')
        self._log("  ✓ tous_les_borniers.docx  créé", 'ok')
        self._log("═" * 54, 'ok')
        self._set_progress(1.0, "Conversion terminée avec succès !")
        self._btn_start.configure_state('normal')
        self._btn_start.set_text("▶  Lancer la conversion")
        for b in self._result_btns:
            b.configure_state('normal')

    def _on_error(self, msg: str):
        self._log(f"\n  ✗ ERREUR : {msg}", 'err')
        self._set_progress(0.0, "Échec — consultez le journal.")
        self._btn_start.configure_state('normal')
        self._btn_start.set_text("▶  Lancer la conversion")
        messagebox.showerror("Erreur de conversion", msg)


# ── Éditeur de modèle de tableau ─────────────────────────────────────

class TemplateEditorDialog(tk.Toplevel):
    """
    Boîte de dialogue pour créer ou modifier un modèle de tableau.

    Permet de définir :
      - Le nom du modèle
      - La liste des colonnes (ajout / suppression / réordonnancement)
      - Le mot-clé de séparation de section
      - La présence et le contenu du pied de page
    """

    def __init__(self, parent, template: TableTemplate,
                 manager: TemplateManager):
        super().__init__(parent)
        self._tpl = template
        self._mgr = manager
        self._saved = False

        self.title("Éditeur de modèle")
        self.geometry("560x620")
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()   # modal

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._build()

    # ── Construction ─────────────────────────────────────────────────

    def _build(self):
        # Titre
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Éditeur de modèle de tableau",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD
                 ).pack(side='left', padx=16, pady=10)

        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=18, pady=14)

        # ── Nom du modèle ─────────────────────────────────────────────
        self._section(body, "Nom du modèle")
        self._name_var = tk.StringVar(value=self._tpl.name)
        tk.Entry(body, textvariable=self._name_var, font=FONT_MAIN,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', bd=5
                 ).pack(fill='x', pady=(0, 10))

        # ── Colonnes ──────────────────────────────────────────────────
        self._section(body, "Colonnes du tableau (une par ligne)")

        col_frame = tk.Frame(body, bg=BG_PANEL)
        col_frame.pack(fill='both', expand=True, pady=(0, 6))

        self._col_listbox = tk.Listbox(
            col_frame, font=FONT_MONO,
            bg=BG_LOG, fg=FG_TEXT,
            selectbackground=COL_ACC, selectforeground="white",
            relief='flat', bd=0, height=6,
        )
        self._col_listbox.pack(side='left', fill='both',
                               expand=True, padx=(8, 0), pady=8)
        for c in self._tpl.columns:
            self._col_listbox.insert('end', c)

        col_btns = tk.Frame(col_frame, bg=BG_PANEL)
        col_btns.pack(side='left', fill='y', padx=8, pady=8)

        for txt, cmd in [
            ("▲ Monter",    self._col_up),
            ("▼ Descendre", self._col_down),
            ("+ Ajouter",   self._col_add),
            ("✕ Retirer",   self._col_remove),
        ]:
            tk.Button(col_btns, text=txt, font=("Segoe UI", 8),
                      bg=BG_CARD, fg=FG_TEXT,
                      activebackground=COL_ACC2,
                      relief='flat', padx=6, pady=4,
                      cursor='hand2', command=cmd,
                      ).pack(fill='x', pady=2)

        # ── Séparateur de section ─────────────────────────────────────
        self._section(body, "Mot-clé de ligne de séparation")
        kw_row = tk.Frame(body, bg=BG_MAIN)
        kw_row.pack(fill='x', pady=(0, 8))
        self._sect_kw_var = tk.StringVar(value=self._tpl.section_keyword)
        tk.Entry(kw_row, textvariable=self._sect_kw_var, font=FONT_MAIN,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', bd=5
                 ).pack(fill='x')

        # ── Pied de page ──────────────────────────────────────────────
        self._section(body, "Pied de page")

        foot_frame = tk.Frame(body, bg=BG_PANEL, padx=10, pady=8)
        foot_frame.pack(fill='x', pady=(0, 10))

        self._has_footer_var = tk.BooleanVar(value=self._tpl.has_footer)
        tk.Checkbutton(
            foot_frame, text="Activer le pied de page",
            variable=self._has_footer_var,
            font=FONT_MAIN, bg=BG_PANEL, fg=FG_TEXT,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            command=self._toggle_footer,
        ).pack(anchor='w')

        self._foot_inner = tk.Frame(foot_frame, bg=BG_PANEL)
        self._foot_inner.pack(fill='x', pady=(6, 0))

        tk.Label(self._foot_inner, text="Étiquette gauche :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_left_var = tk.StringVar(
            value=self._tpl.footer_left_label)
        tk.Entry(self._foot_inner, textvariable=self._foot_left_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x', pady=(0, 4))

        tk.Label(self._foot_inner,
                 text="Ligne 1 ({PET}, {BORNIER}…) :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_r1_var = tk.StringVar(
            value=self._tpl.footer_row1_format)
        tk.Entry(self._foot_inner, textvariable=self._foot_r1_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x', pady=(0, 4))

        tk.Label(self._foot_inner,
                 text="Ligne 2 ({NO_PLAN}, {INDICE}, {PAGE}…) :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_r2_var = tk.StringVar(
            value=self._tpl.footer_row2_format)
        tk.Entry(self._foot_inner, textvariable=self._foot_r2_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x')

        self._toggle_footer()

        # ── Boutons ───────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=BG_MAIN)
        btn_row.pack(fill='x', pady=(8, 0))

        tk.Button(
            btn_row, text="Enregistrer", font=FONT_BOLD,
            bg=COL_ACC, fg="white",
            activebackground=BTN_HVR, activeforeground="white",
            relief='flat', padx=18, pady=7, cursor='hand2',
            command=self._save,
        ).pack(side='left')

        tk.Button(
            btn_row, text="Annuler", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_MUTED,
            relief='flat', padx=12, pady=7, cursor='hand2',
            command=self.destroy,
        ).pack(side='left', padx=(10, 0))

    # ── Helpers UI ────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=FONT_BOLD,
                 fg=COL_ACC, bg=BG_MAIN, anchor='w'
                 ).pack(fill='x', pady=(6, 2))

    def _toggle_footer(self):
        state = 'normal' if self._has_footer_var.get() else 'disabled'
        for w in self._foot_inner.winfo_children():
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ── Actions sur les colonnes ──────────────────────────────────────

    def _col_up(self):
        sel = self._col_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self._col_listbox.get(i)
        self._col_listbox.delete(i)
        self._col_listbox.insert(i - 1, val)
        self._col_listbox.selection_set(i - 1)

    def _col_down(self):
        sel = self._col_listbox.curselection()
        if not sel or sel[0] >= self._col_listbox.size() - 1:
            return
        i = sel[0]
        val = self._col_listbox.get(i)
        self._col_listbox.delete(i)
        self._col_listbox.insert(i + 1, val)
        self._col_listbox.selection_set(i + 1)

    def _col_add(self):
        dlg = _SimpleInput(self, "Nom de la colonne",
                           "Entrez le nom du mot-clé de colonne :")
        self.wait_window(dlg)
        val = dlg.result
        if val:
            self._col_listbox.insert('end', val.upper().strip())

    def _col_remove(self):
        sel = self._col_listbox.curselection()
        if sel:
            self._col_listbox.delete(sel[0])

    # ── Sauvegarde ───────────────────────────────────────────────────

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Nom manquant",
                                   "Veuillez saisir un nom pour le modèle.",
                                   parent=self)
            return
        cols = [self._col_listbox.get(i)
                for i in range(self._col_listbox.size())]
        if not cols:
            messagebox.showwarning("Colonnes manquantes",
                                   "Ajoutez au moins une colonne.",
                                   parent=self)
            return

        tpl = TableTemplate(
            name=name,
            columns=cols,
            section_keyword=self._sect_kw_var.get().strip(),
            has_footer=self._has_footer_var.get(),
            footer_left_label=self._foot_left_var.get(),
            footer_row1_format=self._foot_r1_var.get(),
            footer_row2_format=self._foot_r2_var.get(),
            footer_detect_keywords=self._tpl.footer_detect_keywords,
            footer_mti_tokens=self._tpl.footer_mti_tokens,
            col_widths={c: 20.0 for c in cols},
            description="",
        )
        self._mgr.add_or_update(tpl)
        self._saved = True
        self.destroy()


class _SimpleInput(tk.Toplevel):
    """Mini-boîte de dialogue pour saisir une valeur texte."""

    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.title(title)
        self.geometry("340x120")
        self.resizable(False, False)
        self.configure(bg=BG_MAIN)
        self.grab_set()
        self.result = ""

        tk.Label(self, text=prompt, font=FONT_MAIN,
                 fg=FG_TEXT, bg=BG_MAIN).pack(padx=14, pady=(14, 4))
        self._var = tk.StringVar()
        e = tk.Entry(self, textvariable=self._var, font=FONT_MAIN,
                     bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                     relief='flat', bd=5)
        e.pack(fill='x', padx=14)
        e.focus_set()
        e.bind("<Return>", lambda _: self._ok())

        tk.Button(self, text="OK", font=FONT_BOLD,
                  bg=COL_ACC, fg="white", relief='flat',
                  padx=16, pady=4, cursor='hand2',
                  command=self._ok).pack(pady=10)

    def _ok(self):
        self.result = self._var.get().strip()
        self.destroy()


# ── Point d'entrée ────────────────────────────────────────────────────

if __name__ == '__main__':
    app = TriosSeconverterApp()
    app.mainloop()
