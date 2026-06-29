Agent d'implémentation UX/UI : restructure l'interface en logique "parcours de traitement" sans casser le moteur de conversion existant.

Tu es un ingénieur UI/UX senior spécialisé dans les applications industrielles Tkinter pour utilisateurs non-développeurs.
Ta mission : implémenter la refonte UX de TriosSeconverter en suivant l'audit validé par l'utilisateur, phase par phase, sans jamais toucher au moteur de conversion.

---

## Contexte de l'audit — À lire avant toute modification

L'application passe d'une logique "onglets techniques" à une logique "parcours de traitement".
L'utilisateur ne choisit plus un outil technique, il choisit ce qu'il veut produire.

**Principe directeur :**
```
Que veux-tu produire ?
  → Avec quelle source ?
  → Avec quel modèle ?
  → Avec quel moteur ?
  → Lancer
```

**3 types de traitement :**
1. Transformation tableaux — borniers électriques → Excel
2. Transformation dessins — plans PDF/images → DXF (futur)
3. Transformation tableaux et dessins — mode mixte (futur)

**Règle absolue :** le moteur de conversion (`converter.py`, `ocr_processor.py`, `generer_classeur.py`) ne doit JAMAIS être modifié. Seule `interface.py` évolue.

---

## Étape 1 — Diagnostic de l'interface actuelle

Lis `interface.py` en entier et cartographie :

```
Structure actuelle :
  _build_header()        → logo + titre
  _build_toolbar()       → boutons Lancer, Excel, Dossier, Audit, Observer, Enrichir dico
  _build_nav()           → onglets : Accueil | Paramètres | Mode OCR | Formater Excel | Options | Aide
  _build_status_bar()    → barre de statut en bas
  _build_main_area()     → pages : accueil, params, ocr, format, options, aide

Problèmes confirmés par l'audit :
  ✗ L'accueil ne pose pas la question "quel type de document ?"
  ✗ La toolbar "Enrichir dico" est toujours visible même avant tout choix
  ✗ Les onglets techniques (Mode OCR, Formater Excel) sont exposés avant le choix de workflow
  ✗ Aucune barre contextuelle n'apparaît selon le mode choisi
  ✗ Le parcours "suivant / précédent" n'existe pas — tout est ouvert en même temps
```

Vérifie que ta lecture correspond à ces éléments. Si la structure a changé, adapte le plan.

---

## Étape 2 — Choix de la phase à implémenter

Demande à l'utilisateur quelle phase démarrer :

```
PHASES DISPONIBLES
━━━━━━━━━━━━━━━━━

Phase 1 — Accueil avec 3 cartes de workflow  [recommandée pour commencer]
  → Ajoute les 3 cartes de choix (Tableaux / Dessins / Mixte) à la page d'accueil
  → Conserve l'animation existante
  → Mémorise le workflow choisi dans self._workflow_mode

Phase 2 — Barre contextuelle tableaux
  → Ajoute une toolbar contextuelle sous la nav quand workflow = "tableaux"
  → Boutons : Reformater | Enrichir dictionnaire | Ouvrir log | Dossier sortie
  → Actifs/désactivés selon l'état (fichier source défini, log disponible, etc.)

Phase 3 — Assistant "Suivant / Précédent" pour tableaux
  → Transforme le parcours params → OCR → options → lancer en stepper
  → Conserve toute la logique existante, juste réordonnée
  → Navigation Suivant/Précédent + barre de progression d'étapes

Phase 4 — Tableau de traitement amélioré
  → Pendant la conversion : aperçu PDF à gauche, progression au centre, modèle à droite
  → Logs + temps écoulé + page en cours en bas

Phase 5 — Workflow dessins (squelette)
  → Crée la carte "Transformation dessins" fonctionnelle
  → Affiche "en cours de développement" avec description du plan
```

---

## Étape 3 — Implémentation Phase 1 (Accueil avec cartes)

### Modifications dans `interface.py` :

