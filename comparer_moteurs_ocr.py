"""
Comparaison Tesseract vs Claude Vision sur une image de bornier.

Usage :
    python comparer_ocr.py                          # premiere image trouvee
    python comparer_ocr.py page_10.png              # image specifique
    python comparer_ocr.py page_10.png --cle XXXXX  # avec cle API Claude

Sans cle API : affiche uniquement le resultat Tesseract.
Avec cle API  : affiche les deux resultats cote a cote + score qualite.

Cout Claude Haiku : ~0.001 euro par image.
"""
import sys
import argparse
import glob
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from template import TemplateManager


def trouver_image(nom: str = None) -> Path:
    """Cherche une image de bornier dans les dossiers connus."""
    dossiers = [
        Path(__file__).parent / "exemple traitement" / "VD23111PE163 (1)_images_pretaitees",
        Path(__file__).parent / "exemple traitement" / "VD23111PE163 (1)_ocr_pages",
        Path(__file__).parent / "images_borniers",
    ]
    if nom:
        for d in dossiers:
            p = d / nom
            if p.exists():
                return p
        # Cherche dans le repertoire courant
        p = Path(nom)
        if p.exists():
            return p
        print(f"Image '{nom}' introuvable. Recherche automatique...")

    for d in dossiers:
        imgs = list(d.glob("*.png")) + list(d.glob("*.jpg"))
        if imgs:
            return sorted(imgs)[0]

    raise FileNotFoundError(
        "Aucune image trouvee. Donnez le chemin complet : "
        "python comparer_ocr.py mon_image.png"
    )


def tesseract_result(image_path: Path, template) -> dict:
    """Extrait avec Tesseract (moteur actuel)."""
    from ocr_processor import BornierTableExtractor
    ext = BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE,
        template=template,
    )
    return ext.extract(image_path)


def claude_result(image_path: Path, template, api_key: str) -> dict:
    """Extrait avec Claude Vision API."""
    Config.CLAUDE_API_KEY = api_key
    Config.OCR_MODE = "claude"
    from claude_ocr import ClaudeVisionExtractor
    return ClaudeVisionExtractor(template).extract(image_path)


def score_qualite(rows: list, col_names: list) -> dict:
    """Calcule des metriques simples de qualite."""
    data_rows = [r for r in rows if r.get("type") == "data"]
    if not data_rows:
        return {"lignes": 0, "cellules_vides_pct": 100, "score": 0}

    total_cells = len(data_rows) * len(col_names)
    vides = sum(
        1 for r in data_rows
        for c in r.get("cells", [])
        if not c.strip()
    )
    vides_pct = round(100 * vides / max(total_cells, 1), 1)
    score = round(100 - vides_pct, 1)
    return {
        "lignes": len(data_rows),
        "cellules_vides_pct": vides_pct,
        "score": score,
    }


def afficher_tableau(rows: list, col_names: list, max_lignes: int = 15):
    """Affiche les donnees en tableau texte."""
    data_rows = [r for r in rows if r.get("type") == "data"]
    largeurs = [max(len(c), 14) for c in col_names]
    for r in data_rows[:max_lignes]:
        for i, c in enumerate(r.get("cells", [])):
            if i < len(largeurs):
                largeurs[i] = max(largeurs[i], min(len(c), 30))

    ligne_sep = "+" + "+".join("-" * (w + 2) for w in largeurs) + "+"

    def ligne(vals):
        parts = []
        for i, w in enumerate(largeurs):
            v = vals[i] if i < len(vals) else ""
            parts.append((" " + v[:w]).ljust(w + 1) + " ")
        return "|" + "|".join(parts) + "|"

    print(ligne_sep)
    print(ligne(col_names))
    print(ligne_sep)
    for r in data_rows[:max_lignes]:
        print(ligne(r.get("cells", [])))
    if len(data_rows) > max_lignes:
        print(f"  ... {len(data_rows) - max_lignes} lignes supplementaires ...")
    print(ligne_sep)


