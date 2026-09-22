Ajoute un panneau d'aperçu des données extraites dans l'interface, visible avant de sauvegarder.

Tu es un ingénieur UX qui implémente une fonctionnalité de prévisualisation dans une interface Tkinter industrielle.
Cette feature permet à l'utilisateur de vérifier le résultat OCR AVANT d'ouvrir Excel, directement dans l'application.

## Contexte

Actuellement, l'utilisateur doit ouvrir le fichier Excel pour voir si l'extraction est correcte.
L'objectif : afficher un tableau de prévisualisation dans un onglet dédié juste après la conversion,
sans ouvrir de logiciel externe.

## Étape 1 — Vérifier la structure actuelle

Lis `interface.py` et note :
- Comment `_result` est stocké après la conversion (méthode `_on_done`)
- Le format exact de `ocr_results` (liste de dicts avec clés : `rows`, `header`, `meta`)
- Comment la fenêtre est organisée (sections body, log, etc.)

Lis `converter.py` pour comprendre ce que retourne `run()` :
- Clés du dict retourné : `images`, `tableaux`, `total`, `excel`, `word`
- Comment `ocr_results` est accessible depuis `_result`

## Étape 2 — Architecture de la feature

La prévisualisation sera un onglet `ttk.Notebook` ajouté après la conversion :

```
┌─────────────────────────────────────────────────────┐
│  JOURNAL D'EXÉCUTION  │  APERÇU DES DONNÉES         │ ← onglets
├─────────────────────────────────────────────────────┤
│  Bornier :  [liste déroulante ▼]  B702A / B703A ... │
│                                                     │
│  ┌──────────┬─────────┬──────────────┬────────────┐ │
│  │  BORNE   │ COULEUR │    SIGNAL    │ JARRETIERES│ │
│  ├──────────┼─────────┼──────────────┼────────────┤ │
│  │  1       │  ROUGE  │  ALIMENTATION│            │ │
│  │  2       │  BLANC  │  GND         │  1/2       │ │
│  └──────────┴─────────┴──────────────┴────────────┘ │
│                                                     │
│  [← Précédent]  Bornier 1 / 12  [Suivant →]        │
└─────────────────────────────────────────────────────┘
```

## Étape 3 — Implémentation

### 3a — Transformer le log en Notebook

Dans `_build_log_section()`, remplacer le `scrolledtext.ScrolledText` direct
par un `ttk.Notebook` avec deux onglets :

```python
def _build_log_section(self, parent):
    notebook = ttk.Notebook(parent)
    notebook.pack(fill='both', expand=True, pady=(8, 0))

    # Onglet 1 : Journal (comme avant)
    log_frame = tk.Frame(notebook, bg=BG_LOG)
    notebook.add(log_frame, text=" Journal d'exécution ")
    self._log_area = scrolledtext.ScrolledText(
        log_frame, bg=BG_LOG, fg=FG_TEXT,
        font=FONT_MONO, wrap='word', state='disabled',
    )
    self._log_area.pack(fill='both', expand=True)

    # Onglet 2 : Aperçu (vide au démarrage)
    self._apercu_frame = tk.Frame(notebook, bg=BG_PANEL)
    notebook.add(self._apercu_frame, text=" Aperçu des données ")
    self._notebook = notebook

    tk.Label(
        self._apercu_frame,
        text="L'aperçu sera disponible après la conversion.",
        fg=FG_MUTED, bg=BG_PANEL, font=FONT_MAIN
    ).pack(pady=40)
```

### 3b — Remplir l'aperçu après conversion

Dans `_on_done()`, après avoir reçu le résultat, appeler `_build_apercu()` :

