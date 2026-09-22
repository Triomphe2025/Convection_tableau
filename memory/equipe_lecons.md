# Mémoire de l'équipe TriosSeconverter — Leçons cumulées

Fichier maintenu par l'agent Apprentissage.
Chaque session significative ajoute ses leçons ici pour alimenter les interventions futures.

> **Note :** la source de vérité est dans la mémoire persistante Claude :
> `C:\Users\Triomphe Tchounda\.claude\projects\...\memory\equipe_lecons.md`
> Ce fichier en est une copie synchronisée.

---

## Score cumulé de l'équipe

**Sessions documentées :** 10
**Dernière mise à jour :** 2026-09-09

| Session | Qualité | Tests | Conformité | Bilan |
|---------|---------|-------|------------|-------|
| Init (2026-06-30) | — | — | — | Équipe créée |
| TIF Pipeline (2026-07-01) | ✓ | 232/232 | REFUSÉ→VALIDÉ | 3 corrections post-audit |
| Skeletonisation (2026-07-01) | ✓ | 236/236 | VALIDÉ 1er tour | 0 correction post-audit |
| findContours pipeline (2026-07-01) | ✓ | 235/235 | VALIDÉ 1er tour | 0 correction post-audit |
| Pipeline avancé raster (2026-07-01) | ✓ | 243/243 | VALIDÉ (8/8) | 1 import redondant corrigé |
| Config CAD + stats DXF (2026-07-02) | ✓ | 264/264 | VALIDÉ après correction | Bug try/except (ordre inversé) |
| TIF→DXF skeletonisation perf (2026-07-02) | ✓ | 279/279 | VALIDÉ | 0 correction post-audit |
| Vectorizer axe médian + B-spline (2026-07-05) | ✓ | 290/290 | VALIDÉ | 0 correction post-audit |
| Mapping manuel colonnes/blocs (2026-08-06) | ✓ | 344/344 | VALIDÉ AVEC RÉSERVES | 0 correction bloquante, 1 réserve nesting |
| Silence Claude Vision + bouton d'arrêt (2026-09-09) | ✓ | 356/356 | VALIDÉ 1er tour | 0 correction post-audit |
| Mapping segment→colonne moteurs vision (2026-09-09) | ✓ | 372/372 | VALIDÉ 1er tour | 0 correction post-audit |

---

## Sessions

### Session 2026-07-02 (suite) — Pipeline TIF→DXF : performance skeletonisation

**Contexte :** Analyse de `00169325.tif` (7504×10504px, 78M pixels) — identification et
correction de 2 problèmes critiques dans `cad/raster_tif_extractor.py`.

**Leçon 1 — Skeletonisation : jamais de boucle while/erode manuelle sur grandes images**
- Boucle cv2.erode + cv2.dilate = O(n²) → 30 min sur 78M pixels
- Solution : skimage.morphology.skeletonize() (Zhang-Suen) → <1 min
- Pattern : import LOCAL dans try/except (pas global) + fallback cv2 dans except ImportError
- Toujours ajouter la garde countNonZero == 0 AVANT le try/except

**Leçon 2 — Seuils de détection : ne jamais hardcoder les pixels absolus**
- `eps_gap_mm=0.254` (2px@200DPI) hardcodé = ne fonctionne pas si résolution change
- Solution : toujours passer par Config.CAD_XXX et exprimer les seuils en mm
- Valeur correcte pour fusion de squelette : 0.5mm (4px@200DPI) minimum

**Leçon 3 — Import de dépendances optionnelles**
- Les bibliothèques optionnelles lourdes (skimage, scipy) : import LOCAL dans la fonction
- Jamais en import global → le module se charge même sans la dépendance installée
- Toujours prévoir un fallback fonctionnel dans except ImportError
- Pattern validé : curve_fitter.py (scipy) + raster_tif_extractor.py (skimage)

