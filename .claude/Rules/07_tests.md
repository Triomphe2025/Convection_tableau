# Règle 07 — Tests automatisés et couverture obligatoire

## Règle fondamentale : 1 fonction = 1 test minimum

**Toute fonction ou méthode écrite doit avoir au moins un test unitaire.**
C'est non négociable. Le code sans test ne passe pas l'audit.

```python
# Exemple : si le backend écrit cette méthode...
def _clean_cell(value: str) -> str:
    """Nettoie une valeur de cellule OCR."""
    ...

# ...le testeur DOIT écrire ces tests :
class TestCleanCell:
    def test_valeur_normale_inchangee(self):
        assert _clean_cell("ROUGE") == "ROUGE"

    def test_valeur_vide_retourne_vide(self):
        assert _clean_cell("") == ""

    def test_caracteres_speciaux_supprimes(self):
        assert _clean_cell("|||") == ""

    def test_none_traite_comme_vide(self):
        assert _clean_cell(None) == ""
```

## Structure des tests requise pour chaque fonction

```python
class Test[NomDeLaClasse]:

    def test_[methode]_cas_nominal(self):
        """Le cas d'usage principal."""
        ...

    def test_[methode]_cas_limite(self):
        """Les cas aux frontières (0, None, "", liste vide, max)."""
        ...

    def test_[methode]_cas_erreur(self):
        """Les entrées invalides — vérifier que l'erreur est gérée proprement."""
        ...
```

## Suite de tests actuelle

```
tests/
  test_config_ollama.py              → Configuration Ollama et URL
  test_methods.py                    → OCR, Excel, bordures cellules
  test_pipeline_image.py             → Pipeline image OCR (lignes, en-tête, frontières de colonnes)
  test_scoring.py                    → Scoring adaptatif d'affectation aux colonnes
  test_column_mapping.py             → Mapping manuel bloc→colonne (Tesseract)
  test_column_mapping_integration.py → Idem, intégration (extract() bout en bout, mécanisme Event)
  test_vision_column_mapping.py      → Mapping manuel segment→colonne (moteurs vision)
  test_wide_template_and_cancel.py   → Avertissement modèle large + arrêt coopératif
  test_cad_raster.py                 → Non-régression mémoire du pipeline raster CAD
  test_cad_raster_tif.py             → Pipeline raster TIF → DXF (raster_tif_extractor)
  test_cad_curve_fitter.py           → cad/curve_fitter.py
  test_cad_segment_merger.py         → cad/segment_merger.py
  test_cad_vectorizer.py             → cad/vectorizer.py, détection de source, écriture DXF
  test_verificateur.py               → verificateur.py, une classe par fonction publique, dicts fabriqués
  test_verificateur_golden.py        → Cas réel 6A 23111PE102 (scan contre conversion), lectures figées
  test_converter_verification.py     → Converter.verifier_conversion et ses aides privées
  test_non_regression_xlsx.py        → Le .xlsx du pipeline reste identique à l'instantané d'avant
```

**487 tests passent** (`pytest tests\`, relevé le 2026-09-20), plus 1 échec attendu documenté
(`test_criteres_du_cahier_des_charges`, cibles chiffrées non atteintes) et 1 test lent facultatif
(`VERIF_TEST_LENT=1`, relecture Tesseract de 15 pages). Barrière de régression à ne jamais abaisser.
Les 3 fichiers `test_*.py` de la racine (31 tests) se lancent séparément.

## Lancer les tests

```powershell
env\Scripts\python.exe -m pytest tests\ -v --tb=short

# Avec couverture (si coverage installé)
env\Scripts\python.exe -m pytest tests\ --cov=. --cov-report=term-missing
```

## Règle de nommage des tests

```python
# Format : test_[methode]_[scenario]
def test_extract_meta_pet_multiword():       # ✓
def test_clean_cell_pipe_only():             # ✓
def test_write_dxf_creates_file():           # ✓

# Interdits
def test_1():                                # ✗ pas de nom descriptif
def test_ok():                               # ✗ trop vague
def tester_la_fonction():                    # ✗ pas le préfixe test_
```

## Tests à ajouter pour chaque nouveau module

### Tout nouveau fichier Python → fichier de test correspondant

| Module créé | Fichier de test requis |
|-------------|----------------------|
| `cad/vector_pdf_extractor.py` | `tests/test_cad_vectoriel.py` |
| `cad/dxf_writer.py` | `tests/test_cad_dxf_writer.py` |
| `cad/block_builder.py` | `tests/test_cad_blocks.py` |
| `cad/source_detector.py` | `tests/test_cad_source_detector.py` |

### Tests CAD prioritaires (à créer)

```python
def test_source_detector_pdf_vectoriel():
def test_source_detector_image_retourne_raster():
def test_extract_vector_pdf_page_count():
def test_coordonnees_rotation_0():
def test_coordonnees_rotation_270():      # validé sur 717-6324-LL02.pdf
def test_write_dxf_creates_file():
def test_dxf_readable_by_ezdxf():
def test_dedup_texts_removes_duplicates():
def test_dedup_lines_removes_same_endpoints():
def test_offset_folio_calcul():
```

## Ce qu'on ne teste PAS

- Les callbacks Tkinter (thread safety — complexité excessive)
- La génération visuelle des DXF (testé manuellement par comparaison PDF)
- Les appels API Claude/Ollama en production (utiliser des mocks ou des fixtures)

## Fixtures de test

Préférer la génération programmatique plutôt que des fichiers binaires committés :

```python
import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def pdf_minimal():
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Test content")
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        doc.save(f.name)
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)
```
