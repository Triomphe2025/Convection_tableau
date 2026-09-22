"""Analyse rapide du dernier Excel généré pour diagnostiquer la distribution des colonnes."""
import openpyxl
from pathlib import Path

xlsx = Path(r'C:\Users\Triomphe Tchounda\Downloads\document test\DOC FINAL\TACHE4_VD23111PE161\tous_les_borniers.xlsx')
wb = openpyxl.load_workbook(str(xlsx), data_only=True)
ws = wb['Borniers']
rows_all = list(ws.iter_rows(values_only=True))

headers = None
data_rows = []
for row in rows_all:
    vals = [str(c).strip() if c is not None else '' for c in row]
    if not any(vals):
        continue
    if headers is None:
        headers = vals
        continue
    data_rows.append(vals)

print(f"Total lignes de donnees : {len(data_rows)}")
print(f"En-tetes : {headers}")
print()

for col_idx in range(4):
    col_name = headers[col_idx] if headers and col_idx < len(headers) else "?"
    vides = sum(1 for r in data_rows if col_idx >= len(r) or not r[col_idx].strip())
    pct = 100 * vides // max(1, len(data_rows))
    print(f"Colonne {col_idx} [{col_name}] : {vides} vides sur {len(data_rows)} ({pct}%)")

parfait = sum(1 for r in data_rows if len(r) >= 4 and all(r[i].strip() for i in range(4)))
print(f"\nLignes avec 4 colonnes remplies : {parfait} ({100*parfait//max(1, len(data_rows))}%)")

print("\n--- 15 exemples de lignes avec colonnes vides ---")
n = 0
for i, r in enumerate(data_rows):
    vides = sum(1 for j in range(4) if j >= len(r) or not r[j].strip())
    if vides >= 2 and n < 15:
        print("  " + " | ".join((r[j][:22] if j < len(r) else "")[:22] for j in range(4)))
        n += 1