**Note Auditeur :** `_extract_geometry_entities` a un paramètre `epsilon_mm: float = 0.5`
dont l'appel depuis `_process_page` ne passe pas `Config.CAD_EPS_GAP_MM` — cohérent
aujourd'hui mais à rendre explicite lors d'une prochaine session.

**Score session :** 5 agents — Analyste ✓, Backend ✓, Auditeur ✓, Testeur ✓, Apprentissage ✓
**Tests :** 279/279 passants — barre maintenue

---

---

### Session 2026-07-05 — Implémentation vectorizer.py (pipeline axe médian + B-spline)

**Contexte :** Document méthodologique fourni par l'utilisateur. L'équipe a implémenté un
pipeline complet de vectorisation TIF→DXF en 7 étapes (chargement → prétraitement →
séparation → squelettisation → graphe → vectorisation → export) dans `cad/vectorizer.py`,
avec un panneau d'avancement visuel (7 étapes ○/●/✓/✗) intégré dans la page Dessins de
l'interface.

**Leçon 1 — Signatures des fonctions internes : toujours lire avant d'écrire**
- `_separate_text_geometry(binary, thresh)` → retourne `(geom_mask, text_mask)` — géom EN PREMIER
- `_trace_paths_from_skeleton(skel, dist_map, dpi)` → 3 arguments obligatoires (pas 1)
- `CadPage(width=, height=, source_mode=)` — NE PAS utiliser `width_mm`, `height_mm`, `page_number`
- `CadDocument(source_path=, pages=)` — `source_path` OBLIGATOIRE
- Toujours lire les vraies signatures avant d'importer des fonctions privées d'un module existant

**Leçon 2 — B-spline de lissage : s > 0 est critique (jamais s=0 sur squelette)**
- `s = 0` → interpolation exacte → reproduit le bruit pixel du squelette (micro-zigzag)
- `s = n * point_tol_mm²` → lissage par moindres carrés → élimine le bruit pixel
- FITPACK choisit automatiquement le nb minimal de points de contrôle avec s > 0
- Toujours vérifier NaN dans les points de contrôle après splprep (cas dégénéré)

**Leçon 3 — Détection de coins : toujours sur tracé dense (jamais après simplification)**
- Ne JAMAIS détecter les coins après Douglas-Peucker ou toute autre simplification
- La simplification arrondit les vrais angles droits (coins de cadre, cotations)
- Fenêtre glissante de 5 points de part et d'autre suffit pour filtrer le bruit pixel
- Ordre validé : DENSE → detect_corners → découpe en tronçons → fit_spline → Douglas-Peucker

**Leçon 4 — Interface multi-étapes visuelles : pattern validé pour thread-safety**
- `self._cad_step_widgets: dict = {}` — stocker `(icon_label, text_label)` par nom d'étape
- Chaque méthode `_cad_step_*` utilise `self.after(0, lambda il=icon_lbl, tl=text_lbl: ...)`
  pour capturer les références et respecter le thread-safety Tkinter
- La boucle de création des widgets n'utilise pas de lambda → pas de risque de closure
- `convert_to_dxf()` : 3 nouveaux paramètres optionnels (`params`, `on_step_start`, `on_step_done`)
  ajoutés avec valeurs par défaut → rétrocompatibilité totale maintenue

**Score session :** 5 agents — Analyste ✓, Backend ✓, Frontend ✓, Auditeur ✓, Testeur ✓
**Tests :** 290/290 passants — +11 nouveaux dans `tests/test_cad_vectorizer.py`

---

### Session 2026-08-06 — Mapping manuel colonnes/blocs (>4 colonnes détectées)

**Contexte :** L'affectation automatique par frontières pixel devient peu fiable quand un
template dépasse 4 colonnes (`Config.MAX_AUTO_COLUMNS`). Nouvelle fonctionnalité : demander
à l'utilisateur un classement manuel bloc→colonne (avec ordre de fusion) via une dialog
Tkinter, sans bloquer le thread de conversion.