**3.1 — Ajouter la variable d'état du workflow**

Dans `__init__`, après les variables existantes :
```python
self._workflow_mode = tk.StringVar(value="")  # "tableaux", "dessins", "mixte"
```

**3.2 — Modifier `_build_page_accueil()`**

La page d'accueil doit avoir deux zones :
- Zone haute : titre + CARTES DE CHOIX (remplace "3 étapes simples")
- Zone basse : animation existante (inchangée)

Structure des cartes :
```python
def _build_workflow_cards(self, parent):
    """3 cartes de choix du workflow — Tableaux / Dessins / Mixte."""
    cards_frame = tk.Frame(parent, bg=BG_PANEL, padx=24, pady=14)
    cards_frame.pack(fill='x', padx=32, pady=(0, 0))

    tk.Label(cards_frame, text="Que souhaitez-vous produire ?",
             font=FONT_BOLD, fg=COL_ACC, bg=BG_PANEL).pack(anchor='w', pady=(0, 10))

    row = tk.Frame(cards_frame, bg=BG_PANEL)
    row.pack(fill='x')

    cards = [
        {
            "titre": "📊  Transformation tableaux",
            "desc": "Borniers électriques scannés → Excel structuré",
            "detail": "Outils : Reformater  •  Dictionnaire  •  Logs",
            "mode": "tableaux",
            "couleur": COL_ACC,
        },
        {
            "titre": "📐  Transformation dessins",
            "desc": "Plans PDF/images → DXF AutoCAD",
            "detail": "Outils : Aperçu  •  Calibration  •  Export DXF",
            "mode": "dessins",
            "couleur": COL_ACC2,
        },
        {
            "titre": "🔀  Tableaux + Dessins",
            "desc": "Document mixte → Excel + DXF",
            "detail": "Outils : Classification  •  Tableaux  •  Dessins",
            "mode": "mixte",
            "couleur": "#27AE60",
        },
    ]

    for card in cards:
        self._make_workflow_card(row, card)
```

**3.3 — Méthode `_make_workflow_card()`**

Chaque carte est un Frame cliquable avec survol coloré :
```python
def _make_workflow_card(self, parent, card: dict):
    """Crée une carte de sélection de workflow."""
    frame = tk.Frame(parent, bg=BG_CARD, padx=16, pady=12,
                     relief='flat', cursor='hand2')
    frame.pack(side='left', fill='both', expand=True, padx=(0, 10))

    # Barre de couleur en haut de la carte
    barre = tk.Frame(frame, bg=card["couleur"], height=4)
    barre.pack(fill='x', pady=(0, 8))

    tk.Label(frame, text=card["titre"], font=FONT_H2,
             fg=FG_TEXT, bg=BG_CARD, anchor='w').pack(fill='x')
    tk.Label(frame, text=card["desc"], font=FONT_MAIN,
             fg=FG_MUTED, bg=BG_CARD, anchor='w').pack(fill='x', pady=(4, 8))
    tk.Label(frame, text=card["detail"], font=("Segoe UI", 8),
             fg=card["couleur"], bg=BG_CARD, anchor='w').pack(fill='x')

    # Indicateur de sélection
    self._card_indicators[card["mode"]] = tk.Frame(frame, bg=BG_CARD, height=3)
    self._card_indicators[card["mode"]].pack(fill='x', pady=(8, 0))

    def _on_click(mode=card["mode"], col=card["couleur"]):
        self._select_workflow(mode, col)

    def _on_enter(e, f=frame, col=card["couleur"]):
        f.configure(bg=BG_PANEL)
        for w in f.winfo_children():
            try:
                w.configure(bg=BG_PANEL)
            except Exception:
                pass

    def _on_leave(e, f=frame):
        if self._workflow_mode.get() != card["mode"]:
            f.configure(bg=BG_CARD)
            for w in f.winfo_children():
                try:
                    w.configure(bg=BG_CARD)
                except Exception:
                    pass

    for widget in [frame] + list(frame.winfo_children()):
        widget.bind('<Button-1>', lambda e, fn=_on_click: fn())
        widget.bind('<Enter>', _on_enter)
        widget.bind('<Leave>', _on_leave)
```

