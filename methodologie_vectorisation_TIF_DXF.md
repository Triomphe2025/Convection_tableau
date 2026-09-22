# Méthodologie de vectorisation TIF → DXF (plans techniques scannés)

Ce document décrit la méthode complète utilisée pour convertir un scan raster bitonal
(TIF 1-bit, ~200 dpi) d'un plan technique en fichier DXF exploitable dans AutoCAD,
avec des traits continus lissés (et non des contours pixelisés dédoublés), une
séparation propre texte/géométrie, et une épaisseur de trait fidèle à l'original.

Il est écrit pour être transmis tel quel à Claude Code afin d'implémenter/industrialiser
cette méthode dans un logiciel réutilisable.

---

## 1. Vue d'ensemble du pipeline

```
TIF bitonal (1 bit, ~200 dpi)
   │
   ├─► 1. Chargement + détection de polarité (noir=encre / blanc=fond)
   │
   ├─► 2. Segmentation texte vs géométrie (taille des composantes connexes)
   │        ├── masque "texte/symboles" (petits éléments)
   │        └── masque "géométrie" (traits longs : lignes, courbes, cadres)
   │
   ├─► 3. Branche GÉOMÉTRIE                         ├─► 4. Branche TEXTE
   │     a. squelettisation (axe médian)             │     a. tracé de contour (Potrace)
   │     b. graphe topologique (nœuds/arêtes)         │     b. sortie : polylignes de
   │     c. élagage des amorces parasites             │        contour fidèles au glyphe
   │     d. carte de distance → épaisseur de trait     │
   │     e. détection de coins (angles vifs protégés) │
   │     f. lissage des courbes : spline B par        │
   │        moindres carrés (pas de zigzag)           │
   │     g. attribution d'épaisseur de ligne           │
   │        (3 paliers standards)                     │
   │                                                    │
   └────────────────┬───────────────────────────────────┘
                     ▼
         Fusion (ezdxf.addons.Importer) → DXF unique
         (calques GEOMETRIE / TEXTE, $LWDISPLAY=1)
```

---

## 2. Détail de chaque étape

### 2.1 Chargement et polarité

- Le TIF est chargé en niveau bilevel (`PIL.Image`, mode `'1'`).
- **Toujours vérifier la polarité** avant de traiter : selon le tag TIFF
  `PhotometricInterpretation`, `True`/`1` peut représenter le blanc (fond) ou le noir
  (encre). Se vérifie en mesurant la fraction de pixels `True` : le fond occupe presque
  toujours >90 % de la surface d'un plan technique. Si `fraction(True) > 0.5` alors
  `True = fond blanc`, `False = encre noire`.
- Résolution : le DPI est lu dans les tags TIFF (`im.info['dpi']`), typiquement 200.
  Facteur d'échelle pixel → mm : `SCALE = 25.4 / dpi`.

### 2.2 Segmentation texte / géométrie

**Pourquoi** : la squelettisation détruit la lisibilité des petits caractères (topologie
instable sur des traits de 1-2 px). Il faut donc isoler le texte et le traiter par une
méthode différente (tracé de contour, qui préserve la forme pleine des glyphes).

**Comment** :
1. `cv2.connectedComponentsWithStats(fg, connectivity=8)` sur le masque foreground.
2. Pour chaque composante, calculer `max(largeur_bbox, hauteur_bbox)`.
3. Seuil `TEXT_THRESH = 60` px (à ~200 dpi) : composante < seuil → texte/symbole,
   composante ≥ seuil → géométrie.
4. Ce seuil est le paramètre le plus sensible à la résolution et à la taille de police du
   plan — à exposer comme réglage utilisateur.

### 2.3 Branche géométrie — squelettisation

- `skimage.morphology.skeletonize(line_mask)` (amincissement de Zhang-Suen) : réduit
  chaque trait à une épaisseur de 1 pixel exactement en son centre (axe médian).
- `sknw.build_sknw(skeleton, multi=True)` : construit un graphe topologique
  (`networkx.MultiGraph`) où les nœuds sont les intersections/embranchements/extrémités,
  et chaque arête porte la liste ordonnée des pixels du tronçon (`data['pts']`).

### 2.4 Élagage des amorces parasites (spurs)