**Leçon 1 — LE pattern de référence pour toute interaction utilisateur synchrone depuis
le thread de conversion : `on_validation` / `ValidationPageDialog` (interface.py ~3838-3930)**
- `threading.Event()` **LOCAL par appel** (jamais une variable d'instance partagée — élimine
  les races entre deux sollicitations consécutives)
- `self.after(0, lambda: self._montrer_XXX_dialog(...))` pour ouvrir la Toplevel sur le
  thread UI depuis le thread worker
- `local_event.wait(timeout=300)` — jamais de wait() sans timeout : si la fenêtre est
  fermée brutalement, le thread worker doit quand même rendre la main
- Le callback de fermeture de la dialog (`_callback(...)`) remplit une `local_result_box[0]`
  puis appelle `local_event.set()` — TOUJOURS avant `self.destroy()`, jamais après
- **Réutilisé à l'identique** pour `_on_column_mapping` / `ColumnMappingDialog` — ne jamais
  réinventer ce mécanisme, le dupliquer.

**Leçon 2 — Une branche de traitement alternative ne doit PAS réutiliser un post-traitement
conçu pour une autre structure de données**
- Le mapping manuel fusionne des blocs bruts (bounds indépendants) vers les colonnes finales
  du template — les étapes `_rebalance_line`, re-OCR par bande ROI, et
  `_reconstruct_intra_cell_spacing` indexent `bounds[ci]` en supposant `ci` = colonne finale
- Réutiliser ces étapes sur des cellules issues d'une fusion produirait des résultats faux
  (re-OCR sur le mauvais rectangle pixel)
- Solution : sauter explicitement ces étapes quand la branche alternative est active, plutôt
  que de forcer leur compatibilité

**Leçon 3 — Cache par run obligatoire dès qu'une interaction utilisateur porte sur une
propriété STRUCTURELLE (template) et non une propriété par-image**
- Sur un lot de 50-300 images, ne jamais resolliciter l'utilisateur à chaque image pour
  une même décision (ici : le mapping dépend du template, pas du contenu de l'image)
- Clé de cache stable recommandée : `tuple(col_keywords)` (ou équivalent identifiant le
  template), stockée en attribut d'instance de l'extracteur (recréé à chaque run)

**Leçon 4 — Retour de callback `None` = toujours un fallback sûr, jamais une exception**
- Convention validée : un callback d'interaction utilisateur qui retourne `None` (annulation,
  timeout, fenêtre fermée) doit systématiquement déclencher le comportement automatique
  existant, sans lever d'exception — cohérent avec `on_validation` qui gère déjà ce cas

**Point de vigilance UX (non bloquant, à corriger dans une itération future) :**
Un mapping utilisateur vide (`{}`, rien classé) ne crashe pas mais produit une perte de
données silencieuse — la ligne entière du tableau est exclue sans avertissement. Ajouter une
confirmation (`messagebox.askyesno`) dans `ColumnMappingDialog._valider()` avant d'accepter
un mapping vide, sur le modèle de `_valider_relancer` qui exige déjà un commentaire non vide.

**Score session :** 6 agents — Analyste ✓, Backend ✓, Frontend ✓, Auditeur △ (réserve mineure
nesting), Testeur ✓ (3 tests supplémentaires ajoutés en investigation), Apprentissage ✓
**Tests :** 344/344 passants — +21 nouveaux (`tests/test_column_mapping.py` +
`tests/test_column_mapping_integration.py`) — 0 régression sur les 323 préexistants

---

### Session 2026-09-09 — Silence Claude Vision (mapping colonnes) + bouton d'arrêt coopératif

**Contexte :** L'utilisateur a signalé que le mapping manuel colonnes/blocs (livré session
2026-08-06) ne se déclenchait jamais en mode Claude Vision — "je vois plus de 4 colonnes et
rien ne se passe". Root cause : le callback n'était câblé QUE sur `BornierTableExtractor`.
Corrigé + ajout d'un bouton "⏹ Arrêter" pour interrompre une conversion en cours.