def main():
    parser = argparse.ArgumentParser(description="Comparaison OCR Tesseract vs Claude Vision")
    parser.add_argument("image", nargs="?", help="Nom ou chemin de l'image (optionnel)")
    parser.add_argument("--cle", "--key", metavar="CLE_API", help="Cle API Anthropic")
    parser.add_argument("--template", default=None, help="Nom du template (defaut: 1er disponible)")
    args = parser.parse_args()

    try:
        image_path = trouver_image(args.image)
    except FileNotFoundError as e:
        print(f"ERREUR : {e}")
        sys.exit(1)

    mgr = TemplateManager()
    tpl_name = args.template or mgr.names()[0]
    if tpl_name not in mgr.names():
        print(f"Template '{tpl_name}' inconnu. Disponibles : {mgr.names()}")
        sys.exit(1)
    tpl = mgr.get(tpl_name)

    print("=" * 65)
    print(f"  Image    : {image_path.name}")
    print(f"  Template : {tpl_name}  ({' | '.join(tpl.columns)})")
    print("=" * 65)

    # ── Tesseract ─────────────────────────────────────────────────────────
    print("\n[1/2] Extraction Tesseract...")
    try:
        res_tess = tesseract_result(image_path, tpl)
        if res_tess.get("success"):
            q = score_qualite(res_tess["rows"], tpl.columns)
            print(f"      Lignes : {q['lignes']}  |  Cellules vides : {q['cellules_vides_pct']}%  |  Score : {q['score']}/100")
            print(f"      Methode detection colonnes : {res_tess.get('detection_method', '?')}")
            print()
            afficher_tableau(res_tess["rows"], tpl.columns)
        else:
            print(f"      ECHEC : {res_tess.get('error')}")
            res_tess = None
    except Exception as e:
        print(f"      ECHEC : {e}")
        res_tess = None

    # ── Claude Vision (si cle fournie) ───────────────────────────────────
    if args.cle:
        print("\n[2/2] Extraction Claude Vision...")
        try:
            res_claude = claude_result(image_path, tpl, args.cle)
            if res_claude.get("success"):
                q = score_qualite(res_claude["rows"], tpl.columns)
                print(f"      Lignes : {q['lignes']}  |  Cellules vides : {q['cellules_vides_pct']}%  |  Score : {q['score']}/100")
                print()
                afficher_tableau(res_claude["rows"], tpl.columns)
            else:
                print(f"      ECHEC : {res_claude.get('error')}")
                res_claude = None
        except Exception as e:
            print(f"      ECHEC : {e}")
            res_claude = None

        # ── Bilan comparatif ─────────────────────────────────────────────
        if res_tess and res_claude:
            q_t = score_qualite(res_tess["rows"], tpl.columns)
            q_c = score_qualite(res_claude["rows"], tpl.columns)
            print("\n" + "=" * 65)
            print("  BILAN COMPARATIF")
            print("=" * 65)
            print(f"  {'':20} {'Tesseract':>15} {'Claude Vision':>15}")
            print(f"  {'Lignes extraites':20} {q_t['lignes']:>15} {q_c['lignes']:>15}")
            print(f"  {'Cellules vides %':20} {q_t['cellules_vides_pct']:>15} {q_c['cellules_vides_pct']:>15}")
            print(f"  {'Score qualite':20} {q_t['score']:>14}/100 {q_c['score']:>14}/100")
            gagnant = "Claude Vision" if q_c["score"] > q_t["score"] else "Tesseract"
            if q_c["score"] == q_t["score"]:
                gagnant = "Egalite"
            print(f"\n  Meilleur resultat : {gagnant}")
            print("=" * 65)
    else:
        print("\n[2/2] Claude Vision : pas de cle API fournie.")
        print("      Pour comparer, lancez :")
        print("      python comparer_ocr.py " + str(image_path.name) + " --cle VOTRE_CLE_ICI")
        print()
        print("      Test gratuit SANS cle : uploadez l'image sur claude.ai")
        print("      et demandez : 'Lis ce tableau, colonnes : " + " | ".join(tpl.columns) + "'")


if __name__ == "__main__":
    main()