La squelettisation crée systématiquement de petites branches artefacts aux croisements
(traits qui « débordent » de quelques pixels). Élagage itératif :

```python
SPUR_LEN_PX = 8.0
while True:
    deg = dict(graph.degree())
    to_remove = [(u, v, k) for u, v, k, data in graph.edges(keys=True, data=True)
                 if (deg[u] == 1 or deg[v] == 1) and edge_length(data) < SPUR_LEN_PX]
    if not to_remove:
        break
    graph.remove_edges_from(to_remove)
graph.remove_nodes_from(list(networkx.isolates(graph)))
```

Sur les plans traités, cela supprime typiquement 10-15 % des arêtes brutes.

### 2.5 Carte de distance → épaisseur réelle du trait

- `scipy.ndimage.distance_transform_edt(line_mask)` : pour chaque pixel noir, distance
  au pixel blanc le plus proche. Au niveau du squelette (axe médian par définition),
  cette valeur = demi-épaisseur exacte du trait à cet endroit.
- Par arête, échantillonner cette carte le long du tracé **en excluant les 20 %
  d'extrémités** (biaisées par les croisements où plusieurs traits se chevauchent), puis
  prendre le **15ᵉ centile** (robuste, proche de l'épaisseur minimale réelle isolée) :

```python
width_mm = 2.0 * np.percentile(dist_map_sampled_along_edge, 15) * SCALE
```

- **Ne pas utiliser d'épaisseur continue par trait** (bruit dû aux lignes parallèles
  proches) : discrétiser en 2-3 paliers standards calibrés sur l'histogramme réel du
  document (mesurer d'abord la distribution des épaisseurs de trait du plan avant de
  choisir les seuils — elle varie fortement selon l'époque/l'outil de traçage) :

```python
def snap_lineweight(width_mm):
    if width_mm < 0.40: return 18   # 0.18 mm — fin (cotations, hachures)
    if width_mm < 0.95: return 35   # 0.35 mm — normal (géométrie principale)
    return 60                       # 0.60 mm — gras (cadre, contours)
```

### 2.6 Détection de coins (angles vifs vs courbes douces)

**Erreur à éviter** : lisser globalement chaque tronçon (spline unique du nœud A au
nœud B) arrondit aussi les vrais angles droits (coins de cadre, cotations) — c'est le
principal défaut des premières itérations de cette méthode.

**Solution** : détecter les coins **directement sur le tracé dense** (pas sur une
version déjà simplifiée), avec une fenêtre glissante robuste au bruit pixel :

```python
CORNER_WINDOW = 5       # points de part et d'autre pour estimer la direction locale
CORNER_ANGLE_DEG = 22.0 # angle de virage au-delà duquel c'est un vrai coin

def find_corners(V):  # V : Nx2 points denses (mm)
    corners = np.zeros(len(V), dtype=bool)
    corners[0] = corners[-1] = True
    for i in range(CORNER_WINDOW, len(V) - CORNER_WINDOW):
        v_in  = V[i] - V[i - CORNER_WINDOW]
        v_out = V[i + CORNER_WINDOW] - V[i]
        angle = angle_between(v_in, v_out)  # degrés
        if angle > CORNER_ANGLE_DEG:
            corners[i] = True
    return corners
```

Le tracé est ensuite découpé en tronçons entre coins consécutifs : un tronçon avec peu
de points (`< MIN_CURVE_PTS = 6`) reste une **ligne droite** (segment simple) ; un
tronçon plus long devient une **courbe** à lisser (étape suivante).

### 2.7 Lissage des courbes : spline B par moindres carrés

C'est le cœur mathématique de la méthode, et la réponse directe à la question
« comment tracer une fonction qui passe au mieux par ~100 points détectés » :

1. Ré-échantillonner le tronçon courbe en ~100 points régulièrement espacés le long de
   l'arc (interpolation linéaire sur l'abscisse curviligne cumulée).
2. Ajustement par moindres carrés d'une **B-spline de lissage** (pas une interpolation
   exacte, qui figerait le bruit pixel) :

```python
from scipy.interpolate import splprep

POINT_TOL_MM = 0.15   # tolérance ≈ résolution du scan
s = n_samples * POINT_TOL_MM ** 2   # budget d'erreur quadratique totale
tck, u = splprep([x_samples, y_samples], k=3, s=s)
t, c, k = tck   # nœuds, points de contrôle, degré
```

