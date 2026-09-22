"""
Test rapide Claude Vision sur une image.

Usage :
  python test_vision.py <chemin_image> [<nom_template>] [<cle_api>]

Exemples :
  python test_vision.py "exemple traitement\\repartiteur 2\\page_pdf_019.png" "REPARTITEUR 2" sk-ant-...
  python test_vision.py images_repartiteur\bornier_21.jpg "REPARTITEUR 2"

La clé API peut aussi être définie via la variable d'environnement ANTHROPIC_API_KEY.
Templates disponibles : voir templates.json
"""

import sys
import os
import json
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_vision.py <chemin_image> [<nom_template>]")
        print()
        print("Images disponibles dans images_repartiteur\\:")
        imgs = sorted(Path("images_repartiteur").glob("bornier_*.jpg"), key=lambda p: int(''.join(filter(str.isdigit, p.stem)) or '0'))
        for img in imgs[:10]:
            print(f"  {img}")
        if len(imgs) > 10:
            print(f"  ... et {len(imgs)-10} autres")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"ERREUR : image introuvable — {image_path}")
        sys.exit(1)

    # Charger le template
    template_name = sys.argv[2] if len(sys.argv) > 2 else "REPARTITEUR 2"
    with open("templates.json", encoding="utf-8") as f:
        all_tpl = json.load(f)

    if template_name not in all_tpl:
        print(f"Template '{template_name}' introuvable.")
        print("Templates disponibles :", list(all_tpl.keys()))
        sys.exit(1)

    tpl_data = all_tpl[template_name]
    from template import TableTemplate
    tpl = TableTemplate(
        name=template_name,
        columns=tpl_data["columns"],
        col_widths=tpl_data.get("col_widths", {}),
        section_keyword=tpl_data.get("section_keyword", "NOM DU CABLE"),
        footer_left_label=tpl_data.get("footer_left_label", "BORNIER :"),
        footer_row1_format=tpl_data.get("footer_row1_format", ""),
        footer_row2_format=tpl_data.get("footer_row2_format", ""),
    )

    # Vérifier la clé API : argument > variable d'environnement > config.py
    from config import Config
    api_key = ""
    if len(sys.argv) > 3:
        api_key = sys.argv[3].strip()
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        api_key = getattr(Config, "CLAUDE_API_KEY", "").strip()
    if not api_key:
        print("ERREUR : clé API Claude manquante.")
        print("Solutions :")
        print("  1. Passez-la en 3e argument : python test_vision.py image.png 'REPARTITEUR 2' sk-ant-...")
        print("  2. Variable d'environnement  : set ANTHROPIC_API_KEY=sk-ant-...")
        print("  3. Ajoutez-la dans config.py : CLAUDE_API_KEY = 'sk-ant-...'")
        sys.exit(1)
    # Injecter dans Config pour que ClaudeVisionExtractor la trouve
    Config.CLAUDE_API_KEY = api_key

    print(f"Image    : {image_path}")
    print(f"Template : {template_name}  →  colonnes : {tpl.columns}")
    print(f"Modèle   : {getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-haiku-4-5-20251001')}")
    print()
    print("Envoi à l'API Claude Vision...")
    print("-" * 70)

    from claude_ocr import ClaudeVisionExtractor
    extractor = ClaudeVisionExtractor(tpl)
    result = extractor.extract(image_path)

    if not result.get("success"):
        print(f"ECHEC : {result.get('error', 'erreur inconnue')}")
        sys.exit(1)

    rows = result.get("rows", [])
    meta = result.get("metadata", {})

    # Afficher le résultat formaté
    print(f"MÉTADONNÉES : {meta}")
    print()

    cols = tpl.columns
    # Largeurs dynamiques
    widths = {c: max(len(c), 4) for c in cols}
    for row in rows:
        for i, c in enumerate(cols):
            val = row["cells"][i] if i < len(row.get("cells", [])) else ""
            widths[c] = max(widths[c], len(val))

    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep    = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        cells = row.get("cells", [])
        line = " | ".join((cells[i] if i < len(cells) else "").ljust(widths[c]) for i, c in enumerate(cols))
        print(line)

    print()
    print(f"Total : {len(rows)} ligne(s) extraite(s)")

    # Vérification rapide : est-ce que SIGNAL contient des codes borne ?
    signal_idx = cols.index("SIGNAL") if "SIGNAL" in cols else -1
    if signal_idx >= 0:
        import re
        borne_pattern = re.compile(r'^\d{1,2}[A-Z]{1,2}$')
        suspects = []
        for row in rows:
            cells = row.get("cells", [])
            val = cells[signal_idx] if signal_idx < len(cells) else ""
            if val and borne_pattern.match(val.strip()):
                suspects.append(val)
        if suspects:
            print()
            print(f"AVERTISSEMENT : {len(suspects)} ligne(s) ont un code borne dans SIGNAL : {suspects[:5]}")
            print("  → Le prompt n'a pas encore corrigé ce cas pour ce tableau.")
        else:
            print("SIGNAL : OK (aucun code borne détecté dans cette colonne)")


if __name__ == "__main__":
    main()