**Leçon 1 — Un callback câblé sur UNE SEULE classe d'extraction ne couvre pas les autres
moteurs — vérifier au niveau du point d'entrée commun, pas dans une classe spécifique**
- Le projet a plusieurs classes d'extraction au même contrat de sortie (`headers`/`rows`)
  mais des mécanismes internes différents : `BornierTableExtractor` (Tesseract, bounds pixel),
  `ClaudeVisionExtractor`/`OllamaVisionExtractor`/etc. (prompt-based, sans bounds),
  `PdfTableExtractor` (PDF vectoriel).
- Toute nouvelle interaction utilisateur basée sur une propriété du TEMPLATE (nombre de
  colonnes, etc.) doit être vérifiée dans `Converter.run()` (point d'entrée commun à TOUS les
  moteurs), jamais dans une classe d'extraction spécifique — sinon elle ne s'applique qu'à un
  seul moteur silencieusement, exactement le bug rapporté ici.
- **Réflexe à appliquer systématiquement à l'avenir** : avant de câbler un nouveau callback
  interactif, lister TOUTES les classes d'extraction existantes (`BornierTableExtractor`,
  `ClaudeVisionExtractor`, `OllamaVisionExtractor`, `DoclingExtractor`, `HybridVisionExtractor`,
  `AgentVisionExtractor`, `PdfTableExtractor`, `LogReplayer`) et vérifier explicitement
  lesquelles sont concernées.

**Leçon 2 — Adapter l'UX aux capacités réelles du moteur, ne pas forcer un mécanisme uniforme**
- Tesseract (bounds pixel disponibles) → dialog de mapping précis bloc→colonne
- Moteurs vision (prompt-based, pas de bounds) → simple avertissement + confirmation oui/non
- Les deux partagent le même point de déclenchement (`Config.MAX_AUTO_COLUMNS`) mais pas la
  même interaction — ne pas essayer d'unifier de force deux UX qui répondent à des contraintes
  techniques différentes.

**Leçon 3 — Pattern d'arrêt coopératif validé (nouveau réflexe pour toute opération longue)**
- `threading.Event` partagé, créé neuf à CHAQUE lancement (jamais réutilisé d'un run à l'autre)
- Vérifié en TOUTE PREMIÈRE instruction de chaque boucle d'extraction → `break` si settée
- JAMAIS de `raise` pour une simple annulation — les résultats déjà accumulés sont retournés
  normalement, le pipeline continue vers la génération Excel avec des résultats partiels
