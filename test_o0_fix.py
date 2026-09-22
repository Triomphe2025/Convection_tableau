"""
Test rapide : vérification de la normalisation O/0 et du découpage de tokens
sur quelques images répartiteur.
"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from ocr_processor import BornierTableExtractor
from config import Config
from template import TemplateManager

# Charger le template REPARTITEUR
tm = TemplateManager()
tpl = tm.get('REPARTITEUR')
if tpl is None:
    print("Template REPARTITEUR introuvable — templates disponibles :")
    for name in tm.list_names():
        print(f"  {name}")
    sys.exit(1)

print(f"Template : {tpl.name}")
print(f"Colonnes : {tpl.columns}\n")

extractor = BornierTableExtractor(
    tesseract_path=Config.TESSERACT_PATH,
    language=Config.OCR_LANGUAGE,
    template=tpl,
)

images_dir = Path(__file__).parent / 'images_repartiteur'
images = sorted(images_dir.glob('*.jpg'), key=lambda p: int(''.join(c for c in p.stem if c.isdigit()) or '0'))[:5]

for img in images:
    print(f"\n{'='*55}")
    print(f"  {img.name}")
    print('='*55)
    result = extractor.extract(img)
    if not result.get('success'):
        print(f"  ECHEC : {result.get('error')}")
        continue
    meta = result.get('metadata', {})
    print(f"  Methode : {result.get('detection_method')}  |  "
          f"Bornier={meta.get('BORNIER', '?')}  PAGE={meta.get('PAGE', '?')}")
    print(f"  {'TENANT':<20} {'JAR':<10} {'ABOUTISSANT':<18} {'SIGNAL'}")
    print(f"  {'-'*70}")
    for row in result.get('rows', []):
        if row['type'] == 'data':
            cells = row.get('cells', [])
            if any(cells):
                print(f"  {str(cells[0] if len(cells) > 0 else ''):<20} "
                      f"{str(cells[1] if len(cells) > 1 else ''):<10} "
                      f"{str(cells[2] if len(cells) > 2 else ''):<18} "
                      f"{str(cells[3] if len(cells) > 3 else '')}")
