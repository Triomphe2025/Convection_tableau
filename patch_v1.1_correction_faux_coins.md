# Patch v1.1 — Correction ciblée du module de détection de coin

Ce document part du fichier `methodologie_vectorisation_TIF_DXF.md` que vous avez déjà
(version sans la section 2.6bis). Il définit **précisément** ce qui doit changer dans le
logiciel, et surtout ce qui **ne doit pas** être touché, pour éviter toute régression.

À transmettre à Claude Code tel quel, avec le fichier `methodologie_vectorisation_TIF_DXF.md`
en pièce jointe/contexte.

---

## 1. Ce qui fonctionne déjà — NE PAS MODIFIER

Ces étapes ont été validées (numériquement et/ou visuellement) et ne doivent pas être
touchées par ce patch. Toute modification de ces fonctions doit être refusée ou signalée
comme hors-périmètre :

| Étape (réf. section du doc) | Fonction/logique | Statut |
|---|---|---|
| 2.1 Chargement + polarité | détection auto du sens noir/blanc | ✅ stable |
| 2.2 Segmentation texte/géométrie | `TEXT_THRESH = 60px` sur composantes connexes | ✅ stable |
| 2.3 Squelettisation + graphe | `skeletonize` + `sknw.build_sknw` | ✅ stable |
| 2.4 Élagage des amorces | boucle d'élagage itérative, `SPUR_LEN_PX = 8` | ✅ stable |
| 2.5 Carte de distance / épaisseur | `distance_transform_edt` + centile 15 tronqué | ✅ stable |
| 2.7 Ajustement spline (le calcul lui-même) | `scipy.interpolate.splprep`, `s = n*tol²` | ✅ stable — **le calcul de spline n'est pas en cause**, seul son entrée (les points) l'était |
| 2.8 Tracé du texte (Potrace) | paramètres `-t 6 -a 1.2 -O 0.15` | ✅ stable |
| 2.9 Fusion / export | `Importer`, `$LWDISPLAY=1`, DXF R2013 | ✅ stable |

**Règle pour Claude Code** : si une modification proposée touche à l'une de ces fonctions
pour résoudre le problème ci-dessous, c'est probablement le mauvais endroit — le bug est
localisé et ne nécessite pas de toucher au reste du pipeline.

---

## 2. Ce qui doit être corrigé — le bug des faux coins

### Symptôme (confirmé visuellement sur plans réels, captures AutoCAD à l'appui)

Des lignes qui devraient être une seule courbe continue présentent de petits
décrochements latéraux ponctuels (mini-segment droit décalé de 1-3 px) au lieu d'un
tracé fluide. Visible surtout près des embranchements vers de petits symboles/repères
(équipements, amorces de cotation) rapprochés le long des lignes principales.

### Cause racine

La fonction de détection de coin (section 2.6 du document actuel) s'applique
**directement sur le tracé pixel brut** issu du squelette (dense mais non lissé). Le
bruit local de la squelettisation — quelques pixels d'amplitude, en particulier près
des embranchements — dépasse ponctuellement le seuil d'angle et déclenche un
"faux coin" là où la ligne est en réalité parfaitement lisse. Le tracé se retrouve
alors coupé en un micro-segment droit à cet endroit, visible comme un décrochement.

### Correctif à implémenter (3 changements, uniquement dans la fonction de détection
de coin et son appelant — ne pas propager ailleurs)

**a) Pré-lissage avant détection de coin**, extrémités d'arête figées :

```python
PRESMOOTH_SIGMA_PX = 2.5

def presmooth_edge(chain_mm):
    """chain_mm: Nx2 points denses en mm. Les 2 extrémités sont les coordonnées
    de nœuds du graphe et DOIVENT rester exactes (connectivité)."""
    if len(chain_mm) <= 2 * PRESMOOTH_SIGMA_PX:
        return chain_mm
    smoothed = chain_mm.copy()
    smoothed[:, 0] = gaussian_filter1d(chain_mm[:, 0], sigma=PRESMOOTH_SIGMA_PX, mode="nearest")
    smoothed[:, 1] = gaussian_filter1d(chain_mm[:, 1], sigma=PRESMOOTH_SIGMA_PX, mode="nearest")
    smoothed[0], smoothed[-1] = chain_mm[0], chain_mm[-1]
    return smoothed
```

`find_corners()` doit désormais recevoir **exclusivement** la version pré-lissée, plus
jamais le tracé brut.