3. Export DXF **en NURBS réelle** (pas en polyligne dense qui simule une courbe) :

```python
sp = msp.add_spline(dxfattribs={"layer": "GEOMETRIE", "lineweight": lw})
sp.dxf.degree = k
sp.control_points = [(x, y, 0) for x, y in zip(c[0], c[1])]
sp.knots = list(t)
```

Résultat : une entité SPLINE éditable dans AutoCAD, identique en nature à une spline
tracée à la main, et non un polygone à facettes.

**Justification du choix `s > 0` (lissage) plutôt que `s = 0` (interpolation stricte)** :
avec `s = 0`, la spline passe exactement par les 100 points, donc reproduit fidèlement
le bruit pixel de la squelettisation (micro-zigzag). Avec `s` calibré sur la tolérance
de résolution du scan, l'algorithme FITPACK choisit automatiquement le nombre minimal
de points de contrôle nécessaires (souvent 4 = un seul segment de Bézier cubique pour
un arc doux), ce qui élimine le bruit tout en respectant la forme réelle.

### 2.8 Branche texte — tracé de contour (Potrace)

Le texte est traité séparément, **sans squelettisation**, pour préserver la forme
pleine des caractères :

```bash
potrace -b dxf -x <SCALE> -t 6 -a 1.2 -O 0.15 -o texte.dxf masque_texte.pbm
```

- `-t 6` (turdsize) : filtre les poussières de scan < 6 px, en conservant les points
  décimaux et petites ponctuations légitimes.
- `-a 1.2` (alphamax) : lissage des courbes de police (plus élevé = lettres moins
  anguleuses).
- `-x <SCALE>` : conversion directe pixel → mm en sortie.

### 2.9 Fusion et export final

```python
from ezdxf.addons import Importer
importer = Importer(text_doc, doc)
importer.import_modelspace()
importer.finalize()
doc.header["$LWDISPLAY"] = 1   # affichage des épaisseurs activé par défaut
doc.saveas("resultat.dxf")     # DXF R2013 (AC1027), large compatibilité
```

---

## 3. Paramètres réglables (à exposer dans l'interface du logiciel)

| Paramètre | Valeur par défaut | Rôle |
|---|---|---|
| `TEXT_THRESH` | 60 px | Seuil taille composante texte vs géométrie |
| `SPUR_LEN_PX` | 8 px | Longueur max d'une amorce de squelette à élaguer |
| `CORNER_WINDOW` | 5 pts | Fenêtre d'estimation de direction pour la détection de coin |
| `CORNER_ANGLE_DEG` | 22° | Angle au-delà duquel un point est un coin protégé |
| `MIN_CURVE_PTS` | 6 pts | Nombre de points min. pour qu'un tronçon soit traité en courbe |
| `POINT_TOL_MM` | 0.15 mm | Tolérance de lissage de la spline (≈ résolution scan) |
| `MIN_EDGE_LEN_PX` | 3 px | Longueur min. d'arête pour ne pas être ignorée (bruit) |
| Paliers de lineweight | 0.18 / 0.35 / 0.60 mm | À recalibrer sur l'histogramme réel de chaque plan |
| Potrace `-t`, `-a`, `-O` | 6, 1.2, 0.15 | Filtrage bruit / lissage police / tolérance contour |

---

## 4. Dépendances

```
Python ≥ 3.10
numpy, scipy, opencv-python (cv2), scikit-image, networkx, sknw, ezdxf, Pillow
potrace (binaire système, ex. apt-get install potrace)
```

---

## 5. Instructions à transmettre à Claude Code

Copier-coller le bloc ci-dessous dans une conversation Claude Code, dans le dépôt du
logiciel à améliorer :

