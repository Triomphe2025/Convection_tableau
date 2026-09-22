"""Test complet extraction PDF PE161 avec template REPARTITEUR 2."""
import sys
import glob
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
sys.path.insert(0, r'c:\Users\Triomphe Tchounda\Downloads\convertion Tableau')

from template import TemplateManager
from pdf_extractor import PdfTableExtractor

matches = glob.glob(r'C:\Users\Triomphe Tchounda\Downloads\convertion Tableau\exemple traitement\*PE161*.pdf')
pdf_path = Path(matches[0])
print("PDF:", pdf_path.name)

mgr = TemplateManager()
tpl = mgr.get("REPARTITEUR 2")
print(f"Template: {tpl.name}, colonnes: {tpl.columns}")
print(f"footer_detect_keywords: {tpl.footer_detect_keywords}")
print(f"footer_extract_fields: {tpl.footer_extract_fields}")

ext = PdfTableExtractor(template=tpl)
results, _ = ext.extract_all(pdf_path)

ok = [r for r in results if r.get('success')]
fail = [r for r in results if not r.get('success')]
print(f"\nPages: {len(results)} total / {len(ok)} succes / {len(fail)} echecs")

# Afficher les 5 premiers resultats
print("\n=== 5 premiers tableaux extraits ===")
for r in ok[:5]:
    meta = r.get('metadata', {})
    rows = r.get('rows', [])
    data_rows = [rw for rw in rows if rw.get('type') == 'data']
    print(f"\n  Page {r['page_num']}:")
    print(f"  META: CABLE={meta.get('CABLE', '?')} TYPE={meta.get('TYPE', '?')} NO_PLAN={meta.get('NO_PLAN', '?')} PAGE={meta.get('PAGE', '?')}")
    print(f"  Lignes data: {len(data_rows)}")
    for row in data_rows[:3]:
        print(f"    {row['cells']}")