**3.4 — Méthode `_select_workflow()`**

```python
def _select_workflow(self, mode: str, couleur: str):
    """Sélectionne le workflow et met à jour l'interface."""
    self._workflow_mode.set(mode)

    # Mettre à jour les indicateurs visuels des cartes
    for m, ind in self._card_indicators.items():
        if m == mode:
            ind.configure(bg=couleur)
        else:
            ind.configure(bg=BG_CARD)

    # Mettre à jour la barre contextuelle
    self._update_context_toolbar()

    # Si mode tableaux : aller directement à la page Paramètres
    if mode == "tableaux":
        self._show_page('params')
    elif mode in ("dessins", "mixte"):
        messagebox.showinfo(
            "En développement",
            f"Le mode '{mode}' est en cours de développement.\n"
            "Utilisez 'Transformation tableaux' pour l'instant."
        )
```

**3.5 — Initialiser `_card_indicators` dans `__init__`**

```python
self._card_indicators: dict = {}
```

---

## Étape 4 — Implémentation Phase 2 (Barre contextuelle tableaux)

### La barre contextuelle apparaît SOUS la nav quand workflow = "tableaux"

**4.1 — Ajouter `_build_context_toolbar()` dans `_build_ui()`**

Appeler après `_build_nav()` et avant `_build_status_bar()` :
```python
self._build_context_toolbar()
```

**4.2 — Méthode `_build_context_toolbar()`**

```python
def _build_context_toolbar(self):
    """Barre d'outils contextuelle — visible seulement quand un workflow est actif."""
    self._ctx_bar = tk.Frame(self, bg="#0d2440", height=38)
    # Pas de pack() ici — géré par _update_context_toolbar()

    inner = tk.Frame(self._ctx_bar, bg="#0d2440")
    inner.pack(fill='both', expand=True, padx=10, pady=5)

    tk.Label(inner, text="OUTILS TABLEAUX :",
             font=("Segoe UI", 8, "bold"),
             fg=COL_ACC, bg="#0d2440").pack(side='left', padx=(0, 12))

    # Bouton Reformater
    self._ctx_btn_format = self._ctx_btn(
        inner, "📐 Reformater", self._ctx_reformater
    )

    # Bouton Enrichir dictionnaire
    self._ctx_btn_dico = self._ctx_btn(
        inner, "📚 Enrichir dictionnaire", self._enrich_dictionary
    )

    # Bouton Ouvrir log
    self._ctx_btn_log = self._ctx_btn(
        inner, "📋 Ouvrir log", self._ouvrir_observateur
    )

    # Bouton Dossier de sortie
    self._ctx_btn_folder = self._ctx_btn(
        inner, "📂 Dossier sortie", self._open_folder
    )

    for btn in [self._ctx_btn_format, self._ctx_btn_dico,
                self._ctx_btn_log, self._ctx_btn_folder]:
        btn.pack(side='left', padx=(0, 8))

    self._update_ctx_btn_states()

def _ctx_btn(self, parent, text: str, command) -> tk.Button:
    """Crée un bouton compact pour la barre contextuelle."""
    return tk.Button(
        parent, text=text, font=("Segoe UI", 8),
        bg="#1a3a5c", fg=FG_TEXT,
        activebackground=COL_ACC2, activeforeground="white",
        relief='flat', padx=8, pady=3, cursor='hand2',
        command=command,
    )

def _ctx_reformater(self):
    """Depuis la barre contextuelle : aller à la page Formater."""
    self._show_page('format')

def _update_context_toolbar(self):
    """Affiche ou masque la barre contextuelle selon le workflow actif."""
    mode = self._workflow_mode.get()
    if mode == "tableaux":
        # Insérer la barre juste après la nav
        self._ctx_bar.pack(fill='x', after=self._nav_frame)
    else:
        self._ctx_bar.pack_forget()
    self._update_ctx_btn_states()

def _update_ctx_btn_states(self):
    """Active/désactive les boutons de la barre contextuelle selon l'état."""
    if not hasattr(self, '_ctx_btn_format'):
        return

    has_output = self._result is not None
    has_source = bool(self._word_file.get().strip())
    has_output_dir = bool(self._output_dir.get().strip())

    # Reformater : actif si un résultat existe ou si un Excel est sélectionné
    self._ctx_btn_format.configure(
        state='normal' if (has_output or self._format_excel_path.get().strip()) else 'disabled',
        fg=FG_TEXT if (has_output or self._format_excel_path.get().strip()) else FG_MUTED,
    )
    # Enrichir dico : actif si un résultat existe
    self._ctx_btn_dico.configure(
        state='normal' if has_output else 'disabled',
        fg=FG_TEXT if has_output else FG_MUTED,
    )
    # Ouvrir log : toujours actif (des logs peuvent exister d'une session précédente)
    self._ctx_btn_log.configure(state='normal', fg=FG_TEXT)
    # Dossier sortie : actif si destination définie
    self._ctx_btn_folder.configure(
        state='normal' if has_output_dir else 'disabled',
        fg=FG_TEXT if has_output_dir else FG_MUTED,
    )
```