```
Objectif : implémenter/refactoriser un module Python de conversion TIF → DXF pour
des plans techniques scannés bitonaux (~200 dpi), produisant un DXF avec des traits
lissés (splines B réelles, pas de polylignes à facettes), du texte lisible séparé
de la géométrie, et une épaisseur de trait DXF (lineweight) dérivée de l'épaisseur
réelle du trait scanné.

Architecture demandée (module unique ou package, au choix, avec fonctions pures
testables séparément) :

1. `load_bilevel(tif_path) -> (foreground_bool_array, dpi)`
   Charge le TIF, détecte automatiquement la polarité (le fond occupe toujours
   > 50% des pixels), retourne un masque booléen où True = encre.

2. `segment_text_vs_geometry(fg, text_thresh_px=60) -> (text_mask, line_mask)`
   Composantes connexes (cv2.connectedComponentsWithStats), classification par
   max(largeur, hauteur) de la bounding box de chaque composante.

3. `build_skeleton_graph(line_mask, spur_len_px=8.0) -> networkx.MultiGraph`
   skimage.morphology.skeletonize + sknw.build_sknw, puis élagage itératif des
   arêtes courtes (< spur_len_px) connectées à un nœud de degré 1.

4. `sample_stroke_width(dist_map, edge_pts, trim_ratio=0.2, percentile=15) -> float`
   scipy.ndimage.distance_transform_edt sur line_mask ; échantillonnage le long
   d'une arête en excluant les extrémités, retourne l'épaisseur en pixels (2x le
   centile choisi de la distance).

5. `detect_corners(points_mm, window=5, angle_deg=22.0) -> bool_array`
   Détection de coin par fenêtre glissante sur le tracé DENSE (pas simplifié),
   angle entre vecteur entrant et sortant sur `window` points de part et d'autre.

6. `fit_curve_lsq_spline(points_mm, point_tol_mm=0.15, max_samples=100) -> (degree, control_points, knots)`
   Rééchantillonnage uniforme en abscisse curviligne puis scipy.interpolate.splprep
   avec s = n_samples * point_tol_mm**2 (lissage par moindres carrés, PAS s=0).

7. `snap_lineweight(width_mm, tiers=[(0.40,18),(0.95,35),(None,60)]) -> int`
   Discrétisation en paliers standards (hundredths de mm, valeurs DXF lineweight).
   Les seuils doivent être calibrés automatiquement sur l'histogramme réel du plan
   traité (percentiles de sample_stroke_width sur l'ensemble des arêtes), pas figés
   en dur — cf. section 3 du document joint pour la méthode de calibration.

8. `build_geometry_dxf(graph, dist_map, scale_mm_per_px, msp, layer="GEOMETRIE")`
   Pour chaque arête du graphe : sample_stroke_width, detect_corners sur le tracé
   converti en mm, découpage en tronçons droits/courbes, écriture LWPOLYLINE
   (droit) ou SPLINE (courbe, via fit_curve_lsq_spline) avec le lineweight calculé.

9. `trace_text_layer(text_mask, scale_mm_per_px, turdsize=6, alphamax=1.2, opttolerance=0.15) -> ezdxf.Drawing`
   Appel au binaire potrace en sous-processus sur le masque texte exporté en PBM,
   backend DXF natif de potrace.

10. `merge_and_export(geometry_doc, text_doc, out_path)`
    Fusion via ezdxf.addons.Importer, calques GEOMETRIE/TEXTE, $LWDISPLAY=1,
    sauvegarde en DXF R2013 (AC1027).

Points d'attention impératifs (bugs déjà rencontrés et corrigés à ne pas
réintroduire) :
- NE JAMAIS détecter les coins sur un tracé déjà simplifié (Douglas-Peucker ou
  autre) : ça arrondit les vrais angles droits des rectangles/cadres. Toujours
  détecter sur le tracé dense d'origine.
- NE JAMAIS squelettiser le texte en même temps que la géométrie : topologie
  instable sur les petits caractères → glyphes illisibles.
- NE JAMAIS utiliser une largeur de trait continue par entité sans discrétisation :
  le bruit dû aux lignes parallèles proches (moins de quelques pixels d'écart)
  produit des largeurs aberrantes localement. Toujours discrétiser en paliers et
  échantillonner en excluant les zones de croisement.
- Toujours activer $LWDISPLAY=1 dans le header DXF, sinon les épaisseurs de ligne
  ne s'affichent pas par défaut à l'ouverture dans AutoCAD.
- Le facteur d'échelle pixel→mm doit être dérivé du DPI réel du TIFF
  (25.4 / dpi), jamais supposé fixe.

Fournir en sortie : un rapport de contrôle qualité automatique (nombre d'entités
par type, vérification NaN sur les points de contrôle des splines, étendue du
dessin comparée à la taille attendue en mm, audit structurel ezdxf.audit()) —
voir section 6 ci-dessous pour le détail des contrôles à reproduire.
```

