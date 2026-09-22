"""
Test Claude Vision sur 3 types de tableaux.
Usage : python tester_3_pages.py <cle_api>
"""
import sys
import json
from pathlib import Path


TESTS = [
    {
        "label": "PAGE 15 — J207A fin (2 lignes, signal sur ligne 2)",
        "image": Path("exemple traitement") / "repartiteur 2" / "test_p020_J207A_fin_PAGE15.png",
        "template": "REPARTITEUR 2",
        "attendu": [
            ("FIL", "59B/VE"), ("TENANT", "EPL J207A 05L"), ("SIGNAL", ""),
            ("FIL", "60BC/R"), ("SIGNAL", "*VOIR CCIF PATAAG31"),
        ],
    },
    {
        "label": "PAGE 47 — AD/B (2 lignes, signaux reels)",
        "image": Path("exemple traitement") / "repartiteur 2" / "test_p052_AD_B_PAGE47.png",
        "template": "REPARTITEUR 2",
        "attendu": [
            ("FIL", "N"), ("TENANT", "EPL AD/B 27"), ("SIGNAL", "+ 48V B (C37V2)"),
            ("FIL", "B"), ("SIGNAL", "0V B (C37V2)"),
        ],
    },
    {
        "label": "PAGE 50 — EAS/TB1, 28 lignes, FIL a 2 sous-cellules",
        "image": Path("exemple traitement") / "repartiteur 2" / "test_p055_EASB1_COPPM_PAGE50.png",
        "template": "REPARTITEUR 2",
        "attendu": [
            ("SIGNAL", "+ COPPM"), ("SIGNAL", "- COPPM"), ("TENANT", "EPL EAS/TB1 01"),
        ],
    },
]


def charger_template(nom):
    with open("templates.json", encoding="utf-8") as f:
        data = json.load(f)
    if nom not in data:
        raise ValueError(f"Template '{nom}' introuvable. Disponibles : {list(data)}")
    d = data[nom]
    from template import TableTemplate
    return TableTemplate(
        name=nom,
        columns=d["columns"],
        col_widths=d.get("col_widths", {}),
        section_keyword=d.get("section_keyword", "NOM DU CABLE"),
        footer_left_label=d.get("footer_left_label", ""),
        footer_row1_format=d.get("footer_row1_format", ""),
        footer_row2_format=d.get("footer_row2_format", ""),
    )


def afficher_tableau(rows, cols):
    if not rows:
        print("  (aucune ligne)")
        return
    widths = {c: max(len(c), 4) for c in cols}
    for row in rows:
        for i, c in enumerate(cols):
            val = row["cells"][i] if i < len(row.get("cells", [])) else ""
            widths[c] = max(widths[c], len(val))
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep    = "-+-".join("-" * widths[c] for c in cols)
    print("  " + header)
    print("  " + sep)
    for row in rows:
        cells = row.get("cells", [])
        line  = " | ".join((cells[i] if i < len(cells) else "").ljust(widths[c])
                           for i, c in enumerate(cols))
        print("  " + line)


def verifier(rows, cols, attendu):
    """Retourne liste de (ok, message) pour chaque point attendu."""
    all_cells = []
    for row in rows:
        cells = row.get("cells", [])
        all_cells.append({c: (cells[i] if i < len(cells) else "") for i, c in enumerate(cols)})

    resultats = []
    for col, valeur_attendue in attendu:
        if col not in cols:
            resultats.append((None, f"{col} absent du template"))
            continue
        valeurs_col = [r.get(col, "") for r in all_cells]
        if valeur_attendue == "":
            # On verifie juste qu'au moins une ligne a ce champ vide
            ok = any(v == "" for v in valeurs_col)
            resultats.append((ok, f"{col}='' (au moins une ligne vide)"))
        else:
            # Cherche une correspondance partielle insensible a la casse
            ok = any(valeur_attendue.lower() in v.lower() for v in valeurs_col)
            resultats.append((ok, f"{col} contient '{valeur_attendue}'"))
    return resultats


def main():
    if len(sys.argv) < 2:
        print("Usage : python tester_3_pages.py <cle_api>")
        print("   ou : set ANTHROPIC_API_KEY=sk-ant-... puis python tester_3_pages.py")
        sys.exit(1)

    api_key = sys.argv[1].strip()

    from config import Config
    Config.CLAUDE_API_KEY = api_key

    from claude_ocr import ClaudeVisionExtractor

    total_ok = 0
    total_checks = 0

    for idx, test in enumerate(TESTS, 1):
        print()
        print("=" * 70)
        print(f"  TEST {idx}/3 — {test['label']}")
        print("=" * 70)

        img = test["image"]
        if not img.exists():
            print(f"  ERREUR : image introuvable — {img}")
            continue

        tpl = charger_template(test["template"])
        print(f"  Template : {test['template']}  colonnes : {tpl.columns}")
        print(f"  Image    : {img.name}")
        print()

        extractor = ClaudeVisionExtractor(tpl)
        result = extractor.extract(img)

        if not result.get("success"):
            print(f"  ECHEC API : {result.get('error', '?')}")
            continue

        rows = result.get("rows", [])
        meta = result.get("metadata", {})
        print(f"  Metadonnees : {meta}")
        print(f"  Lignes extraites : {len(rows)}")
        print()
        afficher_tableau(rows, tpl.columns)

        # Verification automatique
        print()
        print("  --- Verification ---")
        checks = verifier(rows, tpl.columns, test["attendu"])
        for ok, msg in checks:
            if ok is None:
                print(f"  ?  {msg}")
            elif ok:
                print(f"  OK {msg}")
                total_ok += 1
            else:
                print(f"  X  {msg}  <- PROBLEME")
            total_checks += 1

    print()
    print("=" * 70)
    print(f"  BILAN : {total_ok}/{total_checks} verifications OK")
    print("=" * 70)
    print()
    input("Appuyez sur Entree pour fermer...")


if __name__ == "__main__":
    main()