- JAMAIS de kill de thread (non supporté proprement en Python, corromprait l'état)

**Leçon 4 — Asymétrie écriture/lecture sur un Event partagé depuis Tkinter**
- Écrire (`.set()`) depuis le thread UI vers un Event lu par le worker : SAFE directement,
  pas besoin de `self.after()` — `threading.Event` est thread-safe nativement et on ne touche
  aucun widget Tkinter.
- Lire une réponse utilisateur (ouvrir une dialog) depuis le thread worker : DOIT passer par
  le pattern complet Event LOCAL + `self.after(0, ...)` + timeout (voir [[Leçon 1 session
  2026-08-06]] — le widget ne peut être créé/lu que depuis le thread UI).

**Point de vigilance (non bloquant, trouvé par le Testeur) :** `_verifier_template_large()`
s'applique aussi au mode replay JSONL (`.jsonl`), où aucun appel API n'a lieu — la confirmation
y est superflue (clic inutile mais pas un bug). À exclure dans une itération future.

**Score session :** 6 agents — Analyste ✓ (vérification systématique de l'état réel du code
avant de figer le plan — confirmé comme bonne pratique sur 2 sessions consécutives), Backend ✓,
Frontend ✓, Auditeur ✓ (validé du premier coup), Testeur ✓ (1 trou de couverture mineur signalé),
Apprentissage ✓.
**Tests :** 356/356 passants — +12 nouveaux (`tests/test_wide_template_and_cancel.py`) —
0 régression sur les 344 préexistants.

---

### Session 2026-09-09 (suite) — Mapping manuel segment→colonne pour moteurs vision

**Contexte :** Distinct du correctif précédent le même jour. L'utilisateur a vu dans les logs
que Claude Vision recevait/renvoyait 6 segments pipe-séparés pour un template à 4 colonnes,
sans pouvoir les classer lui-même — `claude_ocr.py::_parse_pipe_response()` (partagée par
Claude/Ollama/Agent, Hybrid délègue en interne) fusionnait automatiquement le surplus via une
heuristique fixe non modifiable. Différence avec `_verifier_template_large()` (session
précédente) : celle-ci vérifie la taille du TEMPLATE avant extraction ; ce nouveau cas se
découvre APRÈS coup, dans la RÉPONSE reçue du moteur vision.

**Leçon la plus réutilisable de toute la série column-mapping :** **un contrat de callback
bien conçu se réutilise intégralement sur un cas d'usage différent, sans changement frontend.**
- `on_column_mapping(candidate_blocks, template_columns, image_path) -> Optional[Dict[str, List[int]]]`
  a servi tel quel pour 2 usages très différents :
  - Tesseract (session 2026-08-06) : `candidate_blocks` = blocs pixel réels (x/x2 = position physique)
  - Vision (cette session) : `candidate_blocks` = segments texte pipe (x/x2 = position ORDINALE synthétique)
- `ColumnMappingDialog` n'a nécessité AUCUNE modification — elle affiche juste `text`+`x`,
  sans présupposer de sémantique pixel.
- **Réflexe à appliquer systématiquement** : avant d'inventer un nouveau mécanisme UI pour un
  besoin qui "ressemble" à un pattern déjà résolu, vérifier si le CONTRAT existant peut être
  réutilisé avec des données synthétiques.

**Leçon 2 — repérer les fonctions PARTAGÉES avant de dupliquer un correctif par moteur**
- `_parse_pipe_response()` est utilisée par `ClaudeVisionExtractor`, `OllamaVisionExtractor`,
  `AgentVisionExtractor` directement, et par `HybridVisionExtractor` indirectement (composition
  interne de Claude+Ollama). Un seul changement dans la fonction partagée module-level a couvert
  4 moteurs d'un coup — grep systématique du nom de la fonction AVANT de commencer à corriger,
  pour ne jamais dupliquer 4× le même correctif ni risquer une incohérence entre moteurs.
- Le cache (`_cached_column_mapping`/`_cached_mapping_key`) reste néanmoins dupliqué PAR
  EXTRACTEUR (pas dans la fonction partagée) car chaque extracteur a son propre cycle de vie
  d'instance — la fonction partagée reste pure/sans état, le cache vit dans l'appelant.

**Point de vigilance (non bloquant) :** le flux de retry post-validation (`converter.py:401-413`,
4 constructions `_retry_extractor`) ne reçoit pas encore `on_column_mapping` — flux secondaire
(retry ponctuel sur feedback utilisateur), à étendre si l'usage le justifie.

**Score session :** 6 agents — Analyste ✓ (repérage préalable de `_parse_pipe_response` comme
fonction partagée, décisif pour la portée du correctif), Backend ✓ (5 fichiers, 16 tests),
Frontend — NON sollicité (contrat existant réutilisé tel quel, zéro nouveau code UI), Auditeur ✓
(validé 1er tour), Testeur ✓ (1 point de vigilance mineur), Apprentissage ✓.
**Tests :** 372/372 passants — +16 nouveaux (`tests/test_vision_column_mapping.py`) —
0 régression sur les 356 préexistants.

---

*Dernière mise à jour : 2026-09-09*