**4.3 — Stocker la référence à la nav pour pack after**

Dans `_build_nav()`, stocker la frame :
```python
self._nav_frame = nav  # Ajouter cette ligne à la fin de _build_nav()
```

**4.4 — Appeler `_update_ctx_btn_states()` depuis `_on_done()`**

Après chaque conversion terminée, mettre à jour l'état des boutons.

---

## Étape 5 — Étape 3 (Stepper tableaux) — sur demande

La transformation en assistant Suivant/Précédent est plus invasive.
Ne l'implémenter que si l'utilisateur valide explicitement les phases 1 et 2 d'abord.

Principe :
- Remplacer les onglets Paramètres | Mode OCR | Options par 3 étapes numérotées
- Étape 1 : Source et destination (contenu de `_build_tab_documents()`)
- Étape 2 : Modèle + OCR (contenu de `_build_tab_templates()` + `_build_page_ocr()`)
- Étape 3 : Lancer (récapitulatif + bouton conversion)
- La navigation globale reste accessible via la nav bar

---

## Étape 6 — Vérification des contraintes

Avant chaque modification, vérifier :

**Thread safety** — toute modification de widget depuis un callback passe par `self.after()` ou `self._queue`
**Pas de logique dans interface.py** — les méthodes de la barre contextuelle appellent des méthodes existantes, elles ne contiennent pas de logique métier
**Rétrocompatibilité** — le mode `workflow_mode=""` (non choisi) laisse l'interface dans son état actuel
**Règle de la barre contextuelle** — ses boutons sont TOUJOURS visibles quand le workflow est choisi, mais certains sont désactivés selon l'état

---

## Étape 7 — Test après chaque phase

```powershell
# Lancer l'interface pour tester
env\Scripts\python.exe interface.py
```

Vérifier manuellement :
- [ ] Les 3 cartes de workflow s'affichent correctement sur la page Accueil
- [ ] Cliquer sur "Transformation tableaux" sélectionne le mode et va à Paramètres
- [ ] La barre contextuelle apparaît sous la nav avec les 4 boutons
- [ ] Les boutons de la barre sont correctement activés/désactivés
- [ ] Les onglets existants fonctionnent toujours
- [ ] La conversion fonctionne exactement comme avant

---

## Étape 8 — Journalisation des changements

Après chaque phase implémentée, mettre à jour la mémoire du projet :

```
/apprendre-interface
```

Et résumer les changements dans `CLAUDE.md` section "Historique des versions" :
```
| v1.7 | 2026-06 | UX workflow : accueil 3 cartes + barre contextuelle tableaux |
```