**b) Fusion des coins rapprochés** (même après lissage, deux détections à quelques
pixels d'écart sont presque toujours un seul artefact) :

```python
MIN_CORNER_SEP_PX = 15.0

def merge_close_corners(corner_idx, V, min_sep_px):
    if len(corner_idx) <= 2:
        return corner_idx
    kept = [corner_idx[0]]
    for idx in corner_idx[1:-1]:
        if np.linalg.norm(V[idx] - V[kept[-1]]) >= min_sep_px:
            kept.append(idx)
    kept.append(corner_idx[-1])
    return np.array(kept)
```

À appeler juste après `find_corners()`, avant le découpage en tronçons droits/courbes.

**c) Densité d'échantillonnage de la spline augmentée** : `N_SPLINE_SAMPLES = 180`
(au lieu de 100) dans l'étape de rééchantillonnage avant `splprep` (section 2.7). Seule
la constante change, pas la logique.

### Résultat attendu (mesuré sur le cas de test qui a servi à isoler le bug)

| Indicateur | Avant patch | Après patch |
|---|---|---|
| Micro-segments droits < 2 mm (signature d'un faux coin) | 1225 | 133 (-89 %) |
| Nombre total de splines | 3165 | 1492 |
| Erreurs d'audit DXF (`doc.audit()`) | 0 | 0 |

### Critère d'acceptation du patch

- Sur un même fichier TIF d'entrée, le nombre de `LWPOLYLINE` de longueur < 2 mm dans
  le calque GEOMETRIE doit diminuer d'au moins 80 % par rapport à la version actuelle.
- `doc.audit()` doit toujours retourner 0 erreur après le patch.
- Aucune spline ne doit avoir de point de contrôle NaN ou hors de l'étendue du dessin
  (mêmes contrôles que section 6 du document de méthodologie).
- Les angles réels (cadre, rectangles, coins à 90°) doivent rester des angles vifs
  (non arrondis) — à vérifier en comptant que les entités `LWPOLYLINE` du calque cadre
  gardent des segments strictement rectilignes.

---

## 3. Ce qui reste ouvert — amélioration future, PAS obligatoire dans ce patch

Ne pas implémenter maintenant sauf demande explicite ; à garder en réserve pour un futur
patch séparé, pour ne pas mélanger les changements :

- **Continuité tangente (G1) stricte entre splines adjacentes** : actuellement, seules
  les coordonnées de point sont garanties exactes à une jonction (héritées des nœuds du
  graphe), pas la direction. Une passe de reprojection des tangentes de bord pourrait
  être ajoutée pour les jonctions où l'angle réel est proche de 180° (prolongement
  naturel), mais ce n'est plus visuellement gênant une fois le patch ci-dessus appliqué
  (la plupart des jonctions restantes sont de vraies ruptures).
- Environ un tiers des splines ont encore une corde courte (< 2 mm) après ce patch —
  à vérifier au cas par cas si ce sont de vraies jonctions rapprochées (attendu, normal
  vu la densité de repères sur certains plans) ou des artefacts résiduels. Ne pas
  chercher à réduire ce chiffre par un réglage plus agressif sans confirmation visuelle
  préalable — un seuillage trop large recommencerait à arrondir de vrais coins.

---

## 4. Instruction à donner telle quelle à Claude Code

```
Contexte : voir methodologie_vectorisation_TIF_DXF.md (section 2.6) et ce patch.

Tâche : corriger uniquement la fonction de détection de coin et son appelant
immédiat dans le pipeline de conversion TIF->DXF, selon les 3 changements décrits
en section 2 de ce patch (pré-lissage gaussien avant détection de coin avec
extrémités figées, fusion des coins à moins de 15px, échantillonnage spline
augmenté à 180 points).

Contrainte stricte : ne modifier aucune autre fonction du pipeline (chargement,
segmentation texte/géométrie, squelettisation, élagage des amorces, calcul de
largeur de trait, calcul de la spline lui-même, tracé du texte, fusion/export).
Si le correctif semble nécessiter de toucher à autre chose que la détection de
coin, s'arrêter et demander confirmation avant de continuer.

Valider avec les critères d'acceptation de la section 2 de ce patch avant de
considérer la tâche terminée. Fournir en sortie le comptage avant/après du nombre
de LWPOLYLINE < 2mm dans le calque GEOMETRIE, et le résultat de doc.audit().
```