---

## 6. Contrôle qualité automatique (à reproduire dans le logiciel)

```python
# 1. Audit structurel DXF
auditor = doc.audit()
assert len(auditor.errors) == 0

# 2. Aucune spline dégénérée
for e in msp.query("SPLINE"):
    pts = np.array([(p[0], p[1]) for p in e.control_points])
    assert not np.isnan(pts).any()

# 3. Étendue cohérente avec la taille physique attendue
expected_w_mm = tif_width_px * scale
expected_h_mm = tif_height_px * scale
# comparer aux extents réels du dessin (avec marge de tolérance)

# 4. Distribution des épaisseurs de trait non dégénérée
# (vérifier qu'on n'a pas 100% des entités sur un seul palier)
```

---

## 7. Limites connues de la méthode (à ne pas promettre au-delà)

- Précision plafonnée par la résolution du scan (0.127 mm/px à 200 dpi) : aucun
  traitement ne peut recréer une information absente des pixels d'origine.
- Les lignes parallèles très rapprochées (moins de ~3 px d'écart) peuvent fusionner
  lors de la squelettisation — pas de séparation garantie dans ce cas.
- Le texte reste un tracé de contour (glyphes vectorisés), pas du texte AutoCAD
  éditable (TEXT/MTEXT) — une passe OCR serait nécessaire pour ça, avec risque de
  perte de fidélité visuelle.
- Les seuils (`TEXT_THRESH`, `CORNER_ANGLE_DEG`, paliers de lineweight) sont
  calibrés empiriquement sur les plans traités jusqu'ici ; à revalider si la
  typographie, l'échelle ou l'époque de traçage du document change fortement.

---

## 8. Annexe — Module optionnel : réparation d'un DXF déjà fragmenté

**Cas d'usage différent** : ce module ne s'applique PAS à la conversion directe
TIF → DXF (où le graphe squelette de `sknw` préserve nativement la topologie, donc
ce problème ne se pose pas). Il sert uniquement si le logiciel doit *réparer* un
DXF déjà produit ailleurs (autre outil, export intermédiaire) dont les polylignes
sont fragmentées sans connectivité déclarée — typiquement des centaines/milliers
de polylignes à 2 points sans lien topologique explicite entre elles.

### 8.1 Reconnexion des fragments (nœuds partagés par proximité + continuité directionnelle)

```python
SNAP_TOL_MM = 0.45      # tolérance de proximité pour considérer deux extrémités comme le même nœud
DIR_TOL_DEG = 40.0      # écart de direction max accepté pour relier deux fragments
```

Algorithme :
1. Extraire toutes les extrémités (début/fin) de chaque polyligne source.
2. Regrouper par proximité (`scipy.spatial.cKDTree.query_pairs(SNAP_TOL_MM)` +
   union-find) en "nœuds" candidats.
3. **Ne fusionner deux fragments que si leurs tangentes locales (calculées sur les
   3-4 derniers points de chaque extrémité) restent cohérentes** en direction
   (angle < `DIR_TOL_DEG`) une fois mis bout à bout — sans ce garde-fou, des
   traits proches mais non liés (ex. deux voies parallèles à quelques pixels
   d'écart) se retrouvent fusionnés à tort.
4. Chaîner à travers les nœuds de degré exactement 2 (passage simple) ; un nœud à
   3+ connexions reste un point de rupture (vraie intersection, jamais fusionné
   automatiquement).

### 8.2 Point d'attention supplémentaire

- **Ne pas confondre fragmentation accidentelle et pointillé intentionnel** : un
  plan CAO peut légitimement contenir des lignes en tirets/pointillés (calque
  d'axe, ligne de propriété). Le seuil `SNAP_TOL_MM` doit rester nettement
  inférieur à l'espacement typique d'un pointillé réel (généralement 1-3 mm),
  sous peine de souder par erreur des tirets distincts en une ligne continue.
- Une fois les fragments reconnectés en chaînes denses, réappliquer directement
  les étapes 2.6 et 2.7 (détection de coins + spline B moindres carrés) sur ces
  chaînes — c'est le même code, il n'a pas besoin d'être dupliqué.