```python
def _on_done(self, result):
    self._result = result
    # ... code existant ...
    if hasattr(self, '_apercu_frame'):
        self._build_apercu(result)

def _build_apercu(self, result):
    # Vider le frame précédent
    for w in self._apercu_frame.winfo_children():
        w.destroy()

    # Récupérer les résultats OCR depuis le converter
    # result est le dict retourné par Converter.run()
    # On stocke les ocr_results dans _apercu_data lors de la conversion
    data = getattr(self, '_apercu_data', [])
    if not data:
        tk.Label(self._apercu_frame, text="Aucune donnée à afficher.",
                 fg=FG_MUTED, bg=BG_PANEL, font=FONT_MAIN).pack(pady=40)
        return

    valides = [r for r in data if r.get('success') and r.get('rows')]
    if not valides:
        tk.Label(self._apercu_frame, text="Aucun bornier valide extrait.",
                 fg=FG_WARN, bg=BG_PANEL, font=FONT_MAIN).pack(pady=40)
        return

    self._apercu_index = 0
    self._apercu_valides = valides
    self._render_apercu()

def _render_apercu(self):
    idx = self._apercu_index
    result = self._apercu_valides[idx]
    total = len(self._apercu_valides)

    for w in self._apercu_frame.winfo_children():
        w.destroy()

    # Barre de navigation
    nav = tk.Frame(self._apercu_frame, bg=BG_PANEL)
    nav.pack(fill='x', padx=10, pady=6)

    tk.Button(nav, text="← Précédent", command=self._apercu_prev,
              bg=BG_CARD, fg=FG_TEXT, relief='flat').pack(side='left')
    tk.Label(nav, text=f"  Bornier {idx+1} / {total} — {result.get('meta', {}).get('BORNIER', '?')}  ",
             fg=FG_TEXT, bg=BG_PANEL, font=FONT_BOLD).pack(side='left')
    tk.Button(nav, text="Suivant →", command=self._apercu_next,
              bg=BG_CARD, fg=FG_TEXT, relief='flat').pack(side='left')

    # Tableau
    cols = result.get('header', ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'])
    rows = result.get('rows', [])[:20]  # Limiter à 20 lignes pour la preview

    frame_tbl = tk.Frame(self._apercu_frame, bg=BG_MAIN)
    frame_tbl.pack(fill='both', expand=True, padx=10, pady=4)

    tree = ttk.Treeview(frame_tbl, columns=cols, show='headings', height=15)
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width=120, anchor='w')
    for row in rows:
        values = [row.get(c, '') for c in cols]
        tree.insert('', 'end', values=values)

    scrollbar = ttk.Scrollbar(frame_tbl, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')

def _apercu_prev(self):
    if self._apercu_index > 0:
        self._apercu_index -= 1
        self._render_apercu()

def _apercu_next(self):
    if self._apercu_index < len(self._apercu_valides) - 1:
        self._apercu_index += 1
        self._render_apercu()
```

### 3c — Exposer ocr_results depuis Converter

Dans `converter.py`, ajouter `ocr_results` dans le dict retourné par `run()` :

```python
return {
    'images':      saved,
    'tableaux':    ok,
    'total':       len(ocr_results) + len(word_results),
    'excel':       excel_path,
    'word':        word_path,
    'ocr_results': ocr_results,   # AJOUT pour l'aperçu
}
```

Dans `interface.py`, dans `_poll_queue()` au moment où on reçoit le résultat :
```python
self._apercu_data = msg.get('ocr_results', [])
```

## Étape 4 — Test

```powershell
env\Scripts\python.exe interface.py
```

Vérifier :
1. Les deux onglets apparaissent bien (Journal / Aperçu des données)
2. Avant conversion : message "L'aperçu sera disponible après la conversion."
3. Après conversion réussie : navigation entre borniers fonctionne
4. Onglet Journal toujours fonctionnel (logs colorés, scroll)
5. Aucune erreur Tkinter dans la console

## Étape 5 — Aller à l'onglet aperçu automatiquement

Après la conversion, basculer automatiquement sur l'onglet aperçu :
```python
# Dans _on_done(), après _build_apercu() :
if hasattr(self, '_notebook'):
    self._notebook.select(1)  # Index 1 = onglet Aperçu
```
