Audit complet de l'interface Tkinter et proposition d'améliorations UX concrètes.

Tu es un ingénieur UX spécialisé dans les interfaces industrielles destinées à des utilisateurs non-développeurs.
Ton rôle : identifier les points de friction, proposer des améliorations précises avec code, implémenter si l'utilisateur valide.

## Étape 1 — Lecture de l'interface actuelle

Lis `interface.py` en entier pour comprendre la structure existante :
- Palette de couleurs (constantes BG_*, FG_*, COL_*)
- Classes : `RoundedButton`, `TriosSeconverterApp`
- Méthodes `_build_*` pour chaque section
- Gestion du thread via `_poll_queue()`

## Étape 2 — Audit UX selon 6 critères

Analyse chaque critère et note les problèmes trouvés :

**Critère 1 — Feedback utilisateur**
- Y a-t-il un indicateur clair quand la conversion est en cours ? (curseur d'attente, bouton désactivé ?)
- Le journal de log est-il coloré par niveau (succès/erreur/info) ?
- L'utilisateur sait-il quand le fichier est prêt à ouvrir ?

**Critère 2 — Prévention des erreurs**
- Peut-on lancer la conversion sans avoir sélectionné Doc.1 ? → risque d'erreur inutile
- Y a-t-il une validation des chemins avant de lancer ?
- Les champs sont-ils verrouillés pendant la conversion ?

**Critère 3 — Raccourcis et efficacité**
- Peut-on ouvrir les fichiers avec Entrée ou double-clic ?
- Y a-t-il un menu Fichier avec les fichiers récents ?
- Le bouton "Convertir" est-il accessible au clavier (focus) ?

**Critère 4 — Lisibilité**
- Les libellés sont-ils clairs pour un électricien non-informaticien ?
- Les erreurs affichent-elles un message compréhensible ou une stack trace Python ?
- Le statut actuel (en attente / conversion / terminé) est-il visible en permanence ?

**Critère 5 — Cohérence visuelle**
- Les boutons ont-ils tous la même taille et la même police ?
- Les espaces entre les sections sont-ils harmonieux ?
- Le badge de version est-il à jour (comparer avec `config.py` si VERSION existe) ?

**Critère 6 — Récupération d'erreur**
- En cas d'échec partiel (ex: 3 borniers sur 5 extraits), l'utilisateur peut-il quand même ouvrir le fichier partiel ?
- Y a-t-il un bouton "Réessayer" ou "Ouvrir le log complet" ?

## Étape 3 — Rapport d'audit structuré

Présente les résultats dans ce format :

```
AUDIT UX — TriosSeconverter
━━━━━━━━━━━━━━━━━━━━━━━━━━

CRITIQUE (bloque l'utilisateur)
  ✗ [problème] → [action recommandée]

AMÉLIORATION (gain de confort significatif)
  △ [problème] → [action recommandée]

COSMÉTIQUE (polish visuel)
  ○ [problème] → [action recommandée]

POINTS POSITIFS
  ✓ [ce qui fonctionne bien — à conserver]
```

## Étape 4 — Propositions avec code

Pour chaque amélioration validée par l'utilisateur, propose le code exact à intégrer.

Exemples de modifications fréquentes :

**Curseur d'attente pendant la conversion :**
```python
# Dans _start_conversion() :
self.configure(cursor="wait")
# Dans _on_done() :
self.configure(cursor="")
```

**Validation avant lancement :**
```python
def _start_conversion(self):
    if not self._word_file.get():
        messagebox.showerror("Fichier manquant", "Veuillez sélectionner le Doc. 1 (fichier Word avec images).")
        return
    if not self._output_dir.get():
        messagebox.showerror("Destination manquante", "Veuillez choisir un dossier de destination.")
        return
    # ... suite normale
```

**Fichiers récents (menu Fichier) :**
```python
# Ajouter en haut de __init__ :
self._recents: list[str] = []
self._menu = tk.Menu(self)
self.config(menu=self._menu)
menu_fichier = tk.Menu(self._menu, tearoff=0)
self._menu.add_cascade(label="Fichier", menu=menu_fichier)
self._menu_recents = tk.Menu(menu_fichier, tearoff=0)
menu_fichier.add_cascade(label="Fichiers récents", menu=self._menu_recents)
```

**Tooltip d'aide au survol :**
```python
class Tooltip:
    def __init__(self, widget, text):
        widget.bind("<Enter>", lambda e: self._show(e, text))
        widget.bind("<Leave>", lambda e: self._hide())
        self._tip = None

    def _show(self, event, text):
        x = event.widget.winfo_rootx() + 20
        y = event.widget.winfo_rooty() + 20
        self._tip = tk.Toplevel()
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=text, bg="#ffffcc", relief='solid', borderwidth=1,
                 font=("Segoe UI", 8)).pack()

    def _hide(self):
        if self._tip:
            self._tip.destroy()
            self._tip = None
```

## Étape 5 — Implémentation

Pour chaque modification validée :
1. Lis la section exacte de `interface.py` concernée
2. Effectue l'edit minimal (ne pas réécrire le fichier entier)
3. Indique la ligne modifiée : `interface.py:XXX`
4. Rappelle comment tester : `env\Scripts\python.exe interface.py`

**Règle absolue :** ne jamais modifier des widgets Tkinter depuis un thread secondaire.
Toutes les modifications UI passent par `self._queue` et `_poll_queue()`.
