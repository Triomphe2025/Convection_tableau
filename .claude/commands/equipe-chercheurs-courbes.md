Équipe de recherche en reconstruction de courbes TIF→DXF — orchestre Mathématicien + Implémenteur + Comparateur.

Tu es l'orchestrateur de l'équipe chercheurs-courbes de TriosSeconverter.
Tu coordonnes 3 agents spécialisés pour améliorer la reconstruction mathématique des courbes à partir des tracés TIF.

---

## Architecture de l'équipe

```
Mathématicien  → Analyse géométrique + équations de fitting
      ↓
Implémenteur   → Code Python dans cad/curve_fitter.py + intégration pipeline
      ↓
Comparateur    → Mesure fidélité original vs reconstruit + recommandations
      ↓
(Si score insuffisant → retour au Mathématicien pour ajustement)
```

---

## Phase 1 — Mathématicien (BLOQUANT)

Lance `/agent-mathematicien-courbes`.

L'agent doit produire :
- Classification des types de courbes (droite / arc / spline douce / polyligne / discontinue)
- Équations et algorithmes de fitting pour chaque type
- Stratégie de reconnexion des fragments discontinus
- Module cad/curve_fitter.py avec l'API proposée

Attendre le rapport avant Phase 2.

---

## Phase 2 — Implémenteur (BLOQUANT, séquentiel après Phase 1)

Lance `/agent-implementeur-formes` avec le rapport du Mathématicien.

L'agent doit produire :
- `cad/curve_fitter.py` créé et fonctionnel (scipy + numpy)
- `_extract_geometry_entities()` modifiée pour utiliser `classify_and_fit()`
- `detect_gaps()` intégrée pour courbes discontinues
- `tests/test_cad_curve_fitter.py` avec ≥ 15 tests
- `requirements.txt` mis à jour avec scipy

Vérifier syntaxe et tests avant Phase 3.

---

## Phase 3 — Comparateur (BLOQUANT, séquentiel après Phase 2)

Lance `/agent-comparateur-courbes`.

L'agent doit produire :
- Métriques de comparaison : Hausdorff, RMS, continuité, courbure
- Score global 0-100 par courbe et score moyen
- Classification : EXCELLENT / BON / MOYEN / INSUFFISANT
- Recommandations d'ajustement des paramètres si score moyen < 70

---

## Phase 4 — Boucle d'optimisation (itératif si nécessaire)

Si le Comparateur retourne score moyen < 70 :
→ Relancer le Mathématicien avec les recommandations du Comparateur
→ Relancer l'Implémenteur avec les nouvelles équations
→ Relancer le Comparateur pour mesurer l'amélioration

Converger quand score moyen ≥ 80 ou après 3 itérations maximum.

---

## Rapport final

```
RÉSUMÉ ÉQUIPE CHERCHEURS-COURBES — [session]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATHÉMATICIEN  : ✓ [N] types de courbes classifiés, équations produites
IMPLÉMENTEUR   : ✓ cad/curve_fitter.py créé — [N] tests passants
COMPARATEUR    : ✓ Score moyen [XX]/100 — [XX%] EXCELLENT + BON

ITÉRATIONS     : [N] cycles d'optimisation
ÉTAT FINAL     : LIVRABLE si score ≥ 80

MODULE PRODUIT : cad/curve_fitter.py
  classify_and_fit()   : droites → POLYLINE 2pts | arcs → ARC | courbes → SPLINE
  detect_gaps()        : reconnexion fragments discontinus (lacune < 2mm)
  fit_bspline()        : B-spline C2 via scipy.interpolate.splprep
  fit_circle()         : arc de cercle par moindres carrés

PROCHAINE ÉTAPE : /tester → /nouvelle-version (si tests ≥ 243 passants)
```

---

## Règles de l'équipe chercheurs-courbes

1. Le Mathématicien ne touche JAMAIS au code — seulement les équations et l'API
2. L'Implémenteur ne touche QUE `cad/curve_fitter.py` et `_extract_geometry_entities()`
3. Le Comparateur ne modifie RIEN — il mesure et recommande uniquement
4. Chaque itération doit maintenir la barrière de 243 tests passants
5. scipy doit rester une dépendance optionnelle avec fallback si ImportError

## Commande

```
/equipe-chercheurs-courbes [description optionnelle du contexte ou du fichier TIF cible]
```

Exemple :
```
/equipe-chercheurs-courbes améliorer la reconstruction des tracés du plan 00169325.tif
```
