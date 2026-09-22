# Règle 04 — Interface graphique Tkinter et UX

## Thread safety — Règle absolue

```
JAMAIS modifier un widget Tkinter depuis un thread secondaire.

Thread de conversion → queue.Queue.put({'type': 'log', 'msg': '...'})
Thread UI (main)    → self.after(80ms, _poll_queue()) → traite la queue
```

Tout callback depuis un thread secondaire doit passer par `self.after(0, lambda: ...)`.

## Architecture workflow UX (v1.7)

L'interface est structurée en **parcours de traitement** :

```
Accueil (3 cartes)
  ↓ Choix : Tableaux / Dessins / Mixte
  ↓
Stepper 3 étapes (workflow tableaux)
  Étape 1 : Source & destination
  Étape 2 : Modèle + OCR + Options
  Étape 3 : Récapitulatif + Lancer
  ↓
Dashboard de conversion
  SOURCE (spinner) | PROGRESSION | MODÈLE ATTENDU
  Journal miroir
  ↓
Résultats
```

## Règles UX validées

1. **Le bouton Lancer** est dans le stepper étape 3 — plus dans la toolbar
2. **La barre contextuelle tableaux** est toujours visible dès le choix du workflow
3. **Les onglets techniques** (Paramètres, Mode OCR, Options) sont cachés par défaut
   → Toggle "⚙ Dev" pour les développeurs
4. **Validation avant Suivant** : source, destination, clé API si nécessaire
5. **Page squelette** pour les features à venir (pas de messagebox)

## Layout Tkinter — Règles validées

```python
# CORRECT pour pages avec zones fixes + zone extensible
page.rowconfigure(0, weight=0)   # header fixe
page.rowconfigure(1, weight=0)   # colonnes fixes
page.rowconfigure(2, weight=0)   # statut fixe
page.rowconfigure(3, weight=1)   # journal — seul à s'étendre
```

**Ne jamais** mettre `expand=True` sur deux widgets frères en même temps.
Utiliser `grid()` pour les pages dashboard (pas `pack()` avec `expand`).

## Pièges Tkinter connus

| Piège | Solution |
|-------|----------|
| pack(expand=True) × 2 → 0px | Utiliser grid() avec rowconfigure(weight) |
| grid() vs pack() mixed → crash | Ne jamais mélanger pour les enfants directs d'un même parent |
| pack(after=widget) → ref perdue | Stocker `self._nav_frame = nav` à la fin de _build_nav() |
| Closure en boucle for → dernière valeur | Capturer par défaut : `def _f(x=val):` |
| Widget depuis thread → erreur Win32 | Toujours via self.after(0, lambda: ...) |
| height= sans pack_propagate → ignoré | Ajouter `.pack_propagate(False)` ou `.grid_propagate(False)` |

## Closures dans les boucles

```python
# MAUVAIS — toutes les cartes ont le même mode (dernier de la boucle)
def _on_click():
    self._select_workflow(card["mode"])

# BON — chaque carte capture sa propre valeur
def _on_click(mode=card["mode"]):
    self._select_workflow(mode)
```

## Palette de couleurs officielle

```python
BG_MAIN  = "#1a1a2e"   # fond principal
BG_PANEL = "#16213e"   # fond panneau
BG_CARD  = "#0f3460"   # fond carte
BG_LOG   = "#0a0a14"   # fond journal
FG_TEXT  = "#e0e0f0"   # texte principal
FG_MUTED = "#7878a0"   # texte désactivé
FG_OK    = "#56c596"   # succès
FG_ERR   = "#e05c5c"   # erreur
FG_WARN  = "#e0a050"   # avertissement
COL_ACC  = "#e94560"   # accent rouge-rose
COL_ACC2 = "#533483"   # accent violet
```

Utiliser `FG_MUTED` pour les boutons désactivés — pas `tk.DISABLED` sur les Labels.
